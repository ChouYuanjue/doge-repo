"""Actual model usage, free-resource estimates and paid account balances.

Only resources that are free to this operator:
* WorkBuddy free account credits, including future check-in projections;
* FreeLLMAPI free provider routes, including community gateways.

Paid direct DeepSeek/OpenRouter usage is counted in actual usage, and their
official account balances are shown separately in their original currencies.
They are OUT OF SCOPE for free recurring/fixed token capacity totals.
The FreeLLMAPI router is a view on its underlying sites, not another provider:
we count its successful upstream requests once. When FreeLLMAPI routes through
the WorkBuddy proxy, that request belongs only to WorkBuddy's JSONL ledger.

No user/chat identifiers, API keys, or account file contents are ever retained.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import Lock
import time
from typing import Any
from urllib import request
from urllib.parse import urlsplit

from .free_capacity import estimate_capacity
from .fixed_balances import collect_fixed_balances
from .official_balances import collect_official_balances
from .project_usage import (BOT_TIMEZONE, actual_provider_usage,
                            deployment_profile, configured_context, period_flags)

FREELLM_DB = Path("/var/lib/freellmapi-lab/freeapi.db")
WORKBUDDY_LOG = Path("/var/lib/workbuddy-lab/usage/usage.jsonl")
WORKBUDDY_ACCOUNTS = Path("/var/lib/workbuddy-lab/accounts")
WORKBUDDY_ACTIVITY = Path("/var/lib/workbuddy-lab/usage/activity_history.jsonl")
FREE_30_DAYS = 30
# International daily activity has historically credited 30 or 50 credits.
# 50 is a deliberately optimistic estimate, NOT a fixed official grant.
INTL_DAILY_ACTIVITY_ESTIMATE = Decimal(50)


def number(value: Any) -> Decimal | None:
    try:
        value = Decimal(str(value))
        return value if value.is_finite() and value >= 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def nat(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def wblog(path: Path = WORKBUDDY_LOG) -> dict | None:
    """The WorkBuddy gateway's complete priced request log, not per-day UI stats."""
    if not path.exists():
        return None
    used = dict(requests=0, tokens=0, input=0, cached=0, output=0,
                month_tokens=0, week_tokens=0,
                credit=Decimal(0), flash_credit=Decimal(0), flash_tokens=0,
                flash_sample_rates=[])
    try:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            for line in file:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue   # half-written trailing line
                if not isinstance(event, dict):
                    continue
                inp = nat(event.get("prompt_tokens"))
                output = nat(event.get("completion_tokens"))
                tokens = nat(event.get("total_tokens")) or inp + output
                credit = number(event.get("credit")) or Decimal(0)
                if not tokens and not credit:
                    continue
                used["requests"] += 1
                used["tokens"] += tokens
                used["input"] += inp
                used["cached"] += min(inp, nat(event.get("cached_tokens")))
                used["output"] += output
                used["credit"] += credit
                stamp = event.get("at")
                if stamp is None:
                    stamp = event.get("iso") or event.get("created_at")
                this_month, this_week = period_flags(stamp)
                if this_month:
                    used["month_tokens"] += tokens
                if this_week:
                    used["week_tokens"] += tokens
                model = str(event.get("model") or "").lower()
                if "deepseek" in model and "flash" in model and tokens and credit:
                    used["flash_credit"] += credit
                    used["flash_tokens"] += tokens
                    if tokens >= 1000:
                        used["flash_sample_rates"].append(credit * Decimal(1_000_000) / tokens)
    except OSError:
        return None
    return used


