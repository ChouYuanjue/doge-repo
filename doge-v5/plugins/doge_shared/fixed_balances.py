"""Only non-renewing, verified balances for Doge's global token quota.

Public /quota never exposes amounts by account. Sources:
- User-confirmed balances in the bot's owner-only runtime data file.
- Verified credit/wallet snapshots already maintained by FreeLLMAPI.
- WorkBuddy cached free-account credits are handled by quota_ledger separately.

Do not read provider secrets, probe account endpoints, invent signup gifts,
or include paid official DeepSeek / paid OpenRouter balances.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
from typing import Any

# Cheapest published Volcengine Doubao Seed 2.0 Mini, low-priority text
# inference, prompt <=32k. Yuan per million uncached input, cached input,
# output. Current Doge context is capped at 14k.
VOLC_MINI_LOW_PRIORITY_CNY = ("0.10", "0.04", "1.00")
DEFAULT_RUNTIME_CONF = "plugin_data/doge_core/fixed_balances.json"
USD_WALLETS = frozenset({"xkiro", "orcarouter", "kilo"})
EXCLUDED = frozenset({"deepseek", "openrouter", "workbuddy"})


def decimal(value: Any) -> Decimal | None:
    try:
        val=Decimal(str(value))
        return val if val.is_finite() and val>=0 else None
    except (TypeError,ValueError,InvalidOperation):
        return None


def shares(profile: dict | None) -> tuple[Decimal,Decimal,Decimal]:
    profile=profile or {}
    inp=decimal(profile.get("input_share"))
    out=decimal(profile.get("output_share"))
    cache=decimal(profile.get("cached_input_share"))
    if inp is None or out is None or inp+out==0:
        inp,out=Decimal("0.92"),Decimal("0.08")
    else:
        total=inp+out
        inp,out=inp/total,out/total
    cache=min(Decimal(1),cache if cache is not None else Decimal("0.5"))
    return inp,out,cache


def blended_price(
    profile: dict | None, *,
    uncached: Decimal, cached: Decimal | None = None, output: Decimal
) -> Decimal:
    inp_share,out_share,c=shares(profile)
    cached_price=uncached if cached is None else cached
    return inp_share*(uncached*(1-c)+cached_price*c)+out_share*output


def credit_to_tokens(
    amount: Any,profile: dict | None, *,
    uncached: Any,cached: Any | None,output: Any
) -> int | None:
    money=decimal(amount)
    inp=decimal(uncached)
    out=decimal(output)
    cached_cost=decimal(cached) if cached is not None else None
    if money is None or inp is None or out is None:
        return None
    cost=blended_price(profile,uncached=inp,cached=cached_cost,output=out)
    return int(money*Decimal(1_000_000)/cost) if cost>0 else None


def manual_balances(path: Path) -> dict[str,dict]:
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return {}
    if not isinstance(obj,dict) or obj.get("schema")!=1:
        return {}
    result={}
    values=obj.get("balances") or {}
    if not isinstance(values,dict):
        return {}
    for name,row in values.items():
        if name in EXCLUDED or not isinstance(row,dict):
            continue
        currency=row.get("currency")
        amount=decimal(row.get("amount"))
        if amount is None or currency not in ("CNY","USD"):
            continue
        result[name]={"amount":amount,"currency":currency,"rate":row.get("price_per_m")}
    return result


def lowest_priced_text(free_db: Path,platform: str,profile: dict | None) -> tuple[Decimal,str] | None:
    try:
        with closing(sqlite3.connect(f"file:{free_db}?mode=ro",uri=True,timeout=1.5)) as con:
            rows=con.execute(
                "SELECT model_id,paid_input_per_m,paid_output_per_m "
                "FROM models WHERE platform=? AND enabled=1",(platform,)
            ).fetchall()
    except (sqlite3.Error,OSError):
        return None
    choices=[]
    for mid,inp,out in rows:
        if str(mid or "").endswith(":free"):
            continue
        a,b=decimal(inp),decimal(out)
        if a is None or b is None or a<=0 or b<=0:
            continue
        blended=blended_price(profile,uncached=a,output=b)
        if blended>0:
            choices.append((blended,str(mid)))
    return min(choices,key=lambda v:v[0]) if choices else None


def snapshots(free_db: Path,profile: dict | None) -> tuple[list[dict],list[str]]:
    """Only wallet/credit metrics with an authoritative recorded remaining.

    Rate-limit request counters and rolling/renewing monthly grants are
    excluded. Provider quota snapshot values must be linked to the official
    credential/account, not free quota or unlimited authorization sentinels.
    """
    try:
        with closing(sqlite3.connect(f"file:{free_db}?mode=ro",uri=True,timeout=1.5)) as con:
            rows=con.execute("""
                SELECT platform,quota_pool_key,metric,remaining_value,
                       reset_at,reset_strategy,source,confidence
                  FROM provider_quota_state
                 WHERE metric IN ('wallet_usd','balance_usd','wallet','credits')
                   AND remaining_value IS NOT NULL
            """).fetchall()
            active={r[0] for r in con.execute(
                "SELECT DISTINCT platform FROM api_keys "
                "WHERE enabled=1 AND status IN ('healthy','unknown')"
            )}
    except (sqlite3.Error,OSError):
        return [],[]
    seen=set()
    fixed=[]
    for platform,pool,metric,remain,reset_at,reset_strategy,origin,confidence in rows:
        if platform not in active or platform in EXCLUDED or platform not in USD_WALLETS:
            continue
        if origin not in ("quota_api","provider_reported","manual"):
            continue
        if metric not in ("wallet_usd","balance_usd"):
            continue   # provider-specific 'credits' may not equal USD
        if reset_at is not None and str(reset_at).strip():
            continue   # renewing allowance, not one-off stored credit
        amount=decimal(remain)
        if amount is None or amount>Decimal(1_000_000):
            continue  # unreachable / unlimited or malformed sentinel
        key=(platform,pool or "shared")
        if key in seen:
            continue
        cost=lowest_priced_text(free_db,platform,profile)
        if cost is None:
            continue
        rate,_=cost
        seen.add(key)
        fixed.append({
            "provider":platform,"amount":str(amount),"currency":"USD",
            "remaining_tokens":int(amount*Decimal(1_000_000)/rate),
            "basis":"官方余额快照，按平台最低非零文本价格",
            "verified":True,
        })
    return fixed,sorted(active & USD_WALLETS)


def collect_fixed_balances(
    data_dir: Path,free_db: Path,profile: dict | None,
    *,manual_path: Path | None=None,
) -> dict:
    configured=manual_balances(manual_path or data_dir/DEFAULT_RUNTIME_CONF)
    result=[]
    for name,entry in configured.items():
        amount,currency=entry["amount"],entry["currency"]
        if name=="volcengine":
            if currency!="CNY":
                continue
            rate=dict(uncached=VOLC_MINI_LOW_PRIORITY_CNY[0],
                      cached=VOLC_MINI_LOW_PRIORITY_CNY[1],
                      output=VOLC_MINI_LOW_PRIORITY_CNY[2])
            value=credit_to_tokens(amount,profile,**rate)
            basis="用户确认人民币余额，豆包Mini最低低优先级价格"
        else:
            val=entry.get("rate")
            if isinstance(val,dict):
                value=credit_to_tokens(
                    amount,profile,uncached=val.get("uncached"),
                    cached=val.get("cached"),output=val.get("output")
                )
            elif currency=="USD":
                price=lowest_priced_text(free_db,name,profile)
                value=int(amount*Decimal(1_000_000)/price[0]) if price else None
            else:
                value=None  # never use USD model prices to convert CNY
            basis="用户确认余额，站点最低可用模型"
        if value is not None:
            result.append(dict(
                provider=name,currency=currency,amount=str(amount),
                remaining_tokens=value,basis=basis,verified=True
            ))
    cached,active=snapshots(free_db,profile)
    already={x["provider"] for x in result}
    result.extend(x for x in cached if x["provider"] not in already)
    unverified=[p for p in active if p not in {x["provider"] for x in result}]
    volc=next((x["remaining_tokens"] for x in result if x["provider"]=="volcengine"),None)
    return dict(sources=result,
                extra_tokens=sum(x["remaining_tokens"] for x in result),
                unverified_sources=unverified,
                volcengine_tokens=volc)
