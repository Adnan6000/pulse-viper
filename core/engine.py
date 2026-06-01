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
from strategies.crt_tbs import CrtTbsStrategy
from dashboard.web_dashboard import WebDashboardServer
from core.safety_engine import SafetyEngine
from core.session_engine import SessionEngine
from core.brain_calibrator import BrainCalibrator

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
        self.analyzed_trades = {}
        
        # Initialize MT5 Connection
        self._initialize_connection()

        # Symbol handling
        if symbols is None:
            self.symbols = self._auto_detect_symbols()
        else:
            self.symbols = self._validate_symbols(symbols)

        if self.symbols:
            settings_manager.set("active_symbol", self.symbols[0])

        # Initialize both Trade Managers (Dynamic property will resolve active one based on settings)
        self.paper_trade_manager = PaperTradeManager(self.config)
        self.live_trade_manager = LiveTradeManager(self.config)
        self.logger.info("🎮 Paper Trade Manager and ⚠️ Live Trade Manager initialized")

        # Sniper pullback and fast 1s loop caches
        self.last_candle_times = {}
        self.last_entry_candle = {}
        self.last_close_candle = {}
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
        
        # Initialize Phase 8 engines
        from core.market_regime import MarketRegimeDetector
        from core.liquidity_map import LiquidityMap
        from core.risk_engine import DynamicRiskEngine
        from core.news_engine import NewsIntelligenceEngine
        
        self.regime_detector = MarketRegimeDetector()
        self.liquidity_map = LiquidityMap()
        self.risk_engine = DynamicRiskEngine()
        self.news_engine = NewsIntelligenceEngine()
        self.news_engine.start()
        
        # Initialize Phase 9 — AI Brain Layer (Trade Decision Synthesizer)
        from core.trade_brain import TradeBrain
        brain_threshold = settings_manager.get("brain_threshold", 55.0)
        self.trade_brain = TradeBrain(base_threshold=brain_threshold)
        self.logger.info(f"🧠 TradeBrain initialized (threshold={brain_threshold})")

        # Initialize Phase 10 safety_engine, session_engine, and brain_calibrator
        self.safety_engine = SafetyEngine()
        self.session_engine = SessionEngine()
        self.brain_calibrator = BrainCalibrator()
        
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
            "no_fvg": 0,
            "regime_filter": 0
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
        """Automatically find working symbols. Prioritizes Gold matching the account type."""
        try:
            available_symbols = [s.name for s in mt5.symbols_get()]
            if not available_symbols:
                return ['EURUSD']
                
            account = mt5.account_info()
            currency = account.currency if account else "USD"
            server = account.server.upper() if account else ""
            is_cent = (currency == "USC") or ("CENT" in server)
            
            # Find all available gold symbols
            gold_symbols = [s for s in available_symbols if 'XAUUSD' in s.upper() or 'GOLD' in s.upper()]
            
            if gold_symbols:
                # If cent account, prioritize those ending in c or .c
                if is_cent:
                    cent_golds = [g for g in gold_symbols if g.endswith('c') or g.endswith('.c')]
                    if cent_golds:
                        mt5.symbol_select(cent_golds[0], True)
                        return [cent_golds[0]]
                
                # Otherwise, try mini, standard, and other preferences
                pref_order = ['XAUUSDm', 'GOLD', 'XAUUSD']
                for pref in pref_order:
                    if pref in gold_symbols:
                        mt5.symbol_select(pref, True)
                        return [pref]
                
                # Fallback to first gold symbol
                mt5.symbol_select(gold_symbols[0], True)
                return [gold_symbols[0]]
                
            # If no gold, search major forex pairs
            major_bases = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF']
            forex_symbols = []
            for s in available_symbols:
                for base in major_bases:
                    if base in s.upper():
                        forex_symbols.append(s)
            
            if forex_symbols:
                # Sort and prioritize cent forex pairs if cent account
                if is_cent:
                    cent_forex = [f for f in forex_symbols if f.endswith('c') or f.endswith('.c')]
                    if cent_forex:
                        mt5.symbol_select(cent_forex[0], True)
                        return [cent_forex[0]]
                        
                # Preference standard majors
                for pref in major_bases:
                    # check if exact matches exist
                    if pref in forex_symbols:
                        mt5.symbol_select(pref, True)
                        return [pref]
                    # check if mini matches exist
                    if f"{pref}m" in forex_symbols:
                        mt5.symbol_select(f"{pref}m", True)
                        return [f"{pref}m"]
                
                mt5.symbol_select(forex_symbols[0], True)
                return [forex_symbols[0]]
                
            return ['EURUSD']
        except Exception as e:
            self.logger.error(f"Error in auto-detecting symbols: {e}")
            return ['EURUSD']

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
        Full 6-Timeframe Cascade Analysis: D1 → H4 → H1 → M15 → M5 → M1

        Cascade hierarchy:
          D1  → Master Bias (bull/bear)
          H4  → Trend Confirmation
          H1  → Swing Structure (OB, FVG, sweep zones)
          M15 → Session Liquidity Sweep
          M5  → Order Flow & MSS
          M1  → Entry Candle (TBS trigger, exact reversal level)

        All modes use M1 for entry timing.
        Mode (scalping/intraday/swing) controls RR ratio and cooldown only.
        """
        try:
            trading_mode = settings_manager.get("trading_mode", "intraday").lower()
            current_time = time.time()
            swing_window = settings_manager.get("smc_swing_window", 3)

            # ── 1. Fetch all 6 timeframes ──────────────────────────────────────────
            # Use per-TF expiry cache to avoid redundant MT5 calls on fast loops
            if not hasattr(self, '_tf_data_cache'):
                self._tf_data_cache = {}
            if not hasattr(self, '_tf_data_expiry'):
                self._tf_data_expiry = {}

            _tf_expiry_map = {
                'D1': (mt5.TIMEFRAME_D1, 500, 3600),   # 1h TTL
                'H4': (mt5.TIMEFRAME_H4, 300, 1200),   # 20min TTL
                'H1': (mt5.TIMEFRAME_H1, 300, 600),    # 10min TTL
                'M15': (mt5.TIMEFRAME_M15, 200, 60),   # 1min TTL
                'M5': (mt5.TIMEFRAME_M5, 200, 30),     # 30s TTL
                'M1': (mt5.TIMEFRAME_M1, 200, 15),     # 15s TTL
            }

            dfs = {}
            for tf_name, (tf_const, bars, ttl) in _tf_expiry_map.items():
                cache_key = f"{symbol}_{tf_name}"
                if cache_key in self._tf_data_expiry and current_time < self._tf_data_expiry[cache_key]:
                    dfs[tf_name] = self._tf_data_cache.get(cache_key)
                else:
                    df = fetch_ohlcv(symbol, tf_const, n=bars)
                    if df is not None and len(df) >= 20:
                        self._tf_data_cache[cache_key] = df
                        self._tf_data_expiry[cache_key] = current_time + ttl
                    dfs[tf_name] = self._tf_data_cache.get(cache_key)

            df_d1  = dfs.get('D1')
            df_h4  = dfs.get('H4')
            df_h1  = dfs.get('H1')
            df_m15 = dfs.get('M15')
            df_m5  = dfs.get('M5')
            df_m1  = dfs.get('M1')

            # M1 is mandatory for entry, H1 for bias minimum
            if df_m1 is None or len(df_m1) < 50:
                self.logger.warning(f"Insufficient M1 bars for {symbol}")
                return None
            if df_h1 is None or len(df_h1) < 50:
                self.logger.warning(f"Insufficient H1 bars for {symbol}")
                return None

            # ── 1.5 Phase 8 Core Intelligence Updates ──────────────────────────────
            # A. News lockout check
            news_locked = False
            news_lockout_reason = None
            if settings_manager.get("news_filter_enabled", True):
                lockout_mins = settings_manager.get("news_lockout_minutes", 30)
                cooldown_mins = settings_manager.get("news_cooldown_minutes", 15)
                current_time_utc = datetime.now(timezone.utc)
                news_locked, news_lockout_reason = self.news_engine.is_execution_locked(
                    current_time_utc, lockout_mins, cooldown_mins
                )

            # B. Update Liquidity Map
            asian_range = self.get_asian_range(symbol)
            self.liquidity_map.update_pools(df_d1, df_h1, asian_range=asian_range)

            # C. Market Regime Detection
            rvol_val = self.volume_cache.get("rvol", 1.0) if hasattr(self, 'volume_cache') and self.volume_cache else 1.0
            from core.market_regime import RegimeType
            regime = self.regime_detector.detect_regime(df_m15, rvol_val)

            # D. Session context (Phase 10)
            session_ctx = self.session_engine.get_session_context()

            # ── 2. Compute SMC indicators on all available timeframes ───────────────
            smc = {}
            for tf_name, df in [('D1', df_d1), ('H4', df_h4), ('H1', df_h1),
                                  ('M15', df_m15), ('M5', df_m5), ('M1', df_m1)]:
                if df is not None and len(df) >= 20:
                    try:
                        smc[tf_name] = SMCIndicators.compute_smc_features(df, window=swing_window)
                    except Exception:
                        smc[tf_name] = None
                else:
                    smc[tf_name] = None

            def get_latest(tf_name):
                s = smc.get(tf_name)
                return s.iloc[-1] if s is not None and len(s) > 0 else None

            latest_d1  = get_latest('D1')
            latest_h4  = get_latest('H4')
            latest_h1  = get_latest('H1')
            latest_m15 = get_latest('M15')
            latest_m5  = get_latest('M5')
            latest_m1  = get_latest('M1')

            # ── 3. Build 6-TF bias cascade ─────────────────────────────────────────
            def bias_val(row):
                if row is None:
                    return 0
                return int(row.get('active_bias', 0))

            d1_bias  = bias_val(latest_d1)
            h4_bias  = bias_val(latest_h4)
            h1_bias  = bias_val(latest_h1)
            m15_bias = bias_val(latest_m15)
            m5_bias  = bias_val(latest_m5)
            m1_bias  = bias_val(latest_m1)

            # Master HTF bias: D1 + H4 must agree, fallback to H1 if D1 unavailable
            if latest_d1 is not None and latest_h4 is not None:
                if d1_bias == h4_bias and d1_bias != 0:
                    htf_bias = d1_bias
                elif d1_bias != 0:
                    htf_bias = d1_bias  # D1 wins if H4 is neutral
                else:
                    htf_bias = h4_bias
            else:
                htf_bias = h1_bias  # fallback for scalping without D1

            # ── 4. Liquidity sweep on M15/H1 ──────────────────────────────────────
            _sweep_lb = settings_manager.get('smc_lookback_sweep', 20)
            sweep_type = 0
            sweep_level = np.nan

            for ctx_name in ['M15', 'H1']:
                ctx_smc = smc.get(ctx_name)
                if ctx_smc is not None and len(ctx_smc) >= _sweep_lb:
                    recent = ctx_smc.iloc[-_sweep_lb:]
                    for _, row in reversed(list(recent.iterrows())):
                        if row['liq_sweep_type'] != 0:
                            sweep_type = int(row['liq_sweep_type'])
                            sweep_level = float(row['liq_sweep_level'])
                            break
                if sweep_type != 0:
                    break

            # ── 5. MSS signal on M5, fallback to M1 ───────────────────────────────
            _mss_lb = settings_manager.get('smc_lookback_mss', 10)
            mss_signal = 0
            for mss_name in ['M5', 'M1']:
                mss_smc = smc.get(mss_name)
                if mss_smc is not None and len(mss_smc) >= _mss_lb:
                    recent = mss_smc.iloc[-_mss_lb:]
                    for _, row in reversed(list(recent.iterrows())):
                        if row['mss_signal'] != 0:
                            mss_signal = int(row['mss_signal'])
                            break
                if mss_signal != 0:
                    break

            # ── 6. FVG on M1 (execution level) ────────────────────────────────────
            _fvg_lb = settings_manager.get('smc_fvg_lookback', 5)
            m1_smc = smc.get('M1')
            if m1_smc is not None and len(m1_smc) > 0:
                recent_fvg = m1_smc.iloc[-_fvg_lb:]
                non_rfvg_rows = recent_fvg[
                    (recent_fvg['fvg_class'] != 'none') &
                    (recent_fvg['fvg_class'] != 'rfvg')
                ] if len(recent_fvg) > 0 else pd.DataFrame()
                if len(non_rfvg_rows) > 0:
                    best_fvg_row = non_rfvg_rows.iloc[-1]
                    fvg_class = best_fvg_row['fvg_class']
                    fvg_type = best_fvg_row['fvg_type']
                    fvg_top = best_fvg_row['fvg_top']
                    fvg_bottom = best_fvg_row['fvg_bottom']
                else:
                    fvg_class = latest_m1['fvg_class'] if latest_m1 is not None else 'none'
                    fvg_type = latest_m1['fvg_type'] if latest_m1 is not None else 'none'
                    fvg_top = latest_m1['fvg_top'] if latest_m1 is not None else np.nan
                    fvg_bottom = latest_m1['fvg_bottom'] if latest_m1 is not None else np.nan
            else:
                fvg_class, fvg_type, fvg_top, fvg_bottom = 'none', 'none', np.nan, np.nan

            # ── 7. LTF reference (always M1) ──────────────────────────────────────
            # For ATR, support/resistance, volatility — use M1 for execution precision
            ref_ltf = latest_m1 if latest_m1 is not None else (latest_m5 if latest_m5 is not None else latest_h1)
            df_ltf = df_m1 if df_m1 is not None else df_m5

            # ── 8. Build 6-TF alignment state for dashboard ───────────────────────
            def bias_label(b):
                return "BULLISH" if b == 1 else ("BEARISH" if b == -1 else "NEUTRAL")

            # Detect VSA signals on M1 and M5 for dashboard labels
            from utils.volume_analyzer import VolumeAnalyzer
            vsa_m1 = VolumeAnalyzer.detect_vsa_signals(df_m1, df_m1['atr'], lookback=3) if df_m1 is not None and 'atr' in df_m1.columns else []
            vsa_m5 = VolumeAnalyzer.detect_vsa_signals(df_m5, df_m5['atr'], lookback=3) if df_m5 is not None and 'atr' in df_m5.columns else []
            
            def get_vsa_label(vsa_list, default_lbl):
                if vsa_list:
                    return vsa_list[0]['pattern']
                return default_lbl

            tf_alignment = {
                'D1':  {'bias': d1_bias,  'label': bias_label(d1_bias)},
                'H4':  {'bias': h4_bias,  'label': bias_label(h4_bias)},
                'H1':  {'bias': h1_bias,  'label': bias_label(h1_bias)},
                'M15': {'bias': m15_bias, 'label': 'SWEEP↑' if sweep_type == 1 else ('SWEEP↓' if sweep_type == -1 else bias_label(m15_bias))},
                'M5':  {'bias': m5_bias,  'label': get_vsa_label(vsa_m5, 'MSS↑' if mss_signal == 1 else ('MSS↓' if mss_signal == -1 else bias_label(m5_bias)))},
                'M1':  {'bias': m1_bias,  'label': get_vsa_label(vsa_m1, 'TBS✅' if mss_signal != 0 and sweep_type != 0 else bias_label(m1_bias))},
                'htf_bias': htf_bias,
                'aligned': (htf_bias != 0 and sweep_type != 0 and mss_signal != 0 and
                           htf_bias == (1 if sweep_type > 0 else -1) and
                           htf_bias == (1 if mss_signal > 0 else -1))
            }
            self._last_tf_alignment = tf_alignment

            # ── 9. Technical sentiment cache ──────────────────────────────────────
            if not hasattr(self, 'sentiment_cache_expiry'):
                self.sentiment_cache_expiry = {}

            tf_sentiment_map = {
                'd1': (mt5.TIMEFRAME_D1, df_d1, 3600),
                'h4': (mt5.TIMEFRAME_H4, df_h4, 1200),
                'h1': (mt5.TIMEFRAME_H1, df_h1, 600),
                'm15': (mt5.TIMEFRAME_M15, df_m15, 60),
                'm5': (mt5.TIMEFRAME_M5, df_m5, 30),
                'm1': (mt5.TIMEFRAME_M1, df_m1, 15),
            }

            _temp_sentiment = dict(self.sentiment_cache)
            sentiment_changed = False
            for tf_name, (tf_const, df_tf, ttl) in tf_sentiment_map.items():
                cache_key = f"{symbol}_{tf_name}"
                if cache_key in self.sentiment_cache_expiry and current_time < self.sentiment_cache_expiry[cache_key]:
                    continue
                if df_tf is not None and len(df_tf) >= 50:
                    _temp_sentiment[tf_name] = sentiment_analyzer.calculate_technical_sentiment(df_tf)
                    self.sentiment_cache_expiry[cache_key] = current_time + ttl
                    sentiment_changed = True

            if sentiment_changed:
                self.sentiment_cache = _temp_sentiment
                try:
                    import json
                    cache_path = os.path.join("configs", "sentiment_cache.json")
                    with open(cache_path, "w") as f:
                        json.dump(self.sentiment_cache, f)
                except Exception:
                    pass

            # ── 10. Daily/weekly key levels cache ─────────────────────────────────
            if not hasattr(self, '_last_daily_levels_time'):
                self._last_daily_levels_time = {}
            if not hasattr(self, 'pdh_cache'):
                self.pdh_cache = {}
                self.pdl_cache = {}
                self.pwh_cache = {}
                self.pwl_cache = {}

            last_lvl_time = self._last_daily_levels_time.get(symbol, 0)
            if current_time - last_lvl_time >= 900 or symbol not in self.pdh_cache:
                try:
                    # Use D1 data already fetched if available
                    if df_d1 is not None and len(df_d1) >= 2:
                        self.pdh_cache[symbol] = float(df_d1.iloc[-2]['high'])
                        self.pdl_cache[symbol] = float(df_d1.iloc[-2]['low'])
                    else:
                        rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 2)
                        if rates_d1 is not None and len(rates_d1) >= 2:
                            self.pdh_cache[symbol] = float(rates_d1[-2]['high'])
                            self.pdl_cache[symbol] = float(rates_d1[-2]['low'])
                        else:
                            self.pdh_cache[symbol] = np.nan
                            self.pdl_cache[symbol] = np.nan

                    rates_w1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 2)
                    if rates_w1 is not None and len(rates_w1) >= 2:
                        self.pwh_cache[symbol] = float(rates_w1[-2]['high'])
                        self.pwl_cache[symbol] = float(rates_w1[-2]['low'])
                    else:
                        self.pwh_cache[symbol] = np.nan
                        self.pwl_cache[symbol] = np.nan
                    self._last_daily_levels_time[symbol] = current_time
                except Exception as ex:
                    self.logger.warning(f"Failed to fetch daily levels: {ex}")

            # ── 11. Volume metrics ─────────────────────────────────────────────────
            if not hasattr(self, '_last_volume_calc_time'):
                self._last_volume_calc_time = {}

            last_vol_time = self._last_volume_calc_time.get(symbol, 0)
            if current_time - last_vol_time >= 10.0 or not self.volume_cache or "rvol" not in self.volume_cache:
                latest_rvol = VolumeAnalyzer.calculate_rvol_latest(df_ltf, period=20)
                latest_buy_press, latest_sell_press = VolumeAnalyzer.calculate_buying_selling_pressure_latest(df_ltf)
                total_press = latest_buy_press + latest_sell_press
                buy_pct = (latest_buy_press / total_press * 100.0) if total_press > 0 else 50.0
                sell_pct = (latest_sell_press / total_press * 100.0) if total_press > 0 else 50.0
                vp_profile = VolumeAnalyzer.calculate_volume_profile(df_ltf, lookback=100, bins=20)
                self.volume_cache = {
                    "rvol": latest_rvol, "buy_pressure": buy_pct,
                    "sell_pressure": sell_pct, "profile": vp_profile
                }
                self._last_volume_calc_time[symbol] = current_time

            # ── 12. Current tick ───────────────────────────────────────────────────
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return None

            # Check sweeps
            ref_atr = float(latest_m1['atr']) if latest_m1 is not None and 'atr' in latest_m1 else 1.0
            swept_pools = self.liquidity_map.check_sweeps(tick.bid, ref_atr)

            sentiment_payload = dict(self.sentiment_cache)
            sentiment_payload['pdh'] = self.pdh_cache.get(symbol, np.nan)
            sentiment_payload['pdl'] = self.pdl_cache.get(symbol, np.nan)
            sentiment_payload['pwh'] = self.pwh_cache.get(symbol, np.nan)
            sentiment_payload['pwl'] = self.pwl_cache.get(symbol, np.nan)

            # ── 13. Strategy evaluation with full 6-TF context ───────────────────
            active_strategy = settings_manager.get("active_strategy", "both")
            if active_strategy == "fib_retest":
                active_strategy = "both"

            fib_action, fib_regime, fib_sl, fib_tp, fib_metadata = None, "sideway", 0.0, 0.0, {}
            crt_action, crt_regime, crt_sl, crt_tp, crt_metadata = None, "sideway", 0.0, 0.0, {}

            if active_strategy in ["crt_tbs", "both"]:
                crt_action, crt_regime, crt_sl, crt_tp, crt_metadata = CrtTbsStrategy.evaluate_crt_tbs(
                    df_d1=df_d1,
                    df_h4=df_h4,
                    df_h1=df_h1,
                    df_m15=df_m15,
                    df_m5=df_m5,
                    df_m1=df_m1,
                    current_price=tick.bid,
                    atr=float(ref_ltf['atr']) if ref_ltf is not None else 1.0,
                    volume_cache=self.volume_cache,
                    sentiment_cache=sentiment_payload,
                    htf_bias=htf_bias
                )

            active_regime = crt_regime if active_strategy == "crt_tbs" else (
                "bullish" if htf_bias == 1 else ("bearish" if htf_bias == -1 else "sideway")
            )
            self.pattern_learner.market_regimes[symbol] = {
                'regime': active_regime.upper(),
                'timestamp': str(pd.Timestamp.now()),
                'volatility': float(ref_ltf['volatility']) if ref_ltf is not None else 0.0,
                'atr_pct': float(ref_ltf['atr_pct']) if ref_ltf is not None else 0.0
            }

            # Extract OB metadata for dashboard chart
            ob_meta = {}
            try:
                if latest_h1 is not None:
                    ob_top = float(latest_h1.get('resistance', np.nan))
                    ob_bottom = float(latest_h1.get('support', np.nan))
                    if not np.isnan(ob_top) and not np.isnan(ob_bottom):
                        ob_meta = {
                            'ob_top': ob_top,
                            'ob_bottom': ob_bottom,
                            'ob_direction': 'bullish' if htf_bias == 1 else 'bearish'
                        }
            except Exception:
                pass

            # Aggregate VSA signals list for Brain scoring
            vsa_signals_combined = []
            for vsa_item in (vsa_m1 or []):
                sig_name = vsa_item.get('pattern', '') if isinstance(vsa_item, dict) else str(vsa_item)
                if sig_name:
                    vsa_signals_combined.append(sig_name)
            for vsa_item in (vsa_m5 or []):
                sig_name = vsa_item.get('pattern', '') if isinstance(vsa_item, dict) else str(vsa_item)
                if sig_name and sig_name not in vsa_signals_combined:
                    vsa_signals_combined.append(sig_name)

            buy_pressure_val = self.volume_cache.get('buy_pressure', 50.0) if self.volume_cache else 50.0
            sell_pressure_val = self.volume_cache.get('sell_pressure', 50.0) if self.volume_cache else 50.0

            analysis = {
                'symbol': symbol,
                'price': tick.bid,
                'bid': tick.bid,
                'ask': tick.ask,
                # Phase 8 Core Intelligence outputs
                'news_locked': news_locked,
                'news_lockout_reason': news_lockout_reason,
                'market_regime': regime.name,
                'swept_pools': swept_pools,
                'resting_pools': self.liquidity_map.get_resting_pools(),
                # 6-TF bias states
                'htf_bias': htf_bias,
                'd1_bias': d1_bias,
                'h4_bias': h4_bias,
                'h1_bias': h1_bias,
                'm15_bias': m15_bias,
                'm5_bias': m5_bias,
                'm1_bias': m1_bias,
                # Sweep/MSS signals
                'm15_sweep_type': sweep_type,
                'm15_sweep_level': float(sweep_level) if not np.isnan(sweep_level) else 0.0,
                'm5_mss_signal': mss_signal,
                # FVG (M1-level)
                'm5_fvg_class': fvg_class,
                'm5_fvg_type': fvg_type,
                'm5_fvg_top': float(fvg_top) if not np.isnan(fvg_top) else 0.0,
                'm5_fvg_bottom': float(fvg_bottom) if not np.isnan(fvg_bottom) else 0.0,
                # Technical levels from M1
                'support': float(ref_ltf['support']) if ref_ltf is not None else 0.0,
                'resistance': float(ref_ltf['resistance']) if ref_ltf is not None else 0.0,
                'volatility': float(ref_ltf['volatility']) if ref_ltf is not None else 0.0,
                'atr_pct': float(ref_ltf['atr_pct']) if ref_ltf is not None else 0.0,
                'atr': float(ref_ltf['atr']) if ref_ltf is not None else 1.0,
                'hour': datetime.now(timezone.utc).hour,
                # Phase 9 Brain Layer inputs
                'vsa_signals': vsa_signals_combined,
                'buy_pressure': buy_pressure_val,
                'sell_pressure': sell_pressure_val,
                # Brain score will be populated in evaluate_entry_rules()
                'brain_score': 0.0,
                'brain_direction': None,
                'brain_threshold': settings_manager.get('brain_threshold', 55.0),
                'brain_reason_map': {},
                # Session intelligence outputs
                'session_name': session_ctx['session_name'],
                'session_score': session_ctx['session_score'],
                # Strategy outputs
                'fib_action': fib_action, 'fib_regime': fib_regime,
                'fib_sl': fib_sl, 'fib_tp': fib_tp, 'fib_metadata': fib_metadata,
                'crt_action': crt_action, 'crt_regime': crt_regime,
                'crt_sl': crt_sl, 'crt_tp': crt_tp, 'crt_metadata': crt_metadata,
                'ob_metadata': ob_meta,
                # Dataframe references
                'df_ltf': df_m1,  # always M1 for entry
                'df_m5': df_m5,
                'df_h1': df_h1,
                'df_h4': df_h4,
                'df_d1': df_d1,
                'tf_alignment': tf_alignment,
                'features': {
                    'active_bias': htf_bias,
                    'd1_bias': d1_bias,
                    'h4_bias': h4_bias,
                    'h1_bias': h1_bias,
                    'liq_sweep_type': sweep_type,
                    'mss_signal': mss_signal,
                    'fvg_class': fvg_class,
                    'support': float(ref_ltf['support']) if ref_ltf is not None else 0.0,
                    'resistance': float(ref_ltf['resistance']) if ref_ltf is not None else 0.0,
                    'atr_pct': float(ref_ltf['atr_pct']) if ref_ltf is not None else 0.0,
                    'volatility': float(ref_ltf['volatility']) if ref_ltf is not None else 0.0,
                    'hour': datetime.now(timezone.utc).hour,
                    'price': tick.bid,
                    'tf_aligned': tf_alignment.get('aligned', False),
                    'market_regime': regime.name,
                    'news_locked': news_locked
                }
            }

            # ── 14. Broker profile (once only) ────────────────────────────────────
            if not getattr(self, '_broker_profile_set', False):
                from utils.symbol_manager import symbol_manager
                profile = symbol_manager.get_broker_profile(symbol)
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
            self.logger.error(f"Error during 6-TF analysis: {e}")
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
        
        # Rule 0: Cooldown check (prevent double-entry on the same candle)
        current_candle = self.last_candle_times.get(symbol, 0)
        if current_candle > 0:
            if current_candle == self.last_entry_candle.get(symbol, 0):
                return None
            if current_candle == self.last_close_candle.get(symbol, 0):
                return None
                
        # Rule 0.1: Safety Engine Check (consecutive losses / drawdown)
        allowed, safety_reason = self.safety_engine.check_entry_allowed()
        if not allowed:
            self.skipped_stats['safety_halt'] = self.skipped_stats.get('safety_halt', 0) + 1
            analysis['brain_block_reason'] = "SAFETY_HALT"
            return None

        bid = analysis['bid']
        ask = analysis['ask']
        atr = analysis['atr']
        
        h1_bias = analysis.get('htf_bias', analysis.get('h1_bias', 0))  # use master HTF bias
        m15_sweep = analysis['m15_sweep_type']
        m5_mss = analysis['m5_mss_signal']
        fvg_class = analysis['m5_fvg_class']
        fvg_type = analysis['m5_fvg_type']
        
        # Rule 1: Killzone Active check
        if not self.is_killzone_active():
            self.skipped_stats['killzone_inactive'] = self.skipped_stats.get('killzone_inactive', 0) + 1
            return None

        # Rule 1.1: News Lockout check
        if analysis.get('news_locked', False):
            self.skipped_stats['news_filter'] = self.skipped_stats.get('news_filter', 0) + 1
            import time
            current_time = time.time()
            if not hasattr(self, '_last_news_log_time'):
                self._last_news_log_time = 0
            if current_time - self._last_news_log_time >= 60.0:
                self.logger.warning(f"🚫 Trade entry blocked on {symbol} due to news lockout: {analysis.get('news_lockout_reason')}")
                self._last_news_log_time = current_time
            return None

        # Rule 1.2: CHAOTIC regime — hard gate before Brain (defence-in-depth)
        # COMPRESSION is handled by Brain v2 via raised threshold (65 pts) — NOT hard-blocked here
        regime_str = analysis.get('market_regime', 'RANGE')
        if settings_manager.get("dynamic_regime_filter", True):
            if regime_str == "CHAOTIC":
                self.skipped_stats['regime_filter'] = self.skipped_stats.get('regime_filter', 0) + 1
                import time
                current_time = time.time()
                if not hasattr(self, '_last_regime_log_time'):
                    self._last_regime_log_time = 0
                if current_time - self._last_regime_log_time >= 60.0:
                    self.logger.warning(f"🚫 Trade entry hard-blocked on {symbol}: CHAOTIC regime (pre-Brain gate)")
                    self._last_regime_log_time = current_time
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

        # Get AI signal confidence from pattern learner
        ai_signal = self.pattern_learner.get_trading_signal(
            symbol,
            analysis['features'],
            df_ltf=analysis.get('df_ltf'),
            df_m5=analysis.get('df_m5'),
            df_h1=analysis.get('df_h1')
        )
        confidence = ai_signal.get('confidence', 0.5)
        adjustment = ai_signal.get('adjustment', 0.0)

        # ── Phase 9 v2: TradeBrain probabilistic scoring gate ─────────────────
        # Strategy signal passed as advisory — Brain decides direction authoritatively
        strategy_signal = analysis.get('crt_action') or analysis.get('fib_action')
        brain_result = self.trade_brain.evaluate(
            analysis=analysis,
            strategy_action=strategy_signal,
            ai_confidence=confidence,
            session_score=analysis.get('session_score', 0.0),
        )
        # Write brain results back into analysis for dashboard consumption
        analysis['brain_score']      = brain_result.brain_score
        analysis['brain_direction']  = brain_result.brain_direction
        analysis['brain_threshold']  = brain_result.threshold
        analysis['brain_reason_map'] = brain_result.reason_map
        analysis['brain_label']      = self.trade_brain.get_score_label(brain_result.brain_score)
        analysis['brain_color']      = self.trade_brain.get_color_zone(brain_result.brain_score)
        analysis['brain_tier1']      = brain_result.tier1_score
        analysis['brain_tier2']      = brain_result.tier2_score
        analysis['brain_tier3']      = brain_result.tier3_score
        analysis['brain_block_reason'] = brain_result.block_reason

        if not brain_result.passed:
            self.skipped_stats['brain_filter'] = self.skipped_stats.get('brain_filter', 0) + 1
            # Log reason at reduced frequency
            import time as _t
            _now = _t.time()
            if not hasattr(self, '_last_brain_block_log'):
                self._last_brain_block_log = {}
            if _now - self._last_brain_block_log.get(symbol, 0) >= 15.0:
                self.logger.info(
                    f"Brain blocked {symbol}: score={brain_result.brain_score:.1f}/{brain_result.threshold:.0f} "
                    f"reason={brain_result.block_reason} "
                    f"T1={brain_result.tier1_score:.0f}/50 T2={brain_result.tier2_score:.0f}/35 T3={brain_result.tier3_score:.0f}/15"
                )
                self._last_brain_block_log[symbol] = _now
            return None

        # Position checking helper
        def can_trade_direction(action: str) -> bool:
            if not settings_manager.get("hedging_mode", False):
                return len(self.trade_manager.positions) == 0
            else:
                has_same_direction = any(p.symbol == symbol and p.action == action for p in self.trade_manager.positions.values())
                return not has_same_direction

        # Get active strategy setting
        active_strategy = settings_manager.get("active_strategy", "both")
        if active_strategy == "fib_retest":
            active_strategy = "both"
            
        disabled_setups = settings_manager.get("disabled_setups", [])
        
        # ── FIX 4 (Brain v2 hierarchy): Brain decided direction above.
        #    Strategy (CRT/SMC) now confirms EXECUTION QUALITY only — no direction control.
        #    Hierarchy: Brain decides direction → Strategy confirms entry quality → Engine executes
        brain_direction = analysis.get('brain_direction')   # authoritative direction from Brain

        # Priority 1: CRT + TBS — execution quality confirmation only
        if active_strategy in ["crt_tbs", "both"]:
            if "CRT_TBS" not in disabled_setups:
                crt_action = analysis.get('crt_action')
                if crt_action in ["BUY", "SELL"] and can_trade_direction(crt_action):
                    # Execute if CRT agrees with Brain direction
                    # (brain_direction is None = conflicted, also blocks here)
                    if crt_action == brain_direction:
                        crt_sl = analysis.get('crt_sl', 0.0)
                        crt_tp = analysis.get('crt_tp', 0.0)
                        if crt_sl > 0.0 and crt_tp > 0.0:
                            self.logger.info(
                                f"CRT+TBS {symbol} | dir={crt_action} | "
                                f"Brain={analysis.get('brain_score', 0):.1f}/{analysis.get('brain_threshold', 55):.0f} "
                                f"T1={analysis.get('brain_tier1', 0):.0f} T2={analysis.get('brain_tier2', 0):.0f} "
                                f"| SL:{crt_sl:.2f} TP:{crt_tp:.2f}"
                            )
                            return crt_action, crt_sl, crt_tp, "CRT_TBS"
                    elif brain_direction is not None:
                        self.logger.info(
                            f"CRT_TBS skipped: strategy={crt_action} conflicts Brain={brain_direction} "
                            f"(score={analysis.get('brain_score', 0):.1f})"
                        )
                    
        # Priority 2: SMC Strategy
        if active_strategy in ["smc", "both"]:
            # Setup classification before entry
            had_sweep = (m15_sweep != 0)
            had_mss = (m5_mss != 0)
            if had_sweep and had_mss:
                setup_type = "SHARP_TURN"
            elif had_mss:
                setup_type = "MSS_ONLY"
            elif had_sweep:
                setup_type = "SWEEP_ONLY"
            else:
                setup_type = "CONTINUATION"
                
            # Block disabled setups
            if setup_type in disabled_setups:
                pass
            else:
                # --- BULLISH ENTRY MODEL (Strict Trend Alignment) ---
                is_bullish_setup = (h1_bias == 1) and (m15_sweep == 1 or m5_mss == 1)
                
                # --- BEARISH ENTRY MODEL (Strict Trend Alignment) ---
                is_bearish_setup = (h1_bias == -1) and (m15_sweep == -1 or m5_mss == -1)
                
                # Throttled logging to avoid log pollution
                import time
                current_time = time.time()
                
                if not hasattr(self, '_last_block_log_time'):
                    self._last_block_log_time = {}
                last_block_log = self._last_block_log_time.get(symbol, 0)
                should_log_block = (current_time - last_block_log >= 60.0)
        
                last_log = getattr(self, '_last_eval_log_time', {})
                if current_time - last_log.get(symbol, 0) >= 10.0:
                    self.logger.info(
                        f"📊 {symbol} Eval | bias={h1_bias} sweep={m15_sweep} mss={m5_mss} fvg={fvg_class} | bull={is_bullish_setup} bear={is_bearish_setup}"
                    )
                    last_log[symbol] = current_time
                    self._last_eval_log_time = last_log
        
                # Premium/Discount check using support and resistance boundaries
                range_mid = 0.5 * (analysis['support'] + analysis['resistance'])
                if is_bullish_setup and can_trade_direction("BUY") and analysis['support'] > 0 and analysis['resistance'] > 0:
                    if bid > range_mid:
                        if should_log_block:
                            self.logger.warning(f"🚫 BUY setup blocked: price ({bid:.2f}) is in Premium zone (above range mid: {range_mid:.2f})")
                            self._last_block_log_time[symbol] = current_time
                        is_bullish_setup = False
        
                if is_bearish_setup and can_trade_direction("SELL") and analysis['support'] > 0 and analysis['resistance'] > 0:
                    if ask < range_mid:
                        if should_log_block:
                            self.logger.warning(f"🚫 SELL setup blocked: price ({ask:.2f}) is in Discount zone (below range mid: {range_mid:.2f})")
                            self._last_block_log_time[symbol] = current_time
                        is_bearish_setup = False
        
                # FIX 4: Brain v2 hierarchy — only execute in Brain's approved direction
                # Brain has already decided direction; SMC entry must confirm, not override
                if is_bullish_setup and brain_direction != "BUY":
                    is_bullish_setup = False   # Brain did not approve BUY
                if is_bearish_setup and brain_direction != "SELL":
                    is_bearish_setup = False   # Brain did not approve SELL

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
                    
                    brain_score = analysis.get('brain_score', 0)
                    self.logger.info(
                        f"🟢 BUY SMC on {symbol} | MSS:1 Sweep:1 FVG:{fvg_class} | "
                        f"BrainScore={brain_score:.1f} RR:{rr_ratio:.2f}"
                    )
                    return "BUY", sl_price, tp_price, setup_type
        
                if is_bearish_setup and can_trade_direction("SELL"):
                    entry_price = bid
                    
                    # SL: placed above the recent LTF resistance swing high
                    sl_price = analysis['resistance'] + (0.2 * atr)
                    sl_price = max(sl_price, entry_price + (1.5 * atr))
                    
                    # TP: Target opposing support liquidity with dynamic RR
                    tp_price = entry_price - (rr_ratio * (sl_price - entry_price))
                    
                    if analysis['support'] < entry_price:
                        tp_price = min(tp_price, analysis['support'])
                    
                    brain_score = analysis.get('brain_score', 0)
                    self.logger.info(
                        f"🔴 SELL SMC on {symbol} | MSS:-1 Sweep:-1 FVG:{fvg_class} | "
                        f"BrainScore={brain_score:.1f} RR:{rr_ratio:.2f}"
                    )
                    return "SELL", sl_price, tp_price, setup_type
                    
        return None

    def execute_and_record_trade(self, symbol: str, action: str, sl: float, tp: float, analysis: Dict):
        """Execute the order and record the initial state into experience memory"""
        # Spread check
        tick = mt5.symbol_info_tick(symbol)
        symbol_info = mt5.symbol_info(symbol)
        spread = (tick.ask - tick.bid) / symbol_info.point
        
        max_spread = settings_manager.get("max_spread_points", self.config.MAX_SPREAD_POINTS)
        if "BTC" in symbol or "ETH" in symbol:
            from utils.symbol_manager import symbol_manager
            profile = symbol_manager.get_broker_profile(symbol)
            max_spread = max(max_spread, profile.get("max_spread_points", 5000))
            
        if spread > max_spread:
            self.logger.warning(f"Trade blocked on {symbol} due to high spread: {spread:.1f} points (Limit: {max_spread})")
            self.skipped_stats['high_spread'] = self.skipped_stats.get('high_spread', 0) + 1
            return
            
        entry_price = tick.ask if action == "BUY" else tick.bid
        
        # Check if Auto Trade is enabled
        auto_trade = settings_manager.get("auto_trade_enabled", True)
        if not auto_trade:
            self.logger.info(f"🔍 [ANALYSIS ONLY] Auto Trade is OFF. Recording setup on {symbol}: {action} entry @ {entry_price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
            self.analyzed_trades[symbol] = {
                "entry": entry_price,
                "sl": sl,
                "tp": tp,
                "action": action,
                "time": time.time(),
                "entry_features": analysis.get('features', {})
            }
            # Record entry candle to prevent double-entry cooldown
            current_candle = self.last_candle_times.get(symbol, 0)
            self.last_entry_candle[symbol] = current_candle
            return
            
        # Calculate dynamic risk percentage if enabled
        risk_percent = None
        if settings_manager.get("dynamic_risk_enabled", True):
            try:
                # Calculate median ATR over df_ltf
                df_ltf = analysis.get('df_ltf')
                if df_ltf is not None and 'atr' in df_ltf.columns:
                    current_atr = float(df_ltf['atr'].iloc[-1])
                    median_atr = float(df_ltf['atr'].rolling(window=min(len(df_ltf), 100), min_periods=1).median().iloc[-1])
                else:
                    current_atr = analysis.get('atr', 1.0)
                    median_atr = current_atr
                
                # Fetch AI confidence score
                ai_signal = self.pattern_learner.get_trading_signal(
                    symbol,
                    analysis['features'],
                    df_ltf=analysis.get('df_ltf'),
                    df_m5=analysis.get('df_m5'),
                    df_h1=analysis.get('df_h1')
                )
                confidence = ai_signal.get('confidence', 0.8)
                
                active_positions = len(self.trade_manager.positions)
                base_risk = settings_manager.get("risk_percent", 1.0)
                
                risk_percent = self.risk_engine.calculate_risk_percent(
                    current_atr=current_atr,
                    median_atr=median_atr,
                    current_spread=spread,
                    max_spread=max_spread,
                    confidence=confidence,
                    active_positions=active_positions,
                    base_risk=base_risk
                )
            except Exception as risk_err:
                self.logger.error(f"Error calculating dynamic risk: {risk_err}")
                risk_percent = settings_manager.get("risk_percent", 1.0)
            
        # Open trade via trade manager
        pos = self.trade_manager.open_position(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            sl_price=sl,
            tp_price=tp,
            risk_percent=risk_percent
        )
        
        # Record the entry candle timestamp to prevent double-entry (do this regardless of success to avoid immediate retry spam)
        current_candle = self.last_candle_times.get(symbol, 0)
        self.last_entry_candle[symbol] = current_candle
        
        if pos:
            # Store initial entry features in positions for outcome learning
            pos.entry_features = analysis['features']
            pos.brain_score = analysis.get('brain_score', 0.0)
            pos.brain_tier1 = analysis.get('brain_tier1', 0.0)
            pos.brain_tier2 = analysis.get('brain_tier2', 0.0)
            pos.brain_tier3 = analysis.get('brain_tier3', 0.0)
            pos.brain_direction = analysis.get('brain_direction')
            pos.brain_block_reason = analysis.get('brain_block_reason')
            pos.brain_reason_map = analysis.get('brain_reason_map', {})
            pos.session = analysis.get('session_name', 'OFF')
            pos.volatility_regime = analysis.get('market_regime', 'RANGE')

    def process_closed_positions(self):
        """Learn from closed positions and update the self-learning DB + trade journal"""
        while len(self.trade_manager.closed_positions) > 0:
            pos = self.trade_manager.closed_positions.pop(0)
            
            # Record the candle timestamp when this trade closed to implement cooldown
            current_candle = self.last_candle_times.get(pos.symbol, 0)
            self.last_close_candle[pos.symbol] = current_candle
            
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
                    "tp": pos.tp1 if hasattr(pos, 'tp1') else pos.tp,
                    "lot_size": pos.volume,
                    "pnl": round(pos.pnl, 2),
                    "rr_achieved": rr_achieved,
                    "close_reason": pos.close_reason,
                    "duration_mins": duration_mins,
                    "setup_type": setup_type,
                    "fvg_class": str(f.get('fvg_class', 'none')).upper(),
                    "bias": bias_label,
                    "volatility_regime": getattr(pos, 'volatility_regime', 'NORMAL'),
                    "spread_at_entry": spread_at_entry,
                    # Phase 10 TradeBrain fields
                    "brain_score": getattr(pos, 'brain_score', 0.0),
                    "brain_tier1": getattr(pos, 'brain_tier1', 0.0),
                    "brain_tier2": getattr(pos, 'brain_tier2', 0.0),
                    "brain_tier3": getattr(pos, 'brain_tier3', 0.0),
                    "brain_direction": getattr(pos, 'brain_direction', None),
                    "brain_block_reason": getattr(pos, 'brain_block_reason', None),
                    "session": getattr(pos, 'session', 'OFF'),
                    "vsa_signals": f.get('vsa_signals', [])
                }
                trade_journal.append_trade(journal_record)
                
                # Phase 10 feedback loops
                self.safety_engine.record_trade_result(pos.pnl)
                self.brain_calibrator.record_outcome(
                    reason_map=getattr(pos, 'brain_reason_map', {}),
                    outcome="WIN" if pos.pnl > 0.0 else ("LOSS" if pos.pnl < 0.0 else "BE"),
                    pnl=pos.pnl
                )
            except Exception as e:
                self.logger.error(f"Failed to write trade to journal / calibrator: {e}")

            self.logger.info(f"🧠 Closed Position Learnt: {pos.symbol} {pos.action} Ticket #{pos.id} closed due to {pos.close_reason} | PnL: ${pos.pnl:.2f}")

    def get_prediction_data(self, symbol: str) -> dict:
        """Return next predicted trade setup, current price, sessions, and 6-TF alignment info."""
        try:
            analysis = self.cached_analysis.get(symbol)
            if not analysis:
                return {}

            tick = mt5.symbol_info_tick(symbol)
            bid = tick.bid if tick else 0.0
            ask = tick.ask if tick else 0.0

            # Run AI prediction with all available TF dataframes
            ai_signal = self.pattern_learner.get_trading_signal(
                symbol,
                analysis.get('features', {}),
                df_ltf=analysis.get('df_ltf'),
                df_m5=analysis.get('df_m5'),
                df_h1=analysis.get('df_h1')
            )

            detected_patterns = ai_signal.get('detected_patterns', [])
            smc_patterns = ai_signal.get('smc_patterns', [])

            if not detected_patterns:
                htf_bias = analysis.get('htf_bias', analysis.get('h1_bias', 0))
                m15_sweep = analysis.get('m15_sweep_type', 0)
                m5_mss = analysis.get('m5_mss_signal', 0)
                fvg_class = str(analysis.get('m5_fvg_class', 'none')).upper()

                if m15_sweep == 1 and m5_mss == 1:
                    detected_patterns = ["BULLISH REVERSAL SWEEP"]
                elif m15_sweep == -1 and m5_mss == -1:
                    detected_patterns = ["BEARISH REVERSAL SWEEP"]
                elif m5_mss == 1:
                    detected_patterns = ["BULLISH STRUCTURE SHIFT"]
                elif m5_mss == -1:
                    detected_patterns = ["BEARISH STRUCTURE SHIFT"]
                elif m15_sweep == 1:
                    detected_patterns = ["BULLISH LIQUIDITY SWEEP"]
                elif m15_sweep == -1:
                    detected_patterns = ["BEARISH LIQUIDITY SWEEP"]
                elif fvg_class == "DFVG":
                    detected_patterns = ["BULLISH FVG ENTRY SCAN"]
                elif fvg_class == "PFVG":
                    detected_patterns = ["BEARISH FVG ENTRY SCAN"]
                else:
                    bias_str = "BULLISH" if htf_bias > 0 else ("BEARISH" if htf_bias < 0 else "NEUTRAL")
                    detected_patterns = [f"{bias_str} REGIME SCAN"]

            # Get CRT metadata from crt_metadata if available
            crt_meta = analysis.get('crt_metadata', {})
            crt_low = crt_meta.get('crt_low', analysis.get('crt_low', 0.0))
            crt_high = crt_meta.get('crt_high', analysis.get('crt_high', 0.0))

            # Get VSA patterns for status API
            from utils.volume_analyzer import VolumeAnalyzer
            vsa_patterns = []
            df_m1 = analysis.get('df_ltf')  # M1
            df_m5 = analysis.get('df_m5')
            if df_m1 is not None and 'atr' in df_m1.columns:
                vsa_patterns += [s['pattern'] for s in VolumeAnalyzer.detect_vsa_signals(df_m1, df_m1['atr'], lookback=3)]
            if df_m5 is not None and 'atr' in df_m5.columns:
                vsa_patterns += [s['pattern'] for s in VolumeAnalyzer.detect_vsa_signals(df_m5, df_m5['atr'], lookback=3)]
            vsa_patterns = list(set(vsa_patterns))

            # Get 6-TF alignment from analysis (set by run_multi_timeframe_analysis)
            tf_alignment = analysis.get('tf_alignment', getattr(self, '_last_tf_alignment', {}))

            result = {
                'symbol': symbol,
                'bid': bid,
                'ask': ask,
                'active_sessions': self.get_active_sessions(),
                # Phase 8 fields
                'news_locked': bool(analysis.get('news_locked', False)),
                'news_lockout_reason': analysis.get('news_lockout_reason'),
                'market_regime': analysis.get('market_regime', 'RANGE'),
                'resting_pools': analysis.get('resting_pools', []),
                'setup': None,
                'action': None,
                'entry': None,
                'sl': None,
                'tp': None,
                'confidence': 0.0,
                'setup_type': None,
                'detected_patterns': detected_patterns,
                'vsa_patterns': vsa_patterns,
                'smc_patterns': smc_patterns,
                'smc_confidence': ai_signal.get('smc_confidence', 0.0),
                'cluster_id': int(ai_signal.get('cluster_id', 0)),
                'training_stats': self.pattern_learner.training_stats.get(symbol, {}),
                # 6-TF bias data for dashboard panel
                'htf_bias': int(analysis.get('htf_bias', analysis.get('h1_bias', 0))),
                'd1_bias': int(analysis.get('d1_bias', 0)),
                'h4_bias': int(analysis.get('h4_bias', 0)),
                'h1_bias': int(analysis.get('h1_bias', 0)),
                'm15_bias': int(analysis.get('m15_bias', 0)),
                'm5_bias': int(analysis.get('m5_bias', 0)),
                'm1_bias': int(analysis.get('m1_bias', 0)),
                'm15_sweep_type': int(analysis.get('m15_sweep_type', 0)),
                'm5_mss_signal': int(analysis.get('m5_mss_signal', 0)),
                'tf_alignment': tf_alignment,
                # CRT zone metadata for chart
                'crt_low': float(crt_low) if crt_low else 0.0,
                'crt_high': float(crt_high) if crt_high else 0.0,
                'ob_metadata': analysis.get('ob_metadata', {}),
                # Phase 9 v2 Brain Layer fields (populated by evaluate_entry_rules)
                'brain_score':        float(analysis.get('brain_score', 0.0)),
                'brain_direction':    analysis.get('brain_direction'),
                'brain_threshold':    float(analysis.get('brain_threshold', 55.0)),
                'brain_reason_map':   analysis.get('brain_reason_map', {}),
                'brain_label':        analysis.get('brain_label', 'BLOCKED'),
                'brain_color':        analysis.get('brain_color', '#ff3366'),
                'brain_tier1':        float(analysis.get('brain_tier1', 0.0)),
                'brain_tier2':        float(analysis.get('brain_tier2', 0.0)),
                'brain_tier3':        float(analysis.get('brain_tier3', 0.0)),
                'brain_block_reason': analysis.get('brain_block_reason'),
                # Phase 10 Safety & Session fields
                'session_name':       analysis.get('session_name', 'OFF'),
                'session_score':      float(analysis.get('session_score', 0.0)),
                'safety_halt':        not self.safety_engine.check_entry_allowed()[0],
                'safety_halt_reason': self.safety_engine.check_entry_allowed()[1],
                'safety_stats':       self.safety_engine.get_stats(),
            }

            setup = self.evaluate_entry_rules(analysis)
            if setup:
                action, sl, tp, setup_type = setup
                entry = ask if action == 'BUY' else bid
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



    def get_asian_range(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        Calculate Asian Range high and low (00:00 to 09:00 UTC) from the last 40 M15 candles.
        """
        try:
            # Fetch last 40 M15 bars
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 40)
            if rates is None or len(rates) == 0:
                return None
            
            # Find rates that fall into the 00:00 to 09:00 UTC window
            asian_highs = []
            asian_lows = []
            
            for rate in rates:
                dt = datetime.fromtimestamp(int(rate['time']), timezone.utc)
                if 0 <= dt.hour < 9:
                    asian_highs.append(float(rate['high']))
                    asian_lows.append(float(rate['low']))
            
            if len(asian_highs) > 0:
                return max(asian_highs), min(asian_lows)
        except Exception as e:
            self.logger.error(f"Error calculating Asian range: {e}")
        return None

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



    def run_engine(self, sleep_seconds=15):
        """Main real-time trading loop (decoupled fast 0.5s cycle with throttled analysis)"""
        self.analysis_interval = float(sleep_seconds)
        loop_sleep = 0.5  # 500ms cycle for instant position updates and pullback checks
        
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
                    # Train on startup to make sure the AI is fully trained on latest price action
                    symbol_patterns = len(self.pattern_learner.patterns.get(f"{symbol}_winning", [])) + \
                                      len(self.pattern_learner.patterns.get(f"{symbol}_losing", []))
                    if symbol_patterns < 200:
                        self.logger.info(f"🧠 Pattern DB has {symbol_patterns} patterns for {symbol} (Sparse < 200). Running startup visual & ML historical training on {symbol}...")
                        self.training_in_progress = True
                        self.trigger_historical_training()
                        self.training_in_progress = False
                    else:
                        self.logger.info(f"🧠 Pattern DB has {symbol_patterns} patterns for {symbol}. Skipping startup yearly training.")
                    
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
                    time.sleep(5)
                    continue
                    
                # Check for dynamic active symbol changes from settings
                active_symbol = settings_manager.get("active_symbol")
                if active_symbol and len(self.symbols) > 0 and self.symbols[0] != active_symbol:
                    self.logger.info(f"🔄 Symbol change requested: switching active symbol from {self.symbols[0]} to {active_symbol}")
                    validated_symbols = self._validate_symbols([active_symbol])
                    if validated_symbols:
                        self.symbols = validated_symbols
                        self.cached_analysis.clear()
                        self.pending_setups.clear()
                        self.last_candle_times.clear()
                        self.last_entry_candle.clear()
                        self.last_close_candle.clear()
                        self.last_analysis_times.clear()
                        self._broker_profile_set = False

                # Process active signals and tracking
                for symbol in self.symbols:
                    tick = mt5.symbol_info_tick(symbol)
                    if not tick:
                        continue
                        
                    # Update positions first (check SL/TP)
                    self.trade_manager.update_positions(symbol, tick.bid, tick.ask)
                    
                    # Monitor and update virtual/analyzed trades if Auto Trade is OFF
                    if symbol in self.analyzed_trades:
                        at = self.analyzed_trades[symbol]
                        bid = tick.bid
                        action = at["action"]
                        sl = at["sl"]
                        tp = at["tp"]
                        
                        closed = False
                        reason = ""
                        if action == "BUY":
                            if bid <= sl:
                                closed = True
                                reason = "SL"
                            elif bid >= tp:
                                closed = True
                                reason = "TP"
                        elif action == "SELL":
                            if bid >= sl:
                                closed = True
                                reason = "SL"
                            elif bid <= tp:
                                closed = True
                                reason = "TP"
                                
                        if closed:
                            self.logger.info(f"🔍 [ANALYSIS ONLY] Setup closed on {symbol} due to {reason} | PnL points: {bid - at['entry'] if action == 'BUY' else at['entry'] - bid:.2f}")
                            # Record close candle cooldown to prevent instant re-entry
                            current_candle = self.last_candle_times.get(symbol, 0)
                            self.last_close_candle[symbol] = current_candle
                            self.analyzed_trades.pop(symbol)
                    
                    # Volume Disaster Check: Early exit safety check removed per user feedback to prevent wicks/volume traps.
                    
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
                                setup_t = pending.get('setup_type', 'SMC')
                                if setup_t == 'CRT_TBS':
                                    if action == "BUY":
                                        if tick.ask <= pending['crt_low']:
                                            triggered = True
                                    elif action == "SELL":
                                        if tick.bid >= pending['crt_high']:
                                            triggered = True
                                else: # SMC setup
                                    if action == "BUY":
                                        if tick.ask <= pending['fvg_top']:
                                            triggered = True
                                    elif action == "SELL":
                                        if tick.bid >= pending['fvg_bottom']:
                                            triggered = True
                                        
                                if triggered:
                                    if setup_t == 'CRT_TBS':
                                        self.logger.info(f"🎯 CRT+TBS pullback entry triggered on {symbol}! Action: {action} @ {tick.ask if action == 'BUY' else tick.bid:.2f} | CRT range boundary hit")
                                    else:
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
                            
                    # Run full analysis if it is a new candle, or every analysis_interval, or if no cache exists
                    time_since_last_analysis = current_time - self.last_analysis_times.get(symbol, 0)
                    if new_candle or time_since_last_analysis >= self.analysis_interval or symbol not in self.cached_analysis:
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
                            
                            # Check news/AI block log throttling
                            if not hasattr(self, '_last_block_log_time'):
                                self._last_block_log_time = {}
                            last_block_log = self._last_block_log_time.get(symbol, 0)
                            should_log_block = (current_time - last_block_log >= 60.0)

                            # Apply news sentiment filter if enabled
                            if settings_manager.get("news_filter_enabled", True):
                                news_state = sentiment_analyzer.get_news_state()
                                news_score = news_state.get("score", 0.0)
                                if action == "BUY" and news_score < -0.4:
                                    if should_log_block:
                                        self.logger.warning(f"🚫 BUY trade blocked by News Sentiment Filter (Score: {news_score:.2f})")
                                        self._last_block_log_time[symbol] = current_time
                                    self.skipped_stats['news_filter'] = self.skipped_stats.get('news_filter', 0) + 1
                                    continue
                                elif action == "SELL" and news_score > 0.4:
                                    if should_log_block:
                                        self.logger.warning(f"🚫 SELL trade blocked by News Sentiment Filter (Score: {news_score:.2f})")
                                        self._last_block_log_time[symbol] = current_time
                                    self.skipped_stats['news_filter'] = self.skipped_stats.get('news_filter', 0) + 1
                                    continue
                                    
                            # Apply pattern learner AI check if enabled
                            if settings_manager.get("self_learning_filter", True):
                                ai_signal = self.pattern_learner.get_trading_signal(symbol, analysis['features'], df_ltf=analysis.get('df_ltf'))
                                confidence = ai_signal.get('confidence', 0.5)
                                adjustment = ai_signal.get('adjustment', 0.0)
                                if confidence < 0.55 or adjustment < 0.0:
                                    if should_log_block:
                                        self.logger.warning(f"🚫 Trade blocked by AI Pattern Learner (Low confidence: {confidence:.2f}, adjustment: {adjustment:.2f})")
                                        self._last_block_log_time[symbol] = current_time
                                    continue
                                    
                            if setup_type == "CRT_TBS":
                                # Save to pending setup with CRT range limits as exact reversal levels
                                crt_low = analysis.get('crt_low')
                                crt_high = analysis.get('crt_high')
                                
                                if crt_low is None or np.isnan(crt_low):
                                    crt_low = tick.ask
                                if crt_high is None or np.isnan(crt_high):
                                    crt_high = tick.bid
                                    
                                self.pending_setups[symbol] = {
                                    'action': action,
                                    'crt_low': crt_low,
                                    'crt_high': crt_high,
                                    'sl': sl,
                                    'tp': tp,
                                    'analysis': analysis,
                                    'candle_time': candle_time,
                                    'setup_type': 'CRT_TBS'
                                }
                                self.logger.info(f"⏳ Pending CRT+TBS {action} setup saved for {symbol}. Wait pullback to range boundary... (Level: {crt_low if action == 'BUY' else crt_high:.2f})")
                                
                                # Immediately check if current price already satisfies the pullback
                                if (action == "BUY" and tick.ask <= crt_low) or (action == "SELL" and tick.bid >= crt_high):
                                    self.logger.info(f"🎯 CRT+TBS entry triggered immediately on {symbol}! Action: {action} @ {tick.ask if action == 'BUY' else tick.bid:.2f}")
                                    self.execute_and_record_trade(symbol, action, sl, tp, analysis)
                                    self.pending_setups.pop(symbol)
                            else: # SMC setup (SHARP_TURN, MSS_ONLY, SWEEP_ONLY, CONTINUATION)
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
                                    'candle_time': candle_time,
                                    'setup_type': 'SMC'
                                }
                                self.logger.info(f"⏳ Pending sniper {action} setup saved for {symbol}. Wait pullback to FVG limits... (FVG: {fvg_bottom:.2f} - {fvg_top:.2f})")
                                
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
                
                time.sleep(loop_sleep)
                
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
        if hasattr(self, 'news_engine') and self.news_engine:
            try:
                self.news_engine.stop()
            except Exception as e:
                self.logger.error(f"Error stopping news engine: {e}")
        shutdown_mt5()
        self.connected = False
        sentiment_analyzer.stop()
        self.logger.info("Engine stopped safely.")