def workbuddy_account_pool(
    path: Path = WORKBUDDY_ACCOUNTS,
    activity_file: Path = WORKBUDDY_ACTIVITY,
) -> dict | None:
    """Read cached balances for all active *free* accounts, not just active realm.

    The account files also contain credentials. Only a strict numeric allowlist
    is extracted, and account ids, realms or filenames never leave this helper.
    """
    if not path.is_dir():
        return None
    balance = Decimal(0)
    count = 0
    cn_daily = Decimal(0)
    has_intl = False
    for file in path.glob("*.json"):
        if file.stem in ("model", "settings", "active_realm"):
            continue
        try:
            row = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(row, dict) or not row.get("enabled", True):
                continue
            credits = row.get("credits") or {}
            if not isinstance(credits, dict) or credits.get("is_paid_user") is True:
                continue
            remain = number(credits.get("remain"))
            if remain is None:
                continue
            balance += remain
            count += 1
            realm = str(row.get("realm") or "")
            checkin = credits.get("checkin") or {}
            if realm == "cn" and isinstance(checkin, dict) and checkin.get("active", True):
                cn_daily += number(checkin.get("daily_credit")) or Decimal(0)
            if realm == "intl":
                has_intl = True
        except (ValueError, OSError):
            continue
    if count == 0:
        return None
    # Intl requires actual daily activity in the recent history before we
    # project future benefits; do not invent a recurring grant for dormant IDs.
    intl_daily = Decimal(0)
    if has_intl and activity_file.exists():
        try:
            now = time.time()
            with activity_file.open("r", encoding="utf-8", errors="replace") as file:
                for line in file:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("realm") != "intl" or event.get("task") != "daily_chat" or event.get("ok") is not True:
                        continue
                    raw_ts = event.get("ts")
                    try:
                        from datetime import datetime, timezone
                        stamp = (datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp()
                                 if isinstance(raw_ts, str) and "-" in raw_ts
                                 else float(raw_ts or 0))
                    except (ValueError, TypeError, OverflowError):
                        continue
                    if 0 <= now - stamp <= 7 * 86400:
                        intl_daily = INTL_DAILY_ACTIVITY_ESTIMATE
                        break
        except OSError:
            pass
    return dict(
        balance=balance, free_accounts=count, cn_daily=cn_daily,
        intl_daily=intl_daily, daily_bonus=cn_daily + intl_daily,
    )


