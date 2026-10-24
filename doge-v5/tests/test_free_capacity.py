"""Monthly capacity checks: native model catalog + global measured bot traffic."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"plugins"))
from doge_shared.free_capacity import estimate_capacity,parse_budget


def model(name,budget="",*,context=0,rpd=0,p_in=None,p_out=None):
    return dict(model_id=name,monthly_token_budget=budget,context_window=context,
                rpd_limit=rpd,paid_input_per_m=p_in,paid_output_per_m=p_out)


def source(platform,*models):
    return dict(platform=platform,models=list(models))


def profile(*,average=7000,daily=20,context=14000):
    return dict(avg_request_tokens=average,requests_per_day=daily,
                context_limit=context,input_share=0.92,output_share=0.08)


class RealisticFreeBudgetTests(unittest.TestCase):
    def test_native_label_parsing(self):
        for label,amount in [
            ("~50-100M",100_000_000),
            ("free · 1M tokens/day (permanently doubled)",30_000_000),
            ("free · 500K tokens/24h",15_000_000),
            ("~2-3M (200/hr)",3_000_000),
            ("~6M",6_000_000),
            ("free · 14.4K rpd",0),
            ("1K calls/mo shared",0),
            ("Free tier: 100,000 tokens/24h shared",0),
            ("free · 200/hr per IP",0),
            ("",0),
        ]:
            with self.subTest(label=label):
                self.assertEqual(parse_budget(label),amount)

    def test_catalog_monthly_total_without_model_level_outputs(self):
        data={
            "xkiro":source("xkiro",
                           model("a","free · 1M tokens/day"),
                           model("b","free · 1M tokens/day"),
                           model("c","free · 500K tokens/day")),
            "groq":source("groq",model("a","~6M"),model("b","~15M")),
            "openrouter":source("openrouter",model("a:free","~6M",context=1_000_000,rpd=50)),
        }
        s=estimate_capacity(data,{"xkiro":1,"groq":1,"openrouter":1},
                            profile=profile(daily=20))
        self.assertEqual(s["native_model_monthly"],102_000_000)
        self.assertEqual(s["native_pool_dedup_monthly"],51_000_000)
        self.assertEqual(s["forecast_30d"],102_000_000)
        self.assertNotIn("sources",s)

    def test_two_healthy_keys_are_two_allowances(self):
        s=estimate_capacity(
            {"groq":source("groq",model("a","~6M"),model("b","~15M"))},
            {"groq":2},profile=profile())
        self.assertEqual(s["native_model_monthly"],42_000_000)
        self.assertEqual(s["native_pool_dedup_monthly"],30_000_000)

    def test_openrouter_free_only_and_global_avg_not_1m_context(self):
        data={"openrouter":source("openrouter",
            model("free-small:free","~6M",context=256000,rpd=50),
            model("free-big:free","free · 50 req/day",context=1_048_576,rpd=50),
            model("paid-model","~900M",context=2_000_000,rpd=1000))}
        s=estimate_capacity(data,{"openrouter":1},profile=profile(average=9000,daily=35))
        self.assertEqual(s["native_model_monthly"],6_000_000)
        self.assertEqual(s["forecast_30d"],35*30*9000)
        self.assertLess(s["forecast_30d"],20_000_000)

    def test_global_requests_limit_and_context_clamp(self):
        d={"openrouter":source("openrouter",model("f:free",rpd=50))}
        s=estimate_capacity(d,{"openrouter":1},profile=profile(average=90_000,daily=100,context=14_000))
        self.assertEqual(s["forecast_30d"],50*30*14_000)

    def test_modelscope_is_at_most_global_demand(self):
        d={"modelscope":source("modelscope",model("qwen",rpd=200,context=2_000_000))}
        s=estimate_capacity(d,{"modelscope":1},profile=profile(average=5000,daily=12))
        self.assertEqual(s["forecast_30d"],12*30*5000)
        self.assertLess(s["forecast_30d"],200*30*5000)

    def test_mistral_cash_recurs_at_cheapest_blended_model_price(self):
        d={"mistral":source("mistral",
            model("expensive","$10/month",p_in=0.9,p_out=1.2),
            model("cheap","$10/month",p_in=0.15,p_out=0.45))}
        s=estimate_capacity(d,{"mistral":1},profile=profile())
        weighted=0.15*0.92+0.45*0.08
        self.assertAlmostEqual(s["forecast_30d"],int(10_000_000/weighted),delta=2)

    def test_mistral_cash_does_not_add_on_top_of_larger_month_label(self):
        d={"mistral":source("mistral",
            model("native","~50-100M",p_in=0.9,p_out=1.2),
            model("cheap","$10/month",p_in=0.15,p_out=0.45))}
        s=estimate_capacity(d,{"mistral":1},profile=profile())
        self.assertEqual(s["forecast_30d"],100_000_000)

    def test_llm7_daily_comma_cap(self):
        d={"llm7":source("llm7",model("default","Free tier: 100,000 tokens/24h shared"))}
        self.assertEqual(estimate_capacity(d,{"llm7":1},profile=profile())["forecast_30d"],3_000_000)

    def test_rate_only_sources_use_actual_usage_not_nonstop_running(self):
        d={
            "kilo":source("kilo",model("f:free","free · 200/hr per IP",context=1_048_576)),
            "ovh":source("ovh",model("a","free · 2/min per IP",context=262144)),
            "unorouter":source("unorouter",model("f:free","free · 1 req/min",context=1_000_000)),
        }
        s=estimate_capacity(d,{"kilo":1,"ovh":1,"unorouter":1},
                            profile=profile(average=13000,daily=30))
        self.assertEqual(s["forecast_30d"],3*30*30*13000)
        self.assertLess(s["forecast_30d"],100_000_000)

    def test_monthly_usage_subtracted_only_once(self):
        d={"groq":source("groq",model("a","~6M"))}
        s=estimate_capacity(d,{"groq":1},profile=profile(),current_month_usage={"groq":1234})
        self.assertEqual(s["month_used"],1234)
        self.assertEqual(s["remaining_month"],6_000_000-1234)

    def test_no_global_usage_falls_back_to_documented_labels_not_fantasy(self):
        d={"openrouter":source("openrouter",model("f:free","~6M",context=1_048_576,rpd=50))}
        s=estimate_capacity(d,{"openrouter":1})
        self.assertEqual(s["forecast_30d"],6_000_000)


if __name__=="__main__":
    unittest.main()
