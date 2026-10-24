"""All-time usage and free-resource availability for Doge.

Only resources that are free to this operator:
* WorkBuddy free account credits, including future check-in projections;
* FreeLLMAPI free provider routes, including community gateways.

Paid direct DeepSeek and paid OpenRouter are explicitly OUT OF SCOPE.
The FreeLLMAPI router is a view on its underlying sites, not another provider:
we count its successful upstream requests once. When FreeLLMAPI routes through
the WorkBuddy proxy, that request belongs only to WorkBuddy's JSONL ledger.

No user/chat identifiers, API keys, or account file contents are ever retained.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import Lock
import time
from typing import Any
from urllib import request

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
                credit=Decimal(0), flash_credit=Decimal(0), flash_tokens=0)
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
                model = str(event.get("model") or "").lower()
                if "deepseek" in model and "flash" in model and tokens and credit:
                    used["flash_credit"] += credit
                    used["flash_tokens"] += tokens
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


def freeapi_pool(path: Path = FREELLM_DB) -> dict | None:
    """One row per successful routed request; inspect all active free sources."""
    if not path.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            # Any request routed to the WorkBuddy custom key is already in WB
            # usage.jsonl. Direct paid OpenRouter calls do not go through this
            # database. An OpenRouter *free* route only counts with :free model.
            used = db.execute("""
                SELECT r.platform, r.model_id, r.created_at,
                       COALESCE(r.input_tokens,0) AS inp,
                       COALESCE(r.output_tokens,0) AS out
                  FROM requests r
                  LEFT JOIN api_keys k ON r.key_id=k.id
                 WHERE r.status='success'
                   AND NOT (r.platform='custom'
                            AND lower(COALESCE(k.label,'')) LIKE '%workbuddy%')
                   AND (r.platform != 'openrouter' OR r.model_id LIKE '%:free')
            """).fetchall()
            keys = db.execute("""
                SELECT platform, id, label, base_url
                  FROM api_keys WHERE enabled=1 AND status IN ('healthy','unknown')
            """).fetchall()
            models = db.execute("""
                SELECT platform, key_id, model_id, enabled, rpm_limit,
                       rpd_limit, tpm_limit, tpd_limit,
                       monthly_token_budget, paid_input_per_m
                  FROM models WHERE enabled=1
            """).fetchall()
            unavailable_charity = [
                "AgentRouter" for row in db.execute(
                    "SELECT label FROM api_keys WHERE platform='custom' AND enabled=0"
                    " AND lower(COALESCE(label,'')) LIKE '%agentrouter%'"
                ).fetchall()
            ]
    except (sqlite3.Error, OSError):
        return None

    by_provider: dict[str, dict] = {}
    total = 0
    now = time.time()
    # request timestamps (ISO SQLite UTC); do not leak request contents.
    import datetime as dt
    current_24h = now - 86400
    for row in used:
        plat = str(row["platform"] or "other")
        tok = nat(row["inp"]) + nat(row["out"])
        total += tok
        item = by_provider.setdefault(plat, dict(tokens=0, requests=0, last24h=0))
        item["tokens"] += tok
        item["requests"] += 1
        try:
            stamp = dt.datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            if stamp.timestamp() >= current_24h:
                item["last24h"] += tok
        except ValueError:
            pass
    active: dict[str, dict] = {}
    for key in keys:
        # WorkBuddy is reported separately, not counted as free routing capacity.
        label = str(key["label"] or "")
        if key["platform"] == "custom" and "workbuddy" in label.lower():
            continue
        source = str(key["platform"])
        if source == "custom":
            from urllib.parse import urlsplit
            host = urlsplit(str(key["base_url"] or "")).hostname or "custom"
            source = "AnyRouter" if "anyrouter" in host else "公益站:" + host[:25]
        active[source] = dict(platform=str(key["platform"]), id=key["id"], label=label,
                              models=[], usage=by_provider.get(str(key["platform"]),{}))
    for model in models:
        for info in active.values():
            if info["platform"] != model["platform"]:
                continue
            if info["platform"] == "custom" and model["key_id"] != info["id"]:
                continue
            if info["platform"] == "openrouter" and ":free" not in str(model["model_id"] or ""):
                continue
            info["models"].append(dict(model))
    # Free-rate/rolling pool: label a *forecast* only where actual model
    # metadata supplies a credible daily or monthly numerical denominator.
    daily: dict[str, int] = {}
    monthly: dict[str, int] = {}
    for provider, info in active.items():
        ms = info["models"]
        if not ms:
            continue
        plat = info["platform"]
        budget = max((nat(m["tpd_limit"]) for m in ms), default=0)
        hints = " ".join(str(m.get("monthly_token_budget") or "") for m in ms)
        if plat == "llm7" and "100,000 tokens/24h" in hints:
            budget = max(budget, 100000)
        if plat == "xkiro" and "500K tokens/day" in hints:
            budget = max(budget, 500000)
        if budget:
            daily[provider] = budget
        if plat == "ollama":
            # Source's own estimates are ~20-30M per month. Take upper bound
            # of the shared account pool, never multiply it by model count.
            matches = re.findall(r"~[0-9.]+-([0-9.]+)M", hints)
            if matches:
                monthly[provider] = max(int(float(x) * 1000000) for x in matches)
        if plat == "mistral" and "$10/month" in hints:
            # Native Mistral free plan: $10/month shared, use cheapest
            # explicitly listed input-only price, optimistic by design.
            prices = [number(m.get("paid_input_per_m")) for m in ms]
            prices = [v for v in prices if v and v > 0]
            if prices:
                monthly[provider] = int(Decimal(10) * Decimal(1000000) / min(prices))
    # A future 30-day projection is not the present exact balance. For rolling
    # sources, use full daily throughput; rate-only gateways remain unbounded
    # over lifetime (subject to time/fair-use).
    forecast_30d = sum(daily.values()) * FREE_30_DAYS + sum(monthly.values())
    finite_remaining_today = sum(
        max(0, cap - by_provider.get(provider, {}).get("last24h", 0))
        for provider, cap in daily.items()
    )
    rate_only = [p for p,x in active.items() if x["models"] and p not in daily and p not in monthly]
    unpriced_credit = {"modelscope": "200 credit/天（24h失效，未获可信token兑换率）"} if "modelscope" in rate_only else {}
    rate_only = [p for p in rate_only if p not in unpriced_credit]
    unmapped = [p for p,x in active.items() if not x["models"]]
    return dict(
        requests=len(used), tokens=total, by_provider=by_provider,
        active_sources=len(active), mapped_sources=sum(bool(x["models"]) for x in active.values()),
        renewable_daily=daily, renewable_monthly=monthly,
        remaining_today=finite_remaining_today,
        forecast_30d=forecast_30d,
        rate_only=rate_only, unpriced_credit=unpriced_credit, unmapped=unmapped,
        unavailable_charity=unavailable_charity,
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


def workbuddy_price_basis(usage: dict | None) -> tuple[Decimal, str]:
    sample_tokens = nat((usage or {}).get("flash_tokens"))
    sample_credit = (usage or {}).get("flash_credit") or Decimal(0)
    if sample_tokens and sample_credit > 0:
        per_m = sample_credit * Decimal(1_000_000) / Decimal(sample_tokens)
        return per_m, "本地历史 DeepSeek Flash 实际 credit/token 比例"
    return Decimal(12), "历史样本缺失，暂按12 credit/百万 token"


def collect(
    data_dir: Path, *, free_db: Path = FREELLM_DB,
    wb_log: Path = WORKBUDDY_LOG, accounts_dir: Path = WORKBUDDY_ACCOUNTS,
    activity_file: Path = WORKBUDDY_ACTIVITY,
) -> dict:
    # No paid-direct providers, not even if provider_stats contains billions.
    usage = wblog(wb_log)
    pool = workbuddy_account_pool(accounts_dir, activity_file)
    free = freeapi_pool(free_db)
    if pool is None:
        # WorkBuddy exposes only the currently selected realm. This fallback
        # must be marked partial and may omit other free accounts.
        pool = dict(balance=None, free_accounts=0, cn_daily=Decimal(0),
                    intl_daily=Decimal(0), daily_bonus=Decimal(0), partial=True)
    if free is None:
        free = dict(tokens=None, requests=None, by_provider={}, active_sources=0,
                    mapped_sources=0, renewable_daily={}, renewable_monthly={},
                    remaining_today=0, forecast_30d=0, rate_only=[], unpriced_credit={}, unmapped=[],
                    unavailable_charity=[], unreadable=True)
    balance = pool.get("balance")
    per_m, price_note = workbuddy_price_basis(usage)
    now_equiv = int(balance * 1000000 / per_m) if balance is not None else None
    future_credit = pool["daily_bonus"] * FREE_30_DAYS
    future_equiv = int(future_credit * 1000000 / per_m)
    free30 = free.get("forecast_30d", 0)
    used_total = (usage or {}).get("tokens", 0) + (free.get("tokens") or 0)
    finite_now = ((now_equiv or 0) + free.get("remaining_today", 0)) if now_equiv is not None else None
    forecast_30d = ((now_equiv or 0) + future_equiv + free30) if now_equiv is not None else None
    return dict(
        used_total=used_total,
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
        finite_now=finite_now,
        forecast_30d=forecast_30d,
        unreadable=[name for name, data in (("WorkBuddy",usage),("FreeLLMAPI",free))
                    if data is None or data.get("unreadable")],
    )


def exact(value: int | None) -> str:
    return f"{value:,}" if value is not None else "不可读"


def compact(value: int | None) -> str:
    if value is None:
        return "不可读"
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return f"{value:,}"


def render(snapshot: dict, *, detail: bool = False) -> str:
    wb, free = snapshot["wb"], snapshot["free"]
    lines = [
        "豆子 · 免费模型总账（全部来源、全部历史）",
        f"累计已用：{snapshot['used_total']:,} tokens",
        f"已知即时剩余：约 {compact(snapshot['finite_now'])} tokens",
        f"未来30天理论可用：约 {compact(snapshot['forecast_30d'])} tokens",
        "（只加有限额度，未计理论不限总额的限速公益池）",
        "",
        f"WorkBuddy：已用 {exact(wb['used_tokens'])} tokens；当前约 {compact(wb['remaining_tokens_now'])}",
        f"  免费账户余额 {wb.get('credit_balance') or '未知'} credit，"
        f"每日预计增加 {wb['credit_daily']} credit",
        f"  未来30天可新领约 {wb['credit_future30']} credit",
        f"FreeLLMAPI 公益路由：已用 {exact(free.get('tokens'))} tokens",
        f"  有限周期额度：当前24h估剩 {compact(free['remaining_today'])}，"
        f"30天约 {compact(free['forecast_30d'])}",
        f"  限速/总额度不明：{len(free['rate_only'])} 个；"
        f"每日积分无法折Token：{len(free['unpriced_credit'])} 个",
        f"  其他已配密钥但未映射模型：{len(free['unmapped'])} 个",
    ]
    if detail:
        lines.extend(["", "额度依据"])
        lines.append(f"  WorkBuddy：{wb['price_basis']}；{Decimal(wb['rate_credit_per_m']):.2f} credit/百万 token")
        lines.append(f"  国际账号每日活跃按最多 {INTL_DAILY_ACTIVITY_ESTIMATE} credit 估；"
                     "每日奖励需成功签到/活动，未来30天不保证到账")
        for provider, cap in sorted(free["renewable_daily"].items()):
            lines.append(f"  {provider}: {compact(cap)} tokens/天（按站点元数据）")
        for provider, cap in sorted(free["renewable_monthly"].items()):
            lines.append(f"  {provider}: 约{compact(cap)} tokens/月（部分为宽松推算）")
        if free["rate_only"]:
            lines.append("  限频/总额未知站点：" + "、".join(sorted(free["rate_only"])))
        for provider,note in sorted(free["unpriced_credit"].items()):
            lines.append(f"  {provider}：{note}")
        if free["unmapped"]:
            lines.append("  暂无有效模型映射：" + "、".join(sorted(free["unmapped"])))
        if free["unavailable_charity"]:
            lines.append("  暂不可用的公益站：" + "、".join(sorted(free["unavailable_charity"])))
        lines.append("  FreeLLMAPI经WorkBuddy的请求只记在WorkBuddy，避免重复统计")
    if snapshot["unreadable"]:
        lines.append("部分账本不可读，结果为已知部分："+"、".join(snapshot["unreadable"]))
    lines.append("注：免费额度会重置或过期；30天数值为乐观容量，未加官方付费DS/OpenRouter，也不包含未折算或无总额公益池。")
    return "\n".join(lines)


class QuotaLedger:
    """Read-only two-ledger service with a 60-second in-memory result cache."""

    def __init__(self, data_dir: Path, *, free_db: Path = FREELLM_DB, wb_log: Path = WORKBUDDY_LOG,
                 accounts_dir: Path = WORKBUDDY_ACCOUNTS, activity_file: Path = WORKBUDDY_ACTIVITY,
                 ttl: float = 60):
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

    def display(self, *, detail: bool = False) -> str:
        return render(self.snapshot(), detail=detail)


@lru_cache(maxsize=3)
def get_quota_ledger(data_dir: Path) -> QuotaLedger:
    return QuotaLedger(Path(data_dir))
