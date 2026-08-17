# core/brain_calibrator.py
"""
PulseViper TradeBrain Calibrator.
Tracks component win-rate statistics from closed trades and adjusts component weights using an EMA loop.
Isolates weight arrays by active market regime (trending vs range) and normalizes weights.
"""
import os
import json
import logging
from typing import Dict, List, Optional

CALIBRATION_FILE = "data/brain_weights.json"
MIN_CALIBRATION_SAMPLES = 30
LEARNING_RATE = 0.05
EMA_ALPHA = 0.1

DEFAULT_T1_WEIGHTS = {
    "d1": 18.0,
    "h4": 14.0,
    "h1": 11.0,
    "m15": 5.0,
    "m5": 2.0
}

DEFAULT_T2_WEIGHTS = {
    "structure": 10.0,
    "fvg": 5.0,
    "vsa": 4.0,
    "volume": 1.5,
    "liquidity": 1.5,
    "statistical_bounds": 5.0,
    "ai_confidence": 8.0
}

class BrainCalibrator:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.BrainCalibrator")
        self._trade_log: List[Dict] = []
        self._weights = self._load_weights()

    def get_weights(self) -> Dict:
        """Return the current active weights dictionary."""
        return self._weights

    def _load_weights(self) -> Dict:
        """Load weights from file or initialize with isolated regime defaults."""
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, "r") as f:
                    data = json.load(f)
                    if "trending" in data and "range" in data:
                        self.logger.info(f"Loaded calibrated weights from {CALIBRATION_FILE}")
                        return data
            except Exception as e:
                self.logger.error(f"Error reading calibrated weights: {e}")

        # Isolated default weight arrays by regime (lowercased key matching)
        return {
            "trending": {
                "tier1": dict(DEFAULT_T1_WEIGHTS),
                "tier2": dict(DEFAULT_T2_WEIGHTS)
            },
            "range": {
                "tier1": dict(DEFAULT_T1_WEIGHTS),
                "tier2": dict(DEFAULT_T2_WEIGHTS)
            }
        }

    def _save_weights(self):
        """Save the calibrated weights to file."""
        try:
            os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
            with open(CALIBRATION_FILE, "w") as f:
                json.dump(self._weights, f, indent=4)
            self.logger.info(f"Saved calibrated weights to {CALIBRATION_FILE}")
        except Exception as e:
            self.logger.error(f"Failed to save calibrated weights: {e}")

    def record_outcome(self, reason_map: Dict, outcome: str, pnl: float, regime: str = "RANGE"):
        """
        Record the closed trade details with its active regime context.
        outcome: "WIN" (PnL > 0), "LOSS" (PnL < 0), or "BE" (PnL = 0)
        """
        if not reason_map:
            return

        self._trade_log.append({
            "reason_map": reason_map,
            "outcome": outcome,
            "pnl": pnl,
            "regime": str(regime).upper()
        })

        # Run calibration check
        if len(self._trade_log) >= 5:
            self.calibrate()

    def calibrate(self):
        """
        Analyze trade outcomes separately by market regime and recalibrate weights.
        """
        if len(self._trade_log) < MIN_CALIBRATION_SAMPLES:
            self.logger.debug(
                f"Calibrator: {len(self._trade_log)}/{MIN_CALIBRATION_SAMPLES} trades logged. Skipping update."
            )
            return

        # Perform isolated adjustments for both regimes
        for r_type in ["TRENDING", "RANGE"]:
            regime_trades = [t for t in self._trade_log if t.get("regime") == r_type]
            if len(regime_trades) < 10:
                # Need at least 10 trades in this specific regime context to run calibration
                continue

            self.logger.info(f"Calibrating weights for regime {r_type} over {len(regime_trades)} trades...")
            r_key = r_type.lower()

            # 1. Update Tier 1 weights
            t1_updated = {}
            for key in DEFAULT_T1_WEIGHTS.keys():
                t1_updated[key] = self._calibrate_component_regime(f"t1_{key}", self._weights[r_key]["tier1"][key], regime_trades)
            
            # Normalize and bound Tier 1
            self._weights[r_key]["tier1"] = self._allocate_constrained_weights(t1_updated, DEFAULT_T1_WEIGHTS, 50.0)

            # 2. Update Tier 2 weights
            t2_updated = {}
            for key in DEFAULT_T2_WEIGHTS.keys():
                t2_updated[key] = self._calibrate_component_regime(f"t2_{key}", self._weights[r_key]["tier2"][key], regime_trades)

            # Normalize and bound Tier 2
            self._weights[r_key]["tier2"] = self._allocate_constrained_weights(t2_updated, DEFAULT_T2_WEIGHTS, 35.0)

        # Save results
        self._save_weights()

    def _calibrate_component_regime(self, reason_key: str, current_weight: float, trades: List[Dict]) -> float:
        """
        Compute the win rate of trades in a specific subset where this component was active.
        Applies learning rate and updates weight via EMA.
        """
        active_trades = []
        wins = 0

        for trade in trades:
            reason_map = trade["reason_map"]
            outcome = trade["outcome"]
            val = reason_map.get(reason_key, 0.0)

            # A component was active if its contribution was non-zero
            if abs(val) > 0.01:
                active_trades.append(trade)
                if outcome == "WIN":
                    wins += 1

        total_active = len(active_trades)
        if total_active < 3:
            # Not enough samples in this regime subset for this component, keep current weight
            return current_weight

        win_rate = wins / total_active
        baseline = 0.50

        # Adjust weight based on performance relative to baseline
        adjustment = (win_rate - baseline) * LEARNING_RATE
        updated_weight = current_weight + adjustment

        # Apply EMA
        new_weight = current_weight * (1.0 - EMA_ALPHA) + updated_weight * EMA_ALPHA
        return new_weight

    def _allocate_constrained_weights(
        self, target_weights: Dict[str, float], default_weights: Dict[str, float], total_target_sum: float
    ) -> Dict[str, float]:
        """Iteratively updates weights to satisfy bounds and sum constraints precisely."""
        weights = {k: v for k, v in target_weights.items()}
        for _ in range(10): # Iterative convergence loop
            current_sum = sum(weights.values())
            if abs(current_sum - total_target_sum) < 1e-4:
                break
            scaling_factor = total_target_sum / current_sum if current_sum > 0 else 1.0
            
            for k in weights:
                weights[k] *= scaling_factor
                min_w = default_weights[k] * 0.85
                max_w = default_weights[k] * 1.15
                weights[k] = max(min_w, min(max_w, weights[k]))
                
        rounded_weights = {k: round(v, 2) for k, v in weights.items()}
        diff = total_target_sum - sum(rounded_weights.values())
        if abs(diff) > 0.001:
            largest_key = max(rounded_weights, key=rounded_weights.get)
            rounded_weights[largest_key] = round(rounded_weights[largest_key] + diff, 2)
            
        return rounded_weights
