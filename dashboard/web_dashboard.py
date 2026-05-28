# dashboard/web_dashboard.py
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from typing import Dict, Any, List
import MetaTrader5 as mt5
from utils.settings_manager import settings_manager
from dashboard.html_template import HTML_TEMPLATE

class DashboardRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, engine, *args, **kwargs):
        self.engine = engine
        super().__init__(*args, **kwargs)
        
    def _set_headers(self, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
    def do_OPTIONS(self):
        self._set_headers(status=200)
        
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == "/":
            self._set_headers("text/html; charset=utf-8")
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif path == "/api/status":
            self._set_headers()
            status_data = self._get_status_data()
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
        elif path == "/api/chart":
            try:
                query = urllib.parse.parse_qs(parsed_url.query)
                symbol = query.get("symbol", [None])[0]
                if not symbol and self.engine.symbols:
                    symbol = self.engine.symbols[0]
                elif not symbol:
                    symbol = "EURUSDm"
                    
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
                
                rates = mt5.copy_rates_from_pos(symbol, tf, 0, 150)
                candles = []
                if rates is not None:
                    for r in rates:
                        candles.append({
                            "time": int(r['time']),
                            "open": float(r['open']),
                            "high": float(r['high']),
                            "low": float(r['low']),
                            "close": float(r['close']),
                            "volume": float(r['tick_volume'])
                        })
                
                # Fetch levels and active trades
                analysis = self.engine.cached_analysis.get(symbol, {})
                fib_meta = analysis.get("fib_metadata", {})
                
                pdh = self.engine.pdh_cache.get(symbol, None)
                pdl = self.engine.pdl_cache.get(symbol, None)
                pwh = self.engine.pwh_cache.get(symbol, None)
                pwl = self.engine.pwl_cache.get(symbol, None)

                levels = {
                    "support": analysis.get("support"),
                    "resistance": analysis.get("resistance"),
                    "fib_50": fib_meta.get("fib_50"),
                    "fib_618": fib_meta.get("fib_618"),
                    "fib_786": fib_meta.get("fib_786"),
                    "poc": fib_meta.get("poc"),
                    "val": fib_meta.get("val"),
                    "vah": fib_meta.get("vah"),
                    "order_blocks": fib_meta.get("order_blocks", {}),
                    "pdh": pdh,
                    "pdl": pdl,
                    "pwh": pwh,
                    "pwl": pwl
                }
                
                open_trades = []
                if hasattr(self.engine.trade_manager, 'positions'):
                    for p in self.engine.trade_manager.positions.values():
                        if p.symbol == symbol:
                            open_trades.append({
                                "entry": p.entry_price,
                                "sl": p.sl,
                                "tp": p.tp,
                                "action": p.action
                            })
                # Add virtual/analyzed trade levels to the chart lines payload
                if hasattr(self.engine, 'analyzed_trades') and symbol in self.engine.analyzed_trades:
                    at = self.engine.analyzed_trades[symbol]
                    open_trades.append({
                        "entry": at["entry"],
                        "sl": at["sl"],
                        "tp": at["tp"],
                        "action": at["action"]
                    })
                            
                self._set_headers()
                self.wfile.write(json.dumps({
                    "symbol": symbol,
                    "timeframe": tf_str,
                    "candles": candles,
                    "levels": levels,
                    "trades": open_trades
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
        else:
            self._set_headers("text/plain", 404)
            self.wfile.write(b"Not Found")
            
    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        if path == "/api/settings":
            try:
                data = json.loads(post_data.decode('utf-8'))
                for key, val in data.items():
                    settings_manager.set(key, val)
                self._set_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=400)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/add_symbol":
            try:
                data = json.loads(post_data.decode('utf-8'))
                symbol = data.get("symbol", "").strip()
                if not symbol:
                    raise ValueError("Symbol name cannot be empty")
                
                # Check availability in MT5
                all_symbols = [s.name for s in mt5.symbols_get()]
                match = None
                for s in all_symbols:
                    if s.upper() == symbol.upper():
                        match = s
                        break
                        
                if not match:
                    self._set_headers(status=400)
                    self.wfile.write(json.dumps({"error": f"Symbol '{symbol}' not found on broker server"}).encode('utf-8'))
                    return
                
                # Enable the symbol
                mt5.symbol_select(match, True)
                
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
                res = self.engine.close_all_positions()
                self._set_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
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
            account = mt5.account_info()
            broker_name = account.company if account else "GENERIC"
            server_name = account.server if account else "DEMO"
            login_num = account.login if account else 0
            
            is_paper = settings_manager.get("paper_mode", True)
            if is_paper:
                balance = getattr(self.engine.trade_manager, 'virtual_balance', 10000.0)
                equity = getattr(self.engine.trade_manager, 'virtual_equity', 10000.0)
                profit = equity - balance
                
                # Dynamic Paper Margin Calculation using MT5 account leverage
                leverage = account.leverage if (account and getattr(account, 'leverage', None)) else 500
                leverage_str = f"1:{leverage}"
                
                total_margin = 0.0
                for ticket, pos in self.engine.trade_manager.positions.items():
                    symbol_info = mt5.symbol_info(pos.symbol)
                    if symbol_info:
                        contract_size = getattr(symbol_info, 'trade_contract_size', 1.0)
                        pos_margin = (contract_size * pos.volume * pos.entry_price) / leverage
                        total_margin += pos_margin
                
                if total_margin > 0:
                    virtual_margin_level = (equity / total_margin) * 100.0
                    margin_level_str = f"{virtual_margin_level:.1f}%"
                else:
                    margin_level_str = "9999.9%"
            else:
                balance = account.balance if account else 0.0
                equity = account.equity if account else 0.0
                profit = account.profit if account else 0.0
                leverage_str = f"1:{account.leverage}" if (account and getattr(account, 'leverage', None)) else "N/A"
                margin_level_str = f"{account.margin_level:.1f}%" if (account and getattr(account, 'margin_level', None) and account.margin_level > 0) else "N/A"
                
            account_data = {
                "broker": broker_name,
                "server": server_name,
                "login": login_num,
                "balance": balance,
                "equity": equity,
                "profit": profit,
                "mode": "paper" if is_paper else "live"
            }
            loop_latency = self.engine.market_state.get('latency_ms', 0.0)
            
            spread_data = {}
            if len(self.engine.symbols) > 0:
                symbol = self.engine.symbols[0]
                tick = mt5.symbol_info_tick(symbol)
                symbol_info = mt5.symbol_info(symbol)
                if tick and symbol_info:
                    spread_points = (tick.ask - tick.bid) / symbol_info.point
                    max_spread = settings_manager.get("max_spread_points", 20)
                    spread_data = {
                        "symbol": symbol,
                        "current": round(spread_points, 1),
                        "max_limit": max_spread,
                        "exceeded": spread_points > max_spread,
                        "bid": tick.bid,
                        "ask": tick.ask
                    }
                else:
                    spread_data = {
                        "symbol": symbol,
                        "current": None,
                        "max_limit": settings_manager.get("max_spread_points", 20),
                        "exceeded": False,
                        "bid": 0.0,
                        "ask": 0.0
                    }
            
            active_settings = settings_manager.get_all()
            
            sent_d1 = 0.0
            sent_h4 = 0.0
            sent_h1 = 0.0
            sent_m30 = 0.0
            sent_m15 = 0.0
            sent_m5 = 0.0
            sent_m1 = 0.0
            h1_lbl = "Neutral"
            m15_lbl = "Neutral"
            m5_lbl = "Neutral"
            
            sentiment_cache = getattr(self.engine, 'sentiment_cache', {})
            if sentiment_cache:
                sent_d1 = sentiment_cache.get('d1', 0.0)
                sent_h4 = sentiment_cache.get('h4', 0.0)
                sent_h1 = sentiment_cache.get('h1', 0.0)
                sent_m30 = sentiment_cache.get('m30', 0.0)
                sent_m15 = sentiment_cache.get('m15', 0.0)
                sent_m5 = sentiment_cache.get('m5', 0.0)
                sent_m1 = sentiment_cache.get('m1', 0.0)
                
                h1_lbl = "Bullish" if sent_h1 > 0.15 else ("Bearish" if sent_h1 < -0.15 else "Neutral")
                m15_lbl = "Bullish" if sent_m15 > 0.15 else ("Bearish" if sent_m15 < -0.15 else "Neutral")
                m5_lbl = "Bullish" if sent_m5 > 0.15 else ("Bearish" if sent_m5 < -0.15 else "Neutral")
                
            from utils.sentiment_analyzer import sentiment_analyzer
            news_state = sentiment_analyzer.get_news_state()
            
            sentiment_data = {
                "d1": sent_d1,
                "h4": sent_h4,
                "h1": sent_h1,
                "m30": sent_m30,
                "m15": sent_m15,
                "m5": sent_m5,
                "m1": sent_m1,
                "h1_bias_label": h1_lbl,
                "m15_sweep_label": m15_lbl,
                "m5_mss_label": m5_lbl,
                "news": news_state.get("score", 0.0),
                "usd_forecast_bias": news_state.get("usd_forecast_bias", "NEUTRAL"),
                "news_articles": news_state.get("articles", []),
                "upcoming_events": news_state.get("upcoming_events", [])
            }
            
            volume_cache = getattr(self.engine, 'volume_cache', {})
            volume_data = {
                "rvol": volume_cache.get("rvol", 1.0),
                "buy_pressure": volume_cache.get("buy_pressure", 50.0),
                "sell_pressure": volume_cache.get("sell_pressure", 50.0),
                "profile": volume_cache.get("profile", {})
            }
            
            active_pos = []
            if hasattr(self.engine.trade_manager, 'positions'):
                for p in self.engine.trade_manager.positions.values():
                    symbol_info = mt5.symbol_info(p.symbol)
                    sl_usd = 0.0
                    tp_usd = 0.0
                    if symbol_info:
                        point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
                        if p.sl != 0:
                            if p.action == "BUY":
                                sl_diff_points = (p.entry_price - p.sl) / symbol_info.point
                            else:
                                sl_diff_points = (p.sl - p.entry_price) / symbol_info.point
                            sl_usd = -1 * (sl_diff_points * point_value * p.volume)
                            
                        if p.tp != 0:
                            if p.action == "BUY":
                                tp_diff_points = (p.tp - p.entry_price) / symbol_info.point
                            else:
                                tp_diff_points = (p.entry_price - p.tp) / symbol_info.point
                            tp_usd = tp_diff_points * point_value * p.volume
                            
                    active_pos.append({
                        "id": p.id,
                        "symbol": p.symbol,
                        "action": p.action,
                        "volume": p.volume,
                        "entry_price": p.entry_price,
                        "sl": p.sl,
                        "tp": p.tp,
                        "pnl": p.pnl,
                        "sl_usd": round(sl_usd, 2) if sl_usd != 0 else None,
                        "tp_usd": round(tp_usd, 2) if tp_usd != 0 else None,
                        "sibling_id": p.sibling_id
                    })
                    
            closed_pos = []
            try:
                from core.trade_journal import trade_journal
                all_trades = trade_journal.get_all_trades()
                recent_trades = all_trades[-50:] if all_trades else []
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
                        "pnl": float(t.get("pnl", 0.0)) if t.get("pnl") != "" else 0.0
                    })
            except Exception as je:
                logging.getLogger("PulseViper.WebDashboard").error(f"Error reading from trade journal: {je}")
                    
            regime = "RANGING"
            if hasattr(self.engine, 'pattern_learner') and len(self.engine.symbols) > 0:
                regime = self.engine.pattern_learner.get_market_regime(self.engine.symbols[0])
                
            prediction_data = {}
            if len(self.engine.symbols) > 0:
                try:
                    prediction_data = self.engine.get_prediction_data(self.engine.symbols[0])
                except Exception:
                    pass

            skipped_stats = getattr(self.engine, 'skipped_stats', {})

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
                "latency_ms": round(loop_latency, 1),
                "spread": spread_data,
                "prediction": prediction_data,
                "skipped_stats": skipped_stats
            }
        except Exception as e:
            logging.getLogger("PulseViper.WebDashboard").error(f"Error gathering status json: {e}")
            return {
                "account": {"broker": "ERROR", "balance": 0, "equity": 0, "profit": 0},
                "settings": {},
                "sentiment": {"h1": 0, "m15": 0, "m5": 0, "news": 0, "news_articles": []},
                "volume": {"rvol": 1, "buy_pressure": 50, "sell_pressure": 50, "profile": {}},
                "positions": [],
                "history": [],
                "market_regime": "RANGING",
                "training_status": "idle",
                "leverage": "N/A",
                "margin_level": "N/A",
                "latency_ms": 0.0,
                "spread": {}
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
            self.server.serve_forever()
        except Exception as e:
            self.logger.error(f"Web Dashboard Server error: {e}")
            
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)
