# core/data_quality.py
import logging
from typing import Dict, Any, List
from core.bar_normalizer import TimeframeDataSnapshot

class DataQualityGate:
    """Enforces strict checks on market data inputs to detect skew, missing intervals, or bad geometry."""
    
    def __init__(self, min_warmup_bars: int = 100, max_missing_pct: float = 10.0, max_stale_seconds: float = 300.0):
        self.logger = logging.getLogger("PulseViper.DataQualityGate")
        self.min_warmup_bars = min_warmup_bars
        self.max_missing_pct = max_missing_pct
        self.max_stale_seconds = max_stale_seconds

    def check(self, snapshot: TimeframeDataSnapshot, current_spread: float, current_atr: float) -> Dict[str, Any]:
        """
        Runs quality checks. Returns a report dictionary.
        If 'critical_failure' is True, downstream logic should reject setup with ABSTAIN_DATA_QUALITY.
        """
        errors: List[str] = []
        warnings: List[str] = []
        critical_failure = False

        # 1. Warm-up check
        if snapshot.actual_bar_count < self.min_warmup_bars:
            errors.append(f"Insufficient bars: {snapshot.actual_bar_count} < {self.min_warmup_bars}")
            critical_failure = True

        # 2. Stale check
        if snapshot.stale_seconds > self.max_stale_seconds:
            errors.append(f"Data stale: {snapshot.stale_seconds:.1f}s > {self.max_stale_seconds}s")
            critical_failure = True

        # 3. Missing interval percentage
        if snapshot.expected_bar_count > 0:
            missing_pct = (snapshot.missing_bar_count / snapshot.expected_bar_count) * 100.0
            if missing_pct > self.max_missing_pct:
                errors.append(f"Excessive missing intervals: {missing_pct:.1f}% > {self.max_missing_pct}%")
                critical_failure = True
            elif missing_pct > 3.0:
                warnings.append(f"Elevated missing intervals: {missing_pct:.1f}%")

        # 4. Monotonicity and geometry checks
        last_t = None
        for idx, bar in enumerate(snapshot.bars):
            t = bar["time"]
            o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

            # Chronological strictly increasing
            if last_t is not None and t <= last_t:
                errors.append(f"Non-increasing timestamp at index {idx}: {t} <= {last_t}")
                critical_failure = True

            # Geometry
            if o <= 0.0 or h <= 0.0 or l <= 0.0 or c <= 0.0:
                errors.append(f"Invalid non-positive price at index {idx}: OHLC=({o},{h},{l},{c})")
                critical_failure = True

            if h < o or h < c or l > o or l > c or h < l:
                errors.append(f"Invalid OHLC geometry at index {idx}: OHLC=({o},{h},{l},{c})")
                critical_failure = True

            last_t = t

        # 5. Volatility and Spread Checks
        if current_spread is None or current_spread < 0.0:
            errors.append("Invalid or missing spread value")
            critical_failure = True
            
        if current_atr is None or current_atr <= 0.0:
            errors.append("Invalid or missing ATR value")
            critical_failure = True

        if critical_failure:
            self.logger.error(f"❌ DataQualityGate Critical Failure on {snapshot.symbol} {snapshot.timeframe}: {errors}")
        elif warnings:
            self.logger.warning(f"⚠️ DataQualityGate Warning on {snapshot.symbol} {snapshot.timeframe}: {warnings}")

        return {
            "critical_failure": critical_failure,
            "errors": errors,
            "warnings": warnings,
            "missing_pct": (snapshot.missing_bar_count / snapshot.expected_bar_count * 100.0) if snapshot.expected_bar_count > 0 else 0.0,
            "stale_seconds": snapshot.stale_seconds,
            "quality_score": 0.0 if critical_failure else max(0.0, 100.0 - len(warnings) * 5.0)
        }
