# utils/settings_manager.py
import os
import json
import logging

DEFAULT_SETTINGS = {
    "paper_mode": True,
    "trading_mode": "intraday",  # "scalping", "intraday", "swing"
    "hedging_mode": False,
    "compounding_mode": True,
    "risk_percent": 1.0,
    "london_session_enabled": True,
    "ny_session_enabled": True,
    "break_even_enabled": True,
    "trailing_stop_enabled": True,
    "self_learning_filter": True,
    "news_filter_enabled": True,
    "max_spread_points": 20,  # Default for Exness Standard, adapted dynamically
    "min_rr_ratio": 2.0,
    "auto_trade_enabled": True,
    "dynamic_risk_enabled": True,
    "dynamic_regime_filter": True,
    "news_lockout_minutes": 30,
    "news_cooldown_minutes": 15
}

class SettingsManager:
    def __init__(self, filepath="configs/settings.json"):
        self.filepath = filepath
        self.logger = logging.getLogger("PulseViper.SettingsManager")
        self.settings = {}
        self.last_mtime = 0.0
        self.load_settings()

    def load_settings(self):
        """Load settings from JSON file. Create defaults if not exists."""
        try:
            if os.path.exists(self.filepath):
                mtime = os.path.getmtime(self.filepath)
                # Only load if modification time has changed
                if mtime == self.last_mtime and self.settings:
                    return
                with open(self.filepath, "r") as f:
                    file_data = json.load(f)
                # Merge loaded settings with defaults to ensure all keys exist
                self.settings = {**DEFAULT_SETTINGS, **file_data}
                self.last_mtime = mtime
            else:
                self.settings = DEFAULT_SETTINGS.copy()
                self.save_settings()
                if os.path.exists(self.filepath):
                    self.last_mtime = os.path.getmtime(self.filepath)
            self.logger.info("Settings loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}")
            self.settings = DEFAULT_SETTINGS.copy()

    def save_settings(self):
        """Save settings to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w") as f:
                json.dump(self.settings, f, indent=4)
            # Update last_mtime to prevent redundant reload right after save
            if os.path.exists(self.filepath):
                self.last_mtime = os.path.getmtime(self.filepath)
        except Exception as e:
            self.logger.error(f"Failed to save settings: {e}")

    def get(self, key, default=None):
        """Get a setting value"""
        self.load_settings()
        return self.settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        """Set a setting value and save"""
        self.load_settings()
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self.save_settings()
        self.logger.info(f"Setting updated: {key} = {value}")

    def toggle(self, key) -> bool:
        """Toggle a boolean setting and save"""
        val = self.get(key, False)
        if isinstance(val, bool):
            new_val = not val
            self.set(key, new_val)
            return new_val
        return val

    def get_all(self):
        """Get all settings dict"""
        self.load_settings()
        return self.settings.copy()

# Global instance
settings_manager = SettingsManager()
