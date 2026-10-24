from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from doge_shared.official_balances import collect_official_balances, _query


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


if __name__ == "__main__":
    unittest.main()
