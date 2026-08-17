# utils/order_flow_traffic_survey.py
"""
Quantum Viper 3.0 — Real-Time Order Flow & Delta Traffic Survey Engine
Specially engineered for Gold (XAUUSDm) on Exness (24-28 pip spread environment).

Core Architecture:
1. Direct Tick-Level Streaming via MT5 Gateway (copy_ticks_from).
2. Transaction Classification: Aggressive Buy (Ask) vs Aggressive Sell (Bid).
3. Order Flow Delta & Cumulative Volume Delta (CVD) Computation.
4. Liquidity Sweep Trap Divergence (Institutional Absorption Detection).
5. PyTorch Feature Tensor Generation (Tick Delta + Volume Imbalance Features).
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
from utils.mt5_gateway import mt5_gateway as mt5

logger = logging.getLogger("PulseViper.OrderFlowTrafficSurvey")


class OrderFlowTrafficSurvey:
    """Real-time Tick-Level Order Flow & Delta Analysis Engine."""

    def __init__(self, tick_window: int = 2000):
        self.tick_window = tick_window
        self.cvd_history = []

    def fetch_recent_ticks(self, symbol: str, num_ticks: int = 1000) -> Optional[pd.DataFrame]:
        """Streams raw tick data directly from MT5 terminal."""
        try:
            now_utc = datetime.now(timezone.utc)
            ticks = mt5.copy_ticks_from(symbol, now_utc, num_ticks, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                return None
            df = pd.DataFrame(ticks)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            logger.warning(f"Error fetching tick data for {symbol}: {e}")
            return None

    def calculate_delta_and_cvd(self, df_ticks: pd.DataFrame) -> Dict[str, Any]:
        """
        Classifies aggressive buy/sell transactions and computes Delta & CVD metrics.
        - Aggressive Buy: Executed at Ask (TICK_FLAG_BUY = 1024 or price >= ask)
        - Aggressive Sell: Executed at Bid (TICK_FLAG_SELL = 2048 or price <= bid)
        """
        if df_ticks is None or len(df_ticks) == 0:
            return {"delta": 0.0, "buy_volume": 0.0, "sell_volume": 0.0, "cvd": 0.0, "ofi_ratio": 0.0}

        flags = df_ticks['flags'].values if 'flags' in df_ticks.columns else np.zeros(len(df_ticks))
        prices = df_ticks['last'].values if 'last' in df_ticks.columns else df_ticks['bid'].values
        volumes = df_ticks['volume'].values if 'volume' in df_ticks.columns else np.ones(len(df_ticks))

        if np.all(volumes <= 0):
            volumes = np.ones(len(prices))

        asks = df_ticks['ask'].values if 'ask' in df_ticks.columns else prices
        bids = df_ticks['bid'].values if 'bid' in df_ticks.columns else prices

        # Flag-based & Price-boundary vectorized classification
        flags_int = flags.astype(np.int64)
        is_buy = (flags_int & 1024) > 0
        is_sell = (flags_int & 2048) > 0

        unclassified = ~(is_buy | is_sell)
        if np.any(unclassified):
            is_buy[unclassified] = prices[unclassified] >= (asks[unclassified] - 1e-6)
            is_sell[unclassified] = prices[unclassified] <= (bids[unclassified] + 1e-6)

        buy_vol = float(np.sum(volumes[is_buy]))
        sell_vol = float(np.sum(volumes[is_sell]))
        delta = buy_vol - sell_vol

        total_vol = buy_vol + sell_vol
        ofi_ratio = (delta / total_vol) if total_vol > 0 else 0.0

        # Update Cumulative Volume Delta (CVD)
        self.cvd_history.append(delta)
        if len(self.cvd_history) > 100:
            self.cvd_history.pop(0)

        cvd = float(np.sum(self.cvd_history))

        return {
            "delta": delta,
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "total_volume": total_vol,
            "cvd": cvd,
            "ofi_ratio": ofi_ratio
        }

    def detect_trap_divergence(
        self, df_ticks: pd.DataFrame, current_price: float, swing_high: float, swing_low: float
    ) -> Tuple[Optional[str], float, str]:
        """
        Detects Order Flow Traps (Price vs Cumulative Delta Divergences):
        1. Bullish Sweep Trap: Price drops breaking swing low while Delta turns heavily positive (Institutional Absorption BUY).
        2. Bearish Sweep Trap: Price spikes breaking swing high while Delta turns heavily negative (Institutional Absorption SELL).
        """
        metrics = self.calculate_delta_and_cvd(df_ticks)
        delta = metrics["delta"]
        ofi_ratio = metrics["ofi_ratio"]

        swing_range = max(swing_high - swing_low, 0.0001)

        # 1. Bullish Trap Divergence: Price near or below swing low, but Delta is strongly positive
        if current_price <= (swing_low + 0.20 * swing_range) and (delta > 0 or ofi_ratio >= 0.15):
            reason = f"BULLISH_TRAP_ABSORPTION (Price @ {current_price:.2f} near low {swing_low:.2f}, Delta: +{delta:.1f})"
            logger.info(f"💎 [ORDER_FLOW_TRAP] {reason}")
            return "BUY", 0.90, reason

        # 2. Bearish Trap Divergence: Price near or above swing high, but Delta is strongly negative
        if current_price >= (swing_high - 0.20 * swing_range) and (delta < 0 or ofi_ratio <= -0.15):
            reason = f"BEARISH_TRAP_ABSORPTION (Price @ {current_price:.2f} near high {swing_high:.2f}, Delta: {delta:.1f})"
            logger.info(f"🔻 [ORDER_FLOW_TRAP] {reason}")
            return "SELL", 0.90, reason

        return None, 0.0, "NO_DIVERGENCE"

    def detect_m1_micro_burst(self, df_ticks: pd.DataFrame, time_window_seconds: int = 15) -> dict:
        """
        Analyzes tick traffic in the last N seconds of the forming M1 candle
        to catch immediate institutional absorption or volume acceleration.
        """
        if df_ticks is None or len(df_ticks) == 0:
            return {"burst_detected": False, "bias": "NEUTRAL"}
            
        if 'time' in df_ticks.columns and len(df_ticks) > 0:
            now = df_ticks['time'].iloc[-1]
            recent_ticks = df_ticks[df_ticks['time'] >= (now - pd.Timedelta(seconds=time_window_seconds))]
        else:
            recent_ticks = df_ticks.tail(20)
            
        if len(recent_ticks) < 10:
            return {"burst_detected": False, "bias": "NEUTRAL"}
            
        metrics = self.calculate_delta_and_cvd(pd.DataFrame(recent_ticks))
        
        # High tick velocity in N seconds
        tick_velocity = len(recent_ticks) / float(time_window_seconds)
        
        if tick_velocity > 5.0 and abs(metrics["ofi_ratio"]) >= 0.25:
            bias = "BUY" if metrics["delta"] > 0 else "SELL"
            return {
                "burst_detected": True,
                "bias": bias,
                "ofi_ratio": metrics["ofi_ratio"],
                "delta": metrics["delta"],
                "velocity": tick_velocity
            }
            
        return {"burst_detected": False, "bias": "NEUTRAL"}

    def extract_nn_feature_vector(self, symbol: str) -> np.ndarray:
        """
        Extracts 30-dimensional Tick Order Flow & Delta Feature Tensor for PyTorch Neural Network input.
        """
        df_ticks = self.fetch_recent_ticks(symbol, num_ticks=1000)
        metrics = self.calculate_delta_and_cvd(df_ticks if df_ticks is not None else pd.DataFrame())

        features = np.zeros(30, dtype=np.float32)
        features[0] = metrics["delta"]
        features[1] = metrics["buy_volume"]
        features[2] = metrics["sell_volume"]
        features[3] = metrics["cvd"]
        features[4] = metrics["ofi_ratio"]

        if df_ticks is not None and len(df_ticks) > 1:
            prices = df_ticks['bid'].values
            features[5] = float(np.std(prices))
            features[6] = float(prices[-1] - prices[0])

        return features


# Global singleton instance
traffic_survey_engine = OrderFlowTrafficSurvey()
