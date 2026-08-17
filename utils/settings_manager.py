# utils/settings_manager.py
import os
import json
import logging
import threading
from typing import Any, Dict

DEFAULT_SETTINGS = {
    "paper_mode": True,
    "trading_mode": "scalping",  # "scalping", "intraday", "swing"
    "primary_timeframe": "M1",
    "use_tick_order_flow": True,
    "max_sl_pips": 12.0,
    "default_tp_pips": 24.0,
    "hedging_mode": False,
    "compounding_mode": False,
    "risk_percent": 0.05,
    "max_daily_trades": 100,
    "use_manual_lot": True,
    "manual_lot_size": 0.01,
    "london_session_enabled": True,
    "ny_session_enabled": True,
    "asian_session_enabled": False,
    "break_even_enabled": True,
    "break_even_pips": 8.0,
    "trailing_stop_enabled": True,
    "trailing_stop_pips": 10.0,
    "self_learning_filter": True,
    "news_filter_enabled": True,
    "use_manual_news_schedule": False,
    "use_live_news_feed": False,
    "max_spread_points": 350,
    "min_rr_ratio": 1.5,
    "auto_trade_enabled": True,
    "dynamic_risk_enabled": True,
    "dynamic_regime_filter": False,
    "killzone_filter_enabled": False,
    "news_lockout_minutes": 5,
    "news_cooldown_minutes": 5,
    "min_ai_confidence": 0.75,
    "max_entry_distance_atr_coef": 3.0,
    "vsa_filter_enabled": False,
    "disabled_setups": [],
    "max_portfolio_heat": 5.0,
    "token_expiry_seconds": 30.0,
    "max_validation_token_age_ms": 5000.0,
    "max_price_drift_points": 50.0,
    "strict_mode": False,
    "safety_engine_enabled": True,
    "emergency_hedging_enabled": True,
    "max_consecutive_losses": 10,
    "max_daily_drawdown_pct": 10.0,
    "max_weekly_drawdown_pct": 25.0,
    "settings_version": 1,
    "control_token": "super_secret_token",
    "active_symbol": "XAUUSDm",
    "allow_untokenized_orders": False
}

SCHEMA = {
    "paper_mode": {"type": bool},
    "trading_mode": {"type": str, "choices": ["scalping", "intraday", "swing"]},
    "primary_timeframe": {"type": str},
    "use_tick_order_flow": {"type": bool},
    "max_sl_pips": {"type": float, "min": 1.0, "max": 500.0},
    "default_tp_pips": {"type": float, "min": 1.0, "max": 1000.0},
    "hedging_mode": {"type": bool},
    "compounding_mode": {"type": bool},
    "risk_percent": {"type": float, "min": 0.0, "max": 0.3},
    "max_daily_trades": {"type": int, "min": 1, "max": 1000},
    "use_manual_lot": {"type": bool},
    "manual_lot_size": {"type": float, "min": 0.01, "max": 100.0},
    "london_session_enabled": {"type": bool},
    "ny_session_enabled": {"type": bool},
    "asian_session_enabled": {"type": bool},
    "break_even_enabled": {"type": bool},
    "break_even_pips": {"type": float, "min": 0.0, "max": 500.0},
    "trailing_stop_enabled": {"type": bool},
    "trailing_stop_pips": {"type": float, "min": 0.0, "max": 500.0},
    "self_learning_filter": {"type": bool},
    "news_filter_enabled": {"type": bool},
    "use_manual_news_schedule": {"type": bool},
    "use_live_news_feed": {"type": bool},
    "max_spread_points": {"type": int, "min": 1, "max": 10000},
    "min_rr_ratio": {"type": float, "min": 1.0, "max": 10.0},
    "auto_trade_enabled": {"type": bool},
    "dynamic_risk_enabled": {"type": bool},
    "dynamic_regime_filter": {"type": bool},
    "news_lockout_minutes": {"type": int, "min": 0, "max": 1440},
    "news_cooldown_minutes": {"type": int, "min": 0, "max": 1440},
    "min_ai_confidence": {"type": float, "min": 0.0, "max": 1.0},
    "max_entry_distance_atr_coef": {"type": float, "min": 0.1, "max": 50.0},
    "vsa_filter_enabled": {"type": bool},
    "killzone_filter_enabled": {"type": bool},
    "disabled_setups": {"type": list},
    "max_portfolio_heat": {"type": float, "min": 0.1, "max": 10.0},
    "token_expiry_seconds": {"type": float, "min": 1.0, "max": 60.0},
    "max_validation_token_age_ms": {"type": float, "min": 100.0, "max": 60000.0},
    "max_price_drift_points": {"type": float, "min": 0.0, "max": 200.0},
    "strict_mode": {"type": bool},
    "emergency_hedging_enabled": {"type": bool},
    "settings_version": {"type": int, "min": 1, "max": 1000000},
    "control_token": {"type": str},
    "active_symbol": {"type": str},
    "allow_untokenized_orders": {"type": bool}
}

