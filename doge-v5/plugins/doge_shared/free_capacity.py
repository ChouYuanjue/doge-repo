"""Monthly free-provider budget, based on FreeLLM's native model labels.

Use one deployment-wide observed request length and the bot's configured
context limit when translating request-rate limits into monthly tokens.
No per-model forecasting, million-token full-context speculation, or 24/7
rate-limit saturation. Credit balances that run out are handled separately.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

DAYS=30


def nonneg(v: Any) -> int:
    try:
        return max(0,int(v or 0))
    except (TypeError,ValueError,OverflowError):
        return 0


def parse_budget(label: str | None) -> int:
    """Matching FreeLLMAPI's current parseBudget, including upper label ranges."""
    if not label:
        return 0
    head=re.sub(r"\([^)]*\)","",str(label).lower()).strip()
    match=re.search(r"~?([\d.]+)(?:-([\d.]+))?([mk])(?![a-z])",head)
    if not match:
        return 0
    tail=head[match.end():]
    if re.match(r"\s*(?:rpd|rpm|rph|rps|req|requests?|calls?|messages?|prompts?|neurons?)\b",tail):
        return 0
    try:
        amount=Decimal(match.group(2) or match.group(1))
    except InvalidOperation:
        return 0
    if not amount.is_finite() or amount<0:
        return 0
    amount*=1_000_000 if match.group(3)=="m" else 1_000
    period=re.split(r"[,·;]",tail)[0]
    if re.search(r"\b(?:per\s*)?days?\b|\bdaily\b|\b24\s*h(?:rs?|ours?)?\b",period):
        amount*=DAYS
    return int(amount)


def estimate_capacity(
    active: dict[str,dict], key_counts: dict[str,int], *,
    profile: dict | None = None,
    current_month_usage: dict[str,int] | None = None,
) -> dict:
    """Use native whole-model monthly total + deployment-wide request samples.

    Native model budgets retain the provider's own global dashboard convention.
    Request-limited free sources only get additional monthly capacity if their
    historical-global request-rate estimate exceeds their existing label; one
    shared allowance is never added once per model or per model alias.
    """
    profile=profile or {}
    context=nonneg(profile.get("context_limit")) or 14000
    average=min(context,max(0,float(profile.get("avg_request_tokens") or 0)))
    daily_load=max(0,float(profile.get("requests_per_day") or 0))

    per_source: dict[str,int]={}
    native=0
    pools: dict[str,int]={}
    model_count=0
    for source,info in active.items():
        platform=info["platform"]
        models=info["models"]
        if platform=="openrouter":
            models=[m for m in models if str(m.get("model_id") or "").endswith(":free")]
        if not models:
            continue
        count=max(1,nonneg(key_counts.get(platform)))
        values=[parse_budget(m.get("monthly_token_budget"))*count for m in models]
        amount=sum(values)
        native+=amount
        per_source[source]=amount
        pools[source]=max(values,default=0)
        model_count+=len(models)

    # All explicit request grants and observed account-wide IP rate gates
    # use ONE historical global avg; no model-specific context length / price.
    max_daily_requests={
        "openrouter":50,     # :free, account-wide, regardless of model
        "modelscope":200,    # daily free experience; conversion unverified
        "kilo":200*24,       # rate-only, bound by actual deployment-wide demand
        "ovh":2*60*24,
        "unorouter":60*24,   # observed shared account rather than per-model
    }
    adjustments={}
    for source, daily_requests in max_daily_requests.items():
        if source not in per_source or not daily_load or not average:
            continue
        expected=int(min(daily_requests,daily_load)*DAYS*average)
        before=per_source[source]
        if expected>before:
            per_source[source]=expected
            adjustments[source]=expected-before

    # Recurring free USD grants (e.g., Mistral $10/month) use the cheapest
    # listed model, weighted by this deployment's *global* input/output
    # ratio. One grant per account, never per model and never a fixed balance.
    if "mistral" in per_source:
        models=active["mistral"]["models"]
        if any("$10/month" in str(m.get("monthly_token_budget"))
               for m in models):
            from decimal import Decimal, InvalidOperation
            share_in=max(0,float(profile.get("input_share") or 0.93))
            share_out=max(0,float(profile.get("output_share") or 0.07))
            prices=[]
            for m in models:
                try:
                    inp=Decimal(str(m.get("paid_input_per_m")))
                    output=Decimal(str(m.get("paid_output_per_m")))
                except (TypeError,InvalidOperation):
                    try:
                        inp=Decimal(str(m.get("paid_input_per_m")))
                        output=inp   # one known input tariff; safe fallback
                    except (TypeError,InvalidOperation):
                        continue
                blended=inp*Decimal(str(share_in))+output*Decimal(str(share_out))
                if blended.is_finite() and blended>0:
                    prices.append(blended)
            if prices:
                equivalent=int(Decimal(10_000_000)/min(prices))
                if equivalent>per_source["mistral"]:
                    adjustments["mistral"]=equivalent-per_source["mistral"]
                    per_source["mistral"]=equivalent

    # The comma-delimited daily quota is ignored by FreeLLM's own K/M parser.
    if "llm7" in per_source and any(
        "100,000 tokens/24h" in str(m.get("monthly_token_budget"))
        for m in active["llm7"]["models"]
    ):
        amount=100_000*DAYS
        if amount>per_source["llm7"]:
            adjustments["llm7"]=amount-per_source["llm7"]
            per_source["llm7"]=amount

    monthly=sum(per_source.values())
    month_used=sum(nonneg(v) for v in (current_month_usage or {}).values())
    return {
        "native_model_monthly":native,
        "native_pool_dedup_monthly":sum(pools.values()),
        "forecast_30d":monthly,
        "month_used":month_used,
        "remaining_month":max(0,monthly-month_used),
        "adjustments_total":sum(adjustments.values()),
        "request_budget_contributions":adjustments,
        "model_count":model_count,
        "historical_requests_per_day":daily_load,
        "historical_avg_tokens_per_request":average,
        "context_limit":context,
    }
