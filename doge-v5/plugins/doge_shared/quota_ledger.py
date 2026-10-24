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

from .free_capacity import estimate_capacity

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


def freeapi_pool(path: Path = FREELLM_DB) -> dict | None:
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
                SELECT r.platform,r.model_id,r.created_at,
                       COALESCE(r.input_tokens,0) AS inp,
                       COALESCE(r.output_tokens,0) AS out
                  FROM requests r LEFT JOIN api_keys k ON r.key_id=k.id
                 WHERE r.status='success'
                   AND NOT (r.platform='custom'
                       AND lower(COALESCE(k.label,'')) LIKE '%workbuddy%')
                   AND (r.platform!='openrouter' OR r.model_id LIKE '%:free')
            """).fetchall()
            keys = db.execute("""
                SELECT platform,id,label,base_url
                  FROM api_keys
                 WHERE enabled=1 AND status IN ('healthy','unknown')
            """).fetchall()
            try:
                models = db.execute("""
                    SELECT rowid AS _model_db_id,platform,key_id,model_id,enabled,
                           rpm_limit,rpd_limit,tpm_limit,tpd_limit,context_window,
                           monthly_token_budget,paid_input_per_m
                      FROM models WHERE enabled=1
                """).fetchall()
            except sqlite3.OperationalError:
                # Older minimal installations have no context or price fields.
                models = db.execute("""
                    SELECT rowid AS _model_db_id,platform,key_id,model_id,enabled,
                           rpm_limit,rpd_limit,tpm_limit,tpd_limit,
                           NULL AS context_window,monthly_token_budget,
                           paid_input_per_m
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
    now = time.time()
    from collections import Counter
    from datetime import datetime, timezone
    now_month = datetime.fromtimestamp(now,timezone.utc).strftime("%Y-%m")
    for row in used:
        platform = str(row["platform"] or "other")
        tokens = nat(row["inp"]) + nat(row["out"])
        total += tokens
        item = by_provider.setdefault(platform, dict(tokens=0,requests=0,last24h=0))
        item["tokens"] += tokens
        item["requests"] += 1
        try:
            when = datetime.fromisoformat(str(row["created_at"]).replace("Z","+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when.timestamp() >= now-86400:
                item["last24h"] += tokens
            if when.astimezone(timezone.utc).strftime("%Y-%m")==now_month:
                current_month_usage[platform] = current_month_usage.get(platform,0) + tokens
        except (ValueError,TypeError):
            pass

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
                            current_month_usage=current_month_usage)
    remaining_today = sum(
        max(0,limit-by_provider.get(provider,{}).get("last24h",0))
        for provider,limit in daily.items()
    )
    rate_only = [source for source,info in active.items()
                 if info["models"] and source not in daily
                 and source not in monthly
                 and source not in cap["derived"]]
    # ModelScope's daily free credits are never treated as an unlimited pool.
    # In minimal/older catalogs lacking a context field, report the credit
    # unit alone instead of inventing a per-token conversion.
    unpriced_credit = {}
    if "modelscope" in active and active["modelscope"]["models"]:
        unpriced_credit["modelscope"] = "200 credit/天（兑换率未核验）"
        rate_only = [source for source in rate_only if source != "modelscope"]
    unmapped = [source for source,info in active.items() if not info["models"]]
    return dict(
        requests=len(used),tokens=total,by_provider=by_provider,
        active_sources=len(active),
        mapped_sources=sum(bool(v["models"]) for v in active.values()),
        renewable_daily=daily,renewable_monthly=monthly,
        remaining_today=remaining_today,
        forecast_30d=cap["optimistic_monthly"],
        native_model_monthly=cap["native_model_monthly"],
        native_pool_dedup_monthly=cap["native_pool_dedup_monthly"],
        native_month_used=cap["current_month_used"],
        optimistic_month_remaining=cap["optimistic_remaining_current_month"],
        conditional_free_30d=cap["conditional_or_upgrade_total"],
        rate_only_monthly_throughput=cap["rate_only_throughput_monthly"],
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
    """Use low-decile *actual Flash* costs for an optimistic credit estimate.

    Flash prompt caching causes the cost/token ratio to vary substantially.
    A positive-sample decile is more defensible than either the weighted
    average (too conservative for this user's goal) or the single minimum.
    """
    candidates = sorted((usage or {}).get("flash_sample_rates") or [])
    if len(candidates) >= 5:
        idx = (len(candidates) - 1) // 10
        per_m = candidates[idx]
        return per_m, ("历史 DeepSeek Flash 单次有效单价的低10%区间"
                       f"（{len(candidates)}条≥1000token样本，已考虑缓存）")
    tokens = nat((usage or {}).get("flash_tokens"))
    spent = (usage or {}).get("flash_credit") or Decimal(0)
    if tokens and spent > 0:
        per_m = spent * Decimal(1_000_000) / Decimal(tokens)
        return per_m, "历史 DeepSeek Flash 平均实付比例（样本不足）"
    return Decimal(12), "Flash历史账本缺失，暂用12 credit/百万token"


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
                    unavailable_charity=[], unreadable=True,
                    native_model_monthly=0,native_pool_dedup_monthly=0,
                    native_month_used=0,optimistic_month_remaining=0,
                    conditional_free_30d=0,rate_only_monthly_throughput=0,
                    capacity=dict(sources={},derived={},rate_only_estimates={},
                                  model_count=0))
    balance = pool.get("balance")
    per_m, price_note = workbuddy_price_basis(usage)
    now_equiv = int(balance * 1000000 / per_m) if balance is not None else None
    future_credit = pool["daily_bonus"] * FREE_30_DAYS
    future_equiv = int(future_credit * 1000000 / per_m)
    free30 = free.get("forecast_30d", 0)
    used_total = (usage or {}).get("tokens", 0) + (free.get("tokens") or 0)
    finite_now = ((now_equiv or 0) + free.get("remaining_today", 0)) if now_equiv is not None else None
    forecast_30d = ((now_equiv or 0) + future_equiv + free30) if now_equiv is not None else None
    conditional_30d = ((now_equiv or 0) + future_equiv + free.get("conditional_free_30d",free30)) if now_equiv is not None else None
    rate_ceiling = free.get("rate_only_monthly_throughput",0)
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
        conditional_30d=conditional_30d,
        rate_only_throughput_30d=rate_ceiling,
        including_rate_only_ceiling=(forecast_30d+rate_ceiling) if forecast_30d is not None else None,
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
    """Small QQ-first overview; full source arithmetic in admin detail."""
    wb, free = snapshot["wb"], snapshot["free"]
    c = free.get("capacity") or {}
    month = snapshot.get("forecast_30d")
    lines = [
        "豆子 · 免费模型额度总账",
        f"累计已用：{snapshot['used_total']:,} tokens（全部已记录历史）",
        f"现有可折算额度：约 {compact(wb['remaining_tokens_now'])} tokens（WorkBuddy已到账免费包）",
        f"未来30天乐观总量：约 {compact(month)} tokens",
        "",
        f"WorkBuddy：已用 {exact(wb['used_tokens'])} tokens；"
        f"固定/赠送包余额 {wb.get('credit_balance') or '未知'} credit，"
        f"折合 {compact(wb['remaining_tokens_now'])}",
        f"  每日签到/活动预计 +{wb['credit_daily']} credit，"
        f"30天再增加 {compact(wb['additional_tokens_30d'])} tokens",
        f"FreeLLMAPI：模型面板标称 {compact(free.get('native_model_monthly'))}/月；"
        f"补算免费额度后 {compact(free.get('forecast_30d'))}/月",
        f"  当前成功请求累计已用 {exact(free.get('tokens'))} tokens；"
        f"活跃可映射来源 {free.get('mapped_sources',0)} 个",
    ]
    derived=c.get("derived") or {}
    for source,label in (("openrouter","OpenRouter免费模型"),
                         ("modelscope","ModelScope免费体验")):
        item=derived.get(source)
        if item and item.get("increment",0)>0:
            lines.append(f"  {label}补算：{compact(item['increment'])}/月（极乐观满上下文）")
    if snapshot.get("rate_only_throughput_30d"):
        lines.append(f"另有限频可续用的公益池：{len(c.get('rate_only_estimates') or {})} 个；"
                     "按满窗口连续调用计算吞吐，未当成余额累加")
    if detail:
        lines.extend(["", "计算依据（同一共享池可能在模型总额内重复）"])
        lines.append(
            f"  FreeLLM原生逐模型预算：{exact(free.get('native_model_monthly'))} tokens/月；"
            f"共享池去重：{exact(free.get('native_pool_dedup_monthly'))} tokens/月；"
            f"活跃模型 {c.get('model_count',0)} 个"
        )
        lines.append(
            f"  WorkBuddy当前{wb.get('credit_balance') or '未知'} credit已包含体验包、运营赠送包和免费订阅；"
            f"未来30天签到预计再领{wb['credit_future30']} credit，"
            f"按{wb['price_basis']}换算 {Decimal(wb['rate_credit_per_m']):.2f} credit/百万 token"
        )
        for source,v in sorted((c.get("sources") or {}).items(),
                               key=lambda pair: pair[1].get("monthly_optimistic",0),reverse=True):
            if v["monthly_optimistic"]<=0:
                continue
            suffix=(f"（额外补 {compact(v['extra_monthly'])}）"
                    if v["extra_monthly"] else "")
            lines.append(f"  {source}：月名义 {compact(v['nominal_monthly'])} → "
                         f"乐观 {compact(v['monthly_optimistic'])}{suffix}")
        for source, data in sorted(derived.items()):
            lines.append("  推算：" + str(data.get("basis") or source))
        if free.get("renewable_daily"):
            lines.append("  明确日限额："+"、".join(
                f"{k} {compact(v)}/天" for k,v in sorted(free["renewable_daily"].items())
            ))
        if free.get("rate_only_monthly_throughput"):
            lines.append(
                f"  仅限频池24×7满上下文理论吞吐：{compact(free['rate_only_monthly_throughput'])}/30天"
                "（另计，不当作储值）"
            )
            for source,data in sorted((c.get("rate_only_estimates") or {}).items()):
                lines.append(
                    f"    {source} {data['basis']} × {data['largest_context']:,} 上下文 ≈ "
                    f"{compact(data['monthly'])}/30天"
                )
        if snapshot.get("conditional_30d") is not None and (
                snapshot["conditional_30d"] > (month or 0)):
            lines.append(
                f"  如果FreeLLM所用OpenRouter密钥拥有充值后1000次/天免费请求资格，"
                f"30天条件上界 ≈ {compact(snapshot['conditional_30d'])} tokens"
                "（该密钥资格尚未核验）"
            )
        if free.get("unpriced_credit"):
            lines.append("  积分换算尚未核实：" + "、".join(sorted(free["unpriced_credit"])))
        if free.get("unmapped"):
            lines.append("  已配置但无模型映射：" + "、".join(sorted(free["unmapped"])))
        if free.get("unavailable_charity"):
            lines.append("  失效公益站：" + "、".join(sorted(free["unavailable_charity"])))
        lines.append("  FreeLLM→WorkBuddy的请求只归WorkBuddy计数；付费DeepSeek/OpenRouter均未列入")
    if snapshot["unreadable"]:
        lines.append("部分账本不可读，只显示已知用量：" + "、".join(snapshot["unreadable"]))
    lines.append("注：乐观总量包含共享模型额度的重复展示和满上下文推算；"
                 "续领、限流、调用长度及账户有效性会影响真实可用量。")
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