AUDIT_LOG_FILE = "configs/settings_audit.json"

class SettingsManager:
    def __init__(self, filepath="configs/settings.json"):
        self.filepath = filepath
        self.logger = logging.getLogger("PulseViper.SettingsManager")
        self.settings = {}
        self.last_mtime = 0.0
        self._lock = threading.Lock()
        self.load_settings()

    def load_settings(self):
        """Load settings from JSON file thread-safely. Create defaults if not exists."""
        with self._lock:
            try:
                if os.path.exists(self.filepath):
                    mtime = os.path.getmtime(self.filepath)
                    if mtime == self.last_mtime and self.settings:
                        return
                    with open(self.filepath, "r") as f:
                        file_data = json.load(f)
                    
                    # Merge with default settings ensuring all fields are populated
                    merged = {**DEFAULT_SETTINGS}
                    for k, v in file_data.items():
                        if k in SCHEMA:
                            try:
                                merged[k] = self._validate_value(k, v)
                            except Exception as e:
                                self.logger.error(f"Validation failed for setting '{k}' during load: {e}")
                    
                    self.settings = merged
                    self.last_mtime = mtime
                else:
                    self.settings = DEFAULT_SETTINGS.copy()
                    self._save_settings_locked()
                    if os.path.exists(self.filepath):
                        self.last_mtime = os.path.getmtime(self.filepath)
                self.logger.info("Settings loaded and validated successfully")
            except Exception as e:
                self.logger.error(f"Failed to load settings: {e}")
                self.settings = DEFAULT_SETTINGS.copy()

    def _save_settings_locked(self):
        """Save settings atomically. Must be called while holding self._lock."""
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            temp_path = self.filepath + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(self.settings, f, indent=4)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass  # fsync may not be fully supported in mock testing environments
            os.replace(temp_path, self.filepath)
            self.last_mtime = os.path.getmtime(self.filepath)
        except Exception as e:
            self.logger.error(f"Failed to save settings atomically: {e}")

    def _validate_value(self, key: str, value: Any) -> Any:
        """Validate value type and range constraints strictly according to SCHEMA rules."""
        if key not in SCHEMA:
            raise KeyError(f"Setting key '{key}' is not allowed in whitelist.")
        rule = SCHEMA[key]
        expected_type: Any = rule["type"]
        
        # Implicit int to float promotion
        if expected_type is float and isinstance(value, int):
            value = float(value)
            
        if not isinstance(value, expected_type):  # type: ignore
            raise ValueError(f"Setting key '{key}' invalid type {type(value)}")
            
        choices = rule.get("choices")
        if choices and value not in choices:
            raise ValueError(f"Setting key '{key}' must be one of {choices}, got '{value}'")
            
        if type(value) in (int, float):
            min_val = rule.get("min")
            if min_val is not None and value < min_val:  # type: ignore
                raise ValueError(f"Setting key '{key}' value {value} is below minimum {min_val}")
                
            max_val = rule.get("max")
            if max_val is not None and value > max_val:  # type: ignore
                raise ValueError(f"Setting key '{key}' value {value} is above maximum {max_val}")
                
        return value

    def get(self, key: str, default: Any = None) -> Any:
        self.load_settings()
        with self._lock:
            return self.settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any, source: str = "SYSTEM", reason: str = "Unspecified") -> None:
        """Validates, sets, and atomically saves the new setting, writing to the audit log."""
        self.load_settings()
        validated_val = self._validate_value(key, value)
        
        with self._lock:
            old_val = self.settings.get(key)
            if old_val == validated_val:
                return
            
            self.settings[key] = validated_val
            # Increment version on modification
            new_version = self.settings.get("settings_version", 1) + 1
            self.settings["settings_version"] = new_version
            self._save_settings_locked()
            
            # Log audit trail record
            self._log_audit_record(key, old_val, validated_val, new_version, source, reason)
            self.logger.info(f"Setting updated: {key} = {validated_val} (version: {new_version}, source: {source})")

    def toggle(self, key: str, source: str = "SYSTEM", reason: str = "Toggle request") -> bool:
        """Toggle a boolean setting and save atomically."""
        val = self.get(key, False)
        if isinstance(val, bool):
            new_val = not val
            self.set(key, new_val, source=source, reason=reason)
            return new_val
        return val

    def get_all(self) -> Dict[str, Any]:
        self.load_settings()
        with self._lock:
            return self.settings.copy()

    def reset_all(self, source: str = "SYSTEM") -> None:
        with self._lock:
            self.settings = DEFAULT_SETTINGS.copy()
            self._save_settings_locked()
            self._log_audit_record("ALL_KEYS", "PRE_RESET", "RESET_TO_DEFAULTS", 1, source, "Reset settings requested")
            self.logger.info("All settings reset to defaults successfully.")

    def _log_audit_record(self, key: str, old_value: Any, new_value: Any, version: int, source: str, reason: str) -> None:
        """Persist a history record to the audit trails JSON file."""
        import time
        record = {
            "timestamp": time.time(),
            "key": key,
            "old_value": old_value,
            "new_value": new_value,
            "settings_version": version,
            "source": source,
            "reason": reason
        }
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
            records = []
            if os.path.exists(AUDIT_LOG_FILE):
                with open(AUDIT_LOG_FILE, "r") as f:
                    try:
                        records = json.load(f)
                        if not isinstance(records, list):
                            records = []
                    except Exception:
                        records = []
            
            records.append(record)
            # Limit audit log size to 1000 items
            if len(records) > 1000:
                records = records[-1000:]
                
            temp_audit = AUDIT_LOG_FILE + ".tmp"
            with open(temp_audit, "w") as f:
                json.dump(records, f, indent=4)
            os.replace(temp_audit, AUDIT_LOG_FILE)
        except Exception as e:
            self.logger.error(f"Failed to write settings audit log: {e}")

