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
             "cached_tokens": 60, "total_tokens": 120, "credit": 0.12,
             "at": time.time()},
            {"model": "glm-5.3", "prompt_tokens": 50,
             "completion_tokens": 10, "total_tokens": 60, "credit": 0.3,
             "at": time.time()},
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

    def test_total_includes_actual_direct_provider_stats_without_double_counting(self):
        self._account("cn", remain=100, daily=100)
        self._account("intl", remain=200, realm="intl")
        self._activity()
        self._wb()
        self._free()
        with sqlite3.connect(self.data / "data_v4.db") as db:
            db.execute("""CREATE TABLE provider_stats(
                provider_id TEXT, status TEXT, token_input_other INTEGER,
                token_input_cached INTEGER, token_output INTEGER,
                created_at TEXT)""")
            stamp=datetime.now(timezone.utc).isoformat()
            db.executemany("INSERT INTO provider_stats VALUES(?,?,?,?,?,?)",[
                ("deepseek/deepseek-v4-flash", "completed", 100, 40, 10, stamp),
                ("openrouter/z-ai/glm-5-flash", "completed", 60, 20, 10, stamp),
                ("workbuddy/deepseek-v4.1-flash", "completed", 999, 0, 0, stamp),
                ("freellmapi/auto", "completed", 999, 0, 0, stamp),
                ("deepseek/deepseek-v4-flash", "aborted", 999, 0, 0, stamp),
            ])
        s = collect(self.data, free_db=self.free, wb_log=self.wb,
                    accounts_dir=self.accounts, activity_file=self.activity)
        self.assertEqual(s["used_total"], 355 + 240)
        self.assertEqual(s["used_month"], 355 + 240)
        self.assertEqual(s["used_week"], 355 + 240)
        self.assertEqual(s["usage_mix"]["cached_input_tokens"], 60 + 60)
        self.assertEqual(s["usage_mix"]["input_tokens"], 150 + 140 + 220)
        self.assertEqual(s["usage_mix"]["output_tokens"], 30 + 35 + 20)
        self.assertEqual(s["wb"]["credit_balance"], "300")
        self.assertEqual(s["wb"]["credit_future30"], "4500")
        self.assertEqual(s["free"]["remaining_today"], 1599875)
        self.assertGreaterEqual(s["forecast_30d"],
                                s["wb"]["additional_tokens_30d"] + 48000000)
        self.assertEqual(s["fixed_remaining"],s["wb"]["remaining_tokens_now"])
        self.assertEqual(s["fixed_volcengine"],None)
        report = render(s, detail=True)
        self.assertIn("历史总消耗：595 tokens", report)
        self.assertIn("每月免费额度：~", report)
        self.assertIn("一次性额度剩余：", report)
        self.assertNotIn("AnyRouter", report)
        self.assertNotIn("999", report)
        self.assertNotIn("secret-account", report)
        self.assertNotIn("very-secret", report)

    def test_each_invocation_recomputes_balance_and_forecast(self):
        self._account("cn", remain=100, daily=100)
        self._wb()
        self._free()
        ledger = QuotaLedger(self.data, free_db=self.free, wb_log=self.wb,
                             accounts_dir=self.accounts, activity_file=self.activity)
        one=ledger.display()
        self.assertNotIn("豆子", one)
        self._account("cn", remain=999, daily=100)
        two=ledger.display(detail=True)
        self.assertIn("999 credit", two)
        self.assertNotIn("100 credit", two)
        self.assertEqual(ledger.snapshot()["wb"]["credit_balance"],"999")

    def test_current_context_and_historical_mix_recalculate_each_time(self):
        self._account("cn",remain=100,daily=100)
        self._wb()
        self._free()
        fixed=self.data/"plugin_data/doge_core/fixed_balances.json"
        fixed.parent.mkdir(parents=True)
        fixed.write_text(json.dumps({"schema":1,"balances":{
            "volcengine":{"amount":"20","currency":"CNY"},
        }}))
        with sqlite3.connect(self.data/"data_v4.db") as db:
            db.execute("""CREATE TABLE provider_stats(
                provider_id TEXT,status TEXT,token_input_other INTEGER,
                token_input_cached INTEGER,token_output INTEGER,created_at TEXT)""")
            db.execute("INSERT INTO provider_stats VALUES(?,?,?,?,?,?)",
                ("deepseek/direct","completed",100_000,30_000,20_000,
                 datetime.now(timezone.utc).isoformat()))
        config=self.data/"cmd_config.json"
        config.write_text(json.dumps({"provider":[{"max_context_tokens":14000}]}))
        ledger=QuotaLedger(self.data,free_db=self.free,wb_log=self.wb,
                           accounts_dir=self.accounts,activity_file=self.activity)
        first=ledger.snapshot()
        self.assertEqual(first["project_profile"]["context_limit"],14000)
        config.write_text(json.dumps({"provider":[{"max_context_tokens":3000}]}))
        second=ledger.snapshot()
        self.assertEqual(second["project_profile"]["context_limit"],3000)
        self.assertLess(second["project_profile"]["avg_request_tokens"],
                        first["project_profile"]["avg_request_tokens"])
        self.assertLess(second["forecast_30d"],first["forecast_30d"])
        with sqlite3.connect(self.data/"data_v4.db") as db:
            db.execute("INSERT INTO provider_stats VALUES(?,?,?,?,?,?)",
                ("openrouter/direct","completed",3000,0,3000,
                 datetime.now(timezone.utc).isoformat()))
        third=ledger.snapshot()
        self.assertEqual(third["project_profile"]["requests"],2)
        self.assertNotEqual(third["project_profile"]["output_share"],
                            second["project_profile"]["output_share"])
        self.assertNotEqual(third["project_profile"]["cached_input_share"],
                            second["project_profile"]["cached_input_share"])
        self.assertNotEqual(third["used_total"], second["used_total"])
        self.assertNotEqual(third["fixed_remaining"], second["fixed_remaining"])
        self.assertIn(f"{100*third['project_profile']['cached_input_share']:.1f}%",
                      render(third))

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
        self.assertIn("历史总消耗：不可读 tokens", report)

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

    def test_volcengine_confirmed_cash_balance_in_fixed_only(self):
        from doge_shared.fixed_balances import credit_to_tokens,VOLC_MINI_LOW_PRIORITY_CNY
        self._account("cn",remain=110,daily=100)
        self._wb()
        self._free()
        config=self.data/"plugin_data/doge_core/fixed_balances.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"schema":1,"balances":{
            "volcengine":{"amount":"20","currency":"CNY"}}}),encoding="utf-8")
        s=collect(self.data,free_db=self.free,wb_log=self.wb,
                  accounts_dir=self.accounts,activity_file=self.activity)
        expected=credit_to_tokens(
            "20",s["project_profile"],
            uncached=VOLC_MINI_LOW_PRIORITY_CNY[0],
            cached=VOLC_MINI_LOW_PRIORITY_CNY[1],
            output=VOLC_MINI_LOW_PRIORITY_CNY[2]
        )
        self.assertEqual(s["fixed_volcengine"],expected)
        self.assertEqual(s["fixed_remaining"],s["wb"]["remaining_tokens_now"]+expected)
        self.assertEqual(s["used_total"],180+175)
        self.assertEqual(s["forecast_30d"],48000000+s["wb"]["additional_tokens_30d"])
        self.assertEqual(len(render(s).splitlines()),17)  # missing AstrBot ledger warning

    def test_short_quota_output_live_usage_ratios_balances_and_si_tokens(self):
        self._account("cn",remain=300,daily=100)
        self._wb()
        self._free()
        s=collect(self.data,free_db=self.free,wb_log=self.wb,
                  accounts_dir=self.accounts,activity_file=self.activity)
        content=render(s)
        lines=content.splitlines()
        self.assertEqual(len(lines),17)  # missing AstrBot ledger warning
        self.assertEqual(lines[4],"")
        self.assertEqual(lines[5],"历史比例：")
        self.assertTrue(lines[6].startswith("缓存命中率： "))
        self.assertTrue(lines[7].startswith("输入/输出： "))
        self.assertEqual(lines[8],"")
        self.assertEqual(lines[9],"免费模型额度：")
        self.assertEqual(lines[12],"")
        self.assertEqual(lines[13],"付费模型余额：")
        self.assertTrue(lines[14].startswith("DeepSeek： "))
        self.assertTrue(lines[15].startswith("OpenRouter： "))
        for name in ("本月消耗：","历史总消耗：","近7天消耗：",
                     "缓存命中率：","输入/输出：","每月免费额度：~","一次性额度剩余：~",
                     "DeepSeek：","OpenRouter："):
            self.assertIn(name,content)
        self.assertNotIn("豆子",content)
        self.assertNotIn("约",content)
        self.assertNotIn("亿",content)
        self.assertIn("M tokens",content)
        self.assertNotIn("单模型",content)
        self.assertNotIn("（输入内）",content)

    def test_registered_command_and_capability(self):
        op=match_invocation("/quota")
        self.assertIsNotNone(op)
        self.assertEqual(op.capability_id,"core.quota")
        self.assertEqual(match_invocation("/quota detail").capability_id,"core.quota")
        self.assertEqual(match_invocation("/quota what").capability_id,"core.quota")
        self.assertIn("quota",registry()["commands"])
        result=search_capabilities("查看模型额度剩余和已使用Token", 10)
        self.assertTrue(any(r["id"] == "core.quota" for r in result))
