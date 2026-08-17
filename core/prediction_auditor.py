import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from utils.mt5_gateway import mt5_gateway as mt5
import pandas as pd
import numpy as np

from core.database import db_instance
from utils.settings_manager import settings_manager

def get_chart_snapshot_json(analysis: Dict[str, Any]) -> str:
    """Extracts the last 40 bars of M5 (or M1) and serializes them with indicators."""
    df = analysis.get("df_m5")
    if df is None or len(df) == 0:
        df = analysis.get("df_ltf")
    if df is None or len(df) == 0:
        return "[]"
        
    try:
        plot_df = df.tail(40).copy()
        
        candles = []
        for time_idx, row in plot_df.iterrows():
            if isinstance(time_idx, pd.Timestamp):
                t_str = time_idx.strftime("%Y-%m-%d %H:%M:%S")
            else:
                t_str = str(time_idx)
                
            def get_float(col, default=0.0):
                val = row.get(col)
                if val is None or pd.isna(val) or np.isinf(val):
                    return default
                return float(val)
                
            candles.append({
                "time": t_str,
                "open": get_float("open"),
                "high": get_float("high"),
                "low": get_float("low"),
                "close": get_float("close"),
                "support": get_float("support"),
                "resistance": get_float("resistance"),
                "ob_top": get_float("ob_top"),
                "ob_bottom": get_float("ob_bottom"),
                "fvg_top": get_float("fvg_top"),
                "fvg_bottom": get_float("fvg_bottom"),
                "fvg_class": str(row.get("fvg_class", "none")),
                "liq_sweep_level": get_float("liq_sweep_level"),
                "liq_sweep_type": int(row.get("liq_sweep_type", 0)),
                "mss_signal": int(row.get("mss_signal", 0))
            })
        return json.dumps(candles)
    except Exception as e:
        logging.getLogger("PulseViper.PredictionAuditor").error(f"Error serializing chart data: {e}")
        return json.dumps({"error": str(e)})

