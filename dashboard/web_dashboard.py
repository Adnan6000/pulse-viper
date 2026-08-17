# dashboard/web_dashboard.py
import json
import logging
import threading
import time
import secrets
import numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from typing import Dict, Any, List
from utils.mt5_gateway import mt5_gateway as mt5
from utils.settings_manager import settings_manager
from dashboard.html_template import HTML_TEMPLATE
from core.news_schedule import news_schedule

# Server-side sessions
sessions = {}

def validate_settings(settings_dict):
    """Validates a settings dictionary against settings_manager schema rules."""
    for k, v in settings_dict.items():
        settings_manager._validate_value(k, v)
    return True

def resolve_broker_symbol(symbol: str, engine=None) -> str:
    """Smartly resolves exact case-sensitive broker symbol name (e.g. BTCUSDm, XAUUSDm, EURUSDm)."""
    if not symbol:
        return symbol
    clean_sym = symbol.strip()
    info = mt5.symbol_info(clean_sym)
    if info is not None:
        return info.name
        
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return clean_sym
        
    sym_upper = clean_sym.upper()
    # 1. Case-insensitive exact match
    for s in all_symbols:
        if s.name.upper() == sym_upper:
            return s.name
            
    # 2. Equivalent symbol mapping (handles BTCUSD -> BTCUSDm, XAUUSD -> XAUUSDm, etc.)
    all_names = [s.name for s in all_symbols]
    if engine and hasattr(engine, 'find_equivalent_symbol'):
        match = engine.find_equivalent_symbol(clean_sym, all_names)
        if match:
            return match
            
    # 3. Base currency prefix search
    for s in all_symbols:
        if s.name.upper().startswith(sym_upper) or sym_upper.startswith(s.name.upper()):
            return s.name
            
    return clean_sym



class DashboardRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, engine, *args, **kwargs):
        self.engine = engine
        super().__init__(*args, **kwargs)
        
    def _set_headers(self, content_type="application/json", status=200, nonce=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        
        origin = self.headers.get("Origin")
        if origin:
            parsed_origin = urllib.parse.urlparse(origin)
            if parsed_origin.hostname in ("127.0.0.1", "localhost"):
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Access-Control-Allow-Credentials', 'true')
                
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-PulseViper-Control-Token')
        
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "script-src-elem 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss: http: https:;"
        )
        self.send_header('Content-Security-Policy', csp)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(status=200)

    def _validate_host_and_origin(self) -> bool:
        host = self.headers.get("Host", "")
        addr = getattr(self.server, 'server_address', None)
        server_port = addr[1] if isinstance(addr, tuple) and len(addr) > 1 else 8000
        allowed_hosts = [
            f"127.0.0.1:{server_port}",
            f"localhost:{server_port}",
            "127.0.0.1",
            "localhost"
        ]
        clean_host = host.strip().lower()
        if not any(clean_host == allowed or clean_host.startswith(allowed + ":") for allowed in ["127.0.0.1", "localhost"]):
            self.send_error(400, "Invalid Host header")
            return False

        if self.command in ("POST", "PUT", "DELETE"):
            origin = self.headers.get("Origin")
            referer = self.headers.get("Referer")
            valid = False
            
            if origin:
                parsed_origin = urllib.parse.urlparse(origin)
                if parsed_origin.hostname in ("127.0.0.1", "localhost"):
                    valid = True
            elif referer:
                parsed_referer = urllib.parse.urlparse(referer)
                if parsed_referer.hostname in ("127.0.0.1", "localhost"):
                    valid = True
            else:
                auth_token = self.headers.get("X-PulseViper-Control-Token")
                expected_token = settings_manager.get("control_token")
                if auth_token and expected_token and auth_token == expected_token:
                    valid = True
                    
            if not valid:
                self.send_error(403, "Invalid Origin or Referer header")
                return False
        return True

    def _is_authenticated(self) -> bool:
        return True

    def do_GET(self):
        if not self._validate_host_and_origin():
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/login":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if path == "/":
            nonce = secrets.token_hex(16)
            self._set_headers("text/html; charset=utf-8", nonce=nonce)
            import importlib
            import sys
            import dashboard.html_template
            importlib.reload(sys.modules['dashboard.html_template'])
            from dashboard.html_template import HTML_TEMPLATE as HOT_HTML
            nonced_html = HOT_HTML.replace("{{NONCE}}", nonce)
            self.wfile.write(nonced_html.encode('utf-8'))
            return

        elif path == "/broadcast":
            nonce = secrets.token_hex(16)
            self._set_headers("text/html; charset=utf-8", nonce=nonce)
            import importlib
            import sys
            import dashboard.html_template
            importlib.reload(sys.modules['dashboard.html_template'])
            from dashboard.html_template import BROADCAST_TEMPLATE as HOT_HTML
            nonced_html = HOT_HTML.replace("{{NONCE}}", nonce)
            self.wfile.write(nonced_html.encode('utf-8'))
            return

        elif path == "/api/broadcast/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            import time
            last_cycle_id = None
            try:
                while True:
                    snapshot = self.engine.get_dashboard_snapshot()
                    if snapshot:
                        from utils.snapshot_helper import deep_thaw
                        thawed = deep_thaw(snapshot)
                        cycle_id = thawed.get("cycle_id", "PV-CYCLE-INIT")
                        
                        tick_data = {
                            "bid": thawed.get("account", {}).get("balance", 0.0),
                            "ask": thawed.get("account", {}).get("equity", 0.0),
                            "spread": thawed.get("spread", {}),
                            "current_price": thawed.get("latency_ms", 0.0),
                            "pnl": thawed.get("account", {}).get("profit", 0.0)
                        }
                        
                        # Send tick event
                        self.wfile.write(f"event: tick\ndata: {json.dumps(tick_data)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                        
                        # Send chart snapshot event if cycle changed
                        if cycle_id != last_cycle_id:
                            self.wfile.write(f"event: chart_snapshot\ndata: {json.dumps(thawed)}\n\n".encode('utf-8'))
                            self.wfile.flush()
                            last_cycle_id = cycle_id
                    time.sleep(0.5)
            except Exception:
                pass
            return
            
        elif path == "/api/status":
            self._set_headers()
            status_data = self._get_status_data()
            self.wfile.write(json.dumps(status_data, default=str).encode('utf-8'))
            
        elif path == "/api/chart":
            try:
                query = urllib.parse.parse_qs(parsed_url.query)
                raw_symbol = query.get("symbol", [None])[0]
                if not raw_symbol and getattr(self, 'engine', None) and self.engine.symbols:
                    raw_symbol = self.engine.symbols[0]
                elif not raw_symbol:
                    raw_symbol = settings_manager.get("active_symbol", "EURUSDm")

                symbol = resolve_broker_symbol(raw_symbol, getattr(self, 'engine', None))
                    
                tf_str = query.get("timeframe", ["M5"])[0]
                tf_map = {
                    "M1": mt5.TIMEFRAME_M1,
                    "M5": mt5.TIMEFRAME_M5,
                    "M15": mt5.TIMEFRAME_M15,
                    "M30": mt5.TIMEFRAME_M30,
                    "H1": mt5.TIMEFRAME_H1,
                    "H4": mt5.TIMEFRAME_H4,
                    "D1": mt5.TIMEFRAME_D1
                }
                tf = tf_map.get(tf_str.upper(), mt5.TIMEFRAME_M5)
                
                # Select symbol in MT5 to guarantee it is enabled for history requests
                mt5.symbol_select(symbol, True)
                rates = mt5.copy_rates_from_pos(symbol, tf, 0, 350)
                if rates is None or len(rates) == 0:
                    rates = mt5.copy_rates_from_pos(symbol, tf, 0, 100)
                if rates is None or len(rates) == 0:
                    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)

                candles = []
                fvgs = []
                sweeps = []
                mss_events = []
                levels = {}
                volume_profile = None
                
                if rates is not None and len(rates) > 0:
                    import pandas as pd
                    df = pd.DataFrame(rates)
                    # Align columns for SMCIndicators
                    df_input = df.copy()
                    df_input['time_dt'] = pd.to_datetime(df_input['time'], unit='s')
                    df_input.set_index('time_dt', inplace=True)
                    df_input.rename(columns={'tick_volume': 'volume'}, inplace=True)
                    df_input = df_input.tail(300) # OPTIMIZATION: Only compute SMC on last 300 bars
                    
                    # Compute SMC features dynamically
                    from utils.smc_indicators import SMCIndicators
                    df_smc = SMCIndicators.compute_smc_features(df_input, window=2)
                    
                    # Compute Volume Profile dynamically
                    from utils.volume_analyzer import VolumeAnalyzer
                    volume_profile = VolumeAnalyzer.calculate_volume_profile(df_input, lookback=100, bins=30)
                    
                    for r in rates:
                        candles.append({
                            "time": int(r['time']),
                            "open": float(r['open']),
                            "high": float(r['high']),
                            "low": float(r['low']),
                            "close": float(r['close']),
                            "volume": float(r['tick_volume'])
                        })
                        
                    # Extract latest levels
                    last_row = df_smc.iloc[-1]
                    latest_support = float(last_row['support']) if not pd.isna(last_row['support']) else None
                    latest_resistance = float(last_row['resistance']) if not pd.isna(last_row['resistance']) else None
                    latest_ob_top = float(last_row['ob_top']) if not pd.isna(last_row['ob_top']) else None
                    latest_ob_bottom = float(last_row['ob_bottom']) if not pd.isna(last_row['ob_bottom']) else None
                    latest_ob_direction = str(last_row['ob_direction']) if ('ob_direction' in last_row and last_row['ob_direction'] != 'none') else None
                    
                    # Traverse the DataFrame to extract FVGs, Sweeps, MSS
                    n_rows = len(df_smc)
                    offset = len(rates) - n_rows
                    for i in range(n_rows):
                        row = df_smc.iloc[i]
                        
                        # FVGs
                        fvg_type = int(row['fvg_type']) if not pd.isna(row['fvg_type']) else 0
                        fvg_class = str(row['fvg_class']) if 'fvg_class' in row else ''
                        # Only show high-quality FVGs (Breakaway Gaps and Runaway FVGs) to reduce chart noise
                        if fvg_type != 0 and fvg_class in ('bag', 'rfvg'):
                            top = float(row['fvg_top'])
                            bottom = float(row['fvg_bottom'])
                            start = max(0, i - 2) + offset
                            end = n_rows - 1 + offset
                            
                            # Check mitigation
                            for k in range(i + 1, n_rows):
                                k_row = df_smc.iloc[k]
                                if fvg_type == 1: # Bullish FVG
                                    if float(k_row['low']) <= bottom:
                                        end = k + offset
                                        break
                                elif fvg_type == -1: # Bearish FVG
                                    if float(k_row['high']) >= top:
                                        end = k + offset
                                        break
                            fvgs.append({
                                "type": "bullish" if fvg_type == 1 else "bearish",
                                "top": top,
                                "bottom": bottom,
                                "start": start,
                                "end": end
                            })
                        
                        # Liquidity Sweeps
                        liq_sweep_type = int(row['liq_sweep_type']) if not pd.isna(row['liq_sweep_type']) else 0
                        if liq_sweep_type != 0:
                            sweeps.append({
                                "index": i + offset,
                                "type": "bullish" if liq_sweep_type == 1 else "bearish",
                                "price": float(row['liq_sweep_level']) if not pd.isna(row['liq_sweep_level']) else float(row['low'] if liq_sweep_type == 1 else row['high'])
                            })
                            
                        # MSS Events
                        mss_signal = int(row['mss_signal']) if not pd.isna(row['mss_signal']) else 0
                        if mss_signal != 0:
                            mss_events.append({
                                "index": i + offset,
                                "type": "bullish" if mss_signal == 1 else "bearish",
                                "price": float(row['close'])
                            })
                            
                    analysis = self.engine.cached_analysis.get(symbol, {})
                    pdh = self.engine.pdh_cache.get(symbol, None)
                    pdl = self.engine.pdl_cache.get(symbol, None)
                    pwh = self.engine.pwh_cache.get(symbol, None)
                    pwl = self.engine.pwl_cache.get(symbol, None)
                    crt_meta = analysis.get("crt_metadata", {})
                    
                    entry_price = None
                    entry_action = None
                    sl_price = None
                    tp_price = None

                    if hasattr(self.engine, 'trade_manager') and self.engine.trade_manager:
                        for ticket, pos in self.engine.trade_manager.positions.items():
                            if getattr(pos, 'symbol', '') == symbol:
                                entry_price = float(getattr(pos, 'entry', 0.0) or getattr(pos, 'entry_price', 0.0) or 0.0)
                                entry_action = str(getattr(pos, 'action', 'BUY'))
                                sl_price = float(getattr(pos, 'sl', 0.0) or 0.0)
                                tp_price = float(getattr(pos, 'tp', 0.0) or 0.0)
                                break
                    if not entry_price and analysis:
                        target = analysis.get("target_setup") or getattr(self.engine, 'last_target_setup', {}).get(symbol)
                        if target:
                            entry_price = float(target.get("entry", 0.0) or 0.0)
                            entry_action = str(target.get("action", "BUY"))
                            sl_price = float(target.get("sl", 0.0) or 0.0)
                            tp_price = float(target.get("tp", 0.0) or 0.0)

                    levels = {
                        "support": latest_support,
                        "resistance": latest_resistance,
                        "crt_high": crt_meta.get("crt_high"),
                        "crt_low": crt_meta.get("crt_low"),
                        "ob_top": latest_ob_top,
                        "ob_bottom": latest_ob_bottom,
                        "ob_direction": latest_ob_direction,
                        "poc": volume_profile.get("poc_price") if volume_profile else None,
                        "volume_profile": volume_profile,
                        "val": volume_profile.get("val_price") if volume_profile else None,
                        "vah": volume_profile.get("vah_price") if volume_profile else None,
                        "pdh": pdh,
                        "pdl": pdl,
                        "pwh": pwh,
                        "pwl": pwl,
                        "entry_price": entry_price,
                        "entry_action": entry_action,
                        "sl_price": sl_price,
                        "tp_price": tp_price
                    }
                else:
                    levels = {
                        "support": None, "resistance": None,
                        "crt_high": None, "crt_low": None,
                        "ob_top": None, "ob_bottom": None,
                        "ob_direction": None, "poc": None,
                        "volume_profile": None, "val": None, "vah": None,
                        "pdh": None, "pdl": None, "pwh": None, "pwl": None,
                        "entry_price": None, "entry_action": None
                    }
                
                open_trades = []
                if hasattr(self.engine, 'trade_manager') and self.engine.trade_manager:
                    for ticket, pos in self.engine.trade_manager.positions.items():
                        if getattr(pos, 'symbol', '') == symbol:
                            open_trades.append({
                                "ticket": ticket,
                                "type": pos.action,
                                "volume": pos.volume,
                                "entry": pos.entry_price,
                                "sl": pos.sl,
                                "tp": pos.tp,
                                "pnl": pos.pnl if hasattr(pos, 'pnl') else 0.0
                            })
                            
                try:
                    self._set_headers()
                    self.wfile.write(json.dumps({
                        "symbol": symbol,
                        "timeframe": tf_str,
                        "candles": candles,
                        "fvgs": fvgs,
                        "sweeps": sweeps,
                        "mss": mss_events,
                        "levels": levels,
                        "trades": open_trades
                    }).encode('utf-8'))
                except (ConnectionResetError, BrokenPipeError, OSError):
                    pass
            except Exception as e:
                try:
                    self._set_headers(status=500)
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                except (ConnectionResetError, BrokenPipeError, OSError):
                    pass
        elif path == "/api/journal":
            try:
                from core.trade_journal import trade_journal
                trades = trade_journal.get_all_trades()
                self._set_headers()
                self.wfile.write(json.dumps({"trades": trades[-200:], "total": len(trades)}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/daily_report":
            try:
                report = self.engine.daily_analyzer.get_latest_report()
                from core.trade_journal import trade_journal
                today_summary = trade_journal.get_daily_summary()
                self._set_headers()
                self.wfile.write(json.dumps({
                    "report": report,
                    "today_summary": today_summary
                }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/backtest_results":
            try:
                results = self.engine.backtester.get_last_results()
                self._set_headers()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/audit_evaluations":
            try:
                import sqlite3
                from core.database import db_instance
                with db_instance._lock:
                    conn = sqlite3.connect(db_instance.db_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM audit_evaluations ORDER BY id DESC LIMIT 100")
                    rows = cursor.fetchall()
                    conn.close()
                
                evaluations = []
                for r in rows:
                    evaluations.append(dict(r))
                    
                self._set_headers()
                self.wfile.write(json.dumps({"evaluations": evaluations}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/logs":
            try:
                import os
                log_lines = []
                log_path = "logs/engine.log"
                if os.path.exists(log_path):
                    # Safely and efficiently read the end of a potentially large file
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(0, os.SEEK_END)
                        file_size = f.tell()
                        seek_size = min(40960, file_size)  # read last 40KB
                        f.seek(file_size - seek_size)
                        content = f.read()
                        lines = content.splitlines()
                        # Clean lines to keep only valid log rows (or last 35 lines)
                        log_lines = lines[-35:]
                self._set_headers()
                self.wfile.write(json.dumps({"logs": log_lines}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/news_schedule":
            try:
                events = news_schedule.get_all_events()
                self._set_headers()
                self.wfile.write(json.dumps({"events": events}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            self._set_headers("text/plain", 404)
            self.wfile.write(b"Not Found")
            
    def do_POST(self):
        if not self._validate_host_and_origin():
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        if path == "/login":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        
        if path == "/api/settings":
            try:
                data = json.loads(post_data.decode('utf-8'))
                validate_settings(data)
                
                # If active_symbol is being updated, ensure it's selected in MT5 and engine immediately
                if "active_symbol" in data:
                    new_sym = str(data["active_symbol"]).strip()
                    if new_sym:
                        match_sym = resolve_broker_symbol(new_sym, getattr(self, 'engine', None))
                        data["active_symbol"] = match_sym
                        mt5.symbol_select(match_sym, True)
                        if hasattr(self, 'engine') and self.engine and match_sym not in self.engine.symbols:
                            self.engine.symbols.append(match_sym)

                # 1. ALWAYS persist directly & immediately to settings_manager (configs/settings.json)
                for key, val in data.items():
                    settings_manager.set(key, val, source="DASHBOARD_API", reason="User updated setting via Web Dashboard")

                # 2. Queue in engine for thread-safe cycle boundary sync if engine is running
                if hasattr(self, 'engine') and self.engine:
                    res = self.engine.queue_settings_update(data)
                    if isinstance(res, dict) and "completion_event" in res:
                        res["completion_event"].wait(timeout=0.5)

                self._set_headers()
                self.wfile.write(json.dumps({"status": "success", "settings": settings_manager.get_all()}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=400)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/reset_settings":
            try:
                settings_manager.reset_all()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/news_schedule/add":
            try:
                data = json.loads(post_data.decode('utf-8'))
                day = data.get("day", "").strip()
                time_utc = data.get("time_utc", "").strip()
                name = data.get("name", "").strip()
                duration_mins = int(data.get("duration_mins", 30))
                
                success = news_schedule.add_event(day, time_utc, name, duration_mins)
                if success:
                    self._set_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                else:
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": "Failed to add event. Check inputs or duplicates."}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/news_schedule/remove":
            try:
                data = json.loads(post_data.decode('utf-8'))
                index = int(data.get("index", -1))
                
                success = news_schedule.remove_event(index)
                if success:
                    self._set_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                else:
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": "Failed to remove event. Index out of range."}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/news_schedule/update":
            try:
                data = json.loads(post_data.decode('utf-8'))
                index = int(data.get("index", -1))
                day = data.get("day")
                time_utc = data.get("time_utc")
                name = data.get("name")
                raw_dur = data.get("duration_mins")
                duration_mins = int(raw_dur) if raw_dur is not None else 30
                
                success = news_schedule.update_event(index, day, time_utc, name, duration_mins)
                if success:
                    self._set_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                else:
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": "Failed to update event."}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/execute_trade":
            try:
                data = json.loads(post_data.decode('utf-8')) if post_data else {}
                raw_sym = data.get("symbol") or getattr(self.engine, 'symbols', ['XAUUSDm'])[0]
                resolved = resolve_broker_symbol(raw_sym, getattr(self, 'engine', None))
                is_micro = bool(data.get("micro_scalp", False))
                
                snapshot = self.engine.get_dashboard_snapshot() if hasattr(self, 'engine') and self.engine else {}
                levels = snapshot.get("levels", {})
                
                if is_micro:
                    tick = mt5.symbol_info_tick(resolved)
                    action = levels.get("entry_action") or "BUY"
                    if tick:
                        entry = tick.ask if action == "BUY" else tick.bid
                    else:
                        entry = levels.get("entry_price") or 4020.0
                    sl = (entry - 1.20) if action == "BUY" else (entry + 1.20)
                    tp = (entry + 2.40) if action == "BUY" else (entry - 2.40)
                    strat_name = "MICRO_SCALP_12P_24P"
                else:
                    entry = levels.get("entry_price")
                    action = levels.get("entry_action") or "BUY"
                    sl = levels.get("sl_price") or 0.0
                    tp = levels.get("tp_price") or 0.0
                    strat_name = "CO_PILOT_HYBRID"
                
                if entry and hasattr(self, 'engine') and self.engine:
                    pos = self.engine.execute_and_record_trade(
                        symbol=resolved,
                        action=action,
                        sl=sl,
                        tp=tp,
                        analysis=self.engine.cached_analysis.get(resolved, {}),
                        strategy_name=strat_name
                    )
                    ticket = getattr(pos, 'ticket', 'MANUAL_EXEC')
                    self._set_headers()
                    self.wfile.write(json.dumps({"status": "success", "action": action, "entry": entry, "ticket": ticket, "mode": "MICRO_SCALP" if is_micro else "CO_PILOT"}).encode('utf-8'))
                else:
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": "No active target setup found on chart to execute."}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/add_symbol":
            try:
                data = json.loads(post_data.decode('utf-8'))
                symbol = data.get("symbol", "").strip()
                if not symbol:
                    raise ValueError("Symbol name cannot be empty")
                
                # Smartly resolve symbol availability on MT5 server
                match = resolve_broker_symbol(symbol, getattr(self, 'engine', None))
                if not match:
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": f"Symbol '{symbol}' not found on broker server"}).encode('utf-8'))
                    return
                
                # Enable the symbol
                if not mt5.symbol_select(match, True):
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": f"Failed to select symbol '{match}' on broker"}).encode('utf-8'))
                    return
                
                # Add to engine symbols
                if match not in self.engine.symbols:
                    self.engine.symbols.append(match)
                    
                # Set active symbol
                settings_manager.set("active_symbol", match)
                
                self._set_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "symbol": match,
                    "all_symbols": self.engine.symbols
                }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=400)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/train":
            try:
                training_thread = threading.Thread(target=self._run_training_job, daemon=True)
                training_thread.start()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "training_started"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/close_all":
            try:
                panic_res = self.engine.trigger_emergency_panic_close()
                command_id = panic_res["command_id"]
                completion_event = panic_res["completion_event"]
                result_holder = panic_res["result_holder"]
                
                completed = completion_event.wait(timeout=3.0)
                if completed:
                    self._set_headers(status=200)
                    self.wfile.write(json.dumps({
                        "status": "SUCCESS",
                        "command_id": command_id,
                        "result": result_holder.get("result")
                    }).encode('utf-8'))
                else:
                    self._set_headers(status=202)
                    self.wfile.write(json.dumps({
                        "status": "ACCEPTED",
                        "command_id": command_id,
                        "message": "Panic command queued, closing asynchronously"
                    }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/journal":
            try:
                from core.trade_journal import trade_journal
                trades = trade_journal.get_all_trades()
                self._set_headers()
                self.wfile.write(json.dumps({"trades": trades[-200:], "total": len(trades)}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/daily_report":
            try:
                report = self.engine.daily_analyzer.get_latest_report()
                from core.trade_journal import trade_journal
                yesterday_summary = trade_journal.get_daily_summary()
                self._set_headers()
                self.wfile.write(json.dumps({
                    "report": report,
                    "today_summary": yesterday_summary
                }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/run_analysis":
            try:
                def _run():
                    from datetime import date
                    self.engine.daily_analyzer.analyze_date(date.today())
                threading.Thread(target=_run, daemon=True).start()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "analysis_started"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/run_backtest":
            try:
                def _run():
                    symbol = self.engine.symbols[0] if self.engine.symbols else "XAUUSDm"
                    trading_mode = settings_manager.get("trading_mode", "scalping")
                    self.engine.backtester.self_optimize(symbol, trading_mode=trading_mode)
                threading.Thread(target=_run, daemon=True).start()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "backtest_started"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/backtest_results":
            try:
                results = self.engine.backtester.get_last_results()
                self._set_headers()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/run_test":
            try:
                data = json.loads(post_data.decode('utf-8'))
                test_type = data.get("test_type", "engine_test")
                
                import subprocess
                import sys
                python_exe = sys.executable or "python"
                
                script_map = {
                    "engine_test": "scratch/test_engine_run.py",
                    "performance_audit": "scratch/performance_audit.py",
                    "safety_check": "scratch/test_safety_engine.py"
                }
                
                script_path = script_map.get(test_type)
                if not script_path:
                    raise ValueError(f"Unknown test type: {test_type}")
                
                res = subprocess.run([python_exe, script_path], capture_output=True, text=True, encoding="utf-8")
                output = res.stdout + "\n" + res.stderr
                
                self._set_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "test_type": test_type,
                    "exit_code": res.returncode,
                    "output": output
                }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        else:
            self._set_headers("text/plain", 404)
            self.wfile.write(b"Not Found")

    def _run_training_job(self):
        if hasattr(self.engine, 'training_in_progress') and self.engine.training_in_progress:
            return
        
        self.engine.training_in_progress = True
        try:
            self.engine.trigger_historical_training()
        except Exception as e:
            self.engine.logger.error(f"Failed to auto-train pattern database: {e}")
        finally:
            self.engine.training_in_progress = False
            
    def _get_status_data(self) -> Dict[str, Any]:
        try:
            snapshot = self.engine.get_dashboard_snapshot()
            if not snapshot:
                return {
                    "account": {"broker": "INITIALIZING", "balance": 0.0, "equity": 0.0, "profit": 0.0},
                    "settings": settings_manager.get_all(),
                    "symbols": self.engine.symbols,
                    "sentiment": {
                        "d1": 0.0, "h4": 0.0, "h1": 0.0, "m30": 0.0, "m15": 0.0, "m5": 0.0, "m1": 0.0,
                        "h1_bias_label": "Neutral", "m15_sweep_label": "Neutral", "m5_mss_label": "Neutral",
                        "news": 0.0, "news_articles": []
                    },
                    "volume": {"rvol": 1, "buy_pressure": 50, "sell_pressure": 50, "profile": {}},
                    "positions": [],
                    "history": [],
                    "market_regime": "RANGING",
                    "training_status": "idle",
                    "leverage": "N/A",
                    "margin_level": "N/A",
                    "latency_ms": 0.0,
                    "spread": {},
                    "diagnostics_status": "UNHEALTHY"
                }

            from utils.snapshot_helper import deep_thaw
            snap_dict = deep_thaw(snapshot)

            acc = snap_dict.get("account", {})
            is_paper = snap_dict.get("risk_status", {}).get("paper_mode", True)
            
            account_data = {
                "broker": acc.get("broker", "GENERIC"),
                "server": "DEMO" if is_paper else "LIVE",
                "login": 0,
                "balance": acc.get("balance", 0.0),
                "equity": acc.get("equity", 0.0),
                "profit": acc.get("profit", 0.0),
                "mode": "paper" if is_paper else "live"
            }
            
            leverage_str = f"1:{acc.get('leverage', 500)}"
            margin_level_str = f"{acc.get('margin_level', 0.0):.1f}%" if acc.get("margin_level", 0.0) > 0 else "N/A"

            spread_data = {}
            if self.engine.symbols:
                symbol = self.engine.symbols[0]
                tick = mt5.symbol_info_tick(symbol)
                symbol_info = mt5.symbol_info(symbol)
                if tick and symbol_info:
                    spread_points = (tick.ask - tick.bid) / symbol_info.point
                    max_spread = settings_manager.get("max_spread_points", 300)
                    spread_data = {
                        "symbol": symbol,
                        "current": round(spread_points, 1),
                        "max_limit": max_spread,
                        "exceeded": spread_points > max_spread,
                        "bid": tick.bid,
                        "ask": tick.ask
                    }

            active_pos = []
            for p in snap_dict.get("positions", ()):
                active_pos.append({
                    "ticket": p.get("ticket"),
                    "symbol": p.get("symbol"),
                    "action": p.get("action"),
                    "volume": p.get("volume"),
                    "entry_price": p.get("entry"),
                    "sl": p.get("sl"),
                    "tp": p.get("tp"),
                    "pnl": p.get("pnl"),
                    "age_seconds": p.get("age_seconds")
                })

            active_settings = settings_manager.get_all()

            from utils.sentiment_analyzer import sentiment_analyzer
            news_state = sentiment_analyzer.get_news_state()
            upcoming_events = list(news_state.get("upcoming_events", []))
            
            tf_alignment = snap_dict.get("tf_alignment", {})
            engine_sentiment = getattr(self.engine, 'sentiment_cache', {}) or {}

            def get_tf_sentiment_score(tf_lower: str, tf_upper: str) -> float:
                # 1. Continuous technical sentiment calculated by sentiment_analyzer
                if tf_lower in engine_sentiment and engine_sentiment[tf_lower] is not None:
                    try:
                        return float(engine_sentiment[tf_lower])
                    except (ValueError, TypeError):
                        pass
                # 2. Alignment bias integer (-1.0, 0.0, 1.0)
                val = tf_alignment.get(tf_upper, {}).get('bias', 0.0)
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0

            d1_score = get_tf_sentiment_score('d1', 'D1')
            h4_score = get_tf_sentiment_score('h4', 'H4')
            h1_score = get_tf_sentiment_score('h1', 'H1')
            m30_score = get_tf_sentiment_score('m30', 'M30')
            m15_score = get_tf_sentiment_score('m15', 'M15')
            m5_score = get_tf_sentiment_score('m5', 'M5')
            m1_score = get_tf_sentiment_score('m1', 'M1')

            def resolve_bias_label(raw_lbl: str, score: float) -> str:
                if raw_lbl and raw_lbl.strip().upper() not in ('NEUTRAL', 'NONE', ''):
                    return raw_lbl.strip()
                if score > 0.15: return 'BULLISH'
                if score < -0.15: return 'BEARISH'
                return 'NEUTRAL'

            h1_lbl = resolve_bias_label(tf_alignment.get('H1', {}).get('label', ''), h1_score)
            m15_lbl = resolve_bias_label(tf_alignment.get('M15', {}).get('label', ''), m15_score)
            m5_lbl = resolve_bias_label(tf_alignment.get('M5', {}).get('label', ''), m5_score)

            sentiment_data = {
                "d1": d1_score,
                "h4": h4_score,
                "h1": h1_score,
                "m30": m30_score,
                "m15": m15_score,
                "m5": m5_score,
                "m1": m1_score,
                "h1_bias_label": h1_lbl,
                "m15_sweep_label": m15_lbl,
                "m5_mss_label": m5_lbl,
                "news": news_state.get("score", 0.0),
                "usd_forecast_bias": news_state.get("usd_forecast_bias", "NEUTRAL"),
                "news_articles": news_state.get("articles", [])[:10],
                "upcoming_events": upcoming_events
            }

            # Get real volume data from engine's volume_cache
            engine_vol = getattr(self.engine, 'volume_cache', {}) or {}
            volume_data = {
                "rvol": float(engine_vol.get("rvol", 1.0)),
                "buy_pressure": float(engine_vol.get("buy_pressure", 50.0)),
                "sell_pressure": float(engine_vol.get("sell_pressure", 50.0)),
                "profile": engine_vol.get("profile", {})
            }

            closed_pos = []
            try:
                from core.trade_journal import trade_journal
                journal_trades = trade_journal.get_all_trades()
                recent_trades = journal_trades[-50:] if journal_trades else []
                for i, t in enumerate(recent_trades):
                    closed_pos.append({
                        "id": f"J-{i+1}",
                        "symbol": t.get("symbol", ""),
                        "action": t.get("action", ""),
                        "volume": float(t.get("lot_size", 0.01)) if t.get("lot_size") != "" else 0.01,
                        "entry_price": float(t.get("entry_price", 0.0)) if t.get("entry_price") != "" else 0.0,
                        "close_price": float(t.get("close_price", 0.0)) if t.get("close_price") != "" else 0.0,
                        "close_time": f"{t.get('date', '')} {t.get('time', '')}".strip(),
                        "close_reason": t.get("close_reason", ""),
                        "pnl": float(t.get("pnl", 0.0)) if t.get("pnl") != "" else 0.0,
                        "strategy_name": t.get("strategy_name", "UNKNOWN"),
                        "entry_pattern": t.get("entry_pattern", "UNKNOWN")
                    })
            except Exception as je:
                logging.getLogger("PulseViper.WebDashboard").error(f"Error reading from trade history: {je}")

            regime = snap_dict.get("market", {}).get("regime", "RANGE")
            prediction_data = snap_dict.get("prediction", {})
            skipped_stats = snap_dict.get("starvation_stats", {})

            routing = snap_dict.get("routing", {})
            best_strategy_suggestion = routing.get("suggestions", {})
            if not best_strategy_suggestion:
                best_strategy_suggestion = {
                    "strategy": "UNKNOWN",
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "total_trades": 0,
                    "net_pnl_R": 0.0,
                    "reason": "Scanning optimizer matrix...",
                    "routing_adjustment": 0.0,
                    "source": "fallback",
                    "mode": settings_manager.get("trading_mode", "intraday"),
                    "session": "LONDON",
                    "regime": regime
                }

            diag = snap_dict.get("diagnostics", {})
            diag_status = "HEALTHY" if diag.get("allowed", True) else "UNHEALTHY"

            return {
                "account": account_data,
                "settings": active_settings,
                "symbols": self.engine.symbols,
                "sentiment": sentiment_data,
                "volume": volume_data,
                "positions": active_pos,
                "history": closed_pos,
                "market_regime": regime,
                "training_status": "training" if getattr(self.engine, 'training_in_progress', False) else "idle",
                "leverage": leverage_str,
                "margin_level": margin_level_str,
                "latency_ms": round(self.engine.market_state.get('latency_ms', 0.0), 1),
                "spread": spread_data,
                "prediction": prediction_data,
                "skipped_stats": skipped_stats,
                "active_sessions": list(snap_dict.get("active_sessions", ())),
                "tf_alignment": tf_alignment,
                "starvation_stats": skipped_stats,
                "is_new_candle_close": False,
                "diagnostics_status": diag_status,
                "session_context": {},
                "strategy_suggestion": best_strategy_suggestion,
                "strategy_rankings": list(snap_dict.get("strategy_rankings", []))
            }
        except Exception as exc:
            logger = logging.getLogger("PulseViper.WebDashboard")
            logger.exception(
                "Error gathering status JSON: %s",
                exc,
            )

            symbols = list(
                getattr(self.engine, "symbols", [])
                or []
            )

            active_symbol = (
                symbols[0]
                if symbols
                else settings_manager.get(
                    "active_symbol",
                    "",
                )
            )

            return {
                "status_error": str(exc),
                "account": {
                    "broker": "ERROR",
                    "server": "",
                    "login": 0,
                    "balance": 0.0,
                    "equity": 0.0,
                    "profit": 0.0,
                    "mode": "unknown",
                },
                "settings": settings_manager.get_all(),
                "symbols": symbols,
                "sentiment": {
                    "d1": 0.0,
                    "h4": 0.0,
                    "h1": 0.0,
                    "m30": 0.0,
                    "m15": 0.0,
                    "m5": 0.0,
                    "m1": 0.0,
                    "news": 0.0,
                    "h1_bias_label": "Unavailable",
                    "m15_sweep_label": "Unavailable",
                    "m5_mss_label": "Unavailable",
                    "usd_forecast_bias": "NEUTRAL",
                    "news_articles": [],
                    "upcoming_events": [],
                },
                "volume": {
                    "rvol": 1.0,
                    "buy_pressure": 50.0,
                    "sell_pressure": 50.0,
                    "profile": {},
                },
                "positions": [],
                "history": [],
                "market_regime": "UNKNOWN",
                "training_status": "idle",
                "leverage": "N/A",
                "margin_level": "N/A",
                "latency_ms": 0.0,
                "spread": {
                    "symbol": active_symbol,
                    "current": None,
                    "max_limit": settings_manager.get(
                        "max_spread_points",
                        300,
                    ),
                    "exceeded": False,
                    "bid": 0.0,
                    "ask": 0.0,
                },
                "prediction": {},
                "skipped_stats": {},
                "active_sessions": [],
                "tf_alignment": {},
                "starvation_stats": {},
                "session_context": {},
                "strategy_suggestion": None,
                "strategy_rankings": [],
                "diagnostics_status": "UNHEALTHY",
                "is_new_candle_close": False,
            }

class WebDashboardServer:
    def __init__(self, engine, port=8000):
        self.engine = engine
        self.port = port
        self.server = None
        self.thread = None
        self.logger = logging.getLogger("PulseViper.WebDashboard")
        
    def start(self):
        handler_factory = lambda *args, **kwargs: DashboardRequestHandler(self.engine, *args, **kwargs)
        self.server = ThreadingHTTPServer(('127.0.0.1', self.port), handler_factory)
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self.logger.info(f"Glassmorphic Web Control Dashboard running at http://localhost:{self.port}")
        
    def _run_server(self):
        try:
            if self.server:
                self.server.serve_forever()
        except Exception as e:
            self.logger.error(f"Web Dashboard Server error: {e}")
            
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)
