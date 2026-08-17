# core/trade_journal.py
"""
PulseViper Trade Journal — SQLite-backed persistent structured log of every trade.
Stores complete TradeBrain v2 metadata, market context, and classifies trades.
"""
import os
import csv
import json
import sqlite3
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

JOURNAL_DB = "data/trade_history.db"
JOURNAL_CSV = "logs/trade_journal.csv"

CSV_FIELDS = [
    "date", "time", "symbol", "action", "entry_price", "close_price",
    "sl", "tp", "lot_size", "pnl", "rr_achieved", "close_reason",
    "duration_mins", "setup_type", "fvg_class", "bias", "volatility_regime",
    "spread_at_entry", "classification", "classification_reason",
    "brain_score", "brain_tier1", "brain_tier2", "brain_tier3",
    "brain_direction", "brain_block_reason", "session", "vsa_signals",
    "entry_features", "audit_id", "strategy_name", "entry_pattern",
    "decision_id", "decision_snapshot", "cycle_id", "execution_id"
]


class TradeJournal:
    """
    SQLite-backed trade log with CSV synchronization, automated GOOD/BAD trade classification,
    and granular statistics reporting.
    """
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.Journal")
        self._ensure_storage()

    def _ensure_storage(self):
        # Ensure directories exist
        os.makedirs("data", exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        os.makedirs("logs/daily_reports", exist_ok=True)
        
        # Initialize SQLite DB
        conn = sqlite3.connect(JOURNAL_DB)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            symbol TEXT,
            action TEXT,
            entry_price REAL,
            close_price REAL,
            sl REAL,
            tp REAL,
            lot_size REAL,
            pnl REAL,
            rr_achieved REAL,
            close_reason TEXT,
            duration_mins REAL,
            setup_type TEXT,
            fvg_class TEXT,
            bias INTEGER,
            volatility_regime TEXT,
            spread_at_entry REAL,
            classification TEXT,
            classification_reason TEXT,
            brain_score REAL,
            brain_tier1 REAL,
            brain_tier2 REAL,
            brain_tier3 REAL,
            brain_direction TEXT,
            brain_block_reason TEXT,
            session TEXT,
            vsa_signals TEXT,
            entry_features TEXT,
            audit_id INTEGER,
            strategy_name TEXT,
            entry_pattern TEXT
        )
        """)
        
        # Schema migration checks: check if decision_id and decision_snapshot columns exist, add if missing
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        if "decision_id" not in columns:
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN decision_id TEXT")
            except Exception as e:
                self.logger.error(f"Migration failed adding decision_id: {e}")
        if "decision_snapshot" not in columns:
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN decision_snapshot TEXT")
            except Exception as e:
                self.logger.error(f"Migration failed adding decision_snapshot: {e}")
        if "cycle_id" not in columns:
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN cycle_id TEXT")
            except Exception as e:
                self.logger.error(f"Migration failed adding cycle_id: {e}")
        if "execution_id" not in columns:
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN execution_id TEXT")
            except Exception as e:
                self.logger.error(f"Migration failed adding execution_id: {e}")
                
        conn.commit()
        conn.close()

        # Migrate database structure if needed (ensure columns exist)
        try:
            conn = sqlite3.connect(JOURNAL_DB)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(trades)")
            columns = [row[1] for row in cursor.fetchall()]
            if "entry_features" not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN entry_features TEXT")
                conn.commit()
            if "audit_id" not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN audit_id INTEGER")
                conn.commit()
            if "strategy_name" not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN strategy_name TEXT")
                conn.commit()
            if "entry_pattern" not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN entry_pattern TEXT")
                conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Failed to migrate trade_history schema: {e}")

        # Initialize CSV Header if CSV doesn't exist
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
        close_reason = str(record.get("close_reason", "")).upper()
        rr = record.get("rr_achieved", 0.0)
        duration = record.get("duration_mins", 0.0)
        setup = record.get("setup_type", "UNKNOWN")
        spread = record.get("spread_at_entry", 0.0)
        brain_score = record.get("brain_score", 0.0)

        # --- GOOD trade criteria ---
        if close_reason == "TP":
            reasons.append("Hit TP target")
        if rr >= 1.5:
            reasons.append(f"Good RR ({rr:.1f}R)")
        if setup == "SHARP_TURN":
            reasons.append("Sharp-Turn SMC setup")
        if pnl > 0 and duration < 30:
            reasons.append("Quick profitable exit")
        if pnl > 0 and brain_score >= 75.0:
            reasons.append(f"High conviction Brain ({brain_score:.0f} pts)")
        if pnl > 0 and close_reason == "SL":
            reasons.append("Trailed SL in profit")

        # --- BAD trade criteria ---
        if close_reason == "SL" and pnl <= 0:
            bad_reasons.append("Stopped out")
        if 0 < rr < 0.5 and close_reason == "TP":
            bad_reasons.append("Weak RR despite TP")
        if spread > 30.0 and pnl <= 0:  # Only penalize spread if the trade ended in a loss
            bad_reasons.append(f"High spread at entry ({spread:.1f} pts)")
        if setup in ("SWEEP_ONLY", "CONTINUATION") and pnl < 0:
            bad_reasons.append(f"Weak setup type ({setup})")
        if duration > 120 and pnl < 0:
            bad_reasons.append("Long losing trade")
        if pnl < 0 and brain_score < 60.0:
            bad_reasons.append(f"Low conviction Brain entry ({brain_score:.0f} pts)")

        if pnl > 0 and not bad_reasons:
            return "GOOD", "; ".join(reasons) if reasons else "Profitable trade"
        elif pnl <= 0 or bad_reasons:
            return "BAD", "; ".join(bad_reasons) if bad_reasons else "Loss trade"
        else:
            return "NEUTRAL", "Mixed outcome"

    def append_trade(self, record: Dict):
        """
        Append a closed trade record to the SQLite DB and synchronize to the CSV journal.
        Automatically classifies the trade as GOOD or BAD.
        """
        # Ensure default/compatibility values
        record = dict(record)  # shallow copy
        if "tp" not in record and "tp1" in record:
            record["tp"] = record["tp1"]

        # Convert vsa_signals list to string if necessary
        vsa_data = record.get("vsa_signals", "")
        if isinstance(vsa_data, list):
            vsa_data = ",".join(vsa_data)
        record["vsa_signals"] = vsa_data

        # Serialize entry_features to JSON string
        entry_feats = record.get("entry_features", {})
        if isinstance(entry_feats, dict):
            try:
                record["entry_features"] = json.dumps(entry_feats)
            except Exception:
                record["entry_features"] = "{}"
        elif not isinstance(entry_feats, str):
            record["entry_features"] = "{}"

        classification, reason = self._classify_trade(record)
        record["classification"] = classification
        record["classification_reason"] = reason

        # Insert to SQLite
        try:
            conn = sqlite3.connect(JOURNAL_DB)
            cursor = conn.cursor()
            query = f"""
                INSERT INTO trades (
                    {','.join(CSV_FIELDS)}
                ) VALUES ({','.join(['?'] * len(CSV_FIELDS))})
            """
            values = tuple(record.get(field, None) for field in CSV_FIELDS)
            cursor.execute(query, values)
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Failed to write trade to SQLite: {e}")

        # Sync to CSV
        try:
            write_header = not os.path.exists(JOURNAL_CSV) or os.path.getsize(JOURNAL_CSV) == 0
            row = {field: record.get(field, "") for field in CSV_FIELDS}
            with open(JOURNAL_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                if write_header:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as e:
            self.logger.error(f"Failed to write trade journal CSV: {e}")

        self.logger.info(
            f"📓 Journal Saved: {record.get('action')} {record.get('symbol')} | "
            f"PnL=${record.get('pnl')} | Brain={record.get('brain_score')} | "
            f"Class={classification} ({reason})"
        )

    def get_all_trades(self) -> List[Dict]:
        """Return all trades from the SQLite database."""
        try:
            conn = sqlite3.connect(JOURNAL_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY id ASC")
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            self.logger.error(f"Failed to read SQLite journal: {e}")
            return []

    def get_trades_for_date(self, target_date: date) -> List[Dict]:
        """Return all trades for a specific date."""
        date_str = target_date.strftime("%Y-%m-%d")
        try:
            conn = sqlite3.connect(JOURNAL_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE date = ? ORDER BY id ASC", (date_str,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            self.logger.error(f"Failed to query SQLite by date: {e}")
            return []

    def get_daily_summary(self, target_date: Optional[date] = None) -> Dict:
        """
        Compute statistics for a given day. Defaults to today.
        """
        if target_date is None:
            target_date = date.today()

        trades = self.get_trades_for_date(target_date)
        if not trades:
            return {"date": str(target_date), "trades": 0, "message": "No trades on this day"}

        wins = [t for t in trades if float(t.get("pnl", 0.0)) > 0]
        losses = [t for t in trades if float(t.get("pnl", 0.0)) <= 0]
        good = [t for t in trades if t.get("classification") == "GOOD"]
        bad = [t for t in trades if t.get("classification") == "BAD"]
        total_pnl = sum(float(t.get("pnl", 0.0)) for t in trades)
        gross_profit = sum(float(t.get("pnl", 0.0)) for t in wins)
        gross_loss = abs(sum(float(t.get("pnl", 0.0)) for t in losses))
        profit_factor = gross_profit / (gross_loss + 1e-9)
        avg_rr = sum(float(t.get("rr_achieved", 0.0)) for t in trades) / len(trades)

        sl_hits = [t for t in trades if str(t.get("close_reason", "")).upper() == "SL"]
        tp_hits = [t for t in trades if str(t.get("close_reason", "")).upper() == "TP"]

        setups = {}
        for t in trades:
            st = t.get("setup_type", "UNKNOWN")
            if st not in setups:
                setups[st] = {"count": 0, "wins": 0, "pnl": 0.0}
            setups[st]["count"] += 1
            if float(t.get("pnl", 0.0)) > 0:
                setups[st]["wins"] += 1
            setups[st]["pnl"] += float(t.get("pnl", 0.0))

        return {
            "date": str(target_date),
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(trades)) * 100.0 if trades else 0.0,
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
