# core/engine.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import os
import logging
from datetime import datetime, timezone
import traceback
from collections import deque
from typing import List, Dict, Tuple, Optional

from utils.mt5_data import fetch_ohlcv, init_mt5, shutdown_mt5
from utils.smc_indicators import SMCIndicators
from configs.config import Config
from core.experience_memory import ExperienceMemory
from core.pattern_learner import PatternLearner
from core.trade_manager import PaperTradeManager, LiveTradeManager
from core.trade_journal import trade_journal
from core.daily_analyzer import DailyAnalyzer
from core.backtester import AdaptiveBacktester
from utils.settings_manager import settings_manager
from utils.volume_analyzer import VolumeAnalyzer
from utils.sentiment_analyzer import sentiment_analyzer
from strategies.fib_retest import FibRetestStrategy
from dashboard.web_dashboard import WebDashboardServer

class AdvancedTradingEngine:
    def __init__(self, symbols=None, strategy_mode='smc', enable_dashboard=True, port=8000):
        self.strategy_mode = strategy_mode
        self.config = Config()
        
        # Setup logging
        import sys
        log_handler = logging.StreamHandler(sys.stdout)
        log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        logging.basicConfig(
            level=logging.INFO,
            handlers=[
                logging.FileHandler("logs/engine.log", encoding="utf-8"),
                log_handler
            ]
        )
        self.logger = logging.getLogger("PulseViper.Engine")

        # Connection health
        self.connected = False
        self.cycle_count = 0
        self.market_state = {}
        
        # Initialize MT5 Connection
        self._initialize_connection()

        # Symbol handling
        if symbols is None:
            self.symbols = self._auto_detect_symbols()
        else:
            self.symbols = self._validate_symbols(symbols)

        # Initialize both Trade Managers (Dynamic property will resolve active one based on settings)
        self.paper_trade_manager = PaperTradeManager(self.config)
        self.live_trade_manager = LiveTradeManager(self.config)
        self.logger.info("🎮 Paper Trade Manager and ⚠️ Live Trade Manager initialized")

        # Sniper pullback and fast 1s loop caches
        self.last_candle_times = {}
        self.last_analysis_times = {}
        self.cached_analysis = {}
        self.pending_setups = {}

        # Initialize AI Learning Systems
        self.experience_memory = ExperienceMemory(capacity=5000)
        self.pattern_learner = PatternLearner(self.experience_memory)
        self.performance_history = deque(maxlen=100)
        
        # Initialize self-improvement systems
        self.daily_analyzer = DailyAnalyzer(pattern_learner=self.pattern_learner)
        self.backtester = AdaptiveBacktester()
        self._last_nightly_date = None  # Track last nightly run date
        
        # Sync historical performance stats
        self._sync_performance_stats()

        # Initialize Sentiment and Volume Caches
        self.sentiment_cache = {"d1": 0.0, "h4": 0.0, "h1": 0.0, "m30": 0.0, "m15": 0.0, "m5": 0.0, "m1": 0.0}
        try:
            import os
            import json
            cache_path = os.path.join("configs", "sentiment_cache.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            if k in self.sentiment_cache:
                                self.sentiment_cache[k] = float(v)
                        self.logger.info(f"Loaded persisted sentiment cache: {self.sentiment_cache}")
        except Exception as e:
            self.logger.warning(f"Failed to load sentiment cache: {e}")

        self.volume_cache = {"rvol": 1.0, "buy_pressure": 50.0, "sell_pressure": 50.0, "profile": {}}
        self.training_in_progress = False
        self.skipped_stats = {
            "high_spread": 0,
            "news_filter": 0,
            "low_confidence": 0,
            "positions_limit": 0,
            "killzone_inactive": 0,
            "no_fvg": 0
        }

        # Start news sentiment analyzer background thread
        sentiment_analyzer.start()

        # Save strategy mode to settings if specified
        if strategy_mode in ['scalping', 'intraday', 'swing']:
            settings_manager.set("trading_mode", strategy_mode)

        # Initialize Dashboard Server
        self.dashboard = None
        if enable_dashboard:
            try:
                self.dashboard = WebDashboardServer(self, port=port)
            except Exception as e:
                self.logger.warning(f"Failed to initialize dashboard: {e}")

    @property
    def trade_manager(self):
        """Dynamically resolve the active trade manager based on settings"""
        if settings_manager.get("paper_mode", True):
            return self.paper_trade_manager
        else:
            return self.live_trade_manager

    def _initialize_connection(self):
        """Initialize connection to MT5 terminal"""
        try:
            if init_mt5():
                self.connected = True
                account = mt5.account_info()
                if account:
                    self.logger.info(f"Connected to MT5 Broker Account: {account.login} | Server: {account.server}")
                else:
                    self.logger.warning("Connected to MT5, but failed to fetch account info")
            else:
                self.connected = False
                raise ConnectionError("Failed to initialize MetaTrader 5")
        except Exception as e:
            self.logger.error(f"MT5 Initialization error: {e}")
            raise e

    def _reconnect_if_needed(self):
        """Health check and auto-reconnection"""
        try:
            account = mt5.account_info()
            if account is None:
                self.connected = False
                self.logger.warning("Connection lost. Retrying MT5 connection...")
                self._initialize_connection()
        except Exception as e:
            self.connected = False
            self.logger.error(f"Reconnection health check failed: {e}")

    def _auto_detect_symbols(self) -> List[str]:
        """Automatically find working symbols. Prioritizes Gold."""
        available_symbols = [s.name for s in mt5.symbols_get()]
        
        # Gold checks
        for sym in ['GOLD', 'XAUUSDm', 'XAUUSD']:
            if sym in available_symbols:
                mt5.symbol_select(sym, True)
                return [sym]
                
        # Fallback to major currency pairs
        for sym in ['EURUSD', 'GBPUSD', 'USDJPY']:
            if sym in available_symbols:
                mt5.symbol_select(sym, True)
                return [sym]
                
        return ['EURUSD']  # Ultimate fallback

    def _validate_symbols(self, symbols: List[str]) -> List[str]:
        """Validate that requested symbols are available on broker"""
        available_symbols = [s.name for s in mt5.symbols_get()]
        valid = []
        for s in symbols:
            if s in available_symbols:
                mt5.symbol_select(s, True)
                valid.append(s)
            else:
                self.logger.warning(f"Requested symbol {s} is not available on broker")
                
        if not valid:
            return self._auto_detect_symbols()
        return valid

    def _sync_performance_stats(self):
        """Sync tracking stats with experience memory"""
        for exp in self.experience_memory.memory:
            trade_rec = {
                'timestamp': exp['timestamp'],
                'symbol': exp['metadata'].get('symbol', 'UNKNOWN'),
                'action': 'BUY' if exp['action'] == 1 else 'SELL',
                'pnl': exp['reward'],
                'close_reason': exp['metadata'].get('close_reason', 'Closed')
            }
            self.performance_history.append(trade_rec)

    def is_killzone_active(self) -> bool:
        """Check if current UTC time is inside the London or New York Killzones"""
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        
        london_start, london_end = self.config.LONDON_SESSION
        ny_start, ny_end = self.config.NY_SESSION
        
        in_london = (london_start <= hour < london_end)
        in_ny = (ny_start <= hour < ny_end)
        
        london_enabled = settings_manager.get("london_session_enabled", True)
        ny_enabled = settings_manager.get("ny_session_enabled", True)
        
        # If both are disabled, bypass session filter (always allow trading)
        if not london_enabled and not ny_enabled:
            return True
            
        london_active = in_london and london_enabled
        ny_active = in_ny and ny_enabled
        
        return london_active or ny_active

    def run_multi_timeframe_analysis(self, symbol: str) -> Optional[Dict]:
        """
        Execute Multi-Timeframe Alignment:
        - HTF (Bias): Trend bias determination
        - Context (Sweep): Liquidity sweeps and session boundaries
        - LTF (Entry): Structural entry shifts (MSS) and volume profiles
        """
        try:
            # Get active strategy mode from settings manager
            trading_mode = settings_manager.get("trading_mode", "intraday").lower()
            
            # Set timeframes dynamically
            if trading_mode == "scalping":
                tf_htf = mt5.TIMEFRAME_H1
                tf_context = mt5.TIMEFRAME_M5
                tf_ltf = mt5.TIMEFRAME_M1
            elif trading_mode == "swing":
                tf_htf = mt5.TIMEFRAME_D1
                tf_context = mt5.TIMEFRAME_H1
                tf_ltf = mt5.TIMEFRAME_M15
            else:  # intraday
                tf_htf = mt5.TIMEFRAME_H1
                tf_context = mt5.TIMEFRAME_M15
                tf_ltf = mt5.TIMEFRAME_M5
                
            # 1. Fetch data
            df_htf = fetch_ohlcv(symbol, tf_htf, n=500)
            df_context = fetch_ohlcv(symbol, tf_context, n=300)
            df_ltf = fetch_ohlcv(symbol, tf_ltf, n=200)
            
            if df_htf is None or df_context is None or df_ltf is None:
                self.logger.warning(f"Failed to fetch multi-timeframe candles for {symbol}")
                return None
                
            if len(df_htf) < 50 or len(df_context) < 50 or len(df_ltf) < 50:
                self.logger.warning(f"Insufficient historical bars for {symbol}")
                return None
                
            # 2. Compute SMC indicators on all timeframes
            htf_smc = SMCIndicators.compute_smc_features(df_htf)
            context_smc = SMCIndicators.compute_smc_features(df_context)
            ltf_smc = SMCIndicators.compute_smc_features(df_ltf)
            
            latest_htf = htf_smc.iloc[-1]
            latest_context = context_smc.iloc[-1]
            latest_ltf = ltf_smc.iloc[-1]
            
            # Read lookback settings (auto-tuned by backtester grid optimizer)
            _sweep_lb = settings_manager.get('smc_lookback_sweep', 20)
            _mss_lb = settings_manager.get('smc_lookback_mss', 10)
            _fvg_lb = settings_manager.get('smc_fvg_lookback', 5)

            # Check recent sweeps on context timeframe
            recent_context_sweeps = context_smc.iloc[-_sweep_lb:]
            sweep_type = 0
            sweep_level = np.nan
            
            # Scan backward to get the most recent sweep
            for _, row in reversed(list(recent_context_sweeps.iterrows())):
                if row['liq_sweep_type'] != 0:
                    sweep_type = int(row['liq_sweep_type'])
                    sweep_level = float(row['liq_sweep_level'])
                    break
                    
            # Check recent MSS on LTF
            recent_ltf_mss = ltf_smc.iloc[-_mss_lb:]
            mss_signal = 0
            # Scan backward to get the most recent MSS
            for _, row in reversed(list(recent_ltf_mss.iterrows())):
                if row['mss_signal'] != 0:
                    mss_signal = int(row['mss_signal'])
                    break

            # FVG class: check last N bars for any non-rfvg FVG
            recent_fvg = ltf_smc.iloc[-_fvg_lb:]
            non_rfvg_rows = recent_fvg[(recent_fvg['fvg_class'] != 'none') & (recent_fvg['fvg_class'] != 'rfvg')] if len(recent_fvg) > 0 else pd.DataFrame()
            if len(non_rfvg_rows) > 0:
                best_fvg_row = non_rfvg_rows.iloc[-1]
                fvg_class = best_fvg_row['fvg_class']
                fvg_type = best_fvg_row['fvg_type']
                fvg_top = best_fvg_row['fvg_top']
                fvg_bottom = best_fvg_row['fvg_bottom']
            else:
                fvg_class = latest_ltf['fvg_class']
                fvg_type = latest_ltf['fvg_type']
                fvg_top = latest_ltf['fvg_top']
                fvg_bottom = latest_ltf['fvg_bottom']

            # Calculate and cache technical sentiment for all 7 timeframes
            tfs = {
                'd1': mt5.TIMEFRAME_D1,
                'h4': mt5.TIMEFRAME_H4,
                'h1': mt5.TIMEFRAME_H1,
                'm30': mt5.TIMEFRAME_M30,
                'm15': mt5.TIMEFRAME_M15,
                'm5': mt5.TIMEFRAME_M5,
                'm1': mt5.TIMEFRAME_M1
            }
            
            # Map current tf_htf, tf_context, tf_ltf to their dataframes to optimize fetching
            mode_tfs = {
                tf_htf: df_htf,
                tf_context: df_context,
                tf_ltf: df_ltf
            }
            
            _temp_sentiment = dict(self.sentiment_cache)  # start with last-known values
            for tf_name, tf_const in tfs.items():
                if tf_const in mode_tfs:
                    df_tf = mode_tfs[tf_const]
                else:
                    df_tf = fetch_ohlcv(symbol, tf_const, n=100)
                
                if df_tf is not None and len(df_tf) >= 50:
                    _temp_sentiment[tf_name] = sentiment_analyzer.calculate_technical_sentiment(df_tf)
                else:
                    _temp_sentiment[tf_name] = self.sentiment_cache.get(tf_name, 0.0)  # keep last value
            self.sentiment_cache = _temp_sentiment  # atomic swap
            try:
                import os
                import json
                cache_path = os.path.join("configs", "sentiment_cache.json")
                with open(cache_path, "w") as f:
                    json.dump(self.sentiment_cache, f)
            except Exception as e:
                pass

            # Calculate and cache volume metrics
            rvol_series = VolumeAnalyzer.calculate_rvol(df_ltf, period=20)
            buy_press_series, sell_press_series = VolumeAnalyzer.calculate_buying_selling_pressure(df_ltf)
            
            latest_rvol = float(rvol_series.iloc[-1])
            latest_buy_press = float(buy_press_series.iloc[-1])
            latest_sell_press = float(sell_press_series.iloc[-1])
            
            total_press = latest_buy_press + latest_sell_press
            if total_press > 0:
                buy_pct = (latest_buy_press / total_press) * 100.0
                sell_pct = (latest_sell_press / total_press) * 100.0
            else:
                buy_pct = 50.0
                sell_pct = 50.0
                
            vp_profile = VolumeAnalyzer.calculate_volume_profile(df_ltf, lookback=100, bins=20)
            
            self.volume_cache = {
                "rvol": latest_rvol,
                "buy_pressure": buy_pct,
                "sell_pressure": sell_pct,
                "profile": vp_profile
            }

            # Current bid/ask
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return None
                
            # Evaluate Fibonacci Retest Strategy
            fib_action, fib_regime, fib_sl, fib_tp, fib_metadata = FibRetestStrategy.evaluate_retest(
                df_context, tick.bid, latest_ltf['atr']
            )
            
            # Update pattern learner's market regimes state (upper case)
            self.pattern_learner.market_regimes[symbol] = {
                'regime': fib_regime.upper(),
                'timestamp': str(pd.Timestamp.now()),
                'volatility': latest_ltf['volatility'],
                'atr_pct': latest_ltf['atr_pct']
            }
                
            analysis = {
                'symbol': symbol,
                'price': tick.bid,
                'bid': tick.bid,
                'ask': tick.ask,
                'h1_bias': latest_htf['active_bias'],
                'm15_sweep_type': sweep_type,
                'm15_sweep_level': sweep_level,
                'm5_mss_signal': mss_signal,
                'm5_fvg_class': fvg_class,
                'm5_fvg_type': fvg_type,
                'm5_fvg_top': fvg_top,
                'm5_fvg_bottom': fvg_bottom,
                'support': latest_ltf['support'],
                'resistance': latest_ltf['resistance'],
                'volatility': latest_ltf['volatility'],
                'atr_pct': latest_ltf['atr_pct'],
                'atr': latest_ltf['atr'],
                'hour': datetime.now(timezone.utc).hour,
                'fib_action': fib_action,
                'fib_regime': fib_regime,
                'fib_sl': fib_sl,
                'fib_tp': fib_tp,
                'fib_metadata': fib_metadata,
                'features': {
                    'active_bias': latest_htf['active_bias'],
                    'liq_sweep_type': sweep_type,
                    'mss_signal': mss_signal,
                    'fvg_class': fvg_class,
                    'support': latest_ltf['support'],
                    'resistance': latest_ltf['resistance'],
                    'atr_pct': latest_ltf['atr_pct'],
                    'volatility': latest_ltf['volatility'],
                    'hour': datetime.now(timezone.utc).hour,
                    'price': tick.bid
                }
            }
            
            # Dynamic broker Adaptation (only on first run or if not configured)
            if not getattr(self, '_broker_profile_set', False):
                from utils.symbol_manager import symbol_manager
                profile = symbol_manager.get_broker_profile(symbol)
                
                # Check if user has explicitly customized max_spread_points in the config file
                has_custom_setting = False
                try:
                    import json
                    if os.path.exists("configs/settings.json"):
                        with open("configs/settings.json", "r") as f:
                            file_data = json.load(f)
                            if "max_spread_points" in file_data and file_data["max_spread_points"] != 20:
                                has_custom_setting = True
                except Exception as e:
                    self.logger.error(f"Error checking settings file: {e}")

                if not has_custom_setting:
                    settings_manager.set("max_spread_points", profile["max_spread_points"])
                self._broker_profile_set = True
            
            return analysis
        except Exception as e:
            self.logger.error(f"Error during MTF analysis: {e}")
            traceback.print_exc()
            return None

    def evaluate_entry_rules(self, analysis: Dict) -> Optional[Tuple[str, float, float, str]]:
        """
        Evaluate entry signals based on:
        - SMC Sharp Turn entry model (returns setup_type "SMC")
        - Fallback Fibonacci Retest model (returns setup_type "FIB")
        
        Returns: Tuple (Action "BUY"/"SELL", StopLoss, TakeProfit, SetupType "SMC"/"FIB") or None
        """
        symbol = analysis['symbol']
        bid = analysis['bid']
        ask = analysis['ask']
        atr = analysis['atr']
        
        h1_bias = analysis['h1_bias']
        m15_sweep = analysis['m15_sweep_type']
        m5_mss = analysis['m5_mss_signal']
        fvg_class = analysis['m5_fvg_class']
        fvg_type = analysis['m5_fvg_type']
        
        # Rule 1: Killzone Active check
        if not self.is_killzone_active():
            self.skipped_stats['killzone_inactive'] = self.skipped_stats.get('killzone_inactive', 0) + 1
            return None
            
        # Get active risk-reward ratio from mode
        trading_mode = settings_manager.get("trading_mode", "intraday").lower()
        if trading_mode == "scalping":
            rr_ratio = 1.5
        elif trading_mode == "swing":
            rr_ratio = 3.0
        else:
            rr_ratio = 2.0
            
        # Allow override from settings
        rr_ratio = settings_manager.get("min_rr_ratio", rr_ratio)

        # Get AI signal confidence/adjustment
        ai_signal = self.pattern_learner.get_trading_signal(symbol, analysis['features'])
        confidence = ai_signal.get('confidence', 0.5)
        adjustment = ai_signal.get('adjustment', 0.0)
        
        # Check if AI confidence warrants a TP boost
        ai_boost = False
        if adjustment > 0.0 or confidence >= 0.6:
            rr_ratio *= 1.5
            ai_boost = True

        # Position checking helper
        def can_trade_direction(action: str) -> bool:
            if not settings_manager.get("hedging_mode", False):
                return len(self.trade_manager.positions) == 0
            else:
                has_same_direction = any(p.symbol == symbol and p.action == action for p in self.trade_manager.positions.values())
                return not has_same_direction

        # --- BULLISH ENTRY MODEL (Sharp Turn BUY) ---
        is_bullish_setup = (h1_bias == 1) and (m15_sweep == 1) and (m5_mss == 1)
        
        # --- BEARISH ENTRY MODEL (Sharp Turn SELL) ---
        is_bearish_setup = (h1_bias == -1) and (m15_sweep == -1) and (m5_mss == -1)

        # Throttled logging to avoid log pollution
        import time
        current_time = time.time()
        last_log = getattr(self, '_last_eval_log_time', {})
        if current_time - last_log.get(symbol, 0) >= 10.0:
            self.logger.info(
                f"📊 {symbol} Eval | bias={h1_bias} sweep={m15_sweep} mss={m5_mss} fvg={fvg_class} | bull={is_bullish_setup} bear={is_bearish_setup}"
            )
            last_log[symbol] = current_time
            self._last_eval_log_time = last_log

        if is_bullish_setup and can_trade_direction("BUY"):
            entry_price = ask
            
            # SL: placed below the recent LTF support swing low
            sl_price = analysis['support'] - (0.2 * atr)  # small buffer
            sl_price = min(sl_price, entry_price - (1.5 * atr))  # minimum SL distance
            
            # TP: Target opposing resistance liquidity with dynamic RR
            tp_price = entry_price + (rr_ratio * (entry_price - sl_price))
            
            # Ensure TP is aligned with major liquidity resistance
            if analysis['resistance'] > entry_price:
                tp_price = max(tp_price, analysis['resistance'])
                
            if ai_boost:
                self.logger.info(f"🧠 High AI confidence (adj={adjustment:.2f}, conf={confidence:.2f}). SMC TP scaled 1.5x, new RR: {rr_ratio:.2f}")
            self.logger.info(f"🟢 BUY SMC setup identified on {symbol} | MSS: 1, Sweep: 1, FVG Class: {fvg_class} | RR: {rr_ratio:.2f}")
            return "BUY", sl_price, tp_price, "SMC"

        if is_bearish_setup and can_trade_direction("SELL"):
            entry_price = bid
            
            # SL: placed above the recent LTF resistance swing high
            sl_price = analysis['resistance'] + (0.2 * atr)
            sl_price = max(sl_price, entry_price + (1.5 * atr))
            
            # TP: Target opposing support liquidity with dynamic RR
            tp_price = entry_price - (rr_ratio * (sl_price - entry_price))
            
            if analysis['support'] < entry_price:
                tp_price = min(tp_price, analysis['support'])
                
            if ai_boost:
                self.logger.info(f"🧠 High AI confidence (adj={adjustment:.2f}, conf={confidence:.2f}). SMC TP scaled 1.5x, new RR: {rr_ratio:.2f}")
            self.logger.info(f"🔴 SELL SMC setup identified on {symbol} | MSS: -1, Sweep: -1, FVG Class: {fvg_class} | RR: {rr_ratio:.2f}")
            return "SELL", sl_price, tp_price, "SMC"

        # --- FALLBACK FIBONACCI RETEST STRATEGY ---
        fib_action = analysis.get('fib_action')
        if fib_action in ["BUY", "SELL"] and can_trade_direction(fib_action):
            entry_price = ask if fib_action == "BUY" else bid
            fib_sl = analysis.get('fib_sl', 0.0)
            fib_tp = analysis.get('fib_tp', 0.0)
            
            if fib_sl > 0.0 and fib_tp > 0.0:
                # Apply dynamic RR scaling to TP distance if AI has high confidence
                if ai_boost:
                    tp_dist = abs(entry_price - fib_tp)
                    if fib_action == "BUY":
                        fib_tp = entry_price + (tp_dist * 1.5)
                    else:
                        fib_tp = entry_price - (tp_dist * 1.5)
                    self.logger.info(f"🧠 High AI confidence (adj={adjustment:.2f}, conf={confidence:.2f}). Fibonacci TP scaled 1.5x, new TP: {fib_tp:.2f}")

                self.logger.info(f"📐 Fibonacci Retest fallback setup identified on {symbol} | Action: {fib_action} | SL: {fib_sl:.2f}, TP: {fib_tp:.2f}")
                return fib_action, fib_sl, fib_tp, "FIB"

        return None

    def execute_and_record_trade(self, symbol: str, action: str, sl: float, tp: float, analysis: Dict):
        """Execute the order and record the initial state into experience memory"""
        # Spread check
        tick = mt5.symbol_info_tick(symbol)
        symbol_info = mt5.symbol_info(symbol)
        spread = (tick.ask - tick.bid) / symbol_info.point
        
        max_spread = settings_manager.get("max_spread_points", self.config.MAX_SPREAD_POINTS)
        if spread > max_spread:
            self.logger.warning(f"Trade blocked on {symbol} due to high spread: {spread:.1f} points (Limit: {max_spread})")
            self.skipped_stats['high_spread'] = self.skipped_stats.get('high_spread', 0) + 1
            return
            
        entry_price = tick.ask if action == "BUY" else tick.bid
        
        # Open trade via trade manager
        pos = self.trade_manager.open_position(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            sl_price=sl,
            tp_price=tp
        )
        
        if pos:
            # Store initial entry features in positions for outcome learning
            pos.entry_features = analysis['features']

    def process_closed_positions(self):
        """Learn from closed positions and update the self-learning DB + trade journal"""
        while len(self.trade_manager.closed_positions) > 0:
            pos = self.trade_manager.closed_positions.pop(0)
            
            # Record in engine performance history
            trade_rec = {
                'timestamp': pos.close_time,
                'symbol': pos.symbol,
                'action': pos.action,
                'pnl': pos.pnl,
                'close_reason': pos.close_reason
            }
            self.performance_history.append(trade_rec)
            
            # 1. Update Pattern Learner with actual closed PnL
            pnl_outcome = 1.0 if pos.pnl > 0 else -1.0
            
            trade_data = {
                'symbol': pos.symbol,
                'outcome': pos.pnl,
                'features': getattr(pos, 'entry_features', {})
            }
            self.pattern_learner.learn_from_trade(trade_data)
            
            # 2. Store in reinforcement learning experience memory
            self.experience_memory.store(
                state=getattr(pos, 'entry_features', {}),
                action=1 if pos.action == 'BUY' else 2,
                reward=pos.pnl,
                next_state={},
                done=True,
                metadata={
                    'symbol': pos.symbol,
                    'close_reason': pos.close_reason,
                    'lots': pos.volume
                }
            )
            
            # 3. Write to structured Trade Journal (CSV + JSON)
            try:
                features = getattr(pos, 'entry_features', {})
                entry_price = pos.entry_price
                close_price = pos.close_price if pos.close_price else entry_price
                sl_dist = abs(entry_price - pos.sl) if pos.sl else 1.0
                rr_achieved = round(abs(close_price - entry_price) / (sl_dist + 1e-9) *
                                    (1 if pos.pnl > 0 else -1), 2)

                # Duration in minutes
                if pos.entry_time and pos.close_time:
                    duration_mins = round((pos.close_time - pos.entry_time).total_seconds() / 60, 1)
                else:
                    duration_mins = 0

                # Determine setup type from features
                f = features
                had_sweep = f.get('liq_sweep_type', 0) != 0
                had_mss = f.get('mss_signal', 0) != 0
                if had_sweep and had_mss:
                    setup_type = "SHARP_TURN"
                elif had_mss:
                    setup_type = "MSS_ONLY"
                elif had_sweep:
                    setup_type = "SWEEP_ONLY"
                else:
                    setup_type = "CONTINUATION"

                # Spread at entry (live snapshot)
                spread_at_entry = 0.0
                try:
                    sym_info = mt5.symbol_info(pos.symbol)
                    tick = mt5.symbol_info_tick(pos.symbol)
                    if tick and sym_info:
                        spread_at_entry = round((tick.ask - tick.bid) / sym_info.point, 1)
                except Exception:
                    pass

                bias = f.get('active_bias', 0)
                bias_label = "BULLISH" if bias > 0 else ("BEARISH" if bias < 0 else "NEUTRAL")

                journal_record = {
                    "date": pos.entry_time.strftime("%Y-%m-%d") if pos.entry_time else str(datetime.now(timezone.utc).date()),
                    "time": pos.entry_time.strftime("%H:%M:%S") if pos.entry_time else "",
                    "symbol": pos.symbol,
                    "action": pos.action,
                    "entry_price": entry_price,
                    "close_price": close_price,
                    "sl": pos.sl,
                    "tp1": pos.tp1 if hasattr(pos, 'tp1') else pos.tp,
                    "tp2": pos.tp2 if hasattr(pos, 'tp2') else pos.tp,
                    "lot_size": pos.volume,
                    "pnl": round(pos.pnl, 2),
                    "rr_achieved": rr_achieved,
                    "close_reason": pos.close_reason,
                    "duration_mins": duration_mins,
                    "setup_type": setup_type,
                    "fvg_class": str(f.get('fvg_class', 'none')).upper(),
                    "bias": bias_label,
                    "volatility_regime": f.get('volatility_regime', 'NORMAL'),
                    "spread_at_entry": spread_at_entry
                }
                trade_journal.append_trade(journal_record)
            except Exception as e:
                self.logger.error(f"Failed to write trade to journal: {e}")

            self.logger.info(f"🧠 Closed Position Learnt: {pos.symbol} {pos.action} Ticket #{pos.id} closed due to {pos.close_reason} | PnL: ${pos.pnl:.2f}")

    def get_prediction_data(self, symbol: str) -> dict:
        """Return next predicted trade setup, current price and session info."""
        try:
            analysis = self.cached_analysis.get(symbol)
            if not analysis:
                return {}
            setup = self.evaluate_entry_rules(analysis)
            tick = mt5.symbol_info_tick(symbol)
            bid = tick.bid if tick else 0.0
            ask = tick.ask if tick else 0.0
            result = {
                'symbol': symbol,
                'bid': bid,
                'ask': ask,
                'active_sessions': self.get_active_sessions(),
                'setup': None,
                'action': None,
                'entry': None,
                'sl': None,
                'tp': None,
                'confidence': 0.0,
                'setup_type': None
            }
            if setup:
                action, sl, tp, setup_type = setup
                entry = ask if action == 'BUY' else bid
                ai_signal = self.pattern_learner.get_trading_signal(symbol, analysis.get('features', {}))
                result.update({
                    'setup': f'{action} LIMIT',
                    'action': action,
                    'entry': round(entry, 5),
                    'sl': round(sl, 5),
                    'tp': round(tp, 5),
                    'confidence': round(ai_signal.get('confidence', 0.5) * 100, 1),
                    'setup_type': setup_type
                })
            return result
        except Exception as e:
            self.logger.error(f"get_prediction_data error: {e}")
            return {}

    def get_active_sessions(self) -> list:
        """Return list of currently active forex market sessions based on UTC hour."""
        from datetime import datetime, timezone
        utc_hour = datetime.now(timezone.utc).hour
        sessions = []
        if 22 <= utc_hour or utc_hour < 7:
            sessions.append('Sydney')
        if 0 <= utc_hour < 9:
            sessions.append('Asian')
        if 8 <= utc_hour < 17:
            sessions.append('London')
        if 13 <= utc_hour < 22:
            sessions.append('New York')
        return sessions

    def self_configure_automation(self):
        """Auto-tune spread limit and risk based on recent skipped stats and journal win rate."""
        try:
            from core.trade_journal import trade_journal
            from utils.settings_manager import settings_manager

            # 1. Spread starvation check: if >50 skips due to spread, relax limit by 20%
            spread_skips = self.skipped_stats.get('high_spread', 0)
            if spread_skips > 50:
                current_max = settings_manager.get('max_spread_points', 450)
                new_max = min(int(current_max * 1.20), 1000)
                settings_manager.set('max_spread_points', new_max)
                self.logger.info(f"🔧 Self-config: Spread starvation detected ({spread_skips} skips). Relaxed max_spread to {new_max}")
                self.skipped_stats['high_spread'] = 0  # reset counter

            # 2. Win rate adjustment: tune risk_percent
            summary = trade_journal.get_daily_summary()
            total = summary.get('total_trades', 0)
            wins = summary.get('wins', 0)
            if total >= 5:
                win_rate = wins / total
                current_risk = settings_manager.get('risk_percent', 1.0)
                if win_rate >= 0.65 and current_risk < 3.0:
                    new_risk = min(current_risk + 0.25, 3.0)
                    settings_manager.set('risk_percent', new_risk)
                    self.logger.info(f"🔧 Self-config: Win rate {win_rate:.0%} >= 65%. Increased risk to {new_risk}%")
                elif win_rate < 0.40 and current_risk > 0.5:
                    new_risk = max(current_risk - 0.25, 0.5)
                    settings_manager.set('risk_percent', new_risk)
                    self.logger.info(f"🔧 Self-config: Win rate {win_rate:.0%} < 40%. Reduced risk to {new_risk}%")
        except Exception as e:
            self.logger.error(f"self_configure_automation error: {e}")

    def _schedule_nightly_tasks(self):
        """Run nightly self-improvement tasks once per day at midnight UTC."""
        import threading
        now_utc = datetime.now(timezone.utc)
        today = now_utc.date()

        # Only run once per day, inside the 00:00–00:05 UTC window
        if self._last_nightly_date == today:
            return
        if not (now_utc.hour == 0 and now_utc.minute < 5):
            return

        self._last_nightly_date = today
        self.logger.info("🌙 Midnight reached — launching nightly self-improvement tasks...")

        def run_nightly():
            try:
                # 1. Analyze yesterday's trades and generate report
                self.logger.info("📊 DailyAnalyzer: Analyzing yesterday's performance...")
                self.daily_analyzer.analyze_yesterday()

                # 2. Adaptive backtest + self-optimize on primary symbol
                for symbol in self.symbols[:1]:
                    self.logger.info(f"🔬 Backtester: Self-optimizing strategy for {symbol}...")
                    trading_mode = settings_manager.get("trading_mode", "intraday")
                    self.backtester.self_optimize(symbol, trading_mode=trading_mode)

                # 3. Self-configuration automation (spread & risk auto-tuning)
                self.self_configure_automation()
                self.logger.info("✅ Nightly self-improvement tasks completed successfully.")
            except Exception as e:
                self.logger.error(f"Error during nightly tasks: {e}")

        thread = threading.Thread(target=run_nightly, daemon=True, name="NightlyTasks")
        thread.start()



    def run_engine(self, sleep_seconds=1):
        """Main real-time trading loop (1-second update cycle)"""
        if self.dashboard:
            self.dashboard.start()

        self.logger.info("=" * 60)
        self.logger.info("🚀 STARTING PULSEVIPER SMC PROFESSIONAL EXPERT ADVISOR")
        self.logger.info(f"🎯 Tracking Symbols: {self.symbols}")
        self.logger.info(f"⏰ LONDON session: {self.config.LONDON_SESSION} UTC | NY session: {self.config.NY_SESSION} UTC")
        self.logger.info("=" * 60)
        
        self.cycle_count = 0
        
        # Auto-run startup training in background if pattern DB is sparse
        def _startup_training():
            try:
                for symbol in self.symbols[:1]:
                    # Only train if pattern DB has < 20 patterns
                    total_patterns = sum(len(v) for v in self.pattern_learner.patterns.values())
                    if total_patterns < 20:
                        self.logger.info(f"🧠 Sparse pattern DB ({total_patterns} patterns). Running startup yearly training on {symbol}...")
                        self.training_in_progress = True
                        # Fetch a year of data on proper TFs
                        df_h1 = fetch_ohlcv(symbol, mt5.TIMEFRAME_H1, n=10000)   # expanded
                        df_m5 = fetch_ohlcv(symbol, mt5.TIMEFRAME_M5, n=40000)  # expanded
                        df_m1 = fetch_ohlcv(symbol, mt5.TIMEFRAME_M1, n=20000)  # expanded
                        if df_h1 is not None and df_m5 is not None and df_m1 is not None:
                            self.logger.info(f"📊 Startup training data: H1={len(df_h1)}, M5={len(df_m5)}, M1={len(df_m1)} bars")
                            self.pattern_learner.train_on_history(symbol, df_h1, df_m5, df_m1)
                        self.training_in_progress = False
                    else:
                        self.logger.info(f"🧠 Pattern DB has {total_patterns} patterns. Skipping startup yearly training.")
                    
                    # Run initial backtest / self-optimization every startup
                    trading_mode = settings_manager.get('trading_mode', 'scalping')
                    self.logger.info(f"🔬 Running startup backtest optimization on {symbol}...")
                    self.backtester.self_optimize(symbol, trading_mode=trading_mode)
            except Exception as e:
                self.logger.error(f"Startup training failed: {e}")
                self.training_in_progress = False

        import threading
        startup_thread = threading.Thread(target=_startup_training, daemon=True, name='StartupTraining')
        startup_thread.start()

        try:
            while True:
                start_time = time.time()
                self.cycle_count += 1
                self._reconnect_if_needed()
                
                if not self.connected:
                    self.logger.warning("MT5 Disconnected. Waiting for recovery...")
                    time.sleep(sleep_seconds)
                    continue
                    
                # Process active signals and tracking
                for symbol in self.symbols:
                    tick = mt5.symbol_info_tick(symbol)
                    if not tick:
                        continue
                        
                    # Update positions first (check SL/TP)
                    self.trade_manager.update_positions(symbol, tick.bid, tick.ask)
                    
                    # 1. Check pending sniper setup pullback entry first
                    if symbol in self.pending_setups:
                        pending = self.pending_setups[symbol]
                        
                        # Expiry check (5 candles on LTF)
                        trading_mode = settings_manager.get("trading_mode", "intraday").lower()
                        tf_seconds = 300  # Default M5
                        tf_ltf = mt5.TIMEFRAME_M5
                        if trading_mode == "scalping":
                            tf_seconds = 60
                            tf_ltf = mt5.TIMEFRAME_M1
                        elif trading_mode == "swing":
                            tf_seconds = 900
                            tf_ltf = mt5.TIMEFRAME_M15
                            
                        rates = mt5.copy_rates_from_pos(symbol, tf_ltf, 0, 1)
                        current_candle_time = int(rates[0]['time']) if rates is not None and len(rates) > 0 else 0
                        
                        # Check expiry
                        if current_candle_time > 0 and pending.get('candle_time', 0) > 0 and (current_candle_time - pending['candle_time']) > 5 * tf_seconds:
                            self.logger.info(f"⏳ Pending sniper setup for {symbol} expired (5 candles passed without pullback)")
                            self.pending_setups.pop(symbol)
                        else:
                            action = pending['action']
                            sl = pending['sl']
                            tp = pending['tp']
                            
                            # Invalidation check: if price goes past SL before triggering
                            if action == "BUY" and tick.bid <= sl:
                                self.logger.info(f"❌ Pending sniper BUY setup for {symbol} invalidated (price hit SL before entry)")
                                self.pending_setups.pop(symbol)
                            elif action == "SELL" and tick.ask >= sl:
                                self.logger.info(f"❌ Pending sniper SELL setup for {symbol} invalidated (price hit SL before entry)")
                                self.pending_setups.pop(symbol)
                            else:
                                # Pullback entry trigger check
                                triggered = False
                                if action == "BUY":
                                    if tick.ask <= pending['fvg_top']:
                                        triggered = True
                                elif action == "SELL":
                                    if tick.bid >= pending['fvg_bottom']:
                                        triggered = True
                                        
                                if triggered:
                                    self.logger.info(f"🎯 SNIPER pullback entry triggered on {symbol}! Action: {action} @ {tick.ask if action == 'BUY' else tick.bid:.2f} | FVG boundary hit")
                                    self.execute_and_record_trade(symbol, action, sl, tp, pending['analysis'])
                                    self.pending_setups.pop(symbol)
                    
                    # 2. Candle tracking & multi-timeframe analysis cache logic
                    current_time = time.time()
                    new_candle = False
                    
                    trading_mode = settings_manager.get("trading_mode", "intraday").lower()
                    if trading_mode == "scalping":
                        tf_ltf = mt5.TIMEFRAME_M1
                    elif trading_mode == "swing":
                        tf_ltf = mt5.TIMEFRAME_M15
                    else:
                        tf_ltf = mt5.TIMEFRAME_M5
                        
                    rates = mt5.copy_rates_from_pos(symbol, tf_ltf, 0, 1)
                    candle_time = int(rates[0]['time']) if rates is not None and len(rates) > 0 else 0
                    
                    if candle_time > 0:
                        last_time = self.last_candle_times.get(symbol, 0)
                        if candle_time != last_time:
                            new_candle = True
                            self.last_candle_times[symbol] = candle_time
                            
                    # Run full analysis if it is a new candle, or every 2s (for real-time dashboard updates), or if no cache exists
                    time_since_last_analysis = current_time - self.last_analysis_times.get(symbol, 0)
                    if new_candle or time_since_last_analysis >= 2.0 or symbol not in self.cached_analysis:
                        analysis = self.run_multi_timeframe_analysis(symbol)
                        if analysis:
                            self.cached_analysis[symbol] = analysis
                            self.last_analysis_times[symbol] = current_time
                    else:
                        analysis = self.cached_analysis.get(symbol)
                        if analysis:
                            # Update cached analysis with real-time ticks
                            analysis['price'] = tick.bid
                            analysis['bid'] = tick.bid
                            analysis['ask'] = tick.ask
                            analysis['features']['price'] = tick.bid
                            
                    if analysis is None:
                        continue
                        
                    # Store current analysis in state for dashboard/monitoring
                    self.market_state[symbol] = {
                        'last_analysis': analysis
                    }
                    
                    # 3. If we don't have a pending setup, evaluate entry rules
                    if symbol not in self.pending_setups:
                        setup = self.evaluate_entry_rules(analysis)
                        if setup:
                            action, sl, tp, setup_type = setup
                            
                            # Apply news sentiment filter if enabled
                            if settings_manager.get("news_filter_enabled", True):
                                news_state = sentiment_analyzer.get_news_state()
                                news_score = news_state.get("score", 0.0)
                                if action == "BUY" and news_score < -0.4:
                                    self.logger.warning(f"🚫 BUY trade blocked by News Sentiment Filter (Score: {news_score:.2f})")
                                    self.skipped_stats['news_filter'] = self.skipped_stats.get('news_filter', 0) + 1
                                    continue
                                elif action == "SELL" and news_score > 0.4:
                                    self.logger.warning(f"🚫 SELL trade blocked by News Sentiment Filter (Score: {news_score:.2f})")
                                    self.skipped_stats['news_filter'] = self.skipped_stats.get('news_filter', 0) + 1
                                    continue
                                    
                            # Apply pattern learner AI check if enabled
                            if settings_manager.get("self_learning_filter", True):
                                ai_signal = self.pattern_learner.get_trading_signal(symbol, analysis['features'])
                                if ai_signal['adjustment'] < -0.3:
                                    self.logger.warning(f"⚠️ Warning: AI Pattern Learner flagged this trade setup with low confidence (Adjustment: {ai_signal['adjustment']}), but proceeding per warning-only configuration.")
                                    
                            if setup_type == "FIB":
                                self.logger.info(f"🎯 FIBONACCI entry triggered immediately on {symbol}! Action: {action} @ {tick.ask if action == 'BUY' else tick.bid:.2f}")
                                self.execute_and_record_trade(symbol, action, sl, tp, analysis)
                            else: # SMC setup
                                # Save to pending setup with FVG boundary limits
                                fvg_top = analysis.get('m5_fvg_top')
                                fvg_bottom = analysis.get('m5_fvg_bottom')
                                
                                if fvg_top is None or np.isnan(fvg_top):
                                    fvg_top = tick.ask if action == "BUY" else tick.bid
                                if fvg_bottom is None or np.isnan(fvg_bottom):
                                    fvg_bottom = tick.ask if action == "BUY" else tick.bid
                                    
                                self.pending_setups[symbol] = {
                                    'action': action,
                                    'fvg_top': fvg_top,
                                    'fvg_bottom': fvg_bottom,
                                    'sl': sl,
                                    'tp': tp,
                                    'analysis': analysis,
                                    'candle_time': candle_time
                                }
                                self.logger.info(f"⏳ Pending sniper {action} setup saved for {symbol}. Wait pullback... (FVG limits: {fvg_bottom:.2f} - {fvg_top:.2f})")
                                
                                # Immediately check if current price already satisfies the pullback
                                if (action == "BUY" and tick.ask <= fvg_top) or (action == "SELL" and tick.bid >= fvg_bottom):
                                    self.logger.info(f"🎯 SNIPER pullback entry triggered immediately on {symbol}! Action: {action}")
                                    self.execute_and_record_trade(symbol, action, sl, tp, analysis)
                                    self.pending_setups.pop(symbol)

                # Process closures and learning updates
                self.process_closed_positions()
                
                # Check and run nightly self-improvement tasks (midnight UTC)
                self._schedule_nightly_tasks()
                
                # Measure latency of loop execution
                self.market_state['latency_ms'] = (time.time() - start_time) * 1000.0
                
                time.sleep(sleep_seconds)
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Engine stopped by user request.")
        except Exception as e:
            self.logger.error(f"💥 Engine crashed: {e}")
            traceback.print_exc()
        finally:
            if self.dashboard:
                self.dashboard.stop()
            self._shutdown()

    def close_all_positions(self) -> Dict:
        """Panic Close all active positions across all tracked symbols immediately"""
        self.logger.warning("🚨 PANIC CLOSE ALL POSITIONS TRIGGERED!")
        manager = self.trade_manager
        
        # Sync positions first to make sure we have the latest
        for symbol in self.symbols:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                manager.update_positions(symbol, tick.bid, tick.ask)
                
        tickets = list(manager.positions.keys())
        closed_tickets = []
        errors = []
        
        for ticket in tickets:
            pos = manager.positions.get(ticket)
            if not pos:
                continue
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                errors.append(f"Failed to get tick for {pos.symbol} to close ticket {ticket}")
                continue
            close_price = tick.bid if pos.action == "BUY" else tick.ask
            res = manager.close_position(ticket, close_price, "PANIC CLOSE")
            if res:
                closed_tickets.append(ticket)
            else:
                errors.append(f"Failed to close ticket {ticket}")
                
        return {
            "success": len(errors) == 0,
            "closed": closed_tickets,
            "errors": errors
        }

    def trigger_historical_training(self):
        """Fetch historical candles and train the AI pattern learner on them."""
        self.logger.info("Starting historical training job from dashboard...")
        if not self.symbols:
            self.logger.warning("No active symbols to train.")
            return
        
        symbol = self.symbols[0]
        trading_mode = settings_manager.get("trading_mode", "intraday").lower()
        
        # Select timeframes based on strategy mode
        if trading_mode == "scalping":
            tf_htf = mt5.TIMEFRAME_H1
            tf_context = mt5.TIMEFRAME_M5
            tf_ltf = mt5.TIMEFRAME_M1
            n_ltf = 20000
            n_context = 40000
            n_htf = 10000
        elif trading_mode == "swing":
            tf_htf = mt5.TIMEFRAME_D1
            tf_context = mt5.TIMEFRAME_H1
            tf_ltf = mt5.TIMEFRAME_M15
            n_ltf = 3000
            n_context = 1500
            n_htf = 1000
        else:  # intraday
            tf_htf = mt5.TIMEFRAME_H1
            tf_context = mt5.TIMEFRAME_M15
            tf_ltf = mt5.TIMEFRAME_M5
            n_ltf = 5000
            n_context = 3000
            n_htf = 1500
            
        self.logger.info(f"Fetching historical bars for training. Mode: {trading_mode}, Symbol: {symbol}")
        df_htf = fetch_ohlcv(symbol, tf_htf, n=n_htf)
        df_context = fetch_ohlcv(symbol, tf_context, n=n_context)
        df_ltf = fetch_ohlcv(symbol, tf_ltf, n=n_ltf)
        
        if df_htf is None or df_context is None or df_ltf is None:
            self.logger.error("Failed to fetch historical candles for training.")
            return
            
        self.logger.info(f"Fetched historical data successfully. HTF: {len(df_htf)}, Context: {len(df_context)}, LTF: {len(df_ltf)}")
        
        try:
            self.pattern_learner.train_on_history(symbol, df_htf, df_context, df_ltf)
        except Exception as e:
            self.logger.error(f"Error during pattern learner training: {e}")

    def _shutdown(self):
        """Safely shut down the connection"""
        self.logger.info("🔒 Shutting down MT5 Connection...")
        shutdown_mt5()
        self.connected = False
        sentiment_analyzer.stop()
        self.logger.info("Engine stopped safely.")