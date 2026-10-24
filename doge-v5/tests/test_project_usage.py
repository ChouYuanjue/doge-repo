from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"plugins"))
from doge_shared.project_usage import deployment_profile,configured_context


class DeploymentTokenProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.db=self.path/"data_v4.db"
        with sqlite3.connect(self.db) as c:
            c.execute("""CREATE TABLE provider_stats(
              provider_id TEXT,status TEXT,
              token_input_other INTEGER,
              token_input_cached INTEGER,token_output INTEGER,
              created_at TEXT)""")

    def add(self,provider,other,cached,out,days_ago=2,status="completed"):
        stamp=(datetime.now(timezone.utc)-timedelta(days=days_ago)).isoformat()
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO provider_stats VALUES(?,?,?,?,?,?)",
                      (provider,status,other,cached,out,stamp))

    def test_all_models_contribute_to_one_global_ratio_and_old_context_is_clamped(self):
        self.add("deepseek/deepseek-flash",100000,100000,40000)
        self.add("openrouter/paid-glm",3000,1000,1000)
        self.add("freellmapi/auto",6000,2000,2000)
        s=deployment_profile(self.db,context_limit=14000)
        self.assertEqual(s["requests"],3)
        self.assertAlmostEqual(s["avg_request_tokens"],(14000+5000+10000)/3,places=2)
        self.assertLessEqual(s["avg_request_tokens"],14000)
        self.assertAlmostEqual(s["input_share"]+s["output_share"],1,places=5)
        self.assertTrue(0<s["cached_input_share"]<1)

    def test_canceled_calls_not_used_and_rate_uses_full_deployment_age(self):
        self.add("deepseek",3000,0,1000,days_ago=20)
        self.add("openrouter",3000,0,1000,days_ago=10)
        self.add("volcengine",3000,0,1000,status="failed")
        s=deployment_profile(self.db,context_limit=14000)
        self.assertEqual(s["requests"],2)
        self.assertGreaterEqual(s["age_days"],19.5)
        self.assertLessEqual(s["requests_per_day"],0.11)

    def test_missing_db_is_empty_not_fabricated(self):
        s=deployment_profile(self.path/"no-file.db")
        self.assertFalse(s["available"])
        self.assertEqual(s["avg_request_tokens"],0)
        self.assertEqual(s["requests"],0)

    def test_current_config_uses_minimum_positive_text_context(self):
        path=self.path/"cmd_config.json"
        path.write_text(json.dumps({
            "provider":[
                {"max_context_tokens":14000},
                {"max_context_tokens":20000},
                {"max_context_tokens":0},
            ]
        }),encoding="utf-8")
        self.assertEqual(configured_context(path),14000)
        self.assertEqual(configured_context(self.path/"absent.json"),14000)

    def test_cache_share_is_clipped_with_same_scale_as_token_use(self):
        self.add("workbuddy",6000,9000,1000)
        s=deployment_profile(self.db,context_limit=14000)
        self.assertEqual(s["avg_request_tokens"],14000)
        self.assertAlmostEqual(s["input_share"],15/16,places=5)
        self.assertAlmostEqual(s["output_share"],1/16,places=5)
        self.assertAlmostEqual(s["cached_input_share"],9000/15000,places=5)


if __name__=="__main__":
    unittest.main()
