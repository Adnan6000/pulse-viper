from __future__ import annotations

import unittest
from unittest.mock import (
    MagicMock,
    patch,
)

from core.trade_brain import (
    BLOCK_REASON_CHAOTIC,
    BLOCK_REASON_CONFLICTED,
    BLOCK_REASON_NEWS,
    BLOCK_REASON_NO_STRATEGY,
    BLOCK_REASON_STRATEGY_CONFLICT,
    MarketRegimeHMM,
    OrderFlowEngine,
    TradeBrain,
)


class TestTradeBrain(unittest.TestCase):
    def setUp(self):
        self.of_engine = MagicMock(
            spec=OrderFlowEngine
        )

        self.hmm = MagicMock(
            spec=MarketRegimeHMM
        )

        self.brain = TradeBrain(
            order_flow_engine=self.of_engine,
            market_regime_hmm=self.hmm,
        )

        self.settings = {
            "dynamic_regime_filter": False,
            "news_filter_enabled": True,
            "self_learning_filter": False,
            "killzone_filter_enabled": False,
            "max_spread_points": 120,
            "trading_mode": "intraday",
            "paper_mode": True,
        }

        self.base_analysis = {
            "symbol": "EURUSD",
            "market_regime": "TRENDING",
            "news_locked": False,
            "killzone_active": True,
            "spread_points": 10.0,
            "session_name": "LONDON",
            "features": {},

            "d1_bias": 1,
            "h4_bias": 1,
            "h1_bias": 1,
            "m15_bias": 1,
            "m5_bias": 1,
            "m1_bias": 1,

            "m15_sweep_type": 1,
            "m5_mss_signal": 1,

            "m5_fvg_class": "fresh",
            "m5_fvg_type": "bullish",

            "vsa_signals": [
                "DEMAND_ABSORPTION"
            ],

            "buy_pressure": 70.0,
            "sell_pressure": 30.0,

            "ofi_imbalance": 0.20,
            "regression_zscore": 0.0,

            "swept_pools": [
                {
                    "type": "sell_stop"
                }
            ],
        }

    def _settings_get(
        self,
        key,
        default=None,
    ):
        return self.settings.get(
            key,
            default,
        )

    def _evaluate(
        self,
        analysis,
        **kwargs,
    ):
        with patch(
            "core.trade_brain.settings_manager.get",
            side_effect=self._settings_get,
        ), patch.object(
            self.brain,
            "_load_performance_matrix",
            return_value={},
        ):
            return self.brain.evaluate(
                analysis,
                **kwargs,
            )

    def test_news_is_hard_block(self):
        analysis = dict(
            self.base_analysis
        )

        analysis["news_locked"] = True

        result = self._evaluate(
            analysis,
            strategy_action="BUY",
            strategy_name="ICT",
        )

        self.assertFalse(
            result.passed
        )

        self.assertEqual(
            result.block_reason,
            BLOCK_REASON_NEWS,
        )

        self.assertEqual(
            result.brain_score,
            0.0,
        )

    def test_chaotic_is_hard_block(self):
        analysis = dict(
            self.base_analysis
        )

        analysis[
            "market_regime"
        ] = "CHAOTIC"

        result = self._evaluate(
            analysis,
            strategy_action="BUY",
            strategy_name="ICT",
        )

        self.assertFalse(
            result.passed
        )

        self.assertEqual(
            result.block_reason,
            BLOCK_REASON_CHAOTIC,
        )

    def test_strong_candidate_can_pass(self):
        result = self._evaluate(
            dict(
                self.base_analysis
            ),
            strategy_action="BUY",
            strategy_name="ICT",
            session_score=5.0,
        )

        self.assertTrue(
            result.passed
        )

        self.assertEqual(
            result.brain_direction,
            "BUY",
        )

        self.assertIsNone(
            result.block_reason
        )

    def test_strategy_is_required(self):
        result = self._evaluate(
            dict(
                self.base_analysis
            ),
            strategy_action=None,
            strategy_name=None,
            session_score=5.0,
        )

        self.assertFalse(
            result.passed
        )

        self.assertEqual(
            result.block_reason,
            BLOCK_REASON_NO_STRATEGY,
        )

    def test_strategy_cannot_flip_direction(self):
        result = self._evaluate(
            dict(
                self.base_analysis
            ),
            strategy_action="SELL",
            strategy_name="ICT",
            session_score=5.0,
        )

        self.assertFalse(
            result.passed
        )

        self.assertEqual(
            result.block_reason,
            BLOCK_REASON_STRATEGY_CONFLICT,
        )

        self.assertEqual(
            result.brain_direction,
            "BUY",
        )

    def test_neutral_analysis_is_conflict(self):
        analysis = dict(
            self.base_analysis
        )

        for key in (
            "d1_bias",
            "h4_bias",
            "h1_bias",
            "m15_bias",
            "m5_bias",
            "m1_bias",
            "m15_sweep_type",
            "m5_mss_signal",
        ):
            analysis[key] = 0

        analysis[
            "m5_fvg_class"
        ] = "none"

        analysis[
            "m5_fvg_type"
        ] = "none"

        analysis[
            "vsa_signals"
        ] = []

        analysis[
            "buy_pressure"
        ] = 50.0

        analysis[
            "sell_pressure"
        ] = 50.0

        analysis[
            "ofi_imbalance"
        ] = 0.0

        analysis[
            "swept_pools"
        ] = []

        result = self._evaluate(
            analysis,
            strategy_action="BUY",
            strategy_name="ICT",
        )

        self.assertFalse(
            result.passed
        )

        self.assertEqual(
            result.block_reason,
            BLOCK_REASON_CONFLICTED,
        )

        self.assertIsNone(
            result.brain_direction
        )

    def test_missing_empirical_matrix_is_neutral(self):
        with patch.object(
            self.brain,
            "_load_performance_matrix",
            return_value={},
        ):
            (
                adjustment,
                reason,
            ) = self.brain._get_strategy_routing_adjustment(
                strategy_name="ICT",
                mode="intraday",
                weekday=0,
                session="LONDON",
                regime="TRENDING",
            )

        self.assertEqual(
            adjustment,
            0.0,
        )

        self.assertEqual(
            reason,
            "NO_EMPIRICAL_DATA",
        )

    def test_paper_mode_does_not_relax_threshold(self):
        paper_result = self._evaluate(
            dict(
                self.base_analysis
            ),
            strategy_action="BUY",
            strategy_name="ICT",
            session_score=5.0,
        )

        self.settings[
            "paper_mode"
        ] = False

        live_result = self._evaluate(
            dict(
                self.base_analysis
            ),
            strategy_action="BUY",
            strategy_name="ICT",
            session_score=5.0,
        )

        self.assertEqual(
            paper_result.threshold,
            live_result.threshold,
        )

        self.assertEqual(
            paper_result.brain_score,
            live_result.brain_score,
        )

        self.assertEqual(
            paper_result.passed,
            live_result.passed,
        )

        self.assertFalse(
            paper_result.reason_map[
                "exploration_override"
            ]
        )


if __name__ == "__main__":
    unittest.main()