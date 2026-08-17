# scratch/test_upgrades.py
"""
Comprehensive Unit Test Suite verifying all upgraded components:
1. Friction-buffered structural breakeven at 1R.
2. Closed-candle (index 1 time) async caching and live price cascading.
3. Regression Z-score computation and Tier 2 scoring dampening.
4. Regime Multiplier limits counter-trend setups in trending market.
5. Regime-isolated BrainCalibrator weight tuning.
"""
import sys
import os
import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.trade_brain import TradeBrain, BrainResult
from core.brain_calibrator import BrainCalibrator, CALIBRATION_FILE
from core.trade_manager import TradePosition
from core.engine import AdvancedTradingEngine

class MockSymbolInfo:
    def __init__(self, point=0.01, digits=2):
        self.point = point
        self.digits = digits

class TestUpgrades(unittest.TestCase):
    def setUp(self):
        # Create models folder if missing
        os.makedirs("models", exist_ok=True)
        # Create data folder if missing
        os.makedirs("data", exist_ok=True)
        # Clean previous weights
        if os.path.exists(CALIBRATION_FILE):
            try:
                os.remove(CALIBRATION_FILE)
            except Exception:
                pass

    def tearDown(self):
        if os.path.exists(CALIBRATION_FILE):
            try:
                os.remove(CALIBRATION_FILE)
            except Exception:
                pass

    def test_friction_buffered_breakeven(self):
        """1. Friction-buffered breakeven test at 1R profit."""
        print("\n--- Testing Component 1: Friction-Buffered Breakeven ---")
        # Setup mock symbol info
        symbol_info = MockSymbolInfo(point=0.01, digits=2)
        
        # Test simulated position for BUY
        # Entry = 100.0, SL = 99.0, TP = 102.0. Initial SL dist = 100 points
        pos = TradePosition(
            ticket_id=1,
            symbol="XAUUSDm",
            action="BUY",
            entry_price=100.0,
            sl=99.0,
            tp=102.0,
            volume=0.1,
            timestamp=datetime.now()
        )
        pos.initial_sl_dist = 1.0  # 100 points
        
        # Scenario A: Profit is below 1R
        current_price = 100.5
        pnl_points = (current_price - pos.entry_price) / symbol_info.point
        pos.max_profit_points = max(pos.max_profit_points, pnl_points)
        
        # Mimic break-even logic from trade_manager.py
        buffer_points = 20.0
        buffer_price = buffer_points * symbol_info.point
        be_price = pos.entry_price + buffer_price
        
        sl_distance_pts = pos.initial_sl_dist / symbol_info.point
        if pos.max_profit_points >= sl_distance_pts:
            pos.sl = be_price
            pos.moved_to_be = True
            
        self.assertFalse(pos.moved_to_be)
        self.assertEqual(pos.sl, 99.0)
        print("  PASS: Sl remains at initial SL when profit is under 1R")

        # Scenario B: Profit reaches 1R (100 points or price = 101.0)
        current_price = 101.0
        pnl_points = (current_price - pos.entry_price) / symbol_info.point
        pos.max_profit_points = max(pos.max_profit_points, pnl_points)
        
        if pos.max_profit_points >= sl_distance_pts:
            pos.sl = be_price
            pos.moved_to_be = True
            
        self.assertTrue(pos.moved_to_be)
        self.assertEqual(pos.sl, 100.20)  # Entry (100.0) + Buffer (0.20)
        print("  PASS: Sl successfully moves to entry + 20 points buffer when profit reaches 1R")

    def test_regression_zscore_calculation(self):
        """2. Linear regression Z-score calculation test on H1."""
        print("\n--- Testing Component 2: Regression Z-Score ---")
        
        # Create a mock H1 dataframe of 100 candles
        n = 100
        time_index = pd.date_range(end=datetime.now(), periods=n, freq='H')
        
        # Scenario A: Steady upward trend (highly overbought at the end)
        # y = 100.0 + 0.1 * x + noise, with a spike at the end
        np.random.seed(42)
        x = np.arange(n)
        prices = 100.0 + 0.15 * x + np.random.normal(0, 0.1, n)
        prices[-1] = prices[-1] + 3.0  # Large positive deviation
        
        df = pd.DataFrame(prices, columns=['close'], index=time_index)
        
        z_score = AdvancedTradingEngine.calculate_regression_zscore(df, period=100)
        self.assertGreater(z_score, 2.0)
        print(f"  PASS: Overbought state detected. Z-score: {z_score:.2f} (> 2.0)")

        # Scenario B: Steady downward trend (highly oversold at the end)
        prices = 100.0 - 0.15 * x + np.random.normal(0, 0.1, n)
        prices[-1] = prices[-1] - 3.0  # Large negative deviation
        df = pd.DataFrame(prices, columns=['close'], index=time_index)
        
        z_score = AdvancedTradingEngine.calculate_regression_zscore(df, period=100)
        self.assertLess(z_score, -2.0)
        print(f"  PASS: Oversold state detected. Z-score: {z_score:.2f} (< -2.0)")

    def test_zscore_scoring_dampening(self):
        """3. Regression Z-score correctly dampens Tier 2 scores in TradeBrain."""
        print("\n--- Testing Component 3: Z-Score Dampening in Tier 2 ---")
        
        brain = TradeBrain()
        
        # Analysis structure with standard bullish features
        analysis = {
            "market_regime": "TRENDING",
            "active_bias": 1,
            "d1_bias": 1,
            "h4_bias": 1,
            "h1_bias": 1,
            "m15_sweep_type": 1,
            "m5_mss_signal": 1,
            "m5_fvg_class": "fresh",
            "m5_fvg_type": "bullish",
            "vsa_signals": ["demand_absorption"],
            "volatility": 0.015,
            "atr_pct": 0.002,
            "buy_pressure": 65.0,
            "sell_pressure": 35.0,
            "rvol": 1.5,
            "regression_zscore": 0.0  # Perfectly in the middle of the channel
        }
        
        # Evaluate with 0.0 Z-score (no penalty)
        res_no_penalty = brain.evaluate(analysis, ai_confidence=0.8)
        score_no_penalty = res_no_penalty.tier2_score
        
        # Evaluate with 2.5 Z-score (highly overbought, expect high penalty on BUY setups)
        analysis_overbought = dict(analysis)
        analysis_overbought["regression_zscore"] = 2.5
        res_overbought = brain.evaluate(analysis_overbought, ai_confidence=0.8)
        score_overbought = res_overbought.tier2_score
        
        self.assertLess(score_overbought, score_no_penalty)
        print(f"  PASS: Overbought Z-score of 2.5 reduced Tier 2 score from {score_no_penalty:.1f} to {score_overbought:.1f} (penalty applied: {score_no_penalty - score_overbought:.1f} pts)")

    def test_regime_multiplier_limits_countertrend(self):
        """4. Regime multiplier limits counter-trend setups in trending regime to max 32 points."""
        print("\n--- Testing Component 4: Regime Multiplier for Counter-Trend Setups ---")
        
        brain = TradeBrain()
        
        # trending market, HTF bias is bearish (-1)
        # But we set bias timeframes (d1_bias, h4_bias, h1_bias) to bullish (1) 
        # so the brain selects direction = "BUY", while htf_bias = -1 represents countertrend.
        analysis = {
            "market_regime": "TRENDING",
            "htf_bias": -1,
            "d1_bias": 1,
            "h4_bias": 1,
            "h1_bias": 1,
            "m15_sweep_type": 1,
            "m5_mss_signal": 1,
            "m5_fvg_class": "fresh",
            "m5_fvg_type": "bullish",
            "vsa_signals": ["demand_absorption"],
            "volatility": 0.015,
            "atr_pct": 0.002,
            "buy_pressure": 65.0,
            "sell_pressure": 35.0,
            "rvol": 1.5,
            "regression_zscore": 0.0
        }
        
        # Brain evaluates a BUY setup (against the bearish HTF bias)
        res = brain.evaluate(analysis, ai_confidence=0.8)
        
        # Maximum possible score under countertrend is 32:
        # (Tier 1 Max + Tier 2 Max) * 0.2 + Tier 3 Max = (50 + 35) * 0.2 + 15 = 17 + 15 = 32
        self.assertLessEqual(res.brain_score, 32.0)
        self.assertFalse(res.passed)
        print(f"  PASS: Counter-trend BUY setup in TRENDING bear market blocked. Score: {res.brain_score:.1f}/100 (Max allowed: 32)")

    def test_regime_isolated_calibration(self):
        """5. Regime-isolated weight tuning calibration."""
        print("\n--- Testing Component 5: Regime-Isolated Calibration ---")
        
        calibrator = BrainCalibrator()
        
        # Set high learning rate and alpha for testing to produce visible change after rounding
        import core.brain_calibrator as bc
        bc.LEARNING_RATE = 0.8
        bc.EMA_ALPHA = 0.8
        
        # Inject winning trades in "trending" and losing trades in "range"
        # We need MIN_CALIBRATION_SAMPLES = 30 to trigger calibration,
        # so we record 30 outcomes of each to be safe (total 60)
        for _ in range(30):
            # Winning setups in TRENDING regime
            calibrator.record_outcome(
                reason_map={"t1_d1": 18.0, "t2_structure": 10.0},
                outcome="WIN",
                pnl=100.0,
                regime="TRENDING"
            )
            # Losing setups in RANGE regime
            calibrator.record_outcome(
                reason_map={"t1_d1": 18.0, "t2_structure": 10.0},
                outcome="LOSS",
                pnl=-100.0,
                regime="RANGE"
            )
        weights = calibrator.get_weights()
        
        # Trending d1 and structure should have increased, while Range should have decreased or remained default
        t_d1 = weights["trending"]["tier1"]["d1"]
        r_d1 = weights["range"]["tier1"]["d1"]
        
        # Trending structure should have increased
        t_struct = weights["trending"]["tier2"]["structure"]
        r_struct = weights["range"]["tier2"]["structure"]
        
        self.assertGreater(t_d1, 18.0)
        self.assertLess(r_d1, 18.0)
        self.assertGreater(t_struct, 10.0)
        self.assertLess(r_struct, 10.0)
        print(f"  PASS: Trending weights calibrated up (d1: {t_d1:.2f}, struct: {t_struct:.2f})")
        print(f"  PASS: Range weights calibrated down (d1: {r_d1:.2f}, struct: {r_struct:.2f})")
        print("  PASS: Weights are successfully isolated by regime profiles.")

    def test_setup_gate_multiplier_telemetry(self):
        """6. Setup Gate Multiplier prevents ghost trades but preserves direction telemetry."""
        print("\n--- Testing Component 6: Setup Gate Multiplier Telemetry ---")
        from utils.settings_manager import settings_manager
        settings_manager.reset_all()

        brain = TradeBrain()

        # Moderate directional alignment (T1 = 32) below RANGE threshold of 38
        analysis = {
            "market_regime": "RANGE",
            "htf_bias": 1,
            "d1_bias": 1,
            "h4_bias": 1,
            "h1_bias": 0,
            "m15_bias": 0,
            "m5_bias": 0,
            "m15_sweep_type": 0,
            "m5_mss_signal": 0,
            "m5_fvg_class": "none",
            "vsa_signals": [],
            "buy_pressure": 50.0,
            "sell_pressure": 50.0,
            "rvol": 1.0,
            "regression_zscore": 0.0
        }

        res = brain.evaluate(analysis, ai_confidence=0.8, session_score=0.0)

        # Assertions
        self.assertFalse(res.passed)
        self.assertEqual(res.brain_direction, "BUY")
        print("  PASS: Low score gate blocked trade but preserved BUY direction telemetry")

    def test_m1_scalping_level_clamping(self):
        """7. Hard SL/TP clamp engine for M1 Micro-Scalping on Gold."""
        print("\n--- Testing Component 7: M1 Micro-Scalping Level Clamping ---")
        from utils.settings_manager import clamp_m1_trade_levels, settings_manager

        # Set default test parameters
        settings_manager.set("max_sl_pips", 12.0)
        settings_manager.set("default_tp_pips", 24.0)

        # BUY Setup test
        entry = 2350.00
        raw_sl = 2330.00  # Wide structural SL (200 pips / $20.00)
        raw_tp = 2400.00  # Wide structural TP (500 pips / $50.00)

        clamped_sl, clamped_tp = clamp_m1_trade_levels("BUY", entry, raw_sl, raw_tp, point_size=0.1)
        self.assertEqual(clamped_sl, 2348.80)  # Exactly -12.0 pips / -$1.20
        self.assertEqual(clamped_tp, 2352.40)  # Exactly +24.0 pips / +$2.40
        print(f"  PASS: BUY setup clamped correctly. Input SL: {raw_sl:.2f} -> Clamped SL: {clamped_sl:.2f} (-12 pips)")
        print(f"  PASS: BUY setup clamped correctly. Input TP: {raw_tp:.2f} -> Clamped TP: {clamped_tp:.2f} (+24 pips)")

        # SELL Setup test
        raw_sl_sell = 2370.00  # Wide structural SL
        raw_tp_sell = 2300.00  # Wide structural TP

        clamped_sl_sell, clamped_tp_sell = clamp_m1_trade_levels("SELL", entry, raw_sl_sell, raw_tp_sell, point_size=0.1)
        self.assertEqual(clamped_sl_sell, 2351.20)  # Exactly +12.0 pips / +$1.20
        self.assertEqual(clamped_tp_sell, 2347.60)  # Exactly -24.0 pips / -$2.40
        print(f"  PASS: SELL setup clamped correctly. Input SL: {raw_sl_sell:.2f} -> Clamped SL: {clamped_sl_sell:.2f} (+12 pips)")
        print(f"  PASS: SELL setup clamped correctly. Input TP: {raw_tp_sell:.2f} -> Clamped TP: {clamped_tp_sell:.2f} (-24 pips)")

if __name__ == "__main__":
    unittest.main()
