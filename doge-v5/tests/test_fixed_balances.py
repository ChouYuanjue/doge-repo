from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"plugins"))
from doge_shared.fixed_balances import (
    blended_price,credit_to_tokens,collect_fixed_balances,
    manual_balances,snapshots,lowest_priced_text
)


class FixedBalanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=self.root/"free.db"
        self.manual=self.root/"manual.json"
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE models(platform TEXT,model_id TEXT,enabled INT,
                   paid_input_per_m REAL,paid_output_per_m REAL);
                CREATE TABLE api_keys(platform TEXT,enabled INT,status TEXT);
                CREATE TABLE provider_quota_state(
                   platform TEXT,quota_pool_key TEXT,metric TEXT,
                   remaining_value REAL,reset_at TEXT,reset_strategy TEXT,
                   source TEXT,confidence TEXT);
            """)
        self.profile=dict(input_share=0.985632,output_share=0.014368,
                          cached_input_share=0.655758,context_limit=14000)

    def config(self,values):
        self.manual.write_text(json.dumps(
            {"schema":1,"balances":values},ensure_ascii=False
        ),encoding="utf-8")

    def test_volc_user_confirmed_cny_is_converted_with_global_real_shares(self):
        self.config({"volcengine":{"currency":"CNY","amount":"20"}})
        s=collect_fixed_balances(self.root,self.db,self.profile,manual_path=self.manual)
        self.assertEqual(len(s["sources"]),1)
        self.assertEqual(s["sources"][0]["amount"],"20")
        self.assertEqual(s["volcengine_tokens"],269719765)
        self.assertEqual(s["extra_tokens"],269719765)

    def test_volc_does_not_assume_the_old_one_time_500k_grant(self):
        s=collect_fixed_balances(self.root,self.db,self.profile,manual_path=self.manual)
        self.assertEqual(s["extra_tokens"],0)
        self.assertIsNone(s["volcengine_tokens"])

    def test_official_ds_and_openrouter_even_if_provided_are_excluded(self):
        self.config({
            "volcengine":{"currency":"CNY","amount":"20"},
            "deepseek":{"currency":"CNY","amount":"90000"},
            "openrouter":{"currency":"USD","amount":"90000"},
            "workbuddy":{"currency":"USD","amount":"90000"},
        })
        s=collect_fixed_balances(self.root,self.db,self.profile,manual_path=self.manual)
        self.assertEqual([v["provider"] for v in s["sources"]],["volcengine"])

    def test_cheapest_nonzero_model_uses_overall_input_output_shares(self):
        with sqlite3.connect(self.db) as con:
            con.executemany("INSERT INTO models VALUES(?,?,?,?,?)",[
                ("xkiro","free:free",1,0,0),
                ("xkiro","expensive",1,0.9,3),
                ("xkiro","cheap",1,0.2,0.6),
                ("xkiro","disabled",0,0.01,0.02),
            ])
        result=lowest_priced_text(self.db,"xkiro",self.profile)
        self.assertEqual(result[1],"cheap")
        expected=blended_price(self.profile,uncached=__import__("decimal").Decimal("0.2"),
                               output=__import__("decimal").Decimal("0.6"))
        self.assertAlmostEqual(float(result[0]),float(expected),places=7)

    def test_verified_usd_wallet_is_included_with_no_shared_key_double_count(self):
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO models VALUES('xkiro','cheap',1,0.2,0.6)")
            con.execute("INSERT INTO api_keys VALUES('xkiro',1,'healthy')")
            for _ in range(2):
                con.execute("INSERT INTO provider_quota_state VALUES(?,?,?,?,?,?,?,?)",
                            ("xkiro","xkiro::account","wallet_usd",7.0,None,
                             "none","quota_api","high"))
            con.execute("INSERT INTO provider_quota_state VALUES(?,?,?,?,?,?,?,?)",
                        ("openrouter","paid","wallet_usd",120.0,None,
                         "none","quota_api","high"))
        result=collect_fixed_balances(self.root,self.db,self.profile,manual_path=self.manual)
        self.assertEqual(len(result["sources"]),1)
        self.assertEqual(result["sources"][0]["provider"],"xkiro")
        self.assertEqual(result["sources"][0]["amount"],"7.0")

    def test_renewing_grants_and_unpriced_credit_units_are_not_one_off_cash(self):
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO models VALUES('xkiro','cheap',1,0.2,0.6)")
            con.execute("INSERT INTO api_keys VALUES('xkiro',1,'healthy')")
            con.executemany("INSERT INTO provider_quota_state VALUES(?,?,?,?,?,?,?,?)",[
                ("xkiro","pool","wallet_usd",7.0,"2026-11-01T00:00:00Z",
                 "provider_reported","quota_api","high"),
                ("xkiro","other","credits",100,None,"none","quota_api","high"),
                ("xkiro","probe","wallet_usd",500,None,"none","probe","none"),
            ])
        data=collect_fixed_balances(self.root,self.db,self.profile,manual_path=self.manual)
        self.assertEqual(data["extra_tokens"],0)
        self.assertIn("xkiro",data["unverified_sources"])

    def test_external_manual_amount_overrides_same_provider_snapshot(self):
        self.config({"xkiro":{"amount":"5","currency":"USD"}})
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO models VALUES('xkiro','cheap',1,0.2,0.6)")
            con.execute("INSERT INTO api_keys VALUES('xkiro',1,'healthy')")
            con.execute("INSERT INTO provider_quota_state VALUES(?,?,?,?,?,?,?,?)",
                        ("xkiro","xkiro::account","balance_usd",7,None,
                         "none","quota_api","high"))
        data=collect_fixed_balances(self.root,self.db,self.profile,manual_path=self.manual)
        self.assertEqual(len(data["sources"]),1)
        self.assertEqual(data["sources"][0]["amount"],"5")

    def test_foreign_currency_requires_compatible_explicit_price(self):
        self.config({"xkiro":{"amount":"12","currency":"CNY"}})
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO models VALUES('xkiro','cheap',1,0.2,0.6)")
        self.assertEqual(collect_fixed_balances(
            self.root,self.db,self.profile,manual_path=self.manual)["extra_tokens"],0)

    def test_invalid_manual_schema_ignored(self):
        self.manual.write_text('{"schema": 99, "balances":{"volcengine":{"currency":"CNY","amount":"999"}}}')
        self.assertEqual(manual_balances(self.manual),{})


if __name__=="__main__":
    unittest.main()
