"""Read live balances of the two official paid providers for /quota.

Keys come only from the locally configured AstrBot provider_sources; they are
used with fixed official HTTPS endpoints and are never logged, returned or
persisted. No paid balance is included in renewable/free-token estimates.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from threading import Event, Lock, Thread
import time
from typing import Callable
from urllib import error, request
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Shanghai")
_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/user/balance",
    "openrouter": "https://openrouter.ai/api/v1/credits",
}


def money(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        return None
    return result if result.is_finite() and abs(result) < 1_000_000_000 else None


def _query(provider: str, key: str) -> dict:
    """Return only numerical balance fields; never return body or credentials."""
    req = request.Request(
        _ENDPOINTS[provider],
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "DogeQuota/1.0",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=4) as response:
            if response.status != 200:
                return {"status": "不可查"}
            body = json.loads(response.read(50_000))
    except error.HTTPError as exc:
        return {"status": f"HTTP {exc.code}"}
    except (error.URLError, TimeoutError, OSError, ValueError, TypeError):
        return {"status": "暂不可查"}

    if not isinstance(body, dict):
        return {"status": "响应无效"}

    if provider == "deepseek":
        balances = body.get("balance_infos")
        if not isinstance(balances, list):
            return {"status": "响应无效"}
        for currency in ("CNY", "USD"):
            for item in balances:
                if isinstance(item, dict) and item.get("currency") == currency:
                    amount = money(item.get("total_balance"))
                    if amount is not None:
                        gift = money(item.get("granted_balance"))
                        return {
                            "status": "ok",
                            "amount": str(amount),
                            "currency": currency,
                            "granted": str(gift) if gift is not None else None,
                        }
        return {"status": "响应无效"}

    data = body.get("data")
    if not isinstance(data, dict):
        return {"status": "响应无效"}
    total, used = money(data.get("total_credits")), money(data.get("total_usage"))
    if total is None or used is None:
        return {"status": "响应无效"}
    return {"status": "ok", "amount": str(total - used), "currency": "USD"}


def _configured_keys(path: Path) -> dict[str, str]:
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    if not isinstance(config, dict):
        return {}
    result = {}
    for source in config.get("provider_sources", []):
        if not isinstance(source, dict) or not source.get("enable", True):
            continue
        provider = str(source.get("id", "")).lower()
        if provider not in _ENDPOINTS:
            continue
        api_base = str(source.get("api_base", ""))
        if provider == "deepseek" and not api_base.startswith("https://api.deepseek.com/"):
            continue
        if provider == "openrouter" and not api_base.startswith("https://openrouter.ai/"):
            continue
        keys = source.get("key")
        if isinstance(keys, list):
            keys = next((k for k in keys if isinstance(k, str) and k.strip()), None)
        if isinstance(keys, str) and keys.strip():
            result[provider] = keys.strip()
    return result


def _fresh(path: Path) -> dict:
    keys = _configured_keys(path)
    rows: dict[str, dict] = {
        provider: {"status": "未配置"} for provider in _ENDPOINTS
    }
    if keys:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {provider: pool.submit(_query, provider, key)
                       for provider, key in keys.items()}
            for provider, future in futures.items():
                try:
                    rows[provider] = future.result()
                except Exception:
                    rows[provider] = {"status": "暂不可查"}
    return {
        "providers": rows,
        "checked_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
    }


def collect_official_balances(path: Path, *, refresh: bool = False) -> dict:
    """Synchronous authoritative official read for tests and refresh worker."""
    return _fresh(Path(path))


class BackgroundOfficialBalances:
    """Single-flight wallet refresh; never let HTTPS block a quota response.

    Only parsed monetary balances are retained. Every read can initiate an
    asynchronous refresh, while repeated calls share its result. Local token
    accounting remains fully live and independent of this short-lived cache.
    """

    def __init__(
        self, path: Path, *,
        min_interval: float = 5.0,
        cold_wait: float = 0.15,
        stale_after: float = 60.0,
        fetch: Callable[[Path], dict] | None = None,
    ):
        self.path = Path(path)
        self.min_interval = max(0.0, min_interval)
        self.cold_wait = max(0.0, cold_wait)
        self.stale_after = max(0.0, stale_after)
        self._fetch = fetch or collect_official_balances
        self._lock = Lock()
        self._event = Event()
        self._version: tuple[int, int] | None = None
        self._generation = 0
        self._inflight: int | None = None
        self._last_launch = float("-inf")
        self._last: dict | None = None
        self._last_at = 0.0

    def _file_version(self) -> tuple[int, int] | None:
        try:
            s = self.path.stat()
            return s.st_mtime_ns, s.st_size
        except OSError:
            return None

    def prefetch(self) -> None:
        version = self._file_version()
        with self._lock:
            if version != self._version:
                self._version = version
                self._generation += 1
                self._last = None
                self._last_at = 0.0
                self._last_launch = float("-inf")
                self._event = Event()
            now = time.monotonic()
            generation = self._generation
            if (self._inflight == generation or
                    now - self._last_launch < self.min_interval):
                return
            self._last_launch = now
            self._inflight = generation
            event = self._event
        Thread(
            target=self._refresh, args=(generation, event),
            name="doge-quota-wallet-refresh", daemon=True,
        ).start()

    def _refresh(self, generation: int, event: Event) -> None:
        try:
            result = self._fetch(self.path)
        except Exception:
            result = {
                "providers": {name: {"status": "暂不可查"} for name in _ENDPOINTS},
                "checked_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
            }
        with self._lock:
            if generation != self._generation:
                return  # Discard another account's response after config switch.
            self._last = result
            self._last_at = time.monotonic()
            self._inflight = None
            event.set()

    def snapshot(self) -> dict:
        self.prefetch()
        with self._lock:
            event = self._event
            ready = self._last is not None
        if not ready:
            event.wait(self.cold_wait)
        with self._lock:
            if self._last is None:
                return {
                    "providers": {name: {"status": "查询中"} for name in _ENDPOINTS},
                    "checked_at": None,
                }
            result = deepcopy(self._last)
            if time.monotonic() - self._last_at > self.stale_after:
                for row in result.get("providers", {}).values():
                    if row.get("status") == "ok":
                        row["stale"] = True
            return result
