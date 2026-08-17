import sqlite3
import os
import logging
import json
from threading import Lock

class PulseViperDatabase:
    def __init__(self, db_path="data/pulse_viper.db"):
        self.db_path = db_path
        self.logger = logging.getLogger("PulseViper.Database")
        self._lock = Lock()
        self._initialize_db()

    def _initialize_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                # Create swing causality table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS swing_causality (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        swing_type TEXT NOT NULL,
                        price REAL NOT NULL,
                        dxy_delta_at_formation REAL,
                        us10y_delta_at_formation REAL,
                        order_flow_imbalance REAL,
                        hmm_regime INTEGER,
                        mins_since_news INTEGER
                    )
                ''')
                # Create audit_evaluations table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS audit_evaluations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        datetime TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        brain_score REAL,
                        threshold REAL,
                        direction TEXT,
                        tier1 REAL,
                        tier2 REAL,
                        tier3 REAL,
                        block_reason TEXT,
                        news_penalty REAL,
                        spread_penalty REAL,
                        regime_penalty REAL,
                        decision_snapshot TEXT,
                        market_regime TEXT,
                        session_name TEXT,
                        spread REAL,
                        atr REAL,
                        dynamic_risk REAL,
                        hypothetical_rr REAL,
                        executed BOOLEAN,
                        would_have_won BOOLEAN,
                        status TEXT,
                        entry_price REAL,
                        sl REAL,
                        tp REAL,
                        chart_data TEXT
                    )
                ''')
                
                # Migrate database structure if needed (ensure new columns exist)
                cursor.execute("PRAGMA table_info(audit_evaluations)")
                columns = [row[1] for row in cursor.fetchall()]
                new_cols = {
                    "entry_price": "REAL",
                    "sl": "REAL",
                    "tp": "REAL",
                    "chart_data": "TEXT"
                }
                for col_name, col_type in new_cols.items():
                    if col_name not in columns:
                        cursor.execute(f"ALTER TABLE audit_evaluations ADD COLUMN {col_name} {col_type}")
                conn.commit()
                conn.close()
            except Exception as e:
                self.logger.error(f"Failed to initialize SQLite Database: {e}")

    def log_swing_causality(self, swing_causality_vector: dict):
        """
        Binds macroeconomic and liquidity context to structural swing points.
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO swing_causality (
                        timestamp, swing_type, price, dxy_delta_at_formation,
                        us10y_delta_at_formation, order_flow_imbalance,
                        hmm_regime, mins_since_news
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(swing_causality_vector.get("timestamp", "")),
                    swing_causality_vector.get("swing_type", "UNKNOWN"),
                    swing_causality_vector.get("price", 0.0),
                    swing_causality_vector.get("dxy_delta_at_formation", 0.0),
                    swing_causality_vector.get("us10y_delta_at_formation", 0.0),
                    swing_causality_vector.get("order_flow_imbalance", 0.0),
                    swing_causality_vector.get("hmm_regime", 0),
                    swing_causality_vector.get("mins_since_news", 999)
                ))
                conn.commit()
                conn.close()
            except Exception as e:
                self.logger.error(f"Failed to log swing causality: {e}")

# Global instance
db_instance = PulseViperDatabase()