def freeapi_pool(path: Path = FREELLM_DB, *, profile: dict | None = None) -> dict | None:
    """All-time free-routed use + native FreeLLM-style optimistic monthly budget.

    Enabled healthy keys and active-profile models reproduce the UI's same
    eligibility conditions. One source's model-label sum remains explicitly
    separate from pooled/dedup and hypothetical full-context request capacity.
    """
    if not path.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            used = db.execute("""
                SELECT r.platform,r.model_id,r.created_at,k.base_url AS upstream_base_url,
                       COALESCE(r.input_tokens,0) AS inp,
                       COALESCE(r.output_tokens,0) AS out
                  FROM requests r LEFT JOIN api_keys k ON r.key_id=k.id
                 WHERE r.status='success'
                   AND NOT (r.platform='custom'
                       AND lower(COALESCE(k.label,'')) LIKE '%workbuddy%')
                   AND (r.platform!='openrouter' OR r.model_id LIKE '%:free')
                 ORDER BY r.rowid ASC
            """).fetchall()
            # Separate from the free-usage ledger: forwarding via WorkBuddy
            # still belongs to WB's token ledger, but is a genuine FreeLLM
            # upstream route worth displaying.
            recent = db.execute("""
                SELECT r.platform,r.model_id,r.created_at,
                       k.base_url AS upstream_base_url,k.label AS upstream_label
                  FROM requests r LEFT JOIN api_keys k ON r.key_id=k.id
                 WHERE r.status='success'
                 ORDER BY r.rowid DESC LIMIT 1
            """).fetchone()
            keys = db.execute("""
                SELECT platform,id,label,base_url
                  FROM api_keys
                 WHERE enabled=1 AND status IN ('healthy','unknown')
            """).fetchall()
            try:
                models = db.execute("""
                    SELECT rowid AS _model_db_id,platform,key_id,model_id,enabled,
                           rpm_limit,rpd_limit,tpm_limit,tpd_limit,context_window,
                           monthly_token_budget,paid_input_per_m,
                           paid_output_per_m
                      FROM models WHERE enabled=1
                """).fetchall()
            except sqlite3.OperationalError:
                # Older minimal installations have no context or price fields.
                models = db.execute("""
                    SELECT rowid AS _model_db_id,platform,key_id,model_id,enabled,
                           rpm_limit,rpd_limit,tpm_limit,tpd_limit,
                           NULL AS context_window,monthly_token_budget,
                           paid_input_per_m,
                           NULL AS paid_output_per_m
                      FROM models WHERE enabled=1
                """).fetchall()
            try:
                row = db.execute("SELECT value FROM settings WHERE key='active_profile_id'").fetchone()
                profile_id = int(row["value"]) if row and row["value"] else None
                if profile_id:
                    profile_ids = {
                        int(x[0]) for x in db.execute(
                            "SELECT model_db_id FROM profile_models WHERE profile_id=?",
                            (profile_id,)
                        ).fetchall()
                    }
                else:
                    profile_ids = None
            except (sqlite3.Error, ValueError, TypeError):
                profile_ids = None
            inactive = [
                "AgentRouter" for _ in db.execute(
                    "SELECT id FROM api_keys WHERE platform='custom' AND enabled=0"
                    " AND lower(COALESCE(label,'')) LIKE '%agentrouter%'"
                ).fetchall()
            ]

    except (sqlite3.Error, OSError):
        return None

    by_provider: dict[str, dict] = {}
    current_month_usage: dict[str, int] = {}
    total = 0
    total_input = total_output = month_tokens = week_tokens = 0
    now = time.time()
    from collections import Counter
    from datetime import timezone
    for row in used:
        platform = str(row["platform"] or "other")
        inp, out = nat(row["inp"]), nat(row["out"])
        tokens = inp + out
        total += tokens
        total_input += inp
        total_output += out
        item = by_provider.setdefault(platform, dict(tokens=0,requests=0,last24h=0))
        item["tokens"] += tokens
        item["requests"] += 1
        try:
            when = datetime.fromisoformat(str(row["created_at"]).replace("Z","+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when.timestamp() >= now-86400:
                item["last24h"] += tokens
        except (ValueError,TypeError):
            pass
        # FreeLLMAPI SQLite timestamps are stored in UTC.
        this_month, this_week = period_flags(row["created_at"], naive_tz=timezone.utc)
        if this_month:
            month_tokens += tokens
            current_month_usage[platform] = current_month_usage.get(platform,0) + tokens
        if this_week:
            week_tokens += tokens

    active: dict[str, dict] = {}
    key_counts = Counter()
    for k in keys:
        label = str(k["label"] or "")
        if k["platform"] == "custom" and "workbuddy" in label.lower():
            continue
        platform = str(k["platform"])
        key_counts[platform] += 1
        source = platform
        if source == "custom":
            from urllib.parse import urlsplit
            host = urlsplit(str(k["base_url"] or "")).hostname or "custom"
            source = "AnyRouter" if "anyrouter" in host else "公益站:" + host[:25]
        active[source] = dict(platform=platform,id=k["id"],label=label,models=[],
                              usage=by_provider.get(platform,{}))

    for r in models:
        model = dict(r)
        if profile_ids is not None and int(model["_model_db_id"]) not in profile_ids:
            continue
        for source,info in active.items():
            if info["platform"] != model["platform"]:
                continue
            if info["platform"] == "custom" and model["key_id"] != info["id"]:
                continue
            if info["platform"] == "openrouter" and not str(model["model_id"]).endswith(":free"):
                continue
            info["models"].append(model)

    # Transparent legacy per-day / per-month categories, no longer the main
    # total. The actual main total is the FreeLLM UI model-aggregate plus a
    # few documented-but-uncounted free allowances.
    daily: dict[str,int] = {}
    monthly: dict[str,int] = {}
    for source,info in active.items():
        ms = info["models"]
        if not ms:
            continue
        plat = info["platform"]
        budget = max((nat(m.get("tpd_limit")) for m in ms),default=0)
        hints = " ".join(str(m.get("monthly_token_budget") or "") for m in ms)
        if plat=="llm7" and "100,000 tokens/24h" in hints:
            budget=max(budget,100000)
        if plat=="xkiro" and "1M tokens/day" in hints:
            budget=max(budget,1_000_000)
        if budget:
            daily[source]=budget
        if plat=="ollama":
            matches=re.findall(r"~[0-9.]+-([0-9.]+)M",hints)
            if matches:
                monthly[source]=max(int(float(x)*1_000_000) for x in matches)
        if plat=="mistral" and "$10/month" in hints:
            prices=[number(m.get("paid_input_per_m")) for m in ms]
            prices=[v for v in prices if v and v>0]
            if prices:
                monthly[source]=int(Decimal(10_000_000)/min(prices))

    cap = estimate_capacity(active,dict(key_counts),
                            profile=profile,
                            current_month_usage=current_month_usage)
    remaining_today = sum(
        max(0,limit-by_provider.get(provider,{}).get("last24h",0))
        for provider,limit in daily.items()
    )
    rate_only = [source for source,info in active.items()
                 if info["models"] and source not in daily
                 and source not in monthly]
    # ModelScope's daily free credits are never treated as an unlimited pool.
    # In minimal/older catalogs lacking a context field, report the credit
    # unit alone instead of inventing a per-token conversion.
    unpriced_credit = {}
    if "modelscope" in active and active["modelscope"]["models"]:
        unpriced_credit["modelscope"] = "200 credit/天（兑换率未核验）"
        rate_only = [source for source in rate_only if source != "modelscope"]
    unmapped = [source for source,info in active.items() if not info["models"]]
    # This records what the upstream gateway actually served most recently,
    # not what its dynamic /auto router will necessarily choose next.
    last_source = str(recent["platform"]) if recent else ""
    if last_source == "custom":
        label = str(recent["upstream_label"] or "").lower()
        if "workbuddy" in label:
            last_source = "WorkBuddy"
        else:
            # Use the public upstream host only, never a saved key label or
            # private address. Raw base_url may contain credentials.
            host = urlsplit(str(recent["upstream_base_url"] or "")).hostname or ""
            try:
                ipaddress.ip_address(host)
                host = ""
            except ValueError:
                pass
            if (host and "." in host and re.fullmatch(r"[a-zA-Z0-9.-]{1,160}", host)
                    and not host.lower().endswith((".local", ".lan", ".internal"))):
                last_source = host.lower()
            else:
                last_source = "自定义上游"
    last_successful_route = (
        dict(platform=last_source,model=str(recent["model_id"]),
             at=str(recent["created_at"]))
        if recent and recent["platform"] and recent["model_id"] else None
    )
    return dict(
        requests=len(used),tokens=total,by_provider=by_provider,
        input=total_input,cached=0,output=total_output,
        month_tokens=month_tokens,week_tokens=week_tokens,
        last_successful_route=last_successful_route,
        active_sources=len(active),
        mapped_sources=sum(bool(v["models"]) for v in active.values()),
        renewable_daily=daily,renewable_monthly=monthly,
        remaining_today=remaining_today,
        forecast_30d=cap["forecast_30d"],
        native_model_monthly=cap["native_model_monthly"],
        native_pool_dedup_monthly=cap["native_pool_dedup_monthly"],
        native_month_used=cap["month_used"],
        optimistic_month_remaining=cap["remaining_month"],
        conditional_free_30d=cap["forecast_30d"],
        rate_only_monthly_throughput=0,

        capacity=cap,
        rate_only=rate_only,unpriced_credit=unpriced_credit,unmapped=unmapped,
        unavailable_charity=inactive,
    )


def _balance_fallback(key: str) -> Decimal | None:
    """WorkBuddy balance API fallback if the account files are unreadable."""
    if not key:
        return None
    req = request.Request("http://127.0.0.1:16302/v1/balance-summary",
                          headers={"Authorization":"Bearer "+key})
    with request.urlopen(req, timeout=3) as response:
        result = json.loads(response.read(100_000))
    return number(result.get("balance")) if result.get("unit") == "credit" else None


def workbuddy_price_basis(usage: dict | None) -> tuple[Decimal,str]:
    """Use *all* historical DeepSeek Flash charges, including cache savings.

    Real aggregate paid credits divided by recorded Flash tokens captures the
    deployment-wide input/output/cache mix without selecting cherry-picked
    low-cost or single-model extreme prompts.
    """
    tokens = nat((usage or {}).get("flash_tokens"))
    spent = (usage or {}).get("flash_credit") or Decimal(0)
    if tokens and spent > 0:
        per_m = spent * Decimal(1_000_000) / Decimal(tokens)
        return per_m, "历史 DeepSeek Flash 全部调用的实际平均信用成本"
    return Decimal(12), "Flash历史账本缺失，暂用12 credit/百万token"


def configured_current_model(path: Path) -> dict | None:
    """Current chat-provider selection from AstrBot config (no API keys read out)."""
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(config, dict):
        return None
    settings = config.get("provider_settings") or {}
    preferred = str(settings.get("default_provider_id") or "") if isinstance(settings, dict) else ""
    providers = [
        item for item in config.get("provider", [])
        if isinstance(item, dict) and item.get("enable", True)
        and isinstance(item.get("id"), str)
    ]
    selected = next((item for item in providers if item["id"] == preferred), None)
    if selected is None:
        selected = next(iter(providers), None)
    if selected is None:
        return None
    route = selected["id"].split("/", 1)[0]
    model = str(selected.get("model") or selected["id"].partition("/")[2]).strip()
    return {"model": model, "source": route} if model and route else None


def collect(
    data_dir: Path, *, free_db: Path = FREELLM_DB,
    wb_log: Path = WORKBUDDY_LOG, accounts_dir: Path = WORKBUDDY_ACCOUNTS,
    activity_file: Path = WORKBUDDY_ACTIVITY,
) -> dict:
    # Each upstream request is counted exactly once. Direct AstrBot providers
    # have their own provider_stats records; WB and FreeLLM have upstream logs.
    usage = wblog(wb_log)
    direct = actual_provider_usage(data_dir / "data_v4.db")
    pool = workbuddy_account_pool(accounts_dir, activity_file)
    context_cap = configured_context(data_dir / "cmd_config.json")
    profile = deployment_profile(data_dir / "data_v4.db", context_limit=context_cap)
    free = freeapi_pool(free_db,profile=profile)
    fixed_extra = collect_fixed_balances(data_dir,free_db,profile)
    official = collect_official_balances(data_dir / "cmd_config.json")
    if pool is None:
        # WorkBuddy exposes only the currently selected realm. This fallback
        # must be marked partial and may omit other free accounts.
        pool = dict(balance=None, free_accounts=0, cn_daily=Decimal(0),
                    intl_daily=Decimal(0), daily_bonus=Decimal(0), partial=True)
    if free is None:
        free = dict(tokens=None,requests=None,by_provider={},active_sources=0,
                    input=0,cached=0,output=0,month_tokens=0,week_tokens=0,
                    mapped_sources=0, renewable_daily={}, renewable_monthly={},
                    remaining_today=0, forecast_30d=0, rate_only=[], unpriced_credit={}, unmapped=[],
                    unavailable_charity=[], unreadable=True,
                    native_model_monthly=0,native_pool_dedup_monthly=0,
                    native_month_used=0,optimistic_month_remaining=0,
                    conditional_free_30d=0,rate_only_monthly_throughput=0,
                    capacity=dict(model_count=0),
)
    balance = pool.get("balance")
    per_m, price_note = workbuddy_price_basis(usage)
    now_equiv = int(balance * 1000000 / per_m) if balance is not None else None
    future_credit = pool["daily_bonus"] * FREE_30_DAYS
    future_equiv = int(future_credit * 1000000 / per_m)
    free30 = free.get("forecast_30d", 0)
    known_sources = [src for src in (direct, usage, free)
                     if src is not None and src.get("tokens") is not None]
    used_total = sum(src["tokens"] for src in known_sources) if known_sources else None
    used_month = sum(src.get("month_tokens", 0) for src in known_sources) if known_sources else None
    used_week = sum(src.get("week_tokens", 0) for src in known_sources) if known_sources else None
    actual_input = sum(src.get("input", 0) for src in known_sources)
    actual_output = sum(src.get("output", 0) for src in known_sources)
    actual_cached = sum(src.get("cached", 0) for src in known_sources)
    actual_io = actual_input + actual_output
    usage_mix = dict(
        input_tokens=actual_input,output_tokens=actual_output,
        cached_input_tokens=actual_cached,
        cache_hit=actual_cached / actual_input if actual_input else None,
        input_share=actual_input / actual_io if actual_io else None,
        output_share=actual_output / actual_io if actual_io else None,
    )
    # Monthly *renewable* supply and once-only balances must be separate.
    # WorkBuddy gift packages must not be rolled into every future month.
    forecast_30d = (future_equiv + free30) if (usage is not None or not free.get("unreadable")) else None
    volc_remaining = fixed_extra.get("volcengine_tokens")
    fixed_now = ((now_equiv or 0)+fixed_extra["extra_tokens"]
                 if now_equiv is not None or fixed_extra["sources"] else None)
    conditional_30d = forecast_30d
    rate_ceiling = 0
    return dict(
        used_total=used_total,
        used_month=used_month,
        used_week=used_week,
        direct=direct,
        usage_mix=usage_mix,
        official=official,
        current_model=configured_current_model(data_dir / "cmd_config.json"),
        updated_at=datetime.now(BOT_TIMEZONE).isoformat(timespec="minutes"),
        free=free,
        wb=dict(
            used_tokens=(usage or {}).get("tokens"),
            requests=(usage or {}).get("requests"),
            credit_spent=str((usage or {}).get("credit", 0)) if usage else None,
            credit_balance=str(balance) if balance is not None else None,
            account_count=pool["free_accounts"],
            credit_daily=str(pool["daily_bonus"]),
            credit_cn_daily=str(pool["cn_daily"]),
            credit_intl_daily=str(pool["intl_daily"]),
            credit_future30=str(future_credit),
            remaining_tokens_now=now_equiv,
            additional_tokens_30d=future_equiv,
            price_basis=price_note,
            rate_credit_per_m=str(per_m),
            partial=pool.get("partial", False),
        ),
        finite_now=fixed_now,
        fixed_remaining=fixed_now,
        fixed_volcengine=volc_remaining,
        fixed_sources=fixed_extra["sources"],
        fixed_balance_missing=fixed_extra["unverified_sources"],
        project_profile=profile,
        forecast_30d=forecast_30d,
        conditional_30d=conditional_30d,
        rate_only_throughput_30d=rate_ceiling,
        including_rate_only_ceiling=(forecast_30d+rate_ceiling) if forecast_30d is not None else None,
        unreadable=[name for name, data in (("AstrBot",direct),("WorkBuddy",usage),("FreeLLMAPI",free))
                    if data is None or data.get("unreadable")],
    )


def exact(value: int | None) -> str:
    return f"{value:,}" if value is not None else "不可读"


def compact(value: int | None) -> str:
    """Human-readable SI token scale, with one convention for all quantities."""
    if value is None:
        return "不可读"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.3f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.3f}M"
    if value >= 1_000:
        return f"{value / 1_000:.3f}K"
    return f"{value:,}"


def _pct(value: float | None) -> str:
    return f"{100*value:.1f}%" if value is not None else "暂无数据"


def _money(row: dict | None) -> str:
    if not row or row.get("status") != "ok":
        return (row or {}).get("status", "暂不可查")
    try:
        amount = Decimal(str(row["amount"]))
    except (InvalidOperation, ValueError, KeyError):
        return "暂不可查"
    prefix = {"CNY": "¥", "USD": "$"}.get(row.get("currency"))
    return f"{prefix}{amount:,.2f}" if prefix else f"{amount:,.2f} {row.get('currency')}"


def _model_lines(selected: dict | None,
                 last_free_route: dict | None = None) -> list[str]:
    if not isinstance(selected, dict) or not selected.get("model"):
        return ["当前模型：未配置", "模型来源：未知"]
    source = str(selected.get("source") or "").strip()
    model = str(selected["model"]).strip()
    if source.lower() == "freellmapi":
        route = last_free_route or {}
        actual_model = str(route.get("model") or "").replace("\n", " ")[:120].strip()
        actual_source = str(route.get("platform") or "").replace("\n", " ")[:120].strip()
        # For /auto a route is selected on each inference request. The latest
        # completed gateway request is factual; a future route is not knowable.
        if actual_model and actual_source and model.lower() == "auto":
            names = {
                "groq": "Groq", "ollama": "Ollama", "openrouter": "OpenRouter",
                "zhipu": "智谱", "modelscope": "ModelScope", "ovh": "OVHcloud",
                "kilo": "Kilo", "xkiro": "xKiro", "mistral": "Mistral",
                "google": "Google", "cloudflare": "Cloudflare",
            }
            actual_source = names.get(actual_source.lower(), actual_source)
            try:
                date = datetime.fromisoformat(str(route["at"]).replace("Z", "+00:00"))
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                stamp = date.astimezone(BOT_TIMEZONE).strftime("%m-%d %H:%M")
            except (ValueError, TypeError, KeyError, OverflowError):
                stamp = "时间未知"
            return [
                f"当前模型：auto（最近执行：{actual_model}）",
                f"模型来源：FreeLLMAPI → {actual_source}（网关最近成功 {stamp}）",
            ]
        return [f"当前模型：{model}", "模型来源：FreeLLMAPI（动态路由，暂无匹配上游记录）"]
    source = {
        "deepseek": "DeepSeek 官方",
        "openrouter": "OpenRouter",
        "workbuddy": "WorkBuddy",
        "freellmapi": "FreeLLMAPI",
    }.get(source.lower(), source or "未知来源")
    return [f"当前模型：{model}", f"模型来源：{source}"]


def render(snapshot: dict, *, detail: bool = False,
           current_model: dict | None = None) -> str:
    """Compact live usage and capacity dashboard for /quota and doge_quota."""
    wb,free=snapshot["wb"],snapshot["free"]
    mix=snapshot.get("usage_mix") or {}
    prof=snapshot.get("project_profile") or {}
    predictive_mix=(
        dict(cache_hit=prof.get("cached_input_share"),
             input_share=prof.get("input_share"),
             output_share=prof.get("output_share"))
        if prof.get("available") else {}
    )
    providers=(snapshot.get("official") or {}).get("providers") or {}
    updated=str(snapshot.get("updated_at") or "")
    stamp=updated[5:16].replace("T", " ") if len(updated)>=16 else "当前"
    lines=[
        f"模型用量与额度 · {stamp}",
        *_model_lines(
            current_model or snapshot.get("current_model"),
            free.get("last_successful_route"),
        ),
        "",
        f"本月消耗：{compact(snapshot.get('used_month'))} tokens",
        f"历史总消耗：{compact(snapshot.get('used_total'))} tokens",
        f"近7天消耗：{compact(snapshot.get('used_week'))} tokens",
        "",
        "历史比例：",
        f"缓存命中率： {_pct(predictive_mix.get('cache_hit'))}",
        f"输入/输出： {_pct(predictive_mix.get('input_share'))}/{_pct(predictive_mix.get('output_share'))}",
        "",
        "免费模型额度：",
        f"每月免费额度：~{compact(snapshot['forecast_30d'])} tokens",
        f"一次性额度剩余：~{compact(snapshot.get('fixed_remaining'))} tokens",
        "",
        "付费模型余额：",
        f"DeepSeek： {_money(providers.get('deepseek'))}",
        f"OpenRouter： {_money(providers.get('openrouter'))}",
    ]
    if detail:
        lines.append("")
        lines.append(
            f"月额估算依据（按当前上下文上限截断）：部署以来 {prof.get('requests',0)} 次调用，"
            f"均长 {int(prof.get('avg_request_tokens') or 0):,} tokens，"
            f"上下文限 {int(prof.get('context_limit') or 0):,}，"
            f"输入 {100*prof.get('input_share',0):.1f}% / 输出 {100*prof.get('output_share',0):.1f}%"
        )
        direct=snapshot.get("direct") or {}
        lines.append(
            "历史实耗（未截断）："
            f"AstrBot直连 {exact(direct.get('tokens'))}；"
            f"WorkBuddy {exact(wb.get('used_tokens'))}；"
            f"FreeLLMAPI {exact(free.get('tokens'))} tokens"
        )
        lines.append(
            f"历史结构：输入 {exact(mix.get('input_tokens'))}、"
            f"缓存输入 {exact(mix.get('cached_input_tokens'))}（含于输入）、"
            f"输出 {exact(mix.get('output_tokens'))} tokens；"
            "未报告缓存的路由按无缓存计"
        )
        lines.append(
            f"历史实耗比例（未截断）：缓存 {_pct(mix.get('cache_hit'))}；"
            f"输入/输出 {_pct(mix.get('input_share'))}/{_pct(mix.get('output_share'))}"
        )
        lines.append(
            f"月额：FreeLLM免费池 ~{compact(free.get('forecast_30d'))} + "
            f"WorkBuddy每日领取 ~{compact(wb.get('additional_tokens_30d'))} tokens；"
            f"换算 {Decimal(wb['rate_credit_per_m']):.2f} credit/M tokens"
        )
        fixed_parts=[f"WorkBuddy已到账 {wb.get('credit_balance') or '未知'} credit"]
        for row in snapshot.get("fixed_sources",[]):
            fixed_parts.append(
                f"{row['provider']} {row['amount']} {row['currency']} ≈ "
                f"{compact(row['remaining_tokens'])} tokens"
            )
        lines.append("固定余额："+"；".join(fixed_parts))
        missing=snapshot.get("fixed_balance_missing") or []
        if missing:
            lines.append("另有未查询成功的钱包余额："+"、".join(missing))
        ds=providers.get("deepseek") or {}
        if ds.get("status")=="ok" and ds.get("granted") is not None:
            lines.append(f"DeepSeek余额包含赠金 {_money(dict(status='ok',amount=ds['granted'],currency=ds.get('currency')))}")
    if snapshot["unreadable"]:
        lines.append("部分账本不可读："+",".join(snapshot["unreadable"]))
    return "\n".join(lines)


class QuotaLedger:
    """Read-only snapshot service; no stale snapshots between /quota calls."""

    def __init__(self, data_dir: Path, *, free_db: Path = FREELLM_DB, wb_log: Path = WORKBUDDY_LOG,
                 accounts_dir: Path = WORKBUDDY_ACCOUNTS, activity_file: Path = WORKBUDDY_ACTIVITY,
                 ttl: float = 0):
        self.data_dir = Path(data_dir)
        self.free_db = Path(free_db)
        self.wb_log = Path(wb_log)
        self.accounts_dir = Path(accounts_dir)
        self.activity_file = Path(activity_file)
        self.ttl = ttl
        self._lock = Lock()
        self._last: dict | None = None
        self._at = -1.0

    def snapshot(self, *, refresh: bool = False) -> dict:
        with self._lock:
            if not refresh and self._last is not None and time.monotonic() - self._at < self.ttl:
                return json.loads(json.dumps(self._last))
            self._last = collect(self.data_dir, free_db=self.free_db, wb_log=self.wb_log,
                                 accounts_dir=self.accounts_dir, activity_file=self.activity_file)
            self._at = time.monotonic()
            return json.loads(json.dumps(self._last))

    def display(self, *, detail: bool = False,
                current_model: dict | None = None) -> str:
        return render(self.snapshot(), detail=detail, current_model=current_model)


@lru_cache(maxsize=3)
def get_quota_ledger(data_dir: Path) -> QuotaLedger:
    return QuotaLedger(Path(data_dir))
