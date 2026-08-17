# core/safety_engine.py
"""
PulseViper Safety & Drawdown Protection Engine.
Monitors consecutive losses, daily drawdown, and weekly drawdown.
Halts trading entry if thresholds are violated.
"""
import logging
import sqlite3
from datetime import datetime, date, timezone, timedelta
from typing import Tuple, Dict
from utils.mt5_gateway import mt5_gateway as mt5
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
        is_paper = settings_manager.get("paper_mode", True)
        
        if not is_paper and mt5.terminal_info() is not None:
            try:
                from configs.config import Config
                magic_number = Config.MAGIC_NUMBER
                
                now_utc = datetime.now(timezone.utc)
                start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
                start_of_week_utc = (now_utc - timedelta(days=now_utc.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                
                # Convert directly to integer Unix timestamps (seconds since epoch)
                now_ts = int(now_utc.timestamp())
                today_ts = int(start_of_today_utc.timestamp())
                week_ts = int(start_of_week_utc.timestamp())
                
                # Query today's deals - ONLY with our magic number using integer timestamps
                deals_today = mt5.history_deals_get(today_ts, now_ts)
                daily_pnl = 0.0
                if deals_today:
                    daily_pnl = sum(d.profit + d.commission + d.swap 
                                    for d in deals_today 
                                    if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT) and d.magic == magic_number)
                
                # Query weekly deals - ONLY with our magic number using integer timestamps
                deals_week = mt5.history_deals_get(week_ts, now_ts)
                weekly_pnl = 0.0
                if deals_week:
                    weekly_pnl = sum(d.profit + d.commission + d.swap 
                                     for d in deals_week 
                                     if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT) and d.magic == magic_number)
                
                # Query recent deals for consecutive losses (only today to allow daily auto-reset)
                deals_all = mt5.history_deals_get(today_ts, now_ts)
                consecutive_losses = 0
                if deals_all:
                    deals_recent = sorted(
                        [d for d in deals_all if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT) and d.magic == magic_number],
                        key=lambda x: x.time
                    )
                    unique_deals = []
                    for d in reversed(deals_recent):
                        net_pnl = d.profit + d.commission + d.swap
                        is_sibling = False
                        for ud in unique_deals:
                            # Group as siblings if: same symbol, same direction (d.type), and closed within 60 seconds
                            if d.symbol == ud['symbol'] and d.type == ud['type'] and abs(d.time - ud['time']) <= 60:
                                is_sibling = True
                                break
                        if not is_sibling:
                            unique_deals.append({
                                'time': d.time,
                                'symbol': d.symbol,
                                'type': d.type,
                                'pnl': net_pnl
                            })
                            
                    for ud in unique_deals:
                        if ud['pnl'] < 0.0:
                            consecutive_losses += 1
                        elif ud['pnl'] > 0.0:
                            break
                            
                return {
                    "daily_pnl": round(daily_pnl, 2),
                    "weekly_pnl": round(weekly_pnl, 2),
                    "consecutive_losses": consecutive_losses
                }
            except Exception as e:
                self.logger.error(f"Error fetching safety stats from MT5: {e}")


        # Fallback to local SQLite database (for paper mode or MT5 failure)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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

            # 3. Consecutive losses (only today to allow daily auto-reset)
            cursor.execute("SELECT date, time, symbol, action, pnl FROM trades WHERE date = ? ORDER BY id DESC LIMIT 50", (today_str,))
            rows = cursor.fetchall()
            unique_trades = []
            for r in rows:
                pnl = float(r['pnl'])
                try:
                    dt_str = f"{r['date']} {r['time']}"
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    dt = datetime.now()
                
                is_sibling = False
                for ut in unique_trades:
                    # Group as siblings if: same symbol, same action, and closed within 60 seconds
                    if r['symbol'] == ut['symbol'] and r['action'] == ut['action'] and abs((dt - ut['dt']).total_seconds()) <= 60:
                        is_sibling = True
                        break
                if not is_sibling:
                    unique_trades.append({
                        'dt': dt,
                        'symbol': r['symbol'],
                        'action': r['action'],
                        'pnl': pnl
                    })
                    
            for ut in unique_trades:
                if ut['pnl'] < 0.0:
                    consecutive_losses += 1
                elif ut['pnl'] > 0.0:
                    break

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

        is_paper = settings_manager.get("paper_mode", True)

        # Fetch settings thresholds
        max_losses = settings_manager.get("max_consecutive_losses", 3)
        max_daily_drawdown_pct = settings_manager.get("max_daily_drawdown_pct", 3.0)
        max_weekly_drawdown_pct = settings_manager.get("max_weekly_drawdown_pct", 8.0)

        # Paper mode: double thresholds to allow more exploration
        if is_paper:
            max_losses = max_losses * 2
            max_daily_drawdown_pct = max_daily_drawdown_pct * 2
            max_weekly_drawdown_pct = max_weekly_drawdown_pct * 2

        # Get current balance
        if is_paper:
            balance = settings_manager.get("virtual_balance", 10000.0)
        else:
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

    def record_trade_result(self, pnl: float):
        """
        Callback to notify safety engine of a trade result.
        Optional: can be used for real-time memory-based checks.
        """
        self.logger.info(f"Recorded trade result of {pnl:.2f} in SafetyEngine.")
