"""Optimistic monthly free-model capacity, aligned with FreeLLMAPI's UI.

The Fallback Models page adds the documented monthly budget of *each* model;
the Free Tier page collapses shared provider pools. Both views are useful, but
they must not be presented as equivalent spendable balances.

Requests × maximum free-model context yields a speculative *upper bound*, not
a provider guarantee. It is displayed separately from confirmed credit grants.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

DAYS = 30


def _nat(v: Any) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _money(v: Any) -> Decimal | None:
    try:
        x = Decimal(str(v))
        return x if x.is_finite() and x >= 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def parse_budget(label: str | None) -> int:
    """Python port of FreeLLMAPI server/src/lib/budget.ts parseBudget."""
    if not label:
        return 0
    head = re.sub(r"\([^)]*\)", "", str(label).lower()).strip()
    match = re.search(r"~?([\d.]+)(?:-([\d.]+))?([mk])(?![a-z])", head)
    if not match:
        return 0
    tail = head[match.end():]
    if re.match(r"\s*(?:rpd|rpm|rph|rps|req|requests?|calls?|messages?|prompts?|neurons?)\b", tail):
        return 0
    try:
        x = Decimal(match.group(2) or match.group(1))
    except InvalidOperation:
        return 0
    if x < 0:
        return 0
    tokens = x * (1_000_000 if match.group(3) == "m" else 1_000)
    period = re.split(r"[,·;]", tail)[0]
    if re.search(r"\b(?:per\s*)?days?\b|\bdaily\b|\b24\s*h(?:rs?|ours?)?\b", period):
        tokens *= DAYS
    return int(tokens)


def _widest(models: list[dict]) -> tuple[int, str]:
    context, model = 0, ""
    for m in models:
        size = _nat(m.get("context_window"))
        if size > context:
            context, model = size, str(m.get("model_id") or "")
    return context, model


def estimate_capacity(
    active: dict[str, dict],
    key_counts: dict[str, int],
    *,
    current_month_usage: dict[str, int] | None = None,
) -> dict:
    """Estimate a configured and healthy catalog, without any paid models."""
    current_month_usage = current_month_usage or {}
    rows: dict[str, dict] = {}
    native_total = 0
    dedup: dict[str, int] = {}

    for source, info in active.items():
        all_models = info["models"]
        if not all_models:
            continue
        platform = str(info["platform"])
        models = ([m for m in all_models
                   if str(m.get("model_id") or "").endswith(":free")]
                  if platform == "openrouter" else all_models)
        if not models:
            continue
        count = max(1, _nat(key_counts.get(platform)))
        model_budget = []
        for m in models:
            mid = str(m.get("model_id") or "")
            cap = parse_budget(m.get("monthly_token_budget")) * count
            model_budget.append((cap, mid))
            pool = ("openrouter::free" if platform == "openrouter" else platform + "::account")
            dedup[pool] = max(dedup.get(pool, 0), cap)
        if not model_budget:
            continue
        native = sum(amount for amount, _ in model_budget)
        native_total += native
        largest_context, largest_model = _widest(models)
        rows[source] = {
            "platform": platform,
            "models": len(model_budget),
            "nominal_monthly": native,
            "monthly_optimistic": native,
            "extra_monthly": 0,
            "largest_context": largest_context,
            "context_model": largest_model,
            "budget_model": max(model_budget)[1],
            "basis": "FreeLLM模型月度标签逐模型累加，共享池可能重叠",
            "rate_only_throughput": 0,
        }

    supplement: dict[str, dict] = {}

    def replace_with_larger(source: str, proposed: int, note: str, model: str = "") -> None:
        row = rows.get(source)
        if not row or proposed <= 0:
            return
        row["monthly_optimistic"] = max(row["nominal_monthly"], proposed)
        row["extra_monthly"] = row["monthly_optimistic"] - row["nominal_monthly"]
        if row["extra_monthly"] > 0:
            row["basis"] = note
        supplement[source] = {
            "monthly": proposed, "increment": row["extra_monthly"],
            "basis": note, "model": model,
        }

    # FreeLLM's parseBudget cannot parse comma-delimited 100,000 tokens/day.
    if "llm7" in rows and any(
        "100,000 tokens/24h" in str(m.get("monthly_token_budget"))
        for m in active["llm7"]["models"]
    ):
        replace_with_larger("llm7", 100_000 * DAYS,
                            "LLM7共享100,000 token/24h，按30日")

    # OpenRouter :free requests. Every model is $0; choose the widest context.
    # 50 req/day is the documented default. After $10 of cumulative top-ups,
    # 1000 req/day is a *conditional* scenario, never presumed in the main sum.
    or_conditional = 0
    if "openrouter" in rows:
        models = [m for m in active["openrouter"]["models"]
                  if str(m.get("model_id") or "").endswith(":free")]
        per_day = max((_nat(m.get("rpd_limit")) for m in models), default=0)
        window, model = _widest(models)
        if per_day and window:
            month = per_day * DAYS * window
            note = (f"OpenRouter :free 每日{per_day}次，免费模型{model}最大上下文"
                    f"{window:,} token/次，按满窗的极端理论上界")
            replace_with_larger("openrouter", month, note, model)
            or_conditional = max(per_day, 1000) * DAYS * window
            supplement["openrouter"].update(
                requests_per_day=per_day,
                conditional_month_if_eligible=or_conditional,
            )

    # ModelScope's documented free experience has 200 daily credits; RPD
    # model metadata independently lists 200 requests. No known exchange
    # rate: this is explicitly an unverified 1 credit = 1 request scenario.
    if "modelscope" in rows:
        models = active["modelscope"]["models"]
        per_day = max((_nat(m.get("rpd_limit")) for m in models), default=0)
        window, model = _widest(models)
        if per_day and window:
            replace_with_larger(
                "modelscope", per_day * DAYS * window,
                f"ModelScope每日{per_day}次×最宽上下文{window:,}，"
                "假设免费积分可支持相应请求，未经实际核验",
                model,
            )

    # Native FreeLLM model budget can exceed a paid-input conversion.
    # Currency grant must be counted once, with the cheapest listed model.
    if "mistral" in rows:
        models = active["mistral"]["models"]
        has_grant = any("$10/month" in str(m.get("monthly_token_budget"))
                        for m in models)
        choices = [(_money(m.get("paid_input_per_m")), m.get("model_id"))
                   for m in models]
        priced = [(v, m) for v, m in choices if v is not None and v > 0]
        if has_grant and priced:
            low, mid = min(priced, key=lambda x: x[0])
            month = int(Decimal(10_000_000) / low)
            replace_with_larger(
                "mistral", month,
                f"Mistral每月赠送$10按模型{mid}最低输入价USD {low}/百万",
                str(mid),
            )

    # Rate-only gateways: a speed ceiling over 30 days, never money balances.
    # Treat all free models as sharing the source's rate cap (avoids multiplying
    # account-wide or per-IP limits by the number of catalog models).
    speed = {}
    rate_limits = {
        "kilo": ("200次/小时/IP", 200 * 24),
        "ovh": ("2次/分钟/IP", 2 * 60 * 24),
        "unorouter": ("1次/分钟共享", 60 * 24),
    }
    for source, (label, per_day) in rate_limits.items():
        row = rows.get(source)
        if not row or not row["largest_context"]:
            continue
        throughput = per_day * DAYS * row["largest_context"]
        row["rate_only_throughput"] = throughput
        speed[source] = {
            "monthly": throughput, "requests_per_day": per_day,
            "largest_context": row["largest_context"],
            "model": row["context_model"], "basis": label,
        }

    month = sum(v["monthly_optimistic"] for v in rows.values())
    current_month_used = sum(_nat(v) for v in current_month_usage.values())
    conditional_delta = 0
    if or_conditional and "openrouter" in rows:
        conditional_delta = max(
            0, or_conditional - rows["openrouter"]["monthly_optimistic"]
        )
    return {
        "native_model_monthly": native_total,
        "native_pool_dedup_monthly": sum(dedup.values()),
        "optimistic_monthly": month,
        "optimistic_remaining_current_month": max(0, month - current_month_used),
        "current_month_used": current_month_used,
        "conditional_or_upgrade_delta": conditional_delta,
        "conditional_or_upgrade_total": month + conditional_delta,
        "rate_only_throughput_monthly": sum(v["monthly"] for v in speed.values()),
        "sources": rows,
        "derived": supplement,
        "rate_only_estimates": speed,
        "model_count": sum(r["models"] for r in rows.values()),
    }
