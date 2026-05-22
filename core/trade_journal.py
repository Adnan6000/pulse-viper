# core/trade_journal.py
"""
PulseViper Trade Journal — Persistent structured log of every trade.
Classifies each trade as GOOD or BAD with reasoning for self-improvement.
"""
import os
import csv
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

JOURNAL_CSV = "logs/trade_journal.csv"
JOURNAL_JSON = "logs/trade_journal.json"

CSV_FIELDS = [
    "date", "time", "symbol", "action", "entry_price", "close_price",
    "sl", "tp1", "tp2", "lot_size", "pnl", "rr_achieved",
    "close_reason", "duration_mins", "setup_type", "fvg_class",
    "bias", "volatility_regime", "spread_at_entry", "classification", "classification_reason"
]


class TradeJournal:
    """
    Append-only structured trade log with daily summary and GOOD/BAD trade classification.
    """
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.Journal")
        self._ensure_files()

    def _ensure_files(self):
        os.makedirs("logs", exist_ok=True)
        os.makedirs("logs/daily_reports", exist_ok=True)
        if not os.path.exists(JOURNAL_CSV):
            with open(JOURNAL_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()

    def _classify_trade(self, record: Dict) -> tuple:
        """
        Classify trade as GOOD or BAD with a short reason.
        Returns (classification: str, reason: str)
        """
        reasons = []
        bad_reasons = []

        pnl = record.get("pnl", 0.0)
        close_reason = record.get("close_reason", "").upper()
        rr = record.get("rr_achieved", 0.0)
        duration = record.get("duration_mins", 0.0)
        setup = record.get("setup_type", "UNKNOWN")
        spread = record.get("spread_at_entry", 0.0)

        # --- GOOD trade criteria ---
        if close_reason == "TP":
            reasons.append("Hit TP target")
        if rr >= 1.5:
            reasons.append(f"Good RR ({rr:.1f}R)")
        if setup == "SHARP_TURN":
            reasons.append("Sharp-Turn SMC setup")
        if pnl > 0 and duration < 30:
            reasons.append("Quick profitable exit")

        # --- BAD trade criteria ---
        if close_reason == "SL":
            bad_reasons.append("Stopped out")
        if 0 < rr < 0.5 and close_reason == "TP":
            bad_reasons.append("Weak RR despite TP")
        if spread > 300:
            bad_reasons.append(f"High spread at entry ({spread:.0f} pts)")
        if setup in ("SWEEP_ONLY", "CONTINUATION") and pnl < 0:
            bad_reasons.append(f"Weak setup type ({setup})")
        if duration > 120 and pnl < 0:
            bad_reasons.append("Long losing trade")

        if pnl > 0 and not bad_reasons:
            return "GOOD", "; ".join(reasons) if reasons else "Profitable trade"
        elif pnl <= 0 or bad_reasons:
            all_bad = bad_reasons + [r for r in reasons if "good" not in r.lower()]
            return "BAD", "; ".join(bad_reasons) if bad_reasons else "Loss trade"
        else:
            return "NEUTRAL", "Mixed signals"

    def append_trade(self, record: Dict):
        """
        Append a closed trade record to the CSV and JSON journal.
        Automatically classifies the trade as GOOD or BAD.
        """
        classification, reason = self._classify_trade(record)
        record["classification"] = classification
        record["classification_reason"] = reason

        # Normalize fields
        row = {field: record.get(field, "") for field in CSV_FIELDS}

        # Append to CSV
        try:
            with open(JOURNAL_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writerow(row)
        except Exception as e:
            self.logger.error(f"Failed to write trade journal CSV: {e}")

        # Append to JSON
        try:
            existing = []
            if os.path.exists(JOURNAL_JSON):
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    try:
                        existing = json.load(f)
                    except json.JSONDecodeError:
                        existing = []
            existing.append(row)
            with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to write trade journal JSON: {e}")

        self.logger.info(
            f"📓 Journal: {row['action']} {row['symbol']} @ {row['entry_price']} → "
            f"PnL=${row['pnl']} [{classification}] — {reason}"
        )

    def get_all_trades(self) -> List[Dict]:
        """Return all trades from the JSON journal."""
        if not os.path.exists(JOURNAL_JSON):
            return []
        try:
            with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to read journal JSON: {e}")
            return []

    def get_trades_for_date(self, target_date: date) -> List[Dict]:
        """Return all trades for a specific date."""
        date_str = target_date.strftime("%Y-%m-%d")
        return [t for t in self.get_all_trades() if str(t.get("date", "")).startswith(date_str)]

    def get_daily_summary(self, target_date: date = None) -> Dict:
        """
        Compute statistics for a given day.
        Defaults to today.
        """
        if target_date is None:
            target_date = date.today()

        trades = self.get_trades_for_date(target_date)
        if not trades:
            return {"date": str(target_date), "trades": 0, "message": "No trades on this day"}

        wins = [t for t in trades if float(t.get("pnl", 0)) > 0]
        losses = [t for t in trades if float(t.get("pnl", 0)) <= 0]
        good = [t for t in trades if t.get("classification") == "GOOD"]
        bad = [t for t in trades if t.get("classification") == "BAD"]
        total_pnl = sum(float(t.get("pnl", 0)) for t in trades)
        gross_profit = sum(float(t.get("pnl", 0)) for t in wins)
        gross_loss = abs(sum(float(t.get("pnl", 0)) for t in losses))
        profit_factor = gross_profit / (gross_loss + 1e-9)
        avg_rr = sum(float(t.get("rr_achieved", 0)) for t in trades) / len(trades)

        # Session breakdown
        sl_hits = [t for t in trades if str(t.get("close_reason", "")).upper() == "SL"]
        tp_hits = [t for t in trades if str(t.get("close_reason", "")).upper() == "TP"]

        # Setup type breakdown
        setups = {}
        for t in trades:
            st = t.get("setup_type", "UNKNOWN")
            if st not in setups:
                setups[st] = {"count": 0, "wins": 0, "pnl": 0.0}
            setups[st]["count"] += 1
            if float(t.get("pnl", 0)) > 0:
                setups[st]["wins"] += 1
            setups[st]["pnl"] += float(t.get("pnl", 0))

        return {
            "date": str(target_date),
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(trades)) * 100,
            "total_pnl": round(total_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 3),
            "avg_rr": round(avg_rr, 2),
            "sl_hits": len(sl_hits),
            "tp_hits": len(tp_hits),
            "good_trades": len(good),
            "bad_trades": len(bad),
            "setup_breakdown": setups
        }

    def get_recent_summary(self, n_days: int = 7) -> Dict:
        """Summarize the last N days of trading."""
        summaries = []
        for i in range(n_days):
            d = date.today() - timedelta(days=i)
            s = self.get_daily_summary(d)
            if s.get("trades", 0) > 0:
                summaries.append(s)
        return {
            "period_days": n_days,
            "active_days": len(summaries),
            "summaries": summaries
        }


# Global singleton
trade_journal = TradeJournal()
