from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.news_schedule import DEFAULT_SCHEDULE
from core.outcome_labeler import OutcomeResolver
from utils.settings_manager import settings_manager


ROOT = Path(__file__).resolve().parents[1]


class TestIntelligencePipeline(unittest.TestCase):

    # =========================================================
    # EXECUTION SAFETY DEFAULTS
    # =========================================================

    def test_execution_safe_defaults(self):
        self.assertTrue(
            settings_manager.get(
                "paper_mode",
                True,
            )
        )

        self.assertFalse(
            settings_manager.get(
                "auto_trade_enabled",
                False,
            )
        )

        self.assertFalse(
            settings_manager.get(
                "allow_untokenized_orders",
                False,
            )
        )

        self.assertFalse(
            settings_manager.get(
                "emergency_hedging_enabled",
                False,
            )
        )

    # =========================================================
    # NEWS SAFETY
    # =========================================================

    def test_no_fabricated_manual_news_defaults(self):
        self.assertEqual(
            list(DEFAULT_SCHEDULE),
            [],
        )

    def test_manual_news_file_is_empty_when_present(self):
        path = (
            ROOT
            / "configs"
            / "news_schedule.json"
        )

        if not path.exists():
            return

        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

        self.assertEqual(
            data,
            [],
        )

    # =========================================================
    # OUTCOME RESOLUTION
    # =========================================================

    def test_unresolved_horizon_is_censored(self):
        """
        If neither stop nor target is touched,
        historical labeling must not fabricate
        a forced winning/losing time exit.
        """

        bars = [
            {
                "open": 2000.0,
                "high": 2005.0,
                "low": 1995.0,
                "close": 2002.0,
            },
            {
                "open": 2002.0,
                "high": 2007.0,
                "low": 1998.0,
                "close": 2001.0,
            },
        ]

        outcome = OutcomeResolver.resolve(
            candidate_id="TEST-CENSORED",
            entry_price=2000.0,
            stop_price=1990.0,
            target_price=2020.0,
            action="BUY",
            bars_future=bars,
        )

        self.assertEqual(
            outcome.outcome_type,
            "CENSORED",
        )

        self.assertIsNone(
            outcome.tp_before_sl
        )

        self.assertIsNone(
            outcome.net_r
        )

    def test_same_bar_without_lower_tf_is_ambiguous(self):
        """
        Main candle touching both TP and SL
        cannot be assigned an arbitrary order.
        """

        bars = [
            {
                "open": 2000.0,
                "high": 2021.0,
                "low": 1989.0,
                "close": 2001.0,
            }
        ]

        outcome = OutcomeResolver.resolve(
            candidate_id="TEST-AMBIGUOUS",
            entry_price=2000.0,
            stop_price=1990.0,
            target_price=2020.0,
            action="BUY",
            bars_future=bars,
        )

        self.assertEqual(
            outcome.outcome_type,
            "AMBIGUOUS_SAME_BAR",
        )

        self.assertTrue(
            outcome.same_bar_ambiguous
        )

        self.assertIsNone(
            outcome.tp_before_sl
        )

        self.assertIsNone(
            outcome.net_r
        )

    def test_lower_tf_can_resolve_same_bar_tp_first(self):
        """
        When lower-TF evidence exists,
        it may causally resolve same-bar order.
        """

        bars = [
            {
                "open": 2000.0,
                "high": 2021.0,
                "low": 1989.0,
                "close": 2001.0,
            }
        ]

        lower_tf = [
            {
                "open": 2000.0,
                "high": 2020.0,
                "low": 1998.0,
                "close": 2018.0,
            },
            {
                "open": 2018.0,
                "high": 2019.0,
                "low": 1990.0,
                "close": 1992.0,
            },
        ]

        outcome = OutcomeResolver.resolve(
            candidate_id="TEST-LTF-TP-FIRST",
            entry_price=2000.0,
            stop_price=1990.0,
            target_price=2020.0,
            action="BUY",
            bars_future=bars,
            lower_tf_bars=lower_tf,
        )

        self.assertEqual(
            outcome.outcome_type,
            "TP_FIRST",
        )

        self.assertTrue(
            outcome.tp_before_sl
        )

        self.assertFalse(
            outcome.same_bar_ambiguous
        )

    def test_default_costs_are_not_fabricated(self):
        """
        Historical labeling must not silently
        invent commission/slippage/spread costs.
        """

        bars = [
            {
                "open": 2000.0,
                "high": 2020.0,
                "low": 1995.0,
                "close": 2019.0,
            }
        ]

        outcome = OutcomeResolver.resolve(
            candidate_id="TEST-COSTS",
            entry_price=2000.0,
            stop_price=1990.0,
            target_price=2020.0,
            action="BUY",
            bars_future=bars,
        )

        self.assertEqual(
            outcome.outcome_type,
            "TP_FIRST",
        )

        self.assertAlmostEqual(
            outcome.spread_r,
            0.0,
        )

        self.assertAlmostEqual(
            outcome.commission_r,
            0.0,
        )

        self.assertAlmostEqual(
            outcome.slippage_r,
            0.0,
        )

        self.assertIsNotNone(
            outcome.net_r
        )

        assert outcome.net_r is not None

        self.assertAlmostEqual(
            outcome.net_r,
            2.0,
        )

    def test_outcome_reports_causal_label_version(self):
        """
        Version belongs to the produced label,
        not necessarily as a module-level constant.
        """

        bars = [
            {
                "open": 2000.0,
                "high": 2020.0,
                "low": 1998.0,
                "close": 2019.0,
            }
        ]

        outcome = OutcomeResolver.resolve(
            candidate_id="TEST-VERSION",
            entry_price=2000.0,
            stop_price=1990.0,
            target_price=2020.0,
            action="BUY",
            bars_future=bars,
        )

        self.assertEqual(
            outcome.label_version,
            "v5.0-causal",
        )

    # =========================================================
    # MODEL REGISTRY
    # =========================================================

    def test_registry_has_no_fabricated_active_model(self):
        path = (
            ROOT
            / "configs"
            / "model_registry.json"
        )

        if not path.exists():
            return

        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

        self.assertIsNone(
            data.get("active")
        )

    # =========================================================
    # DASHBOARD SAFETY
    # =========================================================

    def test_dashboard_has_no_manual_one_click_trade(self):
        source = (
            ROOT
            / "dashboard"
            / "html_template.py"
        ).read_text(
            encoding="utf-8",
            errors="ignore",
        )

        self.assertNotIn(
            "executeCopilotTrade",
            source,
        )

        self.assertNotIn(
            "EXECUTE CO-PILOT TRADE",
            source,
        )

        self.assertNotIn(
            "/api/execute_trade",
            source,
        )

    def test_dashboard_has_no_runtime_innerhtml(self):
        source = (
            ROOT
            / "dashboard"
            / "html_template.py"
        ).read_text(
            encoding="utf-8",
            errors="ignore",
        )

        self.assertNotIn(
            ".innerHTML",
            source,
        )

    # =========================================================
    # ENGINE REGRESSION GUARDS
    # =========================================================

    def test_engine_has_no_fabricated_strategy_matrix(self):
        source = (
            ROOT
            / "core"
            / "engine.py"
        ).read_text(
            encoding="utf-8",
            errors="ignore",
        )

        forbidden = (
            '"total_trades": 42',
            "Scanning optimizer matrix",
        )

        for text in forbidden:
            self.assertNotIn(
                text,
                source,
            )

    def test_engine_has_no_automatic_historical_training_workers(self):
        source = (
            ROOT
            / "core"
            / "engine.py"
        ).read_text(
            encoding="utf-8",
            errors="ignore",
        )

        forbidden = (
            "StartupTraining",
            "ContinuousTraining",
        )

        for text in forbidden:
            self.assertNotIn(
                text,
                source,
            )


if __name__ == "__main__":
    unittest.main()