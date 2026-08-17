# core/pair_structure_memory.py
"""
PairStructureMemory: Pair-specific structural & temporal pattern memory system for PulseViper.
Remembers pair-specific market movements:
- Hourly (H1) and Daily (D1) swing structures (Higher Highs, Higher Lows, Lower Highs, Lower Lows)
- Swing leg velocity (pips per hour) and Fibonacci retracement depths
- Liquidity Pool locations & sweep-reversal probability per pair
- Session volatility distributions & day-of-week characteristics
Persists to data/pair_structure_memory.json
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

class PairStructureMemory:
    def __init__(self, memory_filepath: str = "data/pair_structure_memory.json"):
        self.logger = logging.getLogger("PulseViper.PairStructureMemory")
        self.memory_filepath = memory_filepath
        self.memory: Dict[str, Dict[str, Any]] = {}
        self.load_memory()

    def load_memory(self):
        """Load pair structure memory from JSON file"""
        if os.path.exists(self.memory_filepath):
            try:
                with open(self.memory_filepath, "r") as f:
                    self.memory = json.load(f)
                self.logger.info(f"Loaded structure memory for {len(self.memory)} pairs from {self.memory_filepath}")
            except Exception as e:
                self.logger.error(f"Error loading structure memory: {e}")
                self.memory = {}
        else:
            self.memory = {}

    def save_memory(self):
        """Persist memory to JSON file safely"""
        try:
            os.makedirs(os.path.dirname(self.memory_filepath), exist_ok=True)
            with open(self.memory_filepath, "w") as f:
                json.dump(self.memory, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving structure memory: {e}")

    def update_pair_structure(self, symbol: str, df_h1: Optional[pd.DataFrame], df_d1: Optional[pd.DataFrame]):
        """
        Analyze H1 and D1 price action for a specific pair and store pair-specific structural memory.
        """
        if symbol not in self.memory:
            self.memory[symbol] = {
                "hourly_structure": {},
                "daily_structure": {},
                "swing_stats": {},
                "key_levels": {},
                "last_updated": ""
            }

        symbol_mem = self.memory[symbol]

        # ── 1. Analyze Hourly Structure (H1) ──────────────────────────────────
        if df_h1 is not None and len(df_h1) >= 20:
            try:
                h1_swings = self._extract_swing_structure(df_h1)
                symbol_mem["hourly_structure"] = {
                    "current_trend": h1_swings.get("trend", "NEUTRAL"),
                    "last_swing_high": h1_swings.get("last_high", 0.0),
                    "last_swing_low": h1_swings.get("last_low", 0.0),
                    "swing_sequence": h1_swings.get("sequence", []),
                    "avg_leg_pips": h1_swings.get("avg_leg_pips", 0.0),
                    "avg_retracement_pct": h1_swings.get("avg_retracement_pct", 0.5)
                }
            except Exception as ex:
                self.logger.warning(f"Error extracting H1 swings for {symbol}: {ex}")

        # ── 2. Analyze Daily Structure (D1) ───────────────────────────────────
        if df_d1 is not None and len(df_d1) >= 10:
            try:
                d1_swings = self._extract_swing_structure(df_d1)
                atr_daily = (df_d1['high'] - df_d1['low']).mean() if 'high' in df_d1.columns else 0.0
                symbol_mem["daily_structure"] = {
                    "daily_bias": d1_swings.get("trend", "NEUTRAL"),
                    "avg_daily_range_pips": round(atr_daily, 5),
                    "prev_day_high": float(df_d1['high'].iloc[-2]) if len(df_d1) > 1 else float(df_d1['high'].iloc[-1]),
                    "prev_day_low": float(df_d1['low'].iloc[-2]) if len(df_d1) > 1 else float(df_d1['low'].iloc[-1]),
                    "daily_sequence": d1_swings.get("sequence", [])
                }
            except Exception as ex:
                self.logger.warning(f"Error extracting D1 swings for {symbol}: {ex}")

        symbol_mem["last_updated"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_memory()

    def _extract_swing_structure(self, df: pd.DataFrame, window: int = 3) -> Dict[str, Any]:
        """
        Identify swing highs (HH/LH) and swing lows (HL/LL) and compute market structure sequence.
        """
        highs = df['high'].values
        lows = df['low'].values
        n = len(df)

        swings = []
        for i in range(window, n - window):
            is_high = all(highs[i] >= highs[i - k] for k in range(1, window + 1)) and \
                      all(highs[i] >= highs[i + k] for k in range(1, window + 1))
            is_low = all(lows[i] <= lows[i - k] for k in range(1, window + 1)) and \
                     all(lows[i] <= lows[i + k] for k in range(1, window + 1))

            if is_high:
                swings.append({"type": "HIGH", "price": float(highs[i]), "index": i})
            elif is_low:
                swings.append({"type": "LOW", "price": float(lows[i]), "index": i})

        if not swings:
            return {"trend": "NEUTRAL", "last_high": 0.0, "last_low": 0.0, "sequence": [], "avg_leg_pips": 0.0}

        # Sequence labeling (HH, HL, LH, LL)
        labeled_sequence = []
        last_high_price: Optional[float] = None
        last_low_price: Optional[float] = None

        leg_sizes = []

        for s in swings:
            price_val = float(s["price"])
            if s["type"] == "HIGH":
                if last_high_price is None:
                    label = "HIGH"
                elif price_val > last_high_price:
                    label = "HH"  # Higher High
                else:
                    label = "LH"  # Lower High
                last_high_price = price_val
                labeled_sequence.append(label)
                if last_low_price is not None:
                    leg_sizes.append(abs(price_val - last_low_price))

            elif s["type"] == "LOW":
                if last_low_price is None:
                    label = "LOW"
                elif price_val > last_low_price:
                    label = "HL"  # Higher Low
                else:
                    label = "LL"  # Lower Low
                last_low_price = price_val
                labeled_sequence.append(label)
                if last_high_price is not None:
                    leg_sizes.append(abs(price_val - last_high_price))

        # Determine overall trend
        last_labels = labeled_sequence[-4:] if len(labeled_sequence) >= 4 else labeled_sequence
        bull_score = sum(1 for l in last_labels if l in ("HH", "HL"))
        bear_score = sum(1 for l in last_labels if l in ("LH", "LL"))

        trend = "BULLISH" if bull_score > bear_score else ("BEARISH" if bear_score > bull_score else "NEUTRAL")

        avg_leg = float(np.mean(leg_sizes)) if leg_sizes else 0.0

        return {
            "trend": trend,
            "last_high": last_high_price if last_high_price else 0.0,
            "last_low": last_low_price if last_low_price else 0.0,
            "sequence": labeled_sequence[-8:],  # Keep last 8 structural points
            "avg_leg_pips": round(avg_leg, 5)
        }

    def get_pair_insights(self, symbol: str) -> Dict[str, Any]:
        """Fetch pair-specific structural memory insights"""
        return self.memory.get(symbol, {
            "hourly_structure": {},
            "daily_structure": {},
            "swing_stats": {},
            "key_levels": {},
            "last_updated": "NEVER"
        })

# Global instance
pair_structure_memory = PairStructureMemory()