class PredictionAuditor:
    """
    Phase 11.5: Prediction & Audit Layer
    The 'black box flight recorder' for the neural engine.
    Logs every technical setup evaluation and retroactively tracks hypothetical outcomes.
    """
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.PredictionAuditor")
        self._stop_flag = False
        self.pattern_learner = None
        
        # We start a background resolver thread that runs every 5 minutes
        self._resolver_thread = threading.Thread(target=self._resolve_loop, daemon=True)
        self._resolver_thread.start()
        
    def log_evaluation(
        self,
        analysis: Dict[str, Any],
        brain_result,
        strategy_action: Optional[str]
    ) -> Optional[int]:
        """
        Log an evaluated technical setup to the audit_evaluations table.
        This must only be called if a technical setup actually fired (e.g. strategy_action is not None).
        Returns the database ID of the audit entry.
        """
        if strategy_action is None:
            return None
            
        try:
            audit_id = analysis.get("audit_id")
            symbol = analysis.get("symbol", "UNKNOWN")
            
            # Extract penalties from brain_result reason_map
            rm = brain_result.reason_map
            news_pen = rm.get("news_penalty", 0.0)
            spread_pen = rm.get("spread_penalty", 0.0)
            regime_pen = rm.get("chaotic_penalty", 0.0)
            
            # Snapshot of the state
            decision_snapshot = json.dumps({
                "htf_alignment": rm.get("t1_d1", 0) + rm.get("t1_h4", 0) + rm.get("t1_h1", 0),
                "structure": rm.get("t2_structure", 0),
                "fvg": rm.get("t2_fvg", 0),
                "vsa": rm.get("t2_vsa", 0),
                "volume": rm.get("t2_volume", 0),
                "ai_confidence": rm.get("t2_ai_confidence", 0),
                "session_quality": rm.get("t3_session_quality", 0),
                "regime_quality": rm.get("t3_regime_quality", 0),
                "features": analysis.get("features", {})
            })
            
            # Risk data
            spread = analysis.get("features", {}).get("spread", 0.0)
            atr = analysis.get("atr", 0.0)
            dynamic_risk = analysis.get("dynamic_risk_percent", 0.0)
            
            executed = (brain_result.passed and brain_result.block_reason is None)
            
            # Resolve entry_price, sl, tp
            entry_price = float(analysis.get("price", 0.0))
            sl = 0.0
            tp = 0.0
            
            # Check for strategy parameters
            for prefix in ["crt", "fib", "ict", "smc", "raja", "bank", "vsa", "avc", "m1_scalping", "vwap", "amd", "src"]:
                if analysis.get(f"{prefix}_action") == strategy_action:
                    sl = float(analysis.get(f"{prefix}_sl", 0.0))
                    tp = float(analysis.get(f"{prefix}_tp", 0.0))
                    break
            if sl == 0.0:
                sl = float(analysis.get("crt_sl") or analysis.get("fib_sl") or analysis.get("sl") or 0.0)
            if tp == 0.0:
                tp = float(analysis.get("crt_tp") or analysis.get("fib_tp") or analysis.get("tp") or 0.0)
            
            with db_instance._lock:
                conn = sqlite3.connect(db_instance.db_path)
                cursor = conn.cursor()
                
                if audit_id is not None:
                    # Update existing record
                    cursor.execute('''
                        UPDATE audit_evaluations SET
                            brain_score = ?, threshold = ?, direction = ?,
                            tier1 = ?, tier2 = ?, tier3 = ?, block_reason = ?,
                            news_penalty = ?, spread_penalty = ?, regime_penalty = ?,
                            decision_snapshot = ?, executed = ?, entry_price = ?, sl = ?, tp = ?
                        WHERE id = ?
                    ''', (
                        brain_result.brain_score,
                        brain_result.threshold,
                        brain_result.brain_direction or strategy_action,
                        brain_result.tier1_score,
                        brain_result.tier2_score,
                        brain_result.tier3_score,
                        brain_result.block_reason,
                        news_pen,
                        spread_pen,
                        regime_pen,
                        decision_snapshot,
                        executed,
                        entry_price,
                        sl,
                        tp,
                        audit_id
                    ))
                    conn.commit()
                    conn.close()
                    return audit_id
                else:
                    # Insert new record
                    chart_data = get_chart_snapshot_json(analysis)
                    
                    cursor.execute('''
                        INSERT INTO audit_evaluations (
                            timestamp, datetime, symbol, brain_score, threshold, direction,
                            tier1, tier2, tier3, block_reason, news_penalty, spread_penalty, regime_penalty,
                            decision_snapshot, market_regime, session_name, spread, atr, dynamic_risk,
                            hypothetical_rr, executed, would_have_won, status,
                            entry_price, sl, tp, chart_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        int(time.time()),
                        str(datetime.now()),
                        symbol,
                        brain_result.brain_score,
                        brain_result.threshold,
                        brain_result.brain_direction or strategy_action,
                        brain_result.tier1_score,
                        brain_result.tier2_score,
                        brain_result.tier3_score,
                        brain_result.block_reason,
                        news_pen,
                        spread_pen,
                        regime_pen,
                        decision_snapshot,
                        analysis.get("market_regime", "UNKNOWN"),
                        analysis.get("session_name", "UNKNOWN"),
                        spread,
                        atr,
                        dynamic_risk,
                        0.0,
                        executed,
                        False,
                        "PENDING",
                        entry_price,
                        sl,
                        tp,
                        chart_data
                    ))
                    conn.commit()
                    inserted_id = cursor.lastrowid
                    conn.close()
                    return inserted_id
                
        except Exception as e:
            self.logger.error(f"Failed to log/update evaluation: {e}")
            return None
            
    def _resolve_loop(self):
        """Background thread that resolves PENDING evaluations every 5 minutes."""
        while not self._stop_flag:
            try:
                time.sleep(300)  # Check every 5 minutes
                self._resolve_pending()
            except Exception as e:
                self.logger.error(f"Error in Prediction Auditor Resolver loop: {e}")
                
    def _resolve_pending(self):
        """Fetch pending records and check recent MT5 data or actual journal logs to resolve outcomes."""
        try:
            with db_instance._lock:
                conn = sqlite3.connect(db_instance.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM audit_evaluations WHERE status = 'PENDING'")
                pending_trades = cursor.fetchall()
                conn.close()
                
            if not pending_trades:
                return
                
            current_time = int(time.time())
            symbols = set(t["symbol"] for t in pending_trades)
            updates = []
            
            for symbol in symbols:
                # 1. If executed, check if there's a closed trade matching in trade_history.db
                sym_trades = [t for t in pending_trades if t["symbol"] == symbol]
                import os
                trade_db_path = "data/trade_history.db"
                
                # Fetch recent M1 candles to trace path for hypothetical skips
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1000)
                
                for t in sym_trades:
                    # Check trade journal if executed
                    if t["executed"] and os.path.exists(trade_db_path):
                        try:
                            conn_th = sqlite3.connect(trade_db_path)
                            conn_th.row_factory = sqlite3.Row
                            cursor_th = conn_th.cursor()
                            cursor_th.execute("SELECT pnl, rr_achieved FROM trades WHERE audit_id = ?", (t["id"],))
                            row_th = cursor_th.fetchone()
                            conn_th.close()
                            if row_th:
                                pnl = row_th["pnl"]
                                rr = row_th["rr_achieved"]
                                updates.append((round(rr, 2), pnl > 0.0, "RESOLVED", t["id"]))
                                continue
                        except Exception as db_err:
                            self.logger.error(f"Error reading trade_history for resolution: {db_err}")
                            
                    entry_time = t["timestamp"]
                    # Skip expiration for executed trades (they remain active until closed)
                    if current_time - entry_time > 86400 and not t["executed"]: # 24 hrs
                        updates.append((0.0, False, "EXPIRED", t["id"]))
                        continue
                        
                    if rates is None or len(rates) == 0:
                        continue
                        
                    future_rates = [r for r in rates if r['time'] > entry_time]
                    if not future_rates:
                        continue
                        
                    # Find entry price at the time
                    entry_price = future_rates[0]['open']
                    atr = t["atr"]
                    if atr == 0.0:
                        updates.append((0.0, False, "EXPIRED", t["id"]))
                        continue
                        
                    direction = t["direction"]
                    
                    if direction == "BUY":
                        sl_price = entry_price - (1.5 * atr)
                    else:
                        sl_price = entry_price + (1.5 * atr)
                        
                    resolved = False
                    max_favorable_price = entry_price
                    
                    for r in future_rates:
                        high = float(r['high'])
                        low = float(r['low'])
                        
                        if direction == "BUY":
                            if high > max_favorable_price:
                                max_favorable_price = high
                            if low <= sl_price:
                                rr = (max_favorable_price - entry_price) / (1.5 * atr)
                                updates.append((round(rr, 2), rr >= 1.5, "RESOLVED", t["id"]))
                                resolved = True
                                won = rr >= 1.5
                                # Trigger learning for skipped setup
                                if not t["executed"]:
                                    try:
                                        snapshot = json.loads(t["decision_snapshot"]) if t["decision_snapshot"] else {}
                                        features = snapshot.get("features", {})
                                        if features:
                                            outcome_lbl = 1.0 if won else -1.0
                                            pnl_val = 1.0 if won else -1.0
                                            if getattr(self, 'pattern_learner', None):
                                                self.pattern_learner.append_live_experience(
                                                    features=features,
                                                    outcome_label=outcome_lbl,
                                                    pnl_realized=pnl_val,
                                                    symbol=t["symbol"]
                                                )
                                    except Exception as ler_err:
                                        self.logger.error(f"Error appending live learning for skipped: {ler_err}")
                                break
                        elif direction == "SELL":
                            if low < max_favorable_price:
                                max_favorable_price = low
                            if high >= sl_price:
                                rr = (entry_price - max_favorable_price) / (1.5 * atr)
                                updates.append((round(rr, 2), rr >= 1.5, "RESOLVED", t["id"]))
                                resolved = True
                                won = rr >= 1.5
                                # Trigger learning for skipped setup
                                if not t["executed"]:
                                    try:
                                        snapshot = json.loads(t["decision_snapshot"]) if t["decision_snapshot"] else {}
                                        features = snapshot.get("features", {})
                                        if features:
                                            outcome_lbl = 1.0 if won else -1.0
                                            pnl_val = 1.0 if won else -1.0
                                            if getattr(self, 'pattern_learner', None):
                                                self.pattern_learner.append_live_experience(
                                                    features=features,
                                                    outcome_label=outcome_lbl,
                                                    pnl_realized=pnl_val,
                                                    symbol=t["symbol"]
                                                )
                                    except Exception as ler_err:
                                        self.logger.error(f"Error appending live learning for skipped: {ler_err}")
                                break
                                
                    if not resolved:
                        # Trade still open hypothetically, calculate floating RR
                        if direction == "BUY":
                            curr_rr = (future_rates[-1]['close'] - entry_price) / (1.5 * atr)
                        else:
                            curr_rr = (entry_price - future_rates[-1]['close']) / (1.5 * atr)
                            
                        # If current RR is massive, we can consider it resolved as a win
                        if curr_rr >= 3.0:
                            updates.append((round(curr_rr, 2), True, "RESOLVED", t["id"]))
                            # Trigger learning for skipped setup
                            if not t["executed"]:
                                try:
                                    snapshot = json.loads(t["decision_snapshot"]) if t["decision_snapshot"] else {}
                                    features = snapshot.get("features", {})
                                    if features:
                                        if getattr(self, 'pattern_learner', None):
                                            self.pattern_learner.append_live_experience(
                                                features=features,
                                                outcome_label=1.0,
                                                pnl_realized=1.0,
                                                symbol=t["symbol"]
                                            )
                                except Exception as ler_err:
                                    self.logger.error(f"Error appending live learning for skipped: {ler_err}")
                            
            if updates:
                with db_instance._lock:
                    conn = sqlite3.connect(db_instance.db_path)
                    cursor = conn.cursor()
                    cursor.executemany('''
                        UPDATE audit_evaluations
                        SET hypothetical_rr = ?, would_have_won = ?, status = ?
                        WHERE id = ?
                    ''', [(rr, int(won), st, aid) for rr, won, st, aid in updates])
                    conn.commit()
                    conn.close()
                    
        except Exception as e:
            self.logger.error(f"Error resolving pending evaluations: {e}")

    def resolve_executed_trade(self, audit_id: int, won: bool, rr: float):
        """Immediately resolve an audit entry with the actual closed trade outcome."""
        try:
            with db_instance._lock:
                conn = sqlite3.connect(db_instance.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE audit_evaluations
                    SET hypothetical_rr = ?, would_have_won = ?, status = 'RESOLVED', executed = 1
                    WHERE id = ?
                ''', (round(rr, 2), int(won), audit_id))
                conn.commit()
                conn.close()
            self.logger.info(f"✅ Audit evaluation {audit_id} resolved with trade outcome: won={won}, rr={rr:.2f}R")
        except Exception as e:
            self.logger.error(f"Failed to resolve executed trade in audit: {e}")

    def update_evaluation_executed(self, audit_id: int, executed: bool, status: str):
        """Update the execution and status fields for a logged evaluation (e.g. invalidations)."""
        try:
            with db_instance._lock:
                conn = sqlite3.connect(db_instance.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE audit_evaluations 
                    SET executed = ?, status = ?
                    WHERE id = ?
                ''', (1 if executed else 0, status, audit_id))
                conn.commit()
                conn.close()
            self.logger.info(f"✅ Audit evaluation {audit_id} updated: executed={executed}, status={status}")
        except Exception as e:
            self.logger.error(f"Failed to update evaluation executed status: {e}")

prediction_auditor = PredictionAuditor()
