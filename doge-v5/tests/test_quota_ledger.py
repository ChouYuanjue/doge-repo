from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from doge_shared.quota_ledger import (
    QuotaLedger, collect, compact, freeapi_pool, render, wblog,
    workbuddy_account_pool, workbuddy_price_basis,
)
from doge_shared.capabilities import match_invocation, registry, search_capabilities


class FreeQuotaLedgerTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.accounts = self.root / "accounts"
        self.accounts.mkdir()
        self.wb = self.root / "usage.jsonl"
        self.activity = self.root / "activity.jsonl"
        self.free = self.root / "free.db"
        self.data = self.root / "data"
        self.data.mkdir()

    def _account(self, name, *, remain=0, realm="cn", daily=100, enabled=True, paid=False):
        d = {
            "realm": realm, "enabled": enabled, "token": "very-secret",
            "credits": {
                "remain": remain, "used": 15, "is_paid_user": paid,
                "checkin": {"daily_credit": daily, "today_credit": daily, "active": True},
            },
        }
        (self.accounts / (name + ".json")).write_text(json.dumps(d), encoding="utf-8")

    def _activity(self, success=True, days_ago=0, *, realm="intl"):
        d = {
            "uid": "secret-account-id", "task": "daily_chat", "ok": success,
            "ts": datetime.fromtimestamp(time.time()-days_ago*86400,timezone.utc).isoformat(),
            "realm": realm,
        }
        self.activity.write_text(json.dumps(d) + "\n", encoding="utf-8")

    def _wb(self):
        rows = [
            {"model": "deepseek-v4.1-flash", "prompt_tokens": 100,
             "completion_tokens": 20, "reasoning_tokens": 18,
             "cached_tokens": 60, "total_tokens": 120, "credit": 0.12},
            {"model": "glm-5.3", "prompt_tokens": 50,
             "completion_tokens": 10, "total_tokens": 60, "credit": 0.3},
        ]
        self.wb.write_text("".join(json.dumps(x) + "\n" for x in rows)+"{\"incomplete\":",encoding="utf-8")

    def _free(self):
        with sqlite3.connect(self.free) as db:
            db.executescript("""
                CREATE TABLE api_keys(id INTEGER, platform TEXT, label TEXT,
                                      base_url TEXT, enabled INTEGER, status TEXT);
                CREATE TABLE models(platform TEXT, key_id INTEGER, model_id TEXT,
                                    enabled INTEGER, rpm_limit INTEGER,
                                    rpd_limit INTEGER, tpm_limit INTEGER,
                                    tpd_limit INTEGER, monthly_token_budget TEXT,
                                    paid_input_per_m REAL);
                CREATE TABLE requests(platform TEXT, key_id INTEGER, model_id TEXT,
                                      created_at TEXT, status TEXT,
                                      input_tokens INTEGER, output_tokens INTEGER);
            """)
            keys = [
                (1, "custom", "WorkBuddy local OAuth proxy", "http://127.0.0.1", 1, "healthy"),
                (2, "custom", "AnyRouter", "https://anyrouter.top/v1", 1, "healthy"),
                (3, "groq", "Groq", "", 1, "healthy"),
                (4, "llm7", "LLM7", "", 1, "healthy"),
                (5, "openrouter", "free only", "", 1, "healthy"),
                (6, "modelscope", "daily credit", "", 1, "healthy"),
                (7, "zhipu", "flash free", "", 1, "healthy"),
                (8, "kilo", "disabled", "", 0, "invalid"),
                (9, "custom", "AgentRouter", "https://co.agentrouter.org", 0, "invalid"),
            ]
            db.executemany("INSERT INTO api_keys VALUES(?,?,?,?,?,?)", keys)
            mods = [
                ("custom", 1, "deepseek-v4.1-flash", 1, 0, 0, 0, 0, ""),
                ("groq", None, "gpt-oss-20b", 1, 30, 1000, 0, 500000, "~15M"),
                ("llm7", None, "default", 1, 40, 0, 0, 0, "Free tier: 100,000 tokens/24h shared"),
                ("zhipu", None, "glm-4.7-flash", 1, 0, 0, 0, 1000000, "~30M"),
                ("openrouter", None, "model:free", 1, 20, 50, 0, 0, "50 req/day"),
                ("openrouter", None, "paid-model", 1, 20, 50, 0, 0, ""),
                ("modelscope", None, "qwen", 1, 0, 200, 0, 0, "Daily login: 200 credits"),
                ("kilo", None, "free-model", 1, 20, 200, 0, 0, ""),
            ]
            db.executemany(
                "INSERT INTO models VALUES(?,?,?,?,?,?,?,?,?,NULL)",mods
            )
            stamp = datetime.now(timezone.utc).isoformat()
            requests = [
                ("custom", 1, "deepseek-v4.1-flash", stamp, "success", 2000, 300), # double-count
                ("groq", 3, "gpt-oss-20b", stamp, "success", 100, 25),
                ("groq", 3, "gpt-oss-20b", stamp, "error", 9999, 9999),
                ("openrouter", 5, "model:free", stamp, "success", 40, 10),
                ("openrouter", 5, "paid-model", stamp, "success", 5000, 400),
            ]
            db.executemany("INSERT INTO requests VALUES(?,?,?,?,?,?,?)", requests)

    def test_workbuddy_two_free_accounts_and_daily_activity(self):
        self._account("cn", remain=300, daily=100)
        self._account("intl", remain=410, realm="intl")
        self._account("paid", remain=10000, paid=True)
        self._account("disabled", remain=10000, enabled=False)
        self._activity()
        pool = workbuddy_account_pool(self.accounts, self.activity)
        self.assertEqual(pool["balance"], 710)
        self.assertEqual(pool["free_accounts"], 2)
        self.assertEqual(pool["cn_daily"], 100)
        self.assertEqual(pool["intl_daily"], 50)
        self.assertEqual(pool["daily_bonus"], 150)
        self._activity(days_ago=11)
        self.assertEqual(workbuddy_account_pool(self.accounts, self.activity)["intl_daily"], 0)

    def test_workbuddy_no_double_count_reasoning_or_incomplete_line(self):
        self._wb()
        usage = wblog(self.wb)
        self.assertEqual(usage["requests"], 2)
        self.assertEqual(usage["tokens"], 180)  # includes reasoning within completion
        self.assertEqual(usage["cached"], 60)
        self.assertEqual(usage["flash_tokens"], 120)
        rate, basis = workbuddy_price_basis(usage)
        self.assertEqual(rate, 1000)
        self.assertIn("Flash", basis)

    def test_freeapi_rollup_ignores_paid_direct_and_duplicate_workbuddy(self):
        self._free()
        r = freeapi_pool(self.free)
        self.assertEqual(r["tokens"], 175)
        self.assertEqual(r["requests"], 2)
        self.assertEqual(r["by_provider"]["groq"]["last24h"], 125)
        self.assertEqual(r["renewable_daily"]["groq"], 500000)
        self.assertEqual(r["renewable_daily"]["llm7"], 100000)
        self.assertEqual(r["renewable_daily"]["zhipu"], 1000000)
        self.assertEqual(r["remaining_today"], 1600000-125)
        self.assertIn("AnyRouter", r["unmapped"])
        self.assertIn("AgentRouter", r["unavailable_charity"])
        self.assertNotIn("modelscope", r["rate_only"])
        self.assertIn("modelscope", r["unpriced_credit"])
        self.assertNotIn("kilo", r["rate_only"])  # disabled key
        self.assertEqual(r["forecast_30d"], 48000000)

    def test_total_is_lifetime_free_only_and_not_paid_provider_stats(self):
        self._account("cn", remain=100, daily=100)
        self._account("intl", remain=200, realm="intl")
        self._activity()
        self._wb()
        self._free()
        with sqlite3.connect(self.data / "data_v4.db") as db:
            db.execute("CREATE TABLE provider_stats(provider_id TEXT, token_input_other INTEGER)")
            db.execute("INSERT INTO provider_stats VALUES('deepseek/deepseek-v4-flash',999999999)")
        s = collect(self.data, free_db=self.free, wb_log=self.wb,
                    accounts_dir=self.accounts, activity_file=self.activity)
        self.assertEqual(s["used_total"], 355)
        self.assertEqual(s["wb"]["credit_balance"], "300")
        self.assertEqual(s["wb"]["credit_future30"], "4500")
        self.assertEqual(s["free"]["remaining_today"], 1599875)
        self.assertEqual(s["forecast_30d"],
                         s["wb"]["additional_tokens_30d"] + 48000000)
        self.assertEqual(s["fixed_remaining"],s["wb"]["remaining_tokens_now"])
        self.assertEqual(s["fixed_volcengine"],None)
        report = render(s, detail=True)
        self.assertIn("消耗：355 tokens", report)
        self.assertIn("每月预估：", report)
        self.assertIn("固定额度剩余：", report)
        self.assertNotIn("AnyRouter", report)
        self.assertNotIn("999999999", report)
        self.assertNotIn("secret-account", report)
        self.assertNotIn("very-secret", report)

    def test_cache_shared_for_public_and_detail_views(self):
        self._account("cn", remain=100, daily=100)
        self._wb()
        self._free()
        ledger = QuotaLedger(self.data, free_db=self.free, wb_log=self.wb,
                             accounts_dir=self.accounts, activity_file=self.activity)
        one=ledger.display()
        self.assertIn("豆子", one)
        self._account("cn", remain=999, daily=100)
        two=ledger.display(detail=True)
        self.assertIn("100 credit", two)
        self.assertNotIn("999 credit", two)
        self.assertEqual(ledger.snapshot(refresh=True)["wb"]["credit_balance"],"999")

    def test_bot_tool_can_read_public_total_but_avoids_private_detail(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import patch
        from doge_shared.agent_tools import DogeQuotaTool

        class FakeLedger:
            def display(self, *, detail=False):
                return "DETAIL:PRIVATE" if detail else "TOTAL:PUBLIC"

        tool = DogeQuotaTool()
        self.assertEqual(tool.name, "doge_quota")
        self.assertIn("detail", tool.parameters["properties"])
        user = SimpleNamespace(context=SimpleNamespace(event=SimpleNamespace(is_admin=lambda: False)))
        admin = SimpleNamespace(context=SimpleNamespace(event=SimpleNamespace(is_admin=lambda: True)))
        with patch("doge_shared.agent_tools.get_quota_ledger", return_value=FakeLedger()) as mock:
            self.assertEqual(asyncio.run(tool.call(user)), "TOTAL:PUBLIC")
            self.assertIn("仅管理员", asyncio.run(tool.call(user,detail=True)))
            self.assertEqual(asyncio.run(tool.call(admin,detail=True)), "DETAIL:PRIVATE")
            self.assertEqual(mock.call_count, 2)

    def test_report_survives_unavailable_gateway_data(self):
        from doge_shared.quota_ledger import render
        report=render(collect(self.data, free_db=self.free,
                               wb_log=self.wb, accounts_dir=self.accounts,
                               activity_file=self.activity))
        self.assertIn("部分账本不可读", report)
        self.assertIn("消耗：不可读 tokens", report)

    def test_freellm_monthly_only_includes_active_profile_models(self):
        self._free()
        with sqlite3.connect(self.free) as db:
            db.executescript("""
                CREATE TABLE settings(key TEXT,value TEXT);
                CREATE TABLE profile_models(profile_id INTEGER,model_db_id INTEGER);
                INSERT INTO settings VALUES('active_profile_id','1');
            """)
            groq_id = db.execute(
                "SELECT rowid FROM models WHERE platform='groq' LIMIT 1"
            ).fetchone()[0]
            db.execute("INSERT INTO profile_models VALUES(1,?)", (groq_id,))
        r = freeapi_pool(self.free)
        self.assertEqual(r["native_model_monthly"],15_000_000)
        self.assertEqual(r["native_pool_dedup_monthly"],15_000_000)
        self.assertEqual(r["forecast_30d"],15_000_000)
        self.assertEqual(r["tokens"],175)  # old successful routes still count

    def test_workbuddy_flash_price_uses_all_real_historical_samples(self):
        rows=[]
        for rate in range(2,22):
            # 100K tokens per call, rate/10 credit per request
            rows.append(dict(
                model="deepseek-v4.1-flash",prompt_tokens=90_000,
                completion_tokens=10_000,total_tokens=100_000,
                credit=rate/10,
            ))
        self.wb.write_text(
            "".join(json.dumps(x)+"\n" for x in rows),
            encoding="utf-8",
        )
        usage=wblog(self.wb)
        price, basis=workbuddy_price_basis(usage)
        self.assertEqual(price,11.5)
        self.assertIn("全部调用",basis)
        self.assertEqual(usage["flash_tokens"],2_000_000)

    def test_fixed_free_account_packs_not_added_twice_to_balance(self):
        self._account("fixed",remain=300,daily=100)
        data=json.loads((self.accounts/"fixed.json").read_text(encoding="utf-8"))
        data["credits"]["packages"]=[
            {"name":"Free Plan Subscription","remain":100,"size":100},
            {"name":"Bonus Pack","remain":200,"size":200},
        ]
        (self.accounts/"fixed.json").write_text(
            json.dumps(data),encoding="utf-8",
        )
        result=workbuddy_account_pool(self.accounts,self.activity)
        self.assertEqual(result["balance"],300)
        self.assertEqual(result["cn_daily"],100)

    def test_volcengine_one_time_grant_and_local_usage_only(self):
        self._account("cn",remain=110,daily=100)
        self._wb()
        self._free()
        with sqlite3.connect(self.free) as db:
            db.execute("INSERT INTO api_keys VALUES(?,?,?,?,?,?)",
                       (11,"volcengine","Ark new-user","",1,"healthy"))
            db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?)",
                       ("volcengine",11,"doubao",datetime.now(timezone.utc).isoformat(),
                        "success",10000,1000))
        s=collect(self.data,free_db=self.free,wb_log=self.wb,
                  accounts_dir=self.accounts,activity_file=self.activity)
        self.assertEqual(s["fixed_volcengine"],489_000)
        self.assertEqual(s["fixed_remaining"],s["wb"]["remaining_tokens_now"]+489_000)
        self.assertEqual(s["used_total"],180+175+11000)
        self.assertEqual(s["forecast_30d"],48000000+s["wb"]["additional_tokens_30d"])
        self.assertIn("火山",render(s))

    def test_short_quota_output_three_main_values_and_no_model_list(self):
        self._account("cn",remain=300,daily=100)
        self._wb()
        self._free()
        s=collect(self.data,free_db=self.free,wb_log=self.wb,
                  accounts_dir=self.accounts,activity_file=self.activity)
        content=render(s)
        self.assertEqual(len(content.splitlines()),4)
        for name in ("消耗：","每月预估：","固定额度剩余："):
            self.assertIn(name,content)
        self.assertNotIn("openrouter",content.lower())
        self.assertNotIn("单模型",content)

    def test_registered_command_and_capability(self):
        op=match_invocation("/quota")
        self.assertIsNotNone(op)
        self.assertEqual(op.capability_id,"core.quota")
        self.assertEqual(match_invocation("/quota detail").capability_id,"core.quota")
        self.assertEqual(match_invocation("/quota what").capability_id,"core.quota")
        self.assertIn("quota",registry()["commands"])
        result=search_capabilities("查看模型额度剩余和已使用Token", 10)
        self.assertTrue(any(r["id"] == "core.quota" for r in result))
