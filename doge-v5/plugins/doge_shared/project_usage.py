"""Global token-use profile from the bot's entire deployment history.

No model-specific ratios. Clamp individual historical runs to the *current*
bot context budget before averaging: previous runs sometimes carried much
longer contexts, which must not inflate future request-limit conversions.
Input, output and cache ratios are derived from the same clipped sample.
No message bodies, user IDs or provider credentials are read.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

BOT_TIMEZONE = ZoneInfo("Asia/Shanghai")


def period_flags(value: object, *, now: datetime | None = None,
                 naive_tz=BOT_TIMEZONE) -> tuple[bool, bool]:
    """Current calendar month and trailing seven days, in the bot's timezone."""
    now = now or datetime.now(BOT_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BOT_TIMEZONE)
    now = now.astimezone(BOT_TIMEZONE)
    if value is None:
        return False, False
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            if stamp > 1e11:
                stamp /= 1000
            dt = datetime.fromtimestamp(stamp, BOT_TIMEZONE)
        else:
            text = str(value)
            if text.replace(".", "", 1).isdigit():
                stamp = float(text)
                dt = datetime.fromtimestamp(stamp / 1000 if stamp > 1e11 else stamp,
                                            BOT_TIMEZONE)
            else:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=naive_tz)
                dt = dt.astimezone(BOT_TIMEZONE)
    except (TypeError, ValueError, OverflowError, OSError):
        return False, False
    return ((dt.year, dt.month) == (now.year, now.month),
            now - timedelta(days=7) <= dt <= now)


def actual_provider_usage(path: Path, *, now: datetime | None = None) -> dict | None:
    """Unclipped, observed AstrBot usage, excluding routes with separate ledgers.

    provider_stats records a model's uncached input, cached input and output.
    WorkBuddy and FreeLLMAPI are read from their own upstream request ledgers
    instead: adding their AstrBot provider_stats rows would double-count calls.
    """
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as db:
            rows = db.execute(
                """SELECT provider_id, token_input_other, token_input_cached,
                          token_output, created_at
                     FROM provider_stats WHERE status='completed'"""
            ).fetchall()
    except (OSError, sqlite3.Error):
        return None
    totals = dict(requests=0, tokens=0, input=0, cached=0, output=0,
                  month_tokens=0, week_tokens=0)
    for provider, other, cached, output, created in rows:
        origin = str(provider or "").split("/", 1)[0].lower()
        if origin in ("workbuddy", "freellmapi"):
            continue
        try:
            other = max(0, int(other or 0))
            cached = max(0, int(cached or 0))
            output = max(0, int(output or 0))
        except (ValueError, TypeError, OverflowError):
            continue
        tokens = other + cached + output
        if not tokens:
            continue
        totals["requests"] += 1
        totals["tokens"] += tokens
        totals["input"] += other + cached
        totals["cached"] += cached
        totals["output"] += output
        # AstrBot/SQLAlchemy stores naive provider_stats timestamps in UTC.
        this_month, this_week = period_flags(created, now=now, naive_tz=timezone.utc)
        if this_month:
            totals["month_tokens"] += tokens
        if this_week:
            totals["week_tokens"] += tokens
    return totals


def deployment_profile(path: Path, *, context_limit: int = 14000, now: float | None = None) -> dict:
    limit = max(1, int(context_limit))
    started = now or time.time()
    try:
        with sqlite3.connect(f"file:{path}?mode=ro",uri=True,timeout=2) as db:
            rows = db.execute(
                """SELECT token_input_other, token_input_cached, token_output, created_at
                     FROM provider_stats WHERE status='completed'"""
            ).fetchall()
    except (OSError,sqlite3.Error):
        rows=[]

    count=0
    input_tokens=0.0
    output_tokens=0.0
    cached_tokens=0.0
    first=None
    for other,cached,output,created in rows:
        try:
            other=max(0,int(other or 0))
            cached=max(0,int(cached or 0))
            output=max(0,int(output or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        total=other+cached+output
        if total == 0:continue
        factor=min(limit,total)/total
        input_tokens+=(other+cached)*factor
        output_tokens+=output*factor
        cached_tokens+=cached*factor
        count+=1
        try:
            dt=datetime.fromisoformat(str(created).replace("Z","+00:00"))
            if dt.tzinfo is None:
                dt=dt.replace(tzinfo=timezone.utc)
            stamp=dt.timestamp()
            first=stamp if first is None else min(first,stamp)
        except (ValueError,OverflowError):
            pass
    if count==0:
        return dict(requests=0,avg_request_tokens=0,context_limit=limit,
                    input_share=0,output_share=0,cached_input_share=0,
                    requests_per_day=0,age_days=0,available=False)
    tokens=input_tokens+output_tokens
    days=max(1.0,(started-first)/86400) if first is not None else 1.0
    return dict(
        requests=count,avg_request_tokens=round(tokens/count,2),
        context_limit=limit,
        input_share=round(input_tokens/tokens,6),
        output_share=round(output_tokens/tokens,6),
        cached_input_share=round(cached_tokens/input_tokens,6) if input_tokens else 0,
        requests_per_day=round(count/days,3),age_days=round(days,2),
        available=True,
    )


def configured_context(path: Path, *, default: int = 14000) -> int:
    """Read the live configured context cap, not catalog maximum windows.

    AstrBot's enabled text providers may carry several context limits; use
    the smallest positive one as the shared operational cap. Exclude visual
    providers with unbounded (zero) context and avoid model-level reporting.
    """
    import json
    try:
        config=json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError,ValueError):
        return default
    numbers=[]
    for provider in config.get("provider",[]):
        if not isinstance(provider,dict):
            continue
        value=provider.get("max_context_tokens")
        if isinstance(value,int) and value>=1000:
            numbers.append(value)
    return min(numbers) if numbers else default
