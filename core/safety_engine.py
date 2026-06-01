# core/safety_engine.py
"""
PulseViper Safety & Drawdown Protection Engine.
Monitors consecutive losses, daily drawdown, and weekly drawdown.
Halts trading entry if thresholds are violated.
"""
import logging
import sqlite3
from datetime import datetime, date, timezone
from typing import Tuple, Dict
import MetaTrader5 as mt5
from utils.settings_manager import settings_manager

JOURNAL_DB = "data/trade_history.db"

class SafetyEngine:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.SafetyEngine")

    def get_stats(self) -> Dict:
        """
        Query database and account info to return current safety stats:
        - daily_pnl: P&L of all trades closed today (UTC)
        - weekly_pnl: P&L of all trades closed this week (Monday to today UTC)
        - consecutive_losses: Count of consecutive losing trades (PnL < 0) since last win
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Calculate start of the week (Monday)
        now = datetime.now(timezone.utc)
        monday = now - timedelta(days=now.weekday())
        monday_str = monday.strftime("%Y-%m-%d")

        daily_pnl = 0.0
        weekly_pnl = 0.0
        consecutive_losses = 0

        try:
            conn = sqlite3.connect(JOURNAL_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Daily PnL
            cursor.execute("SELECT SUM(pnl) FROM trades WHERE date = ?", (today_str,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                daily_pnl = float(row[0])

            # 2. Weekly PnL
            cursor.execute("SELECT SUM(pnl) FROM trades WHERE date >= ?", (monday_str,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                weekly_pnl = float(row[0])

            # 3. Consecutive losses (read recent trades in reverse)
            cursor.execute("SELECT pnl FROM trades ORDER BY id DESC LIMIT 50")
            rows = cursor.fetchall()
            for r in rows:
                pnl = float(r['pnl'])
                if pnl < 0.0:
                    consecutive_losses += 1
                elif pnl > 0.0:
                    # Found a win, stop counting
                    break
                # If pnl is exactly 0 (break-even), we ignore it and continue checking

            conn.close()
        except Exception as e:
            self.logger.error(f"Error reading safety stats from DB: {e}")

        return {
            "daily_pnl": daily_pnl,
            "weekly_pnl": weekly_pnl,
            "consecutive_losses": consecutive_losses
        }

    def check_entry_allowed(self) -> Tuple[bool, str]:
        """
        Perform safety checks.
        Returns: Tuple[is_allowed: bool, reason: str]
        """
        if not settings_manager.get("safety_engine_enabled", True):
            return True, "Safety Engine disabled"

        # Fetch settings thresholds
        max_losses = settings_manager.get("max_consecutive_losses", 3)
        max_daily_drawdown_pct = settings_manager.get("max_daily_drawdown_pct", 3.0)
        max_weekly_drawdown_pct = settings_manager.get("max_weekly_drawdown_pct", 8.0)

        # Get current balance
        balance = 10000.0
        if mt5.terminal_info() is not None:
            acct = mt5.account_info()
            if acct is not None:
                balance = float(acct.balance)

        stats = self.get_stats()
        daily_pnl = stats["daily_pnl"]
        weekly_pnl = stats["weekly_pnl"]
        consecutive_losses = stats["consecutive_losses"]

        # Calculate drawdown percentages relative to account balance
        # If daily_pnl is negative, daily_drawdown is positive
        daily_drawdown_pct = (-daily_pnl / balance) * 100.0 if daily_pnl < 0 else 0.0
        weekly_drawdown_pct = (-weekly_pnl / balance) * 100.0 if weekly_pnl < 0 else 0.0

        # Check thresholds
        if consecutive_losses >= max_losses:
            reason = f"HALT: {consecutive_losses} consecutive losses (Max: {max_losses})"
            self.logger.warning(reason)
            return False, reason

        if daily_drawdown_pct >= max_daily_drawdown_pct:
            reason = f"HALT: Daily drawdown {daily_drawdown_pct:.2f}% violated (Max: {max_daily_drawdown_pct:.1f}%)"
            self.logger.warning(reason)
            return False, reason

        if weekly_drawdown_pct >= max_weekly_drawdown_pct:
            reason = f"HALT: Weekly drawdown {weekly_drawdown_pct:.2f}% violated (Max: {max_weekly_drawdown_pct:.1f}%)"
            self.logger.warning(reason)
            return False, reason

        return True, "Allowed"


# Helper function to compute Monday UTC
from datetime import timedelta
