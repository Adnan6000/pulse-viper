
import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import numpy as np

# Ensure the project root is in the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.trade_brain import TradeBrain, MarketRegimeHMM, OrderFlowEngine

class TestTradeBrain(unittest.TestCase):

    def setUp(self):
        """Set up a mock environment for testing the TradeBrain."""
        # Mock the dependencies
        self.mock_of_engine = MagicMock(spec=OrderFlowEngine)
        self.mock_hmm_detector = MagicMock(spec=MarketRegimeHMM)

        # Instantiate the TradeBrain with mocked dependencies
        self.brain = TradeBrain(
            order_flow_engine=self.mock_of_engine,
            market_regime_hmm=self.mock_hmm_detector
        )

        # Mock the settings manager that is used throughout the brain
        self.settings_patcher = patch('utils.settings_manager.settings_manager')
        self.mock_settings_manager = self.settings_patcher.start()
        self.mock_settings_manager.get.side_effect = self.get_setting

        # Mock the trade_pattern_memory
        self.pattern_memory_patcher = patch('core.trade_pattern_memory.trade_pattern_memory')
        self.mock_pattern_memory = self.pattern_memory_patcher.start()
        self.mock_pattern_memory.get_modifier.return_value = 0.0

        # Default settings for most tests
        self.settings = {
            "dynamic_regime_filter": True,
            "news_filter_enabled": True,
            "self_learning_filter": False, # Disable AI/self-learning by default for deterministic tests
            "strict_mode": True,
            "paper_mode": True,
            "max_spread_points": 300,
            "strict_news_veto": False,
            "trading_mode": "intraday"
        }

        # A base analysis dict that can be overridden in each test
        self.base_analysis = {
            "symbol": "EURUSD",
            "market_regime": "RANGE",
            "news_locked": False,
            "killzone_active": True,
            "price": 1.1000,
            "atr": 0.0010,
            "features": {"spread": 10, "atr": 0.0010},
            "d1_bias": 0, "h4_bias": 0, "h1_bias": 0, "m15_bias": 0, "m5_bias": 0, "m1_bias": 0,
            "m15_sweep_type": 0, "m5_mss_signal": 0,
            "m5_fvg_class": "none", "m5_fvg_type": "none",
            "vsa_signals": [],
            "buy_pressure": 50.0, "sell_pressure": 50.0,
            "rvol": 1.0,
            "ofi_imbalance": 0.0,
            "regression_zscore": 0.0,
            "htf_bias": 0,
            "df_ltf": None, "df_m5": None, "df_m15": None, "df_h1": None, "df_h4": None,
            "session_name": "LONDON",
        }
        
        # Mock engine/detector return values
        self.mock_of_engine.fetch_and_build_footprint.return_value = {
            "order_flow_boost": 0.0, "poc_price": 0.0, "total_delta": 0.0,
            "buy_imbalances": [], "sell_imbalances": [],
            "absorption_detected": {"passive_demand_nodes": [], "passive_supply_nodes": []}
        }
        self.mock_hmm_detector.decode_current_regime.return_value = ("RANGE", {0: 1.0, 1: 0.0, 2: 0.0})


    def get_setting(self, key, default=None):
        """Side effect function for the mocked settings_manager.get()."""
        return self.settings.get(key, default)

    def tearDown(self):
        """Stop the patchers."""
        self.settings_patcher.stop()
        self.pattern_memory_patcher.stop()

    def test_news_lockout_gate(self):
        """Test that a trade is blocked immediately if news_locked is True."""
        print("\nRunning test: test_news_lockout_gate")
        analysis = self.base_analysis.copy()
        analysis["news_locked"] = True

        result = self.brain.evaluate(analysis)

        self.assertFalse(result.passed, "Trade should not pass during news lockout.")
        self.assertEqual(result.block_reason, "NEWS_LOCKOUT", "Block reason should be NEWS_LOCKOUT.")
        self.assertEqual(result.brain_score, 0.0, "Brain score should be 0 during news lockout.")
        print("PASS: test_news_lockout_gate")

    def test_chaotic_regime_gate(self):
        """Test that a trade is blocked immediately if the regime is CHAOTIC."""
        print("\nRunning test: test_chaotic_regime_gate")
        analysis = self.base_analysis.copy()
        analysis["market_regime"] = "CHAOTIC"

        result = self.brain.evaluate(analysis)

        self.assertFalse(result.passed, "Trade should not pass in CHAOTIC regime.")
        self.assertEqual(result.block_reason, "CHAOTIC_REGIME", "Block reason should be CHAOTIC_REGIME.")
        self.assertEqual(result.brain_score, 0.0, "Brain score should be 0 in CHAOTIC regime.")
        print("PASS: test_chaotic_regime_gate")

    def test_perfect_buy_scenario_trending(self):
        """Test a clear-cut BUY setup in a TRENDING market."""
        print("\nRunning test: test_perfect_buy_scenario_trending")
        analysis = self.base_analysis.copy()
        analysis.update({
            "market_regime": "TRENDING",
            "d1_bias": 1, "h4_bias": 1, "h1_bias": 1, "m15_bias": 1, "m5_bias": 1, "m1_bias": 1,
            "htf_bias": 1,
            "m15_sweep_type": 1,      # Bullish sweep
            "m5_mss_signal": 1,       # Bullish MSS
            "m5_fvg_class": "fresh",  # High quality FVG
            "m5_fvg_type": "bullish",
            "vsa_signals": ["demand_absorption"], # Bullish VSA
            "buy_pressure": 70.0,
            "sell_pressure": 30.0,
            "regression_zscore": -1.5, # Oversold, good for a buy
            "swept_pools": [{"type": "sell_stop"}], # Bullish liquidity confirmation
            "news_sentiment": 0.5, # Positive sentiment
            "session_name": "NEW_YORK",
        })
        
        # Mock a high AI confidence
        ai_confidence = 0.85
        
        # Mock methods that require dataframes to return True
        with patch.object(self.brain, '_is_price_near_htf_levels', return_value=(True, 'mocked')) as mock_htf_gate:
            result = self.brain.evaluate(analysis, ai_confidence=ai_confidence)

            self.assertTrue(result.passed, f"Trade should pass, but was blocked with reason: {result.block_reason}")
            self.assertEqual(result.brain_direction, "BUY", "Direction should be BUY.")
            self.assertGreater(result.brain_score, 60, f"Score should be high for a perfect setup, but was {result.brain_score:.2f}")
            self.assertIsNone(result.block_reason, f"There should be no block reason, but got {result.block_reason}")
            
            # Check if tier scores are reasonable
            self.assertGreater(result.tier1_score, 40, "Tier 1 (Directional) score should be high.")
            self.assertGreater(result.tier2_score, 20, "Tier 2 (Execution) score should be high.")
            self.assertGreater(result.tier3_score, 5, "Tier 3 (Risk) score should be positive.")
        print("PASS: test_perfect_buy_scenario_trending")

    def test_perfect_sell_scenario(self):
        """Test a clear-cut SELL setup in a TRENDING market."""
        print("\nRunning test: test_perfect_sell_scenario")
        analysis = self.base_analysis.copy()
        analysis.update({
            "market_regime": "TRENDING",
            "d1_bias": -1, "h4_bias": -1, "h1_bias": -1, "m15_bias": -1, "m5_bias": -1, "m1_bias": -1,
            "htf_bias": -1,
            "m15_sweep_type": -1,      # Bearish sweep
            "m5_mss_signal": -1,       # Bearish MSS
            "m5_fvg_class": "fresh",  # High quality FVG
            "m5_fvg_type": "bearish",
            "vsa_signals": ["supply_absorption"], # Bearish VSA
            "buy_pressure": 30.0,
            "sell_pressure": 70.0,
            "regression_zscore": 1.5, # Overbought, good for a sell
            "swept_pools": [{"type": "buy_stop"}], # Bearish liquidity confirmation
            "news_sentiment": -0.5, # Negative sentiment
        })
        ai_confidence = 0.85
        with patch.object(self.brain, '_is_price_near_htf_levels', return_value=(True, 'mocked')):
            result = self.brain.evaluate(analysis, ai_confidence=ai_confidence)

            self.assertTrue(result.passed, f"Trade should pass, but was blocked with reason: {result.block_reason}")
            self.assertEqual(result.brain_direction, "SELL", "Direction should be SELL.")
            self.assertGreater(result.brain_score, 60, f"Score should be high for a perfect setup, but was {result.brain_score:.2f}")
            self.assertIsNone(result.block_reason, f"There should be no block reason, but got {result.block_reason}")
        print("PASS: test_perfect_sell_scenario")

    def test_conflicted_direction_scenario(self):
        """Test a scenario with conflicting signals, expecting no trade."""
        print("\nRunning test: test_conflicted_direction_scenario")
        analysis = self.base_analysis.copy()
        analysis.update({
            "market_regime": "TRENDING",
            "d1_bias": 1, "h4_bias": 1,     # Bullish HTF
            "h1_bias": -1, "m15_bias": -1, # Bearish MTF
            "m5_mss_signal": -1,          # Bearish LTF structure
            "m5_fvg_type": "bullish",     # Bullish FVG (conflict)
        })
        with patch.object(self.brain, '_is_price_near_htf_levels', return_value=(True, 'mocked')):
            result = self.brain.evaluate(analysis)

            self.assertIsNone(result.brain_direction, "Brain direction should be None due to conflict.")
            self.assertFalse(result.passed, "Trade should not pass when direction is conflicted.")
            self.assertEqual(result.block_reason, "DIRECTIONAL_CONFLICT", "Block reason should be DIRECTIONAL_CONFLICT.")
        print("PASS: test_conflicted_direction_scenario")


if __name__ == '__main__':
    unittest.main()

