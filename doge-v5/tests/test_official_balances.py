from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from doge_shared.official_balances import (
    BackgroundOfficialBalances, collect_official_balances, _query,
)


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=-1):
        return self.body[:n]


class OfficialBalanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "cmd_config.json"
        self.path.write_text(json.dumps({
            "provider_sources": [
                {"id": "deepseek", "enable": True,
                 "api_base": "https://api.deepseek.com/v1", "key": ["deepseek-secret"]},
                {"id": "openrouter", "enable": True,
                 "api_base": "https://openrouter.ai/api/v1", "key": ["openrouter-secret"]},
            ],
        }), encoding="utf-8")

    def test_fetch_both_official_balances_real_time_and_no_leaked_keys(self):
        counts = []

        def fake_urlopen(req, timeout):
            counts.append(req.full_url)
            self.assertTrue(req.get_header("Authorization").startswith("Bearer "))
            if "deepseek.com" in req.full_url:
                return FakeResponse({
                    "is_available": True,
                    "balance_infos": [{
                        "currency": "CNY",
                        "total_balance": "17.64",
                        "granted_balance": "0.96",
                        "topped_up_balance": "16.67",
                    }],
                })
            return FakeResponse({
                "data": {"total_credits": 148.16,
                         "total_usage": fake_urlopen.openrouter_used},
            })
        fake_urlopen.openrouter_used = 140.816043895

        with patch("doge_shared.official_balances.request.urlopen", side_effect=fake_urlopen):
            first = collect_official_balances(self.path)
            self.assertEqual(first["providers"]["deepseek"]["amount"], "17.64")
            self.assertEqual(first["providers"]["openrouter"]["amount"], "7.343956105")
            self.assertIn("checked_at", first)
            fake_urlopen.openrouter_used = 145.16
            second = collect_official_balances(self.path)
        self.assertEqual(second["providers"]["openrouter"]["amount"], "3.00")
        self.assertEqual(len(counts), 4)
        self.assertNotIn("secret", str(first))
        self.assertNotIn("secret", str(second))
        self.assertNotIn("api_key", str(second))

    def test_invalid_and_unavailable_balances_not_invented(self):
        with patch("doge_shared.official_balances.request.urlopen",
                   side_effect=HTTPError("url", 401, "denied", {}, None)):
            response = collect_official_balances(self.path)
        self.assertEqual(response["providers"]["deepseek"], {"status": "HTTP 401"})
        self.assertEqual(response["providers"]["openrouter"], {"status": "HTTP 401"})

    def test_missing_keys_and_nonofficial_host_fail_closed(self):
        self.path.write_text(json.dumps({"provider_sources": [
            {"id": "deepseek", "enable": True, "key": "secret",
             "api_base": "https://api.deepseek.com.attacker.com/v1"},
        ]}), encoding="utf-8")
        with patch("doge_shared.official_balances.request.urlopen") as called:
            out = collect_official_balances(self.path)
        called.assert_not_called()
        self.assertEqual(out["providers"]["deepseek"]["status"], "未配置")

    def test_malformed_official_payload_does_not_conjure_money(self):
        with patch("doge_shared.official_balances.request.urlopen",
                   return_value=FakeResponse({"data": {"total_credits": "NaN"}})):
            self.assertEqual(_query("openrouter", "secret")["status"], "响应无效")

    def test_background_wallet_refresh_nonblocking_coalesced_and_updated(self):
        entered = Event()
        release = Event()
        result_ready = Event()
        calls = []

        def fetch(_path):
            calls.append(1)
            entered.set()
            if len(calls) == 1:
                release.wait(2)
            result_ready.set()
            return {"providers": {
                "deepseek": {"status": "ok", "amount": str(len(calls)),
                             "currency": "CNY"},
                "openrouter": {"status": "ok", "amount": "7.34",
                               "currency": "USD"},
            }, "checked_at": "now"}

        cache = BackgroundOfficialBalances(
            self.path, min_interval=0.2, cold_wait=0.02, fetch=fetch,
        )
        started = time.perf_counter()
        first = cache.snapshot()
        self.assertLess(time.perf_counter() - started, 0.15)
        self.assertTrue(entered.wait(1))
        self.assertEqual(first["providers"]["deepseek"]["status"], "查询中")
        for _ in range(6):
            cache.snapshot()
        self.assertEqual(len(calls), 1)  # Single flight while HTTPS is slow.
        release.set()
        self.assertTrue(result_ready.wait(1))
        for _ in range(100):
            value = cache.snapshot()
            if value["providers"]["deepseek"].get("amount") == "1":
                break
            time.sleep(.005)
        self.assertEqual(value["providers"]["deepseek"]["amount"], "1")
        time.sleep(.21)
        started = time.perf_counter()
        previous = cache.snapshot()
        self.assertLess(time.perf_counter() - started, 0.15)
        self.assertIn(previous["providers"]["deepseek"]["amount"], ("1", "2"))
        for _ in range(100):
            value = cache.snapshot()
            if value["providers"]["deepseek"].get("amount") == "2":
                break
            time.sleep(.005)
        self.assertEqual(value["providers"]["deepseek"]["amount"], "2")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("secret", str(value))

    def test_config_change_invalidates_wallet_without_leaking_old_account(self):
        old_started, old_release, new_done = Event(), Event(), Event()

        def fetch(path):
            content = path.read_text(encoding="utf-8")
            if "old-account" in content:
                old_started.set()
                old_release.wait(2)
                amount = "42.00"
            else:
                amount = "13.00"
                new_done.set()
            return {"providers": {
                "deepseek": {"status": "ok", "amount": amount,
                             "currency": "CNY"},
                "openrouter": {"status": "未配置"},
            }, "checked_at": "now"}

        self.path.write_text("old-account", encoding="utf-8")
        cache = BackgroundOfficialBalances(
            self.path, min_interval=1, cold_wait=0.01, fetch=fetch,
        )
        cache.prefetch()
        self.assertTrue(old_started.wait(1))
        self.path.write_text("new-account-with-different-length", encoding="utf-8")
        value = cache.snapshot()
        self.assertNotEqual(value["providers"]["deepseek"].get("amount"), "42.00")
        self.assertTrue(new_done.wait(1))
        old_release.set()
        for _ in range(100):
            value = cache.snapshot()
            if value["providers"]["deepseek"].get("amount") == "13.00":
                break
            time.sleep(.005)
        self.assertEqual(value["providers"]["deepseek"]["amount"], "13.00")

    def test_old_wallet_result_is_marked_refreshing_without_blocking(self):
        def fetch(_path):
            return {"providers": {
                "deepseek": {"status": "ok", "amount": "12.50", "currency": "CNY"},
                "openrouter": {"status": "暂不可查"},
            }, "checked_at": "now"}

        cache = BackgroundOfficialBalances(
            self.path, min_interval=60, cold_wait=0.1,
            stale_after=0.01, fetch=fetch,
        )
        cache.prefetch()
        for _ in range(100):
            value = cache.snapshot()
            if value["providers"]["deepseek"].get("status") == "ok":
                break
            time.sleep(.005)
        self.assertEqual(value["providers"]["deepseek"]["amount"], "12.50")
        time.sleep(.02)
        previous = cache.snapshot()
        self.assertTrue(previous["providers"]["deepseek"].get("stale"))
        from doge_shared.quota_ledger import _money
        self.assertEqual(_money(previous["providers"]["deepseek"]),
                         "¥12.50（刷新中）")
        self.assertNotIn("stale",previous["providers"]["openrouter"])


if __name__ == "__main__":
    unittest.main()
