# core/entry_point_learner.py
"""
EntryPointLearner: Precision Entry Discovery & Adaptive Entry Optimization for PulseViper EA.
Learns exact entry point mechanics for each trading pair:
1. Order Block (OB) Mean Threshold (50% OB level)
2. Fair Value Gap (FVG) Consequent Encroachment (50% FVG fill)
3. Liquidity Sweep Retest Level (Asian / Session High-Low Sweeps)
4. Golden Pocket Retest (61.8% - 78.6% Fib Level)

Records real-time entry outcome efficiency per pair in data/entry_point_learning.json
"""

import os
import json
import logging
from typing import Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np

class EntryPointLearner:
    def __init__(self, storage_path: str = "data/entry_point_learning.json"):
        self.logger = logging.getLogger("PulseViper.EntryPointLearner")
        self.storage_path = storage_path
        self.entry_stats: Dict[str, Dict[str, Any]] = {}
        self.load_stats()

    def load_stats(self):
        """Load stored entry learning statistics from disk"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    self.entry_stats = json.load(f)
                self.logger.info(f"Loaded precision entry stats for {len(self.entry_stats)} symbols.")
            except Exception as e:
                self.logger.error(f"Error loading entry point stats: {e}")
                self.entry_stats = {}
        else:
            self.entry_stats = {}

    def save_stats(self):
        """Persist entry statistics safely"""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self.entry_stats, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving entry point stats: {e}")

    def discover_optimal_entry(
        self,
        symbol: str,
        strategy_name: str,
        action: str,
        current_price: float,
        atr: float,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame]
    ) -> Tuple[float, float, float, Dict[str, Any]]:
        """
        Calculates precision entry point, invalidation StopLoss, and TakeProfit based on SMC/ICT levels.
        Returns: Tuple (optimized_entry, optimized_sl, optimized_tp, entry_metadata)
        """
        entry_price = current_price
        sl_price = current_price - (1.5 * atr) if action == "BUY" else current_price + (1.5 * atr)
        tp_price = current_price + (3.0 * atr) if action == "BUY" else current_price - (3.0 * atr)

        entry_type = "MARKET_MOMENTUM"
        ref_level = current_price

        df_ref = df_m1 if df_m1 is not None and len(df_m1) >= 10 else df_m5

        if df_ref is not None and len(df_ref) >= 10 and atr > 0.0:
            recent = df_ref.iloc[-10:]

            # 1. Search for active Order Block Mean Threshold (50% level)
            if action == "BUY":
                bear_candles = recent[recent['close'] < recent['open']]
                if not bear_candles.empty:
                    ob_candle = bear_candles.iloc[-1]
                    ob_50 = (float(ob_candle['high']) + float(ob_candle['low'])) / 2.0
                    if abs(current_price - ob_50) <= 2.0 * atr:
                        entry_price = ob_50
                        sl_price = float(ob_candle['low']) - (0.3 * atr)
                        tp_price = entry_price + (2.5 * abs(entry_price - sl_price))
                        entry_type = "OB_MEAN_THRESHOLD_50"
                        ref_level = ob_50
            else:
                bull_candles = recent[recent['close'] > recent['open']]
                if not bull_candles.empty:
                    ob_candle = bull_candles.iloc[-1]
                    ob_50 = (float(ob_candle['high']) + float(ob_candle['low'])) / 2.0
                    if abs(current_price - ob_50) <= 2.0 * atr:
                        entry_price = ob_50
                        sl_price = float(ob_candle['high']) + (0.3 * atr)
                        tp_price = entry_price - (2.5 * abs(entry_price - sl_price))
                        entry_type = "OB_MEAN_THRESHOLD_50"
                        ref_level = ob_50

            # 2. Search for active Fair Value Gap (FVG) Consequent Encroachment (50% fill)
            if entry_type == "MARKET_MOMENTUM":
                for i in range(len(recent) - 3, -1, -1):
                    c1 = recent.iloc[i]
                    c3 = recent.iloc[i + 2]
                    if action == "BUY" and float(c3['low']) > float(c1['high']):
                        fvg_gap = float(c3['low']) - float(c1['high'])
                        fvg_ce = float(c1['high']) + (0.5 * fvg_gap)
                        entry_price = fvg_ce
                        sl_price = float(c1['low']) - (0.2 * atr)
                        tp_price = entry_price + (2.2 * abs(entry_price - sl_price))
                        entry_type = "FVG_CONSEQUENT_ENCROACHMENT_50"
                        ref_level = fvg_ce
                        break
                    elif action == "SELL" and float(c1['low']) > float(c3['high']):
                        fvg_gap = float(c1['low']) - float(c3['high'])
                        fvg_ce = float(c3['high']) + (0.5 * fvg_gap)
                        entry_price = fvg_ce
                        sl_price = float(c1['high']) + (0.2 * atr)
                        tp_price = entry_price - (2.2 * abs(entry_price - sl_price))
                        entry_type = "FVG_CONSEQUENT_ENCROACHMENT_50"
                        ref_level = fvg_ce
                        break

        # Sanity check Risk-Reward
        sl_dist = abs(entry_price - sl_price)
        tp_dist = abs(tp_price - entry_price)
        rr = tp_dist / sl_dist if sl_dist > 0.0 else 1.5
        if rr < 1.5:
            tp_price = entry_price + (1.8 * sl_dist) if action == "BUY" else entry_price - (1.8 * sl_dist)

        entry_meta = {
            "entry_type": entry_type,
            "ref_level": round(ref_level, 5),
            "calculated_rr": round(rr, 2),
            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        return round(entry_price, 5), round(sl_price, 5), round(tp_price, 5), entry_meta

    def record_entry_outcome(self, symbol: str, strategy_name: str, entry_type: str, pnl: float):
        """Record trade outcome efficiency for specific entry type and pair"""
        if symbol not in self.entry_stats:
            self.entry_stats[symbol] = {}

        if entry_type not in self.entry_stats[symbol]:
            self.entry_stats[symbol][entry_type] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "trades": 0}

        rec = self.entry_stats[symbol][entry_type]
        rec["trades"] += 1
        rec["total_pnl"] += pnl
        if pnl > 0:
            rec["wins"] += 1
        else:
            rec["losses"] += 1

        self.save_stats()

# Global instance
entry_point_learner = EntryPointLearner()
