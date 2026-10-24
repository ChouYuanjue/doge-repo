"""Precise native-label compatibility and optimistic free capacity boundaries."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
from doge_shared.free_capacity import estimate_capacity, parse_budget


def model(name: str, budget: str = "", *, context: int = 0, rpd: int = 0,
          rpm: int = 0, input_price: float | None = None) -> dict:
    return dict(model_id=name,monthly_token_budget=budget,context_window=context,
                rpd_limit=rpd,rpm_limit=rpm,paid_input_per_m=input_price)


def source(platform: str, *models: dict) -> dict:
    return dict(platform=platform,models=list(models))


class OptimisticFreeCapacityTests(unittest.TestCase):
    def test_parse_native_budget_upper_end_and_daily_multipliers(self):
        for label, tokens in [
            ("~50-100M", 100_000_000),
            ("~2-3M (200/hr)", 3_000_000),
            ("free · 1M tokens/day (permanently doubled)", 30_000_000),
            ("free · 500K tokens/24h", 15_000_000),
            ("~6M", 6_000_000),
            ("free · 14.4K rpd", 0),
            ("1K calls/mo shared", 0),
            ("Free tier: 100,000 tokens/24h shared", 0),
            ("$10/month shared API credits", 0),
            ("free · 200/hr per IP", 0),
            ("", 0),
        ]:
            with self.subTest(label=label):
                self.assertEqual(parse_budget(label),tokens)

    def test_native_free_tier_aggregates_models_and_explains_pool_overlap(self):
        data = {
            "xkiro":source("xkiro", model("m1","free · 1M tokens/day"),
                            model("m2","free · 1M tokens/day"),
                            model("m3","free · 500K tokens/day")),
            "groq":source("groq",model("cheap","~6M"),
                          model("best","~15M")),
            "openrouter":source("openrouter",model("some:free","~6M",context=262144,rpd=50)),
        }
        d = estimate_capacity(data,{"xkiro":1,"groq":1,"openrouter":1})
        self.assertEqual(d["native_model_monthly"],75_000_000+21_000_000+6_000_000)
        self.assertEqual(d["native_pool_dedup_monthly"],30_000_000+15_000_000+6_000_000)
        self.assertEqual(d["model_count"],6)
        self.assertGreater(d["optimistic_monthly"],d["native_model_monthly"])

    def test_multiple_keys_scale_documented_allowances_but_not_models(self):
        d=estimate_capacity(
            {"groq":source("groq",model("m1","~6M"),model("m2","~15M"))},
            {"groq":2},
        )
        self.assertEqual(d["native_model_monthly"],42_000_000)
        self.assertEqual(d["native_pool_dedup_monthly"],30_000_000)

    def test_openrouter_free_requests_can_be_counted_without_paid_balance(self):
        d=estimate_capacity({
            "openrouter":source("openrouter",
                model("a:free","~6M",context=256_000,rpd=50),
                model("b:free","free · 50 req/day",context=1_048_576,rpd=50),
                model("paid-model","~900M",context=2_000_000,rpd=1000),
            )},{"openrouter":1})
        self.assertEqual(d["native_model_monthly"],6_000_000)
        self.assertEqual(d["optimistic_monthly"],50*30*1_048_576)
        self.assertEqual(d["derived"]["openrouter"]["requests_per_day"],50)
        self.assertEqual(d["conditional_or_upgrade_total"],1000*30*1_048_576)
        self.assertEqual(d["sources"]["openrouter"]["context_model"],"b:free")

    def test_modelscope_uses_request_ceiling_with_explicit_unverified_basis(self):
        d=estimate_capacity({
            "modelscope":source("modelscope",
                model("qwen","Daily login: 200 credits",context=262144,rpd=200))
        },{"modelscope":1})
        self.assertEqual(d["optimistic_monthly"],200*30*262144)
        self.assertIn("未经",d["derived"]["modelscope"]["basis"])
        self.assertEqual(d["native_model_monthly"],0)

    def test_llm7_comma_number_not_dropped(self):
        d=estimate_capacity({
            "llm7":source("llm7",model("default","Free tier: 100,000 tokens/24h shared"))
        },{"llm7":1})
        self.assertEqual(d["optimistic_monthly"],3_000_000)

    def test_mistral_cash_grant_chooses_cheapest_model_without_double_count(self):
        d=estimate_capacity({
            "mistral":source("mistral",
                model("expensive","Free plan · $10/month shared API credits",
                      input_price=0.9),
                model("cheap","Free plan · $10/month shared API credits",
                      input_price=0.15))
        },{"mistral":1})
        self.assertEqual(d["native_model_monthly"],0)
        self.assertEqual(d["optimistic_monthly"],66_666_666)
        self.assertIn("cheap",d["derived"]["mistral"]["basis"])
        bigger=estimate_capacity({
            "mistral":source("mistral",
                model("native","~50-100M",input_price=0.9),
                model("cheap","Free plan · $10/month shared API credits",input_price=0.15))
        },{"mistral":1})
        self.assertEqual(bigger["optimistic_monthly"],100_000_000)
        self.assertEqual(bigger["derived"]["mistral"]["increment"],0)

    def test_rate_only_is_separate_theoretical_throughput_not_stored_balance(self):
        d=estimate_capacity({
            "kilo":source("kilo",model("best:free","free · 200/hr per IP",context=1_048_576)),
            "ovh":source("ovh",model("best","free · 2/min per IP",context=262144,rpm=2)),
            "unorouter":source("unorouter",model("best:free","free · 1 req/min",context=1_000_000,rpm=1)),
        },{"kilo":1,"ovh":1,"unorouter":1})
        self.assertEqual(d["native_model_monthly"],0)
        self.assertEqual(d["optimistic_monthly"],0)
        self.assertEqual(d["rate_only_estimates"]["kilo"]["monthly"],
                         200*24*30*1_048_576)
        self.assertEqual(d["rate_only_estimates"]["ovh"]["monthly"],2*60*24*30*262144)
        self.assertEqual(d["rate_only_estimates"]["unorouter"]["monthly"],60*24*30*1_000_000)
        self.assertGreater(d["rate_only_throughput_monthly"],100_000_000_000)

    def test_month_usage_is_subtracted_once_from_nominal_remaining(self):
        d=estimate_capacity({
            "groq":source("groq",model("m1","~6M"))
        },{"groq":1},current_month_usage={"groq":1234})
        self.assertEqual(d["native_model_monthly"],6_000_000)
        self.assertEqual(d["optimistic_remaining_current_month"],5_998_766)


if __name__=="__main__":
    unittest.main()