# Global singleton instance
settings_manager = SettingsManager()


def clamp_m1_trade_levels(order_type: str, entry_price: float, raw_sl: float, raw_tp: float, point_size: float = 0.1, symbol: str = "XAUUSDm") -> tuple:
    """
    Hard-clamps TP and SL for M1 micro-scalping on Gold.
    Ensures SL never exceeds MAX_SL_PIPS (12 pips = $1.20 movement) while satisfying Exness minimum stops level.
    """
    max_sl_pips = float(settings_manager.get("max_sl_pips", 12.0))
    default_tp_pips = float(settings_manager.get("default_tp_pips", 24.0))

    max_sl_dist = max_sl_pips * point_size   # 12 pips * 0.1 = 1.20
    target_tp_dist = default_tp_pips * point_size # 24 pips * 0.1 = 2.40

    if order_type.upper() == "BUY":
        # SL cannot be further than 12 pips below entry
        clamped_sl = max(raw_sl, entry_price - max_sl_dist)
        # Fix TP to micro-scalp target if structural TP is unrealistically far (> 35 pips)
        clamped_tp = entry_price + target_tp_dist if (raw_tp - entry_price) > (35.0 * point_size) else raw_tp
    else: # SELL
        # SL cannot be further than 12 pips above entry
        clamped_sl = min(raw_sl, entry_price + max_sl_dist)
        clamped_tp = entry_price - target_tp_dist if (entry_price - raw_tp) > (35.0 * point_size) else raw_tp

    return validate_and_clamp_stops(symbol, order_type, entry_price, clamped_sl, clamped_tp)


def validate_and_clamp_stops(symbol: str, order_type: str, entry_price: float, raw_sl: float, raw_tp: float) -> tuple:
    """
    Validates and clamps Stop Loss and Take Profit levels against Exness minimum stops level (SYMBOL_TRADE_STOPS_LEVEL).
    Prevents MT5 error 10016 (INVALID_STOPS) or 10015 (INVALID_PRICE).
    """
    from utils.mt5_gateway import mt5_gateway as mt5
    info = mt5.symbol_info(symbol)
    point = info.point if (info and hasattr(info, 'point') and info.point > 0) else 0.01
    digits = info.digits if (info and hasattr(info, 'digits')) else 2
    stops_level = getattr(info, 'trade_stops_level', 120) if info else 120
    min_dist = stops_level * point if (info and hasattr(info, 'point') and info.point > 0) else 1.20

    order_type_upper = order_type.upper()
    if order_type_upper == "BUY":
        max_allowed_sl = entry_price - min_dist
        final_sl = min(raw_sl, max_allowed_sl)
        min_allowed_tp = entry_price + min_dist
        final_tp = max(raw_tp, min_allowed_tp)
    else:  # SELL
        min_allowed_sl = entry_price + min_dist
        final_sl = max(raw_sl, min_allowed_sl)
        max_allowed_tp = entry_price - min_dist
        final_tp = min(raw_tp, max_allowed_tp)

    return round(final_sl, digits), round(final_tp, digits)

