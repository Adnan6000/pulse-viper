# core/starvation_analyzer.py
import json
import os
import logging
from datetime import datetime, date
from collections import defaultdict
from typing import Dict, Any

class StarvationAnalyzer:
    """
    Phase 11: Trade Starvation Analytics
    Tracks the funnel of signals: Found -> Blocked -> Executed
    Maintains a count of block reasons to identify what is choking the system.
    """
    def __init__(self, filepath="data/starvation_stats.json"):
        self.filepath = filepath
        self.logger = logging.getLogger("PulseViper.StarvationAnalyzer")
        self.stats = {
            "date": str(datetime.now().date()),
            "signals_found": 0,
            "signals_blocked": 0,
            "signals_executed": 0,
            "block_reasons": defaultdict(int)
        }
        self.load_stats()

    def _check_rollover(self):
        """Reset stats if it is a new day."""
        current_date = str(datetime.now().date())
        if self.stats["date"] != current_date:
            self.stats = {
                "date": current_date,
                "signals_found": 0,
                "signals_blocked": 0,
                "signals_executed": 0,
                "block_reasons": defaultdict(int)
            }
            self.save_stats()

    def load_stats(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                if data.get("date") == str(datetime.now().date()):
                    self.stats["date"] = data["date"]
                    self.stats["signals_found"] = data.get("signals_found", 0)
                    self.stats["signals_blocked"] = data.get("signals_blocked", 0)
                    self.stats["signals_executed"] = data.get("signals_executed", 0)
                    
                    reasons = data.get("block_reasons", {})
                    self.stats["block_reasons"] = defaultdict(int, reasons)
                else:
                    self._check_rollover()
            except Exception as e:
                self.logger.error(f"Failed to load starvation stats: {e}")
                self._check_rollover()

    def save_stats(self):
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            data_to_save = {
                "date": self.stats["date"],
                "signals_found": self.stats["signals_found"],
                "signals_blocked": self.stats["signals_blocked"],
                "signals_executed": self.stats["signals_executed"],
                "block_reasons": dict(self.stats["block_reasons"])
            }
            with open(self.filepath, "w") as f:
                json.dump(data_to_save, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save starvation stats: {e}")

    def record_signal_found(self):
        self._check_rollover()
        self.stats["signals_found"] += 1
        self.save_stats()

    def record_signal_blocked(self, reason: str):
        self._check_rollover()
        self.stats["signals_blocked"] += 1
        if reason:
            self.stats["block_reasons"][reason] += 1
        self.save_stats()

    def record_signal_executed(self):
        self._check_rollover()
        self.stats["signals_executed"] += 1
        self.save_stats()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        self._check_rollover()
        
        # Sort block reasons by frequency (descending)
        sorted_reasons = sorted(
            self.stats["block_reasons"].items(),
            key=lambda item: item[1],
            reverse=True
        )
        
        return {
            "signals_found": self.stats["signals_found"],
            "signals_blocked": self.stats["signals_blocked"],
            "signals_executed": self.stats["signals_executed"],
            "top_blockers": sorted_reasons[:5]  # Return top 5 blockers
        }
