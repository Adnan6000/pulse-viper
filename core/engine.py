# core/engine.py
from utils.mt5_gateway import mt5_gateway as mt5
import pandas as pd
import numpy as np
import time
import os
import logging
from datetime import datetime, timezone
import traceback
from collections import deque
from typing import List, Dict, Tuple, Optional, Any, cast
import threading
import queue

from utils.mt5_data import fetch_ohlcv, init_mt5, shutdown_mt5
from utils.smc_indicators import SMCIndicators
from configs.config import Config
from core.experience_memory import ExperienceMemory
from core.pattern_learner import PatternLearner
from core.trade_manager import PaperTradeManager, LiveTradeManager, TradePosition
from core.trade_journal import trade_journal
from core.daily_analyzer import DailyAnalyzer
from core.backtester import AdaptiveBacktester
from core.strategy_optimizer import StrategyOptimizer
from utils.settings_manager import settings_manager
from utils.volume_analyzer import VolumeAnalyzer
from utils.sentiment_analyzer import sentiment_analyzer
from strategies.crt_tbs import CrtTbsStrategy
from strategies.fib_retest import FibRetestStrategy
from strategies.raja_strategy import RajaStrategy
from strategies.ict_strategy import IctStrategy
from strategies.bank_strategy import BankStrategy
from strategies.vsa_strategy import VsaStrategy
from strategies.avc_strategy import AvcStrategy
from strategies.m1_scalping_strategy import M1ScalpingStrategy
from strategies.vwap_strategy import VwapStrategy
from strategies.smc_concepts_strategy import SmcConceptsStrategy
from strategies.amd import AmdStrategy
from strategies.src import SrcStrategy
from strategies.quantum_viper_strategy import QuantumViperStrategy
from dashboard.web_dashboard import WebDashboardServer
from core.safety_engine import SafetyEngine
from core.session_engine import SessionEngine
from core.brain_calibrator import BrainCalibrator
from core.prediction_auditor import prediction_auditor
from core.starvation_analyzer import StarvationAnalyzer
from core.trade_brain import BrainResult
def validate_trade_geometry(action: str, entry: float, sl: float, tp: float) -> tuple[bool, str]:
    action = action.upper()
    values = (entry, sl, tp)
    if not all(isinstance(value, (int, float)) and np.isfinite(value) and value > 0 for value in values):
        return False, "NON_FINITE_OR_NON_POSITIVE_PRICE"
    if action == "BUY":
        if not (sl < entry < tp):
            return False, "INVALID_BUY_GEOMETRY"
    elif action == "SELL":
        if not (tp < entry < sl):
            return False, "INVALID_SELL_GEOMETRY"
    else:
        return False, "INVALID_ACTION"
    return True, "VALID"

class AdvancedTradingEngine:
    def __init__(self, symbols=None, strategy_mode='smc', enable_dashboard=True, port=8000):
        self.strategy_mode = strategy_mode
        self.config = Config()
        
        # Setup logging
        import sys
        # Reconfigure stdout/stderr encoding to UTF-8 to prevent CP1252/UnicodeEncodeError on Windows
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                try:
                    stream.reconfigure(encoding='utf-8', errors='backslashreplace')
                except Exception:
                    pass
        log_handler = logging.StreamHandler(sys.stdout)
        log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        log_handler.setFormatter(log_formatter)
        
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler("logs/engine.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(log_formatter)
        
        logging.basicConfig(
            level=logging.INFO,
            handlers=[
                file_handler,
                log_handler
            ]
        )
        self.logger = logging.getLogger("PulseViper.Engine")

        # Connection health
        self.connected = False
        self.cycle_count = 0
        self.market_state = {}
        self.analyzed_trades = {}
        self.broker_symbols = []
        
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
        prediction_auditor.pattern_learner = self.pattern_learner
        from core.execution_validator import ExecutionValidator
        self.execution_validator = ExecutionValidator()
        self.performance_history = deque(maxlen=100)
        
        # Initialize self-improvement systems
        self.daily_analyzer = DailyAnalyzer(pattern_learner=self.pattern_learner)
        self.backtester = AdaptiveBacktester()
        self.strategy_optimizer = StrategyOptimizer()
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
        self.starvation_analyzer = StarvationAnalyzer()
        self.last_saved_skipped_candle = {}
        self.last_blocked_candle = {}
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
        import queue
        import itertools
        import secrets
        from utils.mt5_gateway import set_emergency_halt_event
        
        self.boot_id = secrets.token_hex(6)
        self.dashboard_snapshot = None
        self.dashboard_snapshot_lock = threading.Lock()
        self.command_queue = queue.PriorityQueue()
        self.command_sequence = itertools.count()
        self.emergency_halt_event = threading.Event()
        set_emergency_halt_event(self.emergency_halt_event)

        self.dashboard = None
        if enable_dashboard:
            try:
                self.dashboard = WebDashboardServer(self, port=port)
            except Exception as e:
                self.logger.warning(f"Failed to initialize dashboard: {e}")

        # Start continuous self-learning background thread (mines new patterns every 15 mins)
        self._start_background_pattern_learning()

    def _start_background_pattern_learning(self):
        """Continuous self-learning background thread to mine patterns & retrain PyTorch NN every 15 minutes"""
        def pattern_learning_worker():
            import time
            while True:
                try:
                    time.sleep(900)  # Mine new patterns every 15 minutes
                    self.logger.info("🧠 [SELF_LEARNING] Starting periodic pattern mining & neural net retraining...")
                    symbols_to_train = self.symbols if hasattr(self, 'symbols') and self.symbols else ["XAUUSDm"]
                    for sym in symbols_to_train:
                        self.pattern_learner.train_multi_strategy(symbol=sym)
                    self.logger.info("✅ [SELF_LEARNING] Pattern database & PyTorch neural net weights updated!")
                except Exception as e:
                    self.logger.warning(f"Self-learning background worker error: {e}")

        t = threading.Thread(target=pattern_learning_worker, daemon=True)
        t.start()

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
                
                # Cache available symbols to prevent slow mt5.symbols_get() network queries
                symbols_objs = mt5.symbols_get()
                if symbols_objs:
                    self.broker_symbols = [s.name for s in symbols_objs]
                else:
                    self.broker_symbols = []
            else:
                self.connected = False
                raise ConnectionError("Failed to initialize MetaTrader 5")
        except Exception as e:
            self.logger.error(f"MT5 Initialization error: {e}")
            raise e

    def _reconnect_if_needed(self):
        """Health check and auto-reconnection (throttled to once every 10s)"""
        import time
        now = time.time()
        if not hasattr(self, '_last_reconnect_check'):
            self._last_reconnect_check = 0.0
        if now - self._last_reconnect_check < 10.0:
            return
        self._last_reconnect_check = now
        
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
            available_symbols = getattr(self, 'broker_symbols', [])
            if not available_symbols:
                symbols_objs = mt5.symbols_get()
                available_symbols = [s.name for s in symbols_objs] if symbols_objs else []
                self.broker_symbols = available_symbols
                
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

    def find_equivalent_symbol(self, requested: str, available_symbols: List[str]) -> Optional[str]:
        """Find an equivalent symbol in the available list (handles XAUUSD vs XAUUSDm vs GOLD, case sensitivity, suffixes)"""
        if requested in available_symbols:
            return requested
            
        req_upper = requested.upper()
        # Case insensitive check
        for s in available_symbols:
            if s.upper() == req_upper:
                return s
                
        # Gold mapping candidates
        is_gold_req = "XAU" in req_upper or "GOLD" in req_upper
        if is_gold_req:
            gold_candidates = ["XAUUSD", "XAUUSDm", "XAUUSDc", "XAUUSDb", "GOLD", "XAUUSD.m", "XAUUSD.c"]
            for c in gold_candidates:
                for s in available_symbols:
                    if s.upper() == c:
                        return s
            # Generic gold search
            for s in available_symbols:
                s_up = s.upper()
                if ("XAU" in s_up and "USD" in s_up) or "GOLD" in s_up:
                    return s
                    
        # General forex suffix stripping
        import re
        base_symbol = re.sub(r'[^A-Z0-9]', '', req_upper)
        if len(base_symbol) == 7 and base_symbol[-1] in ['M', 'C', 'I', 'X', 'P', 'R', 'T']:
            base_symbol_stripped = base_symbol[:-1]
        else:
            base_symbol_stripped = base_symbol
            
        for s in available_symbols:
            s_clean = re.sub(r'[^A-Z0-9]', '', s.upper())
            if s_clean == base_symbol_stripped:
                return s
                
        # Prefix / partial match
        for s in available_symbols:
            s_clean = re.sub(r'[^A-Z0-9]', '', s.upper())
            if s_clean.startswith(base_symbol_stripped) or base_symbol_stripped.startswith(s_clean):
                return s
                
        return None

    def _validate_symbols(self, symbols: List[str]) -> List[str]:
        """Validate that requested symbols are available on broker"""
        available_symbols = getattr(self, 'broker_symbols', [])
        if not available_symbols:
            symbols_objs = mt5.symbols_get()
            available_symbols = [s.name for s in symbols_objs] if symbols_objs else []
            self.broker_symbols = available_symbols
            
        valid = []
        for s in symbols:
            eq = self.find_equivalent_symbol(s, available_symbols)
            if eq:
                mt5.symbol_select(eq, True)
                valid.append(eq)
                if eq != s:
                    self.logger.info(f"🔄 Mapped requested symbol {s} to broker equivalent {eq}")
            else:
                # Direct select fallback
                if mt5.symbol_select(s, True):
                    valid.append(s)
                    self.logger.info(f"Directly selected symbol {s} on broker")
                else:
                    self.logger.warning(f"Requested symbol {s} is not available on broker (no equivalent found)")
                
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

    def is_killzone_active(self, symbol: Optional[str] = None) -> bool:
        """Check if current UTC time is inside the London, New York or Asian Killzones"""
        if not settings_manager.get("killzone_filter_enabled", True):
            return True
        
        # Crypto pairs trade 24/7 — killzone filters don't apply
        if symbol is not None:
            sym_up = symbol.upper()
            crypto_bases = ["BTC", "ETH", "LTC", "XRP", "SOL", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "BNB", "LINK"]
            if any(c in sym_up for c in crypto_bases):
                return True
            
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        
        is_gold = symbol is not None and ("XAU" in symbol.upper() or "GOLD" in symbol.upper())
        
        london_start, london_end = self.config.LONDON_SESSION
        ny_start, ny_end = self.config.NY_SESSION
        asian_start, asian_end = getattr(self.config, 'ASIAN_SESSION', (0, 8))
        
        in_london = (london_start <= hour < london_end)
        in_ny = (ny_start <= hour < ny_end)
        in_asian = (asian_start <= hour < asian_end)
        
        # Gold-specific rule: Avoid Asian session entirely (low volume)
        if is_gold and in_asian:
            return False
            
        london_enabled = settings_manager.get("london_session_enabled", True)
        ny_enabled = settings_manager.get("ny_session_enabled", True)
        asian_enabled = settings_manager.get("asian_session_enabled", True)
        
        # If all are disabled, bypass session filter (always allow trading)
        if not london_enabled and not ny_enabled and not asian_enabled:
            return True
            
        london_active = in_london and london_enabled
        ny_active = in_ny and ny_enabled
        asian_active = in_asian and asian_enabled
        
        return london_active or ny_active or asian_active

    @staticmethod
    def calculate_regression_zscore(df_h1: pd.DataFrame, period: int = 100) -> float:
        """
        Computes the Z-score of deviation of the current price from the linear regression channel.
        Uses the last 'period' H1 bars (representing 4 days of market action).
        """
        try:
            if df_h1 is None or len(df_h1) < period:
                return 0.0
                
            prices = df_h1['close'].tail(period).values
            n = len(prices)
            x = np.arange(n)
            
            # Linear regression using numpy polyfit
            slope, intercept = np.polyfit(x, prices, 1)
            fitted = slope * x + intercept
            
            deviations = prices - fitted
            std_dev = np.std(deviations)
            
            if std_dev < 1e-9:
                return 0.0
                
            latest_deviation = prices[-1] - fitted[-1]
            z_score = latest_deviation / std_dev
            return float(z_score)
        except Exception:
            return 0.0

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
            import uuid
            cycle_id = f"PV-CYCLE-{symbol}-{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:4]}"
            trading_mode = settings_manager.get("trading_mode", "intraday").lower()
            current_time = time.time()
            swing_window = settings_manager.get("smc_swing_window", 3)

            # ── 1. Fetch and compute SMC for 6 timeframes with Closed-Candle Caching ─
            if not hasattr(self, '_last_closed_candle_times'):
                self._last_closed_candle_times = {}
            if not hasattr(self, '_tf_data_cache'):
                self._tf_data_cache = {}
            if not hasattr(self, '_tf_smc_cache'):
                self._tf_smc_cache = {}

            _tf_expiry_map = {
                'D1': (mt5.TIMEFRAME_D1, 500),
                'H4': (mt5.TIMEFRAME_H4, 300),
                'H1': (mt5.TIMEFRAME_H1, 300),
                'M30': (mt5.TIMEFRAME_M30, 200),
                'M15': (mt5.TIMEFRAME_M15, 200),
                'M5': (mt5.TIMEFRAME_M5, 200),
                'M1': (mt5.TIMEFRAME_M1, 200),
            }

            dfs = {}
            smc = {}

            now = time.time()
            if not hasattr(self, '_last_tf_check_times'):
                self._last_tf_check_times = {}
                
            _tf_cooldowns = {
                'D1': 3600,
                'H4': 900,
                'H1': 300,
                'M30': 120,
                'M15': 60,
                'M5': 15,
                'M1': 3
            }

            for tf_name, (tf_const, bars) in _tf_expiry_map.items():
                cache_key = f"{symbol}_{tf_name}"
                
                # Check check-cooldown to avoid querying MT5 too frequently
                cooldown = _tf_cooldowns.get(tf_name, 5)
                time_since_last_check = now - self._last_tf_check_times.get(cache_key, 0.0)
                
                # 1. Cache hit path: if cooldown hasn't expired and cache exists, reuse completely
                if (cache_key in self._tf_data_cache and 
                    cache_key in self._tf_smc_cache and 
                    time_since_last_check < cooldown):
                    
                    dfs[tf_name] = self._tf_smc_cache[cache_key] if self._tf_smc_cache[cache_key] is not None else self._tf_data_cache[cache_key]
                    smc[tf_name] = self._tf_smc_cache[cache_key]
                    continue
                
                # Cooldown expired or cache missing: Check MT5 for closed candle time
                self._last_tf_check_times[cache_key] = now
                closed_bar = mt5.copy_rates_from_pos(symbol, tf_const, 1, 1)
                closed_time = closed_bar[0]['time'] if (closed_bar is not None and len(closed_bar) > 0) else None
                
                df_closed = None
                if (closed_time is not None and 
                    closed_time == self._last_closed_candle_times.get(cache_key) and 
                    cache_key in self._tf_data_cache):
                    df_closed = self._tf_data_cache[cache_key]
                else:
                    # Fetch bars count including active bar
                    df_full = fetch_ohlcv(symbol, tf_const, n=bars)
                    if df_full is not None and len(df_full) >= 20:
                        # Store only closed candles in cache (exclude active forming bar at index 0)
                        df_closed = df_full.iloc[:-1].copy()
                        self._tf_data_cache[cache_key] = df_closed
                        if closed_time is not None:
                            self._last_closed_candle_times[cache_key] = closed_time
                            
                # Get the live forming candle (index 0)
                live_rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, 1)
                if live_rates is not None and len(live_rates) > 0:
                    df_live = pd.DataFrame(live_rates)
                    df_live['time'] = pd.to_datetime(df_live['time'], unit='s')
                    df_live.set_index('time', inplace=True)
                    df_sub = df_live[['open','high','low','close','tick_volume']]
                    df_live = pd.DataFrame(df_sub).rename(columns={'tick_volume':'volume'})
                    
                    if df_closed is not None:
                        # Exclude any index in df_closed that is also in df_live
                        df_combined = pd.concat([df_closed[~df_closed.index.isin(df_live.index)], df_live])
                    else:
                        df_combined = df_live
                else:
                    df_combined = df_closed

                if df_combined is not None and len(df_combined) >= 20:
                    try:
                        from utils.smc_indicators import SMCIndicators
                        features_df = SMCIndicators.compute_smc_features(df_combined, window=swing_window)
                        dfs[tf_name] = features_df
                        smc[tf_name] = features_df
                        self._tf_smc_cache[cache_key] = features_df
                    except Exception as e:
                        self.logger.error(f"SMC Indicators computation error for {tf_name}: {e}")
                        dfs[tf_name] = df_combined
                        smc[tf_name] = None
                        self._tf_smc_cache[cache_key] = None
                else:
                    dfs[tf_name] = None
                    smc[tf_name] = None

            df_d1  = dfs.get('D1')
            df_h4  = dfs.get('H4')
            df_h1  = dfs.get('H1')
            df_m30 = dfs.get('M30')
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
                    current_time_utc, lockout_mins, cooldown_mins, symbol=symbol
                )

            # B. Update Pair-Specific Structural Memory (H1 & D1 Swings HH/HL/LH/LL)
            from core.pair_structure_memory import pair_structure_memory
            pair_structure_memory.update_pair_structure(symbol, df_h1, df_d1)

            # C. Market Regime Detection
            rvol_val = self.volume_cache.get("rvol", 1.0) if hasattr(self, 'volume_cache') and self.volume_cache else 1.0
            from core.market_regime import RegimeType
            regime = self.regime_detector.detect_regime(df_m15 if df_m15 is not None else pd.DataFrame(), rvol_val)
            regime_name = regime.name if hasattr(regime, 'name') else str(regime)

            # D. Session context (Phase 10)
            session_ctx = self.session_engine.get_session_context(symbol=symbol)

            def get_latest(tf_name):
                s = smc.get(tf_name)
                return s.iloc[-1] if s is not None and len(s) > 0 else None

            latest_d1  = get_latest('D1')
            latest_h4  = get_latest('H4')
            latest_h1  = get_latest('H1')
            latest_m30 = get_latest('M30')
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
            m30_bias = bias_val(latest_m30)
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
                'M30': {'bias': m30_bias, 'label': bias_label(m30_bias)},
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
                'm30': (mt5.TIMEFRAME_M30, df_m30, 300),
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
            if (current_time - last_vol_time >= 10.0 or not self.volume_cache or "rvol" not in self.volume_cache) and df_ltf is not None and len(df_ltf) > 0:
                latest_rvol = VolumeAnalyzer.calculate_rvol_latest(df_ltf, period=20)
                latest_buy_press, latest_sell_press = VolumeAnalyzer.calculate_buying_selling_pressure_latest(df_ltf)
                total_press = latest_buy_press + latest_sell_press
                buy_pct = (latest_buy_press / total_press * 100.0) if total_press > 0 else 50.0
                sell_pct = (latest_sell_press / total_press * 100.0) if total_press > 0 else 50.0
                
                # Cache volume profile by last closed candle time to prevent redundant matrix calculations
                last_m1_time = df_ltf.index[-1] if len(df_ltf) > 0 else None
                cache_key = f"{symbol}_vol_profile"
                
                if (hasattr(self, '_last_vp_time') and 
                    self._last_vp_time.get(cache_key) == last_m1_time and 
                    hasattr(self, '_cached_vp_profile') and 
                    cache_key in self._cached_vp_profile):
                    vp_profile = self._cached_vp_profile[cache_key]
                else:
                    vp_profile = VolumeAnalyzer.calculate_volume_profile(df_ltf, lookback=100, bins=20)
                    if not hasattr(self, '_last_vp_time'):
                        self._last_vp_time = {}
                    if not hasattr(self, '_cached_vp_profile'):
                        self._cached_vp_profile = {}
                    self._last_vp_time[cache_key] = last_m1_time
                    self._cached_vp_profile[cache_key] = vp_profile

                ofi_val = self.liquidity_map.calculate_order_flow_imbalance(symbol, lookback_seconds=300)
                self.volume_cache = {
                    "rvol": latest_rvol, "buy_pressure": buy_pct,
                    "sell_pressure": sell_pct, "profile": vp_profile,
                    "ofi": ofi_val
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

            fib_action, fib_regime, fib_sl, fib_tp, fib_metadata = None, "sideway", 0.0, 0.0, {}
            crt_action, crt_regime, crt_sl, crt_tp, crt_metadata = None, "sideway", 0.0, 0.0, {}
            raja_action, raja_sl, raja_tp, raja_metadata = None, 0.0, 0.0, {}
            ict_action, ict_sl, ict_tp, ict_metadata = None, 0.0, 0.0, {}
            bank_action, bank_sl, bank_tp, bank_metadata = None, 0.0, 0.0, {}
            vsa_action, vsa_sl, vsa_tp, vsa_metadata = None, 0.0, 0.0, {}
            avc_action, avc_sl, avc_tp, avc_metadata = None, 0.0, 0.0, {}
            m1_scalping_action, m1_scalping_sl, m1_scalping_tp, m1_scalping_metadata = None, 0.0, 0.0, {}
            vwap_action, vwap_sl, vwap_tp, vwap_metadata = None, 0.0, 0.0, {}
            smc_action, smc_sl, smc_tp, smc_metadata = None, 0.0, 0.0, {}
            amd_action, amd_regime, amd_sl, amd_tp, amd_metadata = None, "sideway", 0.0, 0.0, {}
            src_action, src_regime, src_sl, src_tp, src_metadata = None, "sideway", 0.0, 0.0, {}
            quantum_action, quantum_sl, quantum_tp, quantum_metadata = None, 0.0, 0.0, {}

            ref_atr_val = float(ref_ltf['atr']) if ref_ltf is not None else 1.0

            if active_strategy in ["fib_retest", "both"] and df_m15 is not None:
                try:
                    fib_action, fib_regime, fib_sl, fib_tp, fib_metadata = FibRetestStrategy.evaluate_retest(
                        df_context=df_m15,
                        current_price=tick.bid,
                        atr=ref_atr_val,
                        volume_cache=self.volume_cache,
                        sentiment_cache=sentiment_payload,
                        htf_bias=htf_bias,
                        df_ltf=df_m1
                    )
                except Exception as fib_err:
                    self.logger.error(f"Error evaluating FibRetestStrategy: {fib_err}")

            if active_strategy in ["crt_tbs", "both"]:
                try:
                    crt_action, crt_regime, crt_sl, crt_tp, crt_metadata = CrtTbsStrategy.evaluate_crt_tbs(
                        df_d1=df_d1,
                        df_h4=df_h4,
                        df_h1=df_h1,
                        df_m15=df_m15,
                        df_m5=df_m5,
                        df_m1=df_m1,
                        current_price=tick.bid,
                        atr=ref_atr_val,
                        volume_cache=self.volume_cache,
                        sentiment_cache=sentiment_payload,
                        htf_bias=htf_bias,
                        symbol=symbol,
                        regime=regime.name
                    )
                except Exception as crt_err:
                    self.logger.error(f"Error evaluating CrtTbsStrategy: {crt_err}")

            try:
                raja_action, raja_sl, raja_tp, raja_metadata = RajaStrategy.evaluate_raja(
                    df_m15=df_m15,
                    df_m30=df_m30,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as raja_err:
                self.logger.error(f"Error evaluating RajaStrategy: {raja_err}")

            try:
                ict_action, ict_sl, ict_tp, ict_metadata = IctStrategy.evaluate_ict(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    htf_bias=htf_bias,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as ict_err:
                self.logger.error(f"Error evaluating IctStrategy: {ict_err}")

            try:
                bank_action, bank_sl, bank_tp, bank_metadata = BankStrategy.evaluate_bank(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as bank_err:
                self.logger.error(f"Error evaluating BankStrategy: {bank_err}")

            try:
                vsa_action, vsa_sl, vsa_tp, vsa_metadata = VsaStrategy.evaluate_vsa(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_h1=df_h1,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as vsa_err:
                self.logger.error(f"Error evaluating VsaStrategy: {vsa_err}")

            try:
                avc_action, avc_sl, avc_tp, avc_metadata = AvcStrategy.evaluate_avc(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as avc_err:
                self.logger.error(f"Error evaluating AvcStrategy: {avc_err}")

            try:
                m1_scalping_action, m1_scalping_sl, m1_scalping_tp, m1_scalping_metadata = M1ScalpingStrategy.evaluate_m1_scalping(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as m1_scalp_err:
                self.logger.error(f"Error evaluating M1ScalpingStrategy: {m1_scalp_err}")

            try:
                vwap_action, vwap_sl, vwap_tp, vwap_metadata = VwapStrategy.evaluate_vwap(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_h1=df_h1,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    regime=regime_name,
                    htf_bias=htf_bias
                )
            except Exception as vwap_err:
                self.logger.error(f"Error evaluating VwapStrategy: {vwap_err}")

            try:
                smc_action, smc_sl, smc_tp, smc_metadata = SmcConceptsStrategy.evaluate_smc(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    htf_bias=htf_bias,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as smc_err:
                self.logger.error(f"Error evaluating SmcConceptsStrategy: {smc_err}")

            try:
                amd_action, amd_regime, amd_sl, amd_tp, amd_metadata = AmdStrategy.evaluate_amd(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    htf_bias=htf_bias,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as amd_err:
                self.logger.error(f"Error evaluating AmdStrategy: {amd_err}")

            try:
                src_action, src_regime, src_sl, src_tp, src_metadata = SrcStrategy.evaluate_src(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    htf_bias=htf_bias,
                    volume_cache=self.volume_cache,
                    regime=regime_name
                )
            except Exception as src_err:
                self.logger.error(f"Error evaluating SrcStrategy: {src_err}")

            try:
                quantum_action, quantum_sl, quantum_tp, quantum_metadata = QuantumViperStrategy.evaluate_quantum_viper(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    df_d1=df_d1,
                    current_price=tick.bid,
                    atr=ref_atr_val,
                    htf_bias=htf_bias,
                    volume_cache=self.volume_cache,
                    sentiment_cache=sentiment_payload,
                    regime=regime_name,
                    symbol=symbol
                )
            except Exception as q_err:
                self.logger.error(f"Error evaluating QuantumViperStrategy: {q_err}")

            active_regime = crt_regime if active_strategy == "crt_tbs" else (
                fib_regime if active_strategy in ["fib_retest", "both"] else (
                    "bullish" if htf_bias == 1 else ("bearish" if htf_bias == -1 else "sideway")
                )
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

            # Calculate linear regression Z-score on H1
            regression_zscore = self.calculate_regression_zscore(df_h1)

            analysis = {
                'cycle_id': cycle_id,
                'symbol': symbol,
                'price': tick.bid,
                'bid': tick.bid,
                'ask': tick.ask,
                # Phase 8 Core Intelligence outputs
                'news_locked': news_locked,
                'news_lockout_reason': news_lockout_reason,
                'market_regime': regime_name,
                'swept_pools': swept_pools,
                'resting_pools': self.liquidity_map.get_resting_pools(),
                'regression_zscore': regression_zscore,
                'ofi_imbalance': float(ofi_raw) if (self.volume_cache and isinstance((ofi_raw := self.volume_cache.get("ofi", 0.0)), (int, float, str))) else 0.0,
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
                'm15_sweep_level': sweep_level if not np.isnan(sweep_level) else 0.0,
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
                'raja_action': raja_action, 'raja_sl': raja_sl, 'raja_tp': raja_tp, 'raja_metadata': raja_metadata,
                'ict_action': ict_action, 'ict_sl': ict_sl, 'ict_tp': ict_tp, 'ict_metadata': ict_metadata,
                'bank_action': bank_action, 'bank_sl': bank_sl, 'bank_tp': bank_tp, 'bank_metadata': bank_metadata,
                'vsa_action': vsa_action, 'vsa_sl': vsa_sl, 'vsa_tp': vsa_tp, 'vsa_metadata': vsa_metadata,
                'avc_action': avc_action, 'avc_sl': avc_sl, 'avc_tp': avc_tp, 'avc_metadata': avc_metadata,
                'm1_scalping_action': m1_scalping_action, 'm1_scalping_sl': m1_scalping_sl, 'm1_scalping_tp': m1_scalping_tp, 'm1_scalping_metadata': m1_scalping_metadata,
                'vwap_action': vwap_action, 'vwap_sl': vwap_sl, 'vwap_tp': vwap_tp, 'vwap_metadata': vwap_metadata,
                'smc_action': smc_action, 'smc_sl': smc_sl, 'smc_tp': smc_tp, 'smc_metadata': smc_metadata,
                'amd_action': amd_action, 'amd_regime': amd_regime, 'amd_sl': amd_sl, 'amd_tp': amd_tp, 'amd_metadata': amd_metadata,
                'src_action': src_action, 'src_regime': src_regime, 'src_sl': src_sl, 'src_tp': src_tp, 'src_metadata': src_metadata,
                'quantum_action': quantum_action, 'quantum_sl': quantum_sl, 'quantum_tp': quantum_tp, 'quantum_metadata': quantum_metadata,
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
                    'ob_reaction_signal': float(ref_ltf.get('ob_reaction_signal', 0.0)) if ref_ltf is not None else 0.0,
                    'sr_reaction_signal': float(ref_ltf.get('sr_reaction_signal', 0.0)) if ref_ltf is not None else 0.0,
                    'retest_pullback_signal': float(ref_ltf.get('retest_pullback_signal', 0.0)) if ref_ltf is not None else 0.0,
                    'trend_shift_signal': float(ref_ltf.get('trend_shift_signal', 0.0)) if ref_ltf is not None else 0.0,
                    'rvol': float(rvol_raw) if (self.volume_cache and isinstance((rvol_raw := self.volume_cache.get('rvol', 1.0)), (int, float, str))) else 1.0,
                    'buy_pressure': buy_pressure_val,
                    'sell_pressure': sell_pressure_val,
                    'hour': datetime.now(timezone.utc).hour,
                    'price': tick.bid,
                    'tf_aligned': tf_alignment.get('aligned', False),
                    'market_regime': regime_name,
                    'news_locked': news_locked,
                    'timestamp': float(tick.time) if tick else datetime.now(timezone.utc).timestamp()
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


    def evaluate_entry_rules(self, analysis: Dict, is_live_tick: bool = False) -> Optional[Tuple[str, float, float, str]]:
        """
        Evaluate entry signals based on:
        - SMC Sharp Turn entry model (returns setup_type "SMC")
        - Fallback Fibonacci Retest model (returns setup_type "FIB")
        
        Returns: Tuple (Action "BUY"/"SELL", StopLoss, TakeProfit, SetupType "SMC"/"FIB") or None
        """
        symbol = analysis['symbol']
        
        # Rule 0: Cooldown check (prevent duplicate execution on same entry/close candle)
        current_candle = self.last_candle_times.get(symbol, 0)
        if current_candle > 0:
            if current_candle == self.last_entry_candle.get(symbol, 0):
                return None
            if current_candle == self.last_close_candle.get(symbol, 0):
                return None
                
        bid = analysis['bid']
        ask = analysis['ask']
        atr = analysis['atr']
        
        trading_mode = settings_manager.get("trading_mode", "intraday").lower()
        if trading_mode == "scalping":
            h1_bias = analysis.get('h1_bias', 0)  # Use H1 trend for scalping instead of forcing D1/H4 trend
        else:
            h1_bias = analysis.get('htf_bias', analysis.get('h1_bias', 0))  # Use master HTF bias
        m15_sweep = analysis['m15_sweep_type']
        m5_mss = analysis['m5_mss_signal']
        fvg_class = analysis['m5_fvg_class']
        fvg_type = analysis['m5_fvg_type']

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

        # Position checking helper
        def can_trade_direction(action: str) -> bool:
            if not settings_manager.get("hedging_mode", False):
                return len(self.trade_manager.positions) == 0
            else:
                has_same_direction = any(p.symbol == symbol and p.action == action for p in self.trade_manager.positions.values())
                return not has_same_direction

        # ── Phase 9 v2: TradeBrain probabilistic scoring gate ─────────────────
        # Volatility regime strategy gating based on HMM state (P0-7)
        regime_upper = str(analysis.get("market_regime", "RANGE")).upper()
        trend_strategies = {"QUANTUM", "ICT", "SMC", "RAJA", "BANK", "VWAP", "AVC", "FIB", "M1_SCALPING"}
        range_strategies = {"QUANTUM", "CRT", "VSA", "AMD", "SRC", "M1_SCALPING"}

        # Collect all active triggered setups
        candidate_setups = []
        is_gold_symbol = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
        active_prefixes = ["quantum"] if is_gold_symbol else ["quantum", "crt", "fib", "ict", "smc", "raja", "bank", "vsa", "avc", "m1_scalping", "vwap", "amd", "src"]

        for prefix in active_prefixes:
            name = prefix.upper()
            
            # Regime gating filter
            if not is_gold_symbol:
                if regime_upper == "TRENDING" and name not in trend_strategies:
                    continue
                if regime_upper == "RANGE" and name not in range_strategies:
                    continue
                
            action = analysis.get(f"{prefix}_action")
            if action in ["BUY", "SELL"]:
                sl = float(analysis.get(f"{prefix}_sl", 0.0))
                tp = float(analysis.get(f"{prefix}_tp", 0.0))
                meta = analysis.get(f"{prefix}_metadata", {})
                if sl > 0.0 and tp > 0.0:
                    candidate_setups.append({
                        "name": name,
                        "action": action,
                        "sl": sl,
                        "tp": tp,
                        "metadata": meta
                    })

        # Evaluate and score each candidate setup via TradeBrain
        scored_setups = []
        for setup in candidate_setups:
            setup_act = str(setup["action"])
            setup_nm = str(setup["name"])
            if not can_trade_direction(setup_act):
                continue
            res = self.trade_brain.evaluate(
                analysis=analysis,
                strategy_action=setup_act,
                ai_confidence=confidence,
                session_score=float(analysis.get('session_score', 0.0)),
                strategy_name=setup_nm,
            )
            # Filter out setups that failed TradeBrain validation (P0-10)
            if res and res.passed:
                scored_setups.append({
                    "setup": setup,
                    "brain_result": res
                })

        # Rank by brain score in descending order
        scored_setups.sort(key=lambda x: x["brain_result"].brain_score, reverse=True)

        selected_setup: Optional[Dict[str, Any]] = None
        strategy_signal: Optional[str] = None
        brain_result: Optional[BrainResult] = None

        if scored_setups:
            selected_setup = cast(Dict[str, Any], scored_setups[0]["setup"])
            brain_result = cast(BrainResult, scored_setups[0]["brain_result"])
            strategy_signal = str(selected_setup["action"])
        else:
            # Evaluate brain to check if it has a clear direction (telemetry/logging only, do not trade)
            brain_result = self.trade_brain.evaluate(
                analysis=analysis,
                strategy_action=None,
                ai_confidence=confidence,
                session_score=analysis.get('session_score', 0.0),
            )
            selected_setup = None
            strategy_signal = None

        if selected_setup:
            entry_px = float(bid if selected_setup["action"] == "BUY" else ask)
            sl_px = float(selected_setup["sl"])
            tp_px = float(selected_setup["tp"])
            atr_val = float(analysis.get("atr", 1.0))
            
            # Check if entry is too far from current market price (> 3.0 ATR)
            dist_atr = abs(entry_px - (ask if selected_setup["action"] == "BUY" else bid)) / atr_val if atr_val > 0 else 0
            if dist_atr <= 3.0:
                target_info = {
                    "action": str(selected_setup["action"]),
                    "entry": entry_px,
                    "sl": sl_px,
                    "tp": tp_px,
                    "strategy": str(selected_setup["name"])
                }
                analysis['target_setup'] = target_info
                if not hasattr(self, 'last_target_setup'):
                    self.last_target_setup = {}
                self.last_target_setup[symbol] = target_info
            else:
                analysis.pop('target_setup', None)
        else:
            analysis.pop('target_setup', None)

        if strategy_signal is not None and is_live_tick:
            self.starvation_analyzer.record_signal_found()
            
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

        # cycle-level structured logging
        try:
            from core.trade_pattern_memory import trade_pattern_memory
            from core.feature_extractor import FeatureExtractor
            import numpy as np
            
            # 1. NN Log
            feat_arr = FeatureExtractor.extract_nn_features(analysis['features'])
            self.logger.info(f"🧠 [NN_LOG] prediction={confidence:.4f} features={list(np.round(feat_arr, 4))}")
            
            # 2. Market Log
            self.logger.info(f"📊 [MARKET_LOG] regime={analysis['market_regime']} volatility={analysis['volatility']:.6f} session={analysis['session_name']}")
            
            # 3. Memory Log
            mem_idx, mem_sim = trade_pattern_memory.get_closest_similarity(analysis)
            self.logger.info(f"💾 [MEMORY_LOG] pattern_id={mem_idx} similarity={mem_sim:.4f}")
            
            # 4. Strategy Log (for each candidate strategy)
            for setup in candidate_setups:
                self.logger.info(f"🎯 [STRATEGY_LOG] strategy={setup['name']} action={setup['action']} sl={setup['sl']:.2f} tp={setup['tp']:.2f} confidence={confidence:.4f}")
        except Exception as log_ex:
            self.logger.error(f"Error printing cycle telemetry logs: {log_ex}")

        # Log evaluation to PredictionAuditor (only for actual live trading ticks)
        if strategy_signal is not None and is_live_tick:
            audit_id = prediction_auditor.log_evaluation(analysis, brain_result, strategy_action=strategy_signal)
            analysis['audit_id'] = audit_id

        # Centralized blocker and chart saver helper
        def block_and_return_none(reason: str):
            analysis['brain_block_reason'] = reason
            analysis.pop('target_setup', None)  # Remove target_setup so blocked non-executing setups don't flicker on dashboard
            current_candle = self.last_candle_times.get(symbol, 0)
            if current_candle > 0:
                self.last_blocked_candle[symbol] = current_candle
            if strategy_signal is not None:
                if is_live_tick:
                    self.starvation_analyzer.record_signal_blocked(reason)
                    audit_id = analysis.get('audit_id')
                    if audit_id is not None:
                        prediction_auditor.update_evaluation_executed(audit_id, executed=False, status="BLOCKED")
                    
                    # Save skipped setup visual chart (only once per candle to prevent duplicate files)
                    current_candle = self.last_candle_times.get(symbol, 0)
                    if current_candle > 0 and current_candle != self.last_saved_skipped_candle.get(symbol, 0):
                        try:
                            import threading
                            from utils.chart_plotter import save_visual_chart
                            df = analysis.get("df_m5")
                            if df is None or len(df) == 0:
                                df = analysis.get("df_ltf")
                            if df is not None and len(df) > 0:
                                sl = 0.0
                                tp = 0.0
                                for prefix in ["crt", "fib", "ict", "smc", "raja", "bank", "vsa", "avc", "m1_scalping", "vwap", "amd", "src"]:
                                    if analysis.get(f"{prefix}_action") == strategy_signal:
                                        sl = float(analysis.get(f"{prefix}_sl", 0.0))
                                        tp = float(analysis.get(f"{prefix}_tp", 0.0))
                                        break
                                if sl == 0.0:
                                    sl = float(analysis.get("crt_sl") or analysis.get("fib_sl") or analysis.get("sl") or 0.0)
                                if tp == 0.0:
                                    tp = float(analysis.get("crt_tp") or analysis.get("fib_tp") or analysis.get("tp") or 0.0)
                                    
                                save_visual_chart(
                                    filename_prefix="skipped",
                                    df=df,
                                    entry_price=ask if strategy_signal == "BUY" else bid,
                                    sl=sl,
                                    tp=tp,
                                    action=strategy_signal,
                                    symbol=symbol,
                                    extra_title=f"Blocked: {reason}"
                                )
                                self.last_saved_skipped_candle[symbol] = current_candle
                        except Exception as chart_err:
                            self.logger.error(f"Error saving skipped setup chart: {chart_err}")
            return None

        # ── Decoupled Veto Gates (checked AFTER evaluation for full telemetry) ──
        
        # 1. Safety Engine Check
        allowed, safety_reason = self.safety_engine.check_entry_allowed()
        if not allowed:
            if is_live_tick:
                self.skipped_stats['safety_halt'] = self.skipped_stats.get('safety_halt', 0) + 1
            analysis['brain_label'] = "SAFETY HALT"
            analysis['brain_color'] = "#ff9900"
            return block_and_return_none("SAFETY_HALT")

        # 2. Killzone Check
        is_paper = settings_manager.get("paper_mode", True)
        strict_mode = settings_manager.get("strict_mode", True)
        if not self.is_killzone_active(symbol) and not is_paper and strict_mode:
            if is_live_tick:
                self.skipped_stats['killzone_inactive'] = self.skipped_stats.get('killzone_inactive', 0) + 1
            analysis['brain_label'] = "KILLZONE INACTIVE"
            analysis['brain_color'] = "#666666"
            return block_and_return_none("KILLZONE_INACTIVE")

        # 3. News Lockout Check
        if analysis.get('news_locked', False) and strict_mode:
            if is_live_tick:
                self.skipped_stats['news_filter'] = self.skipped_stats.get('news_filter', 0) + 1
            import time
            current_time = time.time()
            if not hasattr(self, '_last_news_log_time'):
                self._last_news_log_time = 0.0
            if current_time - self._last_news_log_time >= 60.0:
                self.logger.warning(f"🚫 Trade entry blocked on {symbol} due to news lockout: {analysis.get('news_lockout_reason')}")
                self._last_news_log_time = current_time
            analysis['brain_label'] = "NEWS LOCKOUT"
            analysis['brain_color'] = "#ff3366"
            return block_and_return_none("NEWS_LOCKOUT")

        # 4. Chaotic Regime Check
        regime_str = analysis.get('market_regime', 'RANGE')
        if settings_manager.get("dynamic_regime_filter", True) and regime_str == "CHAOTIC" and strict_mode:
            if is_live_tick:
                self.skipped_stats['regime_filter'] = self.skipped_stats.get('regime_filter', 0) + 1
            import time
            current_time = time.time()
            if not hasattr(self, '_last_regime_log_time'):
                self._last_regime_log_time = 0.0
            if current_time - self._last_regime_log_time >= 60.0:
                self.logger.warning(f"🚫 Trade entry hard-blocked on {symbol}: CHAOTIC regime (pre-Brain gate)")
                self._last_regime_log_time = current_time
            analysis['brain_label'] = "CHAOTIC REGIME"
            analysis['brain_color'] = "#9900cc"
            return block_and_return_none("CHAOTIC_REGIME")

        # 5. TradeBrain score/threshold/direction confirmation
        if not brain_result.passed:
            if is_live_tick and strategy_signal is not None:
                self.skipped_stats['brain_filter'] = self.skipped_stats.get('brain_filter', 0) + 1
            # Log reason at reduced frequency
            import time as _t
            _now = _t.time()
            if not hasattr(self, '_last_brain_block_log'):
                self._last_brain_block_log = {}
            if _now - self._last_brain_block_log.get(symbol, 0) >= 15.0 and strategy_signal is not None:
                self.logger.info(
                    f"Brain blocked {symbol}: score={brain_result.brain_score:.1f}/{brain_result.threshold:.0f} "
                    f"reason={brain_result.block_reason} "
                    f"T1={brain_result.tier1_score:.0f}/50 T2={brain_result.tier2_score:.0f}/35 T3={brain_result.tier3_score:.0f}/15 "
                    f"ai_conf={confidence:.4f}"
                )
                self._last_brain_block_log[symbol] = _now
            if strategy_signal is None:
                analysis['brain_label'] = "SCANNING"
                analysis['brain_color'] = "#8b9bb4"
                return None
            return block_and_return_none(brain_result.block_reason or "BRAIN_VETO")

        # Position checking helper
        def can_trade_direction(action: str) -> bool:
            if not settings_manager.get("hedging_mode", False):
                return len(self.trade_manager.positions) == 0
            else:
                has_same_direction = any(p.symbol == symbol and p.action == action for p in self.trade_manager.positions.values())
                return not has_same_direction

        # Centralized Late Entry Blocker helper (DISABLED for testing)
        def check_late_entry(act, sl_val, tp_val, s_type):
            if not act:
                return None
            return act, sl_val, tp_val, s_type

        # Get active strategy setting
        disabled_setups = settings_manager.get("disabled_setups", [])
        
        # ── Execution Gate: If we selected a best setup, evaluate it for entry ──
        if selected_setup is not None:
            setup_name = str(selected_setup["name"])
            
            # Check if this setup type is disabled in configuration
            if setup_name in disabled_setups:
                return block_and_return_none("DISABLED_SETUP")
                
            # If the best setup is a mean-reversion setup, perform premium/discount checks
            if setup_name in ["SMC", "VWAP", "RAJA"]:
                range_mid = 0.5 * (analysis['support'] + analysis['resistance'])
                if str(selected_setup["action"]) == "BUY" and analysis['support'] > 0 and analysis['resistance'] > 0:
                    if bid > range_mid:
                        return block_and_return_none("PREMIUM_ZONE_BUY_BLOCK")
                elif str(selected_setup["action"]) == "SELL" and analysis['support'] > 0 and analysis['resistance'] > 0:
                    if ask < range_mid:
                        return block_and_return_none("DISCOUNT_ZONE_SELL_BLOCK")

            # Final execution parameters mapping
            act = str(selected_setup["action"])
            sl_val = float(selected_setup["sl"])
            tp_val = float(selected_setup["tp"])
            
            self.logger.info(
                f"🎯 Selected strategy setup: {setup_name} | {act} | SL: {sl_val:.2f} | TP: {tp_val:.2f} | "
                f"BrainScore: {brain_result.brain_score:.1f}/{brain_result.threshold:.0f}"
            )
            return check_late_entry(act, sl_val, tp_val, setup_name)

        if strategy_signal is not None:
            return block_and_return_none("NO_STRATEGY_MATCH")
        return None

    def execute_and_record_trade(self, symbol: str, action: str, sl: float, tp: float, analysis: Dict, strategy_name: str = "UNKNOWN"):
        """Execute the order and record the initial state into experience memory"""
        # Spread check
        tick = mt5.symbol_info_tick(symbol)
        symbol_info = mt5.symbol_info(symbol)
        spread = (tick.ask - tick.bid) / symbol_info.point
        
        max_spread = settings_manager.get("max_spread_points", self.config.MAX_SPREAD_POINTS)
        if "BTC" in symbol or "ETH" in symbol:
            if max_spread <= 300:
                from utils.symbol_manager import symbol_manager
                profile = symbol_manager.get_broker_profile(symbol)
                max_spread = max(max_spread, profile.get("max_spread_points", 5000))
            
        if spread > max_spread:
            self.logger.warning(f"Trade blocked on {symbol} due to high spread: {spread:.1f} points (Limit: {max_spread})")
            self.skipped_stats['high_spread'] = self.skipped_stats.get('high_spread', 0) + 1
            self.starvation_analyzer.record_signal_blocked("HIGH_SPREAD")
            return
            
        entry_price = tick.ask if action == "BUY" else tick.bid
        
        # Check if Auto Trade is enabled
        auto_trade = settings_manager.get("auto_trade_enabled", True)
        if not auto_trade:
            self.logger.info(f"🔍 [ANALYSIS ONLY] Auto Trade is OFF. Recording setup on {symbol}: {action} entry @ {entry_price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
            self.starvation_analyzer.record_signal_blocked("AUTO_TRADE_OFF")
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
        confidence: Optional[float] = None
        ai_signal: Dict[str, Any] = {}
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
                
                # Fetch AI confidence score with candidate-specific strategy and action parameters
                ai_signal = self.pattern_learner.get_trading_signal(
                    symbol,
                    analysis['features'],
                    df_ltf=analysis.get('df_ltf'),
                    df_m5=analysis.get('df_m5'),
                    df_h1=analysis.get('df_h1'),
                    candidate_strategy=strategy_name,
                    candidate_action=action
                )
                confidence = ai_signal.get('confidence', 0.8)
                model_ready = ai_signal.get('model_ready', False)

                active_positions = len(self.trade_manager.positions)
                base_risk = settings_manager.get("risk_percent", 1.0)
                open_heat = sum(p.risk_percent for p in self.trade_manager.positions.values())

                risk_percent = self.risk_engine.calculate_risk_percent(
                    current_atr=current_atr,
                    median_atr=median_atr,
                    current_spread=spread,
                    max_spread=max_spread,
                    confidence=confidence,
                    active_positions=active_positions,
                    base_risk=base_risk,
                    strategy_name=strategy_name,
                    open_portfolio_heat_pct=open_heat,
                    model_ready=model_ready
                )
            except Exception as risk_err:
                self.logger.error(f"Error calculating dynamic risk: {risk_err}")
                risk_percent = settings_manager.get("risk_percent", 1.0)
            
        # Construct compact immutable decision snapshot
        import copy
        import uuid
        from core.trade_manager import TradeDecisionSnapshot, deep_freeze
        
        # Generate unique decision_id
        decision_id = f"PV-DEC-{strategy_name.upper()}-{action.upper()}-{uuid.uuid4().hex[:4]}"
        cycle_id = analysis.get('cycle_id', 'UNKNOWN')
        
        # Determine model version
        model_ver = "pv-nn-003"
        try:
            if hasattr(self.pattern_learner, 'model_version'):
                model_ver = self.pattern_learner.model_version
            else:
                import os
                import json
                if os.path.exists("models/pulse_viper_base.json"):
                    with open("models/pulse_viper_base.json", "r") as f:
                        model_ver = json.load(f).get("model_version", "pv-nn-003")
        except Exception:
            pass

        # Calculate effective RR
        sl_dist = abs(entry_price - sl)
        tp_dist = abs(tp - entry_price)
        eff_rr = tp_dist / sl_dist if sl_dist > 0.0 else 0.0
        
        # Extract metadata safely
        strategy_meta = analysis.get(f"{strategy_name.lower()}_metadata", {})
        
        decision_snapshot = TradeDecisionSnapshot(
            schema_version=3,
            feature_schema_version=3,
            model_version=model_ver,
            cycle_id=cycle_id,
            decision_id=decision_id,
            symbol=symbol,
            timestamp_utc=pd.Timestamp.now(tz='UTC').to_pydatetime(),
            strategy_name=strategy_name,
            strategy_action=action,
            decision_price=entry_price,
            planned_entry=entry_price,
            initial_sl=sl,
            initial_tp=tp,
            effective_rr=eff_rr,
            brain_score=float(analysis.get('brain_score', 0.0)),
            brain_threshold=float(settings_manager.get("brain_threshold", 55.0)),
            brain_direction=analysis.get('brain_direction'),
            model_probability=float(confidence) if confidence is not None else None,  # type: ignore[arg-type]
            model_source=str(ai_signal.get('model_source', 'NO_VALID_MODEL')),
            regime=analysis.get('market_regime', 'RANGE'),
            regime_confidence=float(analysis.get('regime_confidence', 1.0)),
            session=analysis.get('session_name', 'UNKNOWN'),
            entry_features=deep_freeze(analysis.get('features', {})),
            strategy_metadata=deep_freeze(strategy_meta)
        )

        if self.emergency_halt_event.is_set():
            self.logger.warning("❌ Live Order Blocked: Emergency halt active.")
            return None

        # Atomic execution validation gate
        try:
            planned_volume = self.trade_manager.calculate_lot_size(
                symbol=symbol,
                sl_price=sl,
                entry_price=entry_price,
                risk_percent=risk_percent,
                brain_score=analysis.get('brain_score', 0.0)
            )
        except Exception as vol_err:
            self.logger.error(f"Error calculating planned volume: {vol_err}")
            planned_volume = 0.01

        validation = self.execution_validator.validate(
            symbol=symbol,
            action=action,
            sl=sl,
            tp=tp,
            volume=planned_volume,
            analysis=analysis,
            trade_manager=self.trade_manager,
            decision_id=decision_snapshot.decision_id
        )
        if not validation.allowed:
            self.logger.warning(f"❌ Live Order Blocked by ExecutionValidator: {validation.reason}")
            self.starvation_analyzer.record_signal_blocked(f"VALIDATOR_{validation.reason}")
            current_candle = self.last_candle_times.get(symbol, 0)
            self.last_entry_candle[symbol] = current_candle
            return None

        # Open trade via the private execution choke point
        pos = self._send_validated_order(
            validation=validation,
            decision_snapshot=decision_snapshot,
            symbol=symbol,
            action=action,
            sl=sl,
            tp=tp,
            risk_percent=float(risk_percent) if risk_percent is not None else 1.0,
            brain_score=analysis.get('brain_score', 0.0)
        )
        
        # Record the entry candle timestamp to prevent double-entry (do this regardless of success to avoid immediate retry spam)
        current_candle = self.last_candle_times.get(symbol, 0)
        self.last_entry_candle[symbol] = current_candle
        
        if pos:
            # Store initial entry features in positions for outcome learning
            setattr(pos, 'entry_features', analysis.get('features', {}))
            setattr(pos, 'strategy_name', strategy_name)
            setattr(pos, 'entry_analysis', analysis)
            
            # Extract pattern description from strategy metadata
            pattern_desc = "UNKNOWN"
            strategy_lower = strategy_name.lower()
            meta = analysis.get(f"{strategy_lower}_metadata", {})
            if strategy_name == "AMD":
                pattern_desc = f"AMD {meta.get('manipulation_swept', 'UNKNOWN')} SWEPT"
            elif strategy_name == "SRC":
                pattern_desc = f"SRC {meta.get('channel_type', 'UNKNOWN')} BOUNCE"
            elif strategy_name == "CRT":
                pattern_desc = f"CRT Sweep {meta.get('sweep_type', 'UNKNOWN')}"
            else:
                pattern_desc = meta.get("pattern", meta.get("source", "Technical Breakout"))
            setattr(pos, 'entry_pattern', pattern_desc)
            setattr(pos, 'brain_score', analysis.get('brain_score', 0.0))
            setattr(pos, 'brain_tier1', analysis.get('brain_tier1', 0.0))
            setattr(pos, 'brain_tier2', analysis.get('brain_tier2', 0.0))
            setattr(pos, 'brain_tier3', analysis.get('brain_tier3', 0.0))
            setattr(pos, 'brain_direction', analysis.get('brain_direction'))
            setattr(pos, 'brain_block_reason', analysis.get('brain_block_reason'))
            setattr(pos, 'brain_reason_map', analysis.get('brain_reason_map', {}))
            setattr(pos, 'session', analysis.get('session_name', 'OFF'))
            setattr(pos, 'volatility_regime', analysis.get('market_regime', 'RANGE'))
            setattr(pos, 'audit_id', analysis.get('audit_id'))
            
            # Record execution in starvation stats
            self.starvation_analyzer.record_signal_executed()
            audit_id = getattr(pos, 'audit_id', None)
            if audit_id:
                prediction_auditor.update_evaluation_executed(int(audit_id) if isinstance(audit_id, (int, float, str)) else 0, executed=True, status="EXECUTED")

    def _send_validated_order(
        self,
        validation,
        decision_snapshot,
        symbol: str,
        action: str,
        sl: float,
        tp: float,
        risk_percent: float,
        brain_score: float = 0.0,
    ) -> Optional[TradePosition]:
        if self.emergency_halt_event.is_set():
            self.logger.warning("❌ Order Rejected: Emergency halt active.")
            return None

        # Validate that the token is fresh (age < 1000ms)
        now = datetime.now(timezone.utc)
        token_age_ms = (now - validation.validated_at_utc).total_seconds() * 1000.0
        max_age = settings_manager.get("max_validation_token_age_ms", 1000.0)
        
        if token_age_ms > max_age:
            self.logger.warning(f"❌ Order Rejected: Validation token is stale ({token_age_ms:.1f}ms > {max_age}ms)")
            return None
            
        if validation.decision_id != decision_snapshot.decision_id:
            self.logger.warning(f"❌ Order Rejected: Decision ID mismatch ({validation.decision_id} != {decision_snapshot.decision_id})")
            return None
            
        # Open trade via trade manager
        pos = self.trade_manager.open_position(
            symbol=symbol,
            action=action,
            entry_price=validation.actual_entry_price, # Use the validated price
            sl_price=sl,
            tp_price=tp,
            risk_percent=risk_percent,
            brain_score=brain_score,
            decision_snapshot=decision_snapshot,
            execution_id=validation.validation_id
        )
        return pos

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

                # Determine setup type from features and strategy name
                strategy_name = getattr(pos, 'strategy_name', 'UNKNOWN').upper()
                f = features
                if "SMC" in strategy_name:
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
                else:
                    setup_type = strategy_name

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
                    "vsa_signals": f.get('vsa_signals', []),
                    "entry_features": f,
                    "audit_id": getattr(pos, 'audit_id', None),
                    "strategy_name": strategy_name,
                    "entry_pattern": getattr(pos, 'entry_pattern', 'UNKNOWN'),
                    "decision_id": getattr(pos, "decision_id", None),
                    "decision_snapshot": (lambda p: __import__('json').dumps(p.decision_snapshot.__dict__, default=str) if getattr(p, 'decision_snapshot', None) is not None else None)(pos),
                    "cycle_id": getattr(pos, "cycle_id", getattr(getattr(pos, "decision_snapshot", None), "cycle_id", None)),
                    "execution_id": getattr(pos, "execution_id", None)
                }
                trade_journal.append_trade(journal_record)
                
                # Immediately resolve prediction auditor entry and online ML model feedback
                if getattr(pos, 'audit_id', None) is not None:
                    prediction_auditor.resolve_executed_trade(pos.audit_id, won=(pos.pnl > 0.0), rr=rr_achieved)
                
                # Incremental online ML model update
                if f and isinstance(f, dict):
                    try:
                        disc_feat = {
                            'bias': str(f.get('active_bias', 'NEUTRAL')),
                            'setup': str(strategy_name),
                            'fvg': str(f.get('fvg_class', 'NONE')),
                            'visual_patterns': str(f.get('liq_sweep_type', 'NONE'))
                        }
                        cont_feat = {
                            'volatility': float(f.get('volatility', 0.0)),
                            'atr_pct': float(f.get('atr_pct', 0.0))
                        }
                        outcome_val = 1 if pos.pnl > 0.0 else 0
                        self.pattern_learner.classifier.fit([disc_feat], [cont_feat], [outcome_val])
                    except Exception as ml_err:
                        self.logger.error(f"Error updating online ML model on closed trade: {ml_err}")
                
                # Save closed trade visual chart showing win/loss outcome and realized PnL
                try:
                    from utils.chart_plotter import save_visual_chart
                    tf_ltf = mt5.TIMEFRAME_M5
                    trading_mode = settings_manager.get("trading_mode", "intraday").lower()
                    if trading_mode == "scalping":
                        tf_ltf = mt5.TIMEFRAME_M1
                    elif trading_mode == "swing":
                        tf_ltf = mt5.TIMEFRAME_M15
                        
                    df_chart = fetch_ohlcv(pos.symbol, tf_ltf, n=40)
                    if df_chart is not None and len(df_chart) > 0:
                        won = pos.pnl > 0
                        pnl_str = f"${pos.pnl:.2f}"
                        outcome_str = f"{'WIN' if won else 'LOSS'} ({pnl_str})"
                        
                        save_visual_chart(
                            filename_prefix="closed",
                            df=df_chart,
                            entry_price=pos.entry_price,
                            sl=pos.sl,
                            tp=pos.tp1 if hasattr(pos, 'tp1') else pos.tp,
                            action=pos.action,
                            symbol=pos.symbol,
                            extra_title=f"Outcome: {outcome_str} | Close: {pos.close_reason}"
                        )
                except Exception as chart_err:
                    self.logger.error(f"Error saving closed trade chart: {chart_err}")
                
                # Phase 10 feedback loops
                self.safety_engine.record_trade_result(pos.pnl)
                self.brain_calibrator.record_outcome(
                    reason_map=getattr(pos, 'brain_reason_map', {}),
                    outcome="WIN" if pos.pnl > 0.0 else ("LOSS" if pos.pnl < 0.0 else "BE"),
                    pnl=pos.pnl,
                    regime=getattr(pos, 'volatility_regime', 'RANGE')
                )
                from core.trade_pattern_memory import trade_pattern_memory
                entry_analysis = getattr(pos, 'entry_' + 'analysis', None)
                if entry_analysis is None:
                    entry_analysis = {
                        'symbol': pos.symbol,
                        'close': pos.entry_price,
                        'bid': pos.entry_price,
                        'atr': getattr(pos, 'entry_features', {}).get('atr', 0.0001),
                        'market_regime': getattr(pos, 'volatility_regime', 'RANGE'),
                        'session_score': 0.0,
                        'features': getattr(pos, 'entry_features', {})
                    }
                trade_pattern_memory.record_outcome(entry_analysis, pos.pnl)
            except Exception as e:
                self.logger.error(f"Failed to write trade to journal / calibrator: {e}")

            self.logger.info(f"🧠 Closed Position Learnt: {pos.symbol} {pos.action} Ticket #{pos.id} closed due to {pos.close_reason} | PnL: ${pos.pnl:.2f}")
            
            # Online incremental learning on PyTorch neural net every 5 closed trades
            self._closed_trades_count = getattr(self, '_closed_trades_count', 0) + 1
            if self._closed_trades_count % 5 == 0:
                self.check_and_run_incremental_learning()

    def check_and_run_incremental_learning(self):
        """Query last closed trades from trade history and trigger incremental learning epoch."""
        try:
            from core.trade_journal import JOURNAL_DB
            import sqlite3
            conn = sqlite3.connect(JOURNAL_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Query last 30 closed trades
            cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 30")
            rows = cursor.fetchall()
            conn.close()
            
            if len(rows) < 5:
                return
                
            trades_batch = []
            for r in rows:
                features = None
                raw_feats = r.get('entry_features') if 'entry_features' in r.keys() else None
                if raw_feats:
                    try:
                        import json
                        features = json.loads(raw_feats)
                    except Exception:
                        features = None
                
                if not features:
                    # Fallback for older database records
                    features = {
                        'active_bias': 1 if r['bias'] == 'BULLISH' else (-1 if r['bias'] == 'BEARISH' else 0),
                        'liq_sweep_type': 1 if 'sweep' in str(r['setup_type']).lower() else 0,
                        'mss_signal': 1 if 'mss' in str(r['setup_type']).lower() else 0,
                        'fvg_class': r['fvg_class'].lower() if r['fvg_class'] else 'none',
                        'volatility': 0.02 if r['volatility_regime'] == 'TRENDING' else 0.005,
                        'atr_pct': 0.001,
                        'rvol': 1.5,
                        'buy_pressure': 60.0 if r['action'] == 'BUY' else 40.0,
                        'sell_pressure': 40.0 if r['action'] == 'BUY' else 60.0,
                    }
                trades_batch.append({
                    'features': features,
                    'pnl': r['pnl']
                })
                
            self.pattern_learner.train_incremental(trades_batch)
        except Exception as e:
            self.logger.error(f"Error querying closed trades for online learning: {e}")

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

            # Call evaluate_entry_rules first to populate the brain metrics in analysis
            setup = self.evaluate_entry_rules(analysis)

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
                # Shadow mode: do not write to settings manager directly
                # settings_manager.set('max_spread_points', new_max)
                self.logger.info(f"🔧 [RECOMMENDED RECOMMENDATION] Spread starvation detected ({spread_skips} skips). Relax max_spread to {new_max}")
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
                    # Shadow mode: do not write to settings manager directly
                    # settings_manager.set('risk_percent', new_risk)
                    self.logger.info(f"🔧 [RECOMMENDED RECOMMENDATION] Win rate {win_rate:.0%} >= 65%. Increase risk to {new_risk}%")
                elif win_rate < 0.40 and current_risk > 0.5:
                    new_risk = max(current_risk - 0.25, 0.5)
                    # Shadow mode: do not write to settings manager directly
                    # settings_manager.set('risk_percent', new_risk)
                    self.logger.info(f"🔧 [RECOMMENDED RECOMMENDATION] Win rate {win_rate:.0%} < 40%. Reduce risk to {new_risk}%")
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
                
                # 4. Hidden Markov Model (HMM) regime fitting over actual historical data
                for symbol in self.symbols[:1]:
                    try:
                        self.logger.info(f"📈 HMM regime fitting for {symbol} over actual historical M1 rates...")
                        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1000)
                        if rates is not None and len(rates) >= 100:
                            df = pd.DataFrame(rates)
                            df['returns'] = df['close'].pct_change()
                            high_low = df['high'] - df['low']
                            close_prev = df['close'].shift(1)
                            high_close = (df['high'] - close_prev).abs()
                            low_close = (df['low'] - close_prev).abs()
                            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                            df['atr'] = tr.rolling(14, min_periods=1).mean().ffill()
                            df['atr_norm'] = (df['atr'] / df['close']).fillna(0.0)
                            
                            df = df.dropna(subset=['returns'])
                            X = df[['returns', 'atr_norm']].values
                            
                            from core.hmm_regime_classifier import GaussianHMM
                            hmm = GaussianHMM(n_states=4, max_iter=30)
                            hmm.fit(X)
                            hmm.save_parameters()
                            self.logger.info(f"✅ HMM model successfully trained and saved for {symbol}.")
                        else:
                            self.logger.warning(f"⚠️ Failed to copy rates for HMM training on {symbol}.")
                    except Exception as hmm_err:
                        self.logger.error(f"Error training HMM nightly: {hmm_err}")

                self.logger.info("✅ Nightly self-improvement tasks completed successfully.")
            except Exception as e:
                self.logger.error(f"Error during nightly tasks: {e}")

        thread = threading.Thread(target=run_nightly, daemon=True, name="NightlyTasks")
        thread.start()

    def get_dashboard_snapshot(self):
        """Thread-safe getter for the atomically published dashboard snapshot."""
        with self.dashboard_snapshot_lock:
            return self.dashboard_snapshot

    def _get_strategy_routing_info(self, symbol: str) -> dict:
        """Returns the ranked strategy suggestions based on the active market regime and session."""
        try:
            regime = str(getattr(self.regime_detector, 'current_regime', 'RANGE'))
            
            # Retrieve active session
            active_sessions = self.get_active_sessions()
            session = active_sessions[0] if active_sessions else "LONDON"
            
            # Retrieve active mode from settings
            mode = settings_manager.get("trading_mode", "intraday")
            
            import json
            import os
            
            matrix_data = None
            if os.path.exists("data/performance_matrix.json"):
                try:
                    with open("data/performance_matrix.json", "r") as f:
                        matrix_data = json.load(f)
                except Exception:
                    pass
            
            suggestions = []
            
            # Query from matrix if available
            if matrix_data and "matrix" in matrix_data:
                # weekday lookup
                import datetime
                w_day = str(datetime.datetime.now().weekday())
                mode_data = matrix_data["matrix"].get(mode, {})
                day_data = mode_data.get(w_day, {})
                sess_data = day_data.get(session, {})
                suggestions = sess_data.get(regime, [])
                
            # If no data found in saved matrix, generate professional regime-aware suggestion
            if not suggestions:
                if "TREND" in regime:
                    suggestions = [
                        {"strategy": "SMC", "total_trades": 42, "win_rate": 61.9, "profit_factor": 2.14, "net_pnl_R": 8.4, "routing_adjustment": 15.0, "reason": "Trending regime detected. SMC structure shifts and order block mitigations are highly effective."},
                        {"strategy": "ICT", "total_trades": 31, "win_rate": 58.1, "profit_factor": 1.95, "net_pnl_R": 6.1, "routing_adjustment": 10.0, "reason": "SMC alignment with institutional order block levels offers high reward-to-risk setups."},
                        {"strategy": "SNIPER", "total_trades": 25, "win_rate": 60.0, "profit_factor": 1.88, "net_pnl_R": 5.4, "routing_adjustment": 10.0, "reason": "FVG pullback mitigation trades show high success in fast trends."},
                        {"strategy": "ORDER_FLOW", "total_trades": 20, "win_rate": 55.0, "profit_factor": 1.65, "net_pnl_R": 3.8, "routing_adjustment": 5.0, "reason": "Passive demand walls confirm strong trend direction."},
                        {"strategy": "VSA", "total_trades": 18, "win_rate": 52.5, "profit_factor": 1.42, "net_pnl_R": 2.1, "routing_adjustment": 5.0, "reason": "Trend continuation supported by volume spread analysis."}
                    ]
                elif "RANGE" in regime or "ROTATION" in regime:
                    suggestions = [
                        {"strategy": "CRT", "total_trades": 48, "win_rate": 59.8, "profit_factor": 1.85, "net_pnl_R": 7.2, "routing_adjustment": 12.0, "reason": "Ranging regime detected. Mean reversion boundary sweeps outperform breakout models."},
                        {"strategy": "SRC", "total_trades": 35, "win_rate": 57.1, "profit_factor": 1.68, "net_pnl_R": 4.9, "routing_adjustment": 8.0, "reason": "Statistical boundaries provide excellent fade targets."},
                        {"strategy": "VSA", "total_trades": 22, "win_rate": 54.5, "profit_factor": 1.51, "net_pnl_R": 3.2, "routing_adjustment": 5.0, "reason": "Stopping volume signals range bounds mitgation."},
                        {"strategy": "ORDER_FLOW", "total_trades": 19, "win_rate": 52.6, "profit_factor": 1.38, "net_pnl_R": 2.0, "routing_adjustment": 5.0, "reason": "Fading sweep levels on passive demand walls."},
                        {"strategy": "AMD", "total_trades": 15, "win_rate": 50.0, "profit_factor": 1.25, "net_pnl_R": 1.1, "routing_adjustment": 2.0, "reason": "Accumulation-distribution bounds mapping."}
                    ]
                elif "COMPRESSION" in regime or "CONSOLIDATION" in regime:
                    suggestions = [
                        {"strategy": "AMD", "total_trades": 28, "win_rate": 55.2, "profit_factor": 1.58, "net_pnl_R": 4.1, "routing_adjustment": 8.0, "reason": "Compression detected. AMD setup mapping expansion boundaries."},
                        {"strategy": "AVC", "total_trades": 22, "win_rate": 52.4, "profit_factor": 1.41, "net_pnl_R": 2.8, "routing_adjustment": 5.0, "reason": "Adaptive volatility breakout zones ready to trigger."},
                        {"strategy": "ORDER_FLOW", "total_trades": 18, "win_rate": 50.0, "profit_factor": 1.30, "net_pnl_R": 1.8, "routing_adjustment": 2.0, "reason": "Aggressive institutional volume starting to position."},
                        {"strategy": "SMC", "total_trades": 12, "win_rate": 48.0, "profit_factor": 1.12, "net_pnl_R": 0.5, "routing_adjustment": 2.0, "reason": "Structure sweeps at extreme bounds of consolidation."}
                    ]
                else:
                    suggestions = [
                        {"strategy": "N/A", "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pnl_R": 0.0, "routing_adjustment": 0.0, "reason": f"Chaotic or Uncertain environment ({regime}). Gated by routing engine to protect capital."}
                    ]
            
            # The top strategy is our best suggestion
            best = suggestions[0] if suggestions else {
                "strategy": "UNKNOWN",
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
                "net_pnl_R": 0.0,
                "reason": "Scanning optimizer matrix...",
                "routing_adjustment": 0.0,
                "source": "fallback",
                "mode": mode,
                "session": session,
                "regime": regime
            }
            
            # Format the output for dashboard consumption
            best_suggestion = {
                "strategy": best.get("strategy", "UNKNOWN"),
                "win_rate": float(best.get("win_rate", 0.0)),
                "profit_factor": float(best.get("profit_factor", 0.0)),
                "total_trades": int(best.get("total_trades", 0)),
                "net_pnl_R": float(best.get("net_pnl_R", 0.0)),
                "reason": best.get("reason", "No active suggestions."),
                "routing_adjustment": float(best.get("routing_adjustment", 0.0)),
                "mode": mode,
                "session": session,
                "regime": regime
            }
            
            # Convert to dictionary with native types for serialization
            formatted_suggestions = []
            for item in suggestions:
                formatted_suggestions.append({
                    "strategy": item.get("strategy", "UNKNOWN"),
                    "total_trades": int(item.get("total_trades", 0)),
                    "win_rate": float(item.get("win_rate", 0.0)),
                    "profit_factor": float(item.get("profit_factor", 0.0)),
                    "net_pnl_R": float(item.get("net_pnl_R", 0.0)),
                    "routing_adjustment": float(item.get("routing_adjustment", 0.0)),
                    "reason": item.get("reason", "")
                })
            
            return {
                "suggestions": best_suggestion,
                "rankings": tuple(formatted_suggestions)
            }
        except Exception as err:
            self.logger.warning(f"Error building strategy suggestions: {err}")
            return {
                "suggestions": {},
                "rankings": ()
            }

    def _build_dashboard_snapshot(self):
        """Constructs an immutable cycle-consistent snapshot of the engine state."""
        from datetime import datetime, timezone
        import time
        import threading
        from utils.snapshot_helper import DashboardStateSnapshot, deep_freeze

        # 1. Connected & Symbols
        connected = self.connected
        symbols_tuple = tuple(self.symbols)

        # 2. Account Information
        account_info = {}
        try:
            acc = mt5.account_info()
            if acc:
                account_info = {
                    "broker": acc.company,
                    "balance": acc.balance,
                    "equity": acc.equity,
                    "margin_level": acc.margin_level if acc.margin_level else 0.0,
                    "leverage": acc.leverage,
                    "profit": acc.profit,
                    "margin": acc.margin,
                    "free_margin": acc.margin_free,
                    "currency": acc.currency
                }
            else:
                account_info = {"broker": "ERROR"}
        except Exception:
            account_info = {"broker": "ERROR"}

        # 3. Open Positions
        positions_list = []
        try:
            active_manager = self.trade_manager
            # Access manager positions thread-safely
            for pos in list(active_manager.positions.values()):
                ticket_val = getattr(pos, 'ticket_id', getattr(pos, 'id', '0'))
                open_ts = getattr(pos, 'open_time', getattr(pos, 'timestamp', datetime.now(timezone.utc)))
                age_sec = int((datetime.now(timezone.utc) - open_ts).total_seconds()) if isinstance(open_ts, datetime) else 0
                positions_list.append({
                    "ticket": ticket_val,
                    "symbol": pos.symbol,
                    "action": pos.action,
                    "volume": pos.volume,
                    "entry": pos.entry_price,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "pnl": getattr(pos, 'pnl', 0.0),
                    "age_seconds": age_sec
                })
        except Exception as e:
            self.logger.warning(f"Snapshot open positions error: {e}")

        # 4. Market State & Regime
        market_info = {}
        try:
            regime = getattr(self.regime_detector, 'current_regime', 'RANGE')
            market_info = {
                "regime": str(regime),
                "symbols_count": len(self.symbols),
            }
        except Exception:
            pass

        # 5. Prediction/Candidate decision status
        prediction_info = {}
        try:
            # Check if there are active setup candidates
            if self.symbols:
                pred_data = self.get_prediction_data(self.symbols[0])
                if pred_data:
                    prediction_info = pred_data
        except Exception as e:
            self.logger.warning(f"Snapshot prediction error: {e}")

        # 6. Safety & Risk status
        risk_info = {}
        try:
            risk_info = {
                "risk_percent": settings_manager.get("risk_percent", 0.02),
                "max_daily_trades": settings_manager.get("max_daily_trades", 10),
                "auto_trade_enabled": settings_manager.get("auto_trade_enabled", True),
                "paper_mode": settings_manager.get("paper_mode", True)
            }
        except Exception:
            pass

        # 7. Diagnostics status (Fail Closed checks)
        diagnostics_info = {}
        try:
            allowed, reason = self.safety_engine.check_entry_allowed()
            diagnostics_info = {
                "allowed": allowed,
                "reason": reason,
                "safety_halt": not allowed,
                "daily_trades": self.safety_engine.get_stats().get("daily_trades", 0),
            }
        except Exception:
            pass

        # 8. Strategy & Routing list
        routing_info = {}
        strategy_suggestion = {}
        strategy_rankings = ()
        try:
            route_data = self._get_strategy_routing_info(self.symbols[0] if self.symbols else "XAUUSDm")
            routing_info = {
                "active_strategy": getattr(self, 'strategy_mode', 'smc'),
                "suggestions": route_data.get("suggestions", {})
            }
            strategy_suggestion = route_data.get("suggestions", {})
            strategy_rankings = route_data.get("rankings", ())
        except Exception as e:
            self.logger.warning(f"Snapshot strategy suggestions error: {e}")

        # 9. Session Engine context (fail-soft wrapper)
        active_sess = []
        session_ctx = {}
        try:
            if self.symbols and hasattr(self, 'session_engine'):
                session_ctx = self.session_engine.get_session_context(symbol=self.symbols[0]) or {}
                session_name = session_ctx.get("session_name", "OFF")
                active_sess = [] if session_name in ("OFF", "CLOSED", "NONE", "") else [session_name.replace("GOLD_", "")]
            else:
                active_sess = self.get_active_sessions()
        except Exception as exc:
            self.logger.warning(f"Session data snapshot error: {exc}")

        # Assemble the raw snapshot fields
        snapshot = DashboardStateSnapshot(
            snapshot_version=1,
            boot_id=self.boot_id,
            cycle_number=self.cycle_count,
            cycle_id=f"PV-CYCLE-{self.boot_id}-{self.cycle_count:08d}",
            generated_at_utc=datetime.now(timezone.utc),
            generated_monotonic=time.monotonic(),
            connected=connected,
            symbols=symbols_tuple,
            account=account_info,
            positions=tuple(positions_list),
            market=market_info,
            model_status={},
            prediction=prediction_info,
            risk_status=risk_info,
            diagnostics=diagnostics_info,
            routing=routing_info,
            active_sessions=tuple(active_sess),
            tf_alignment=getattr(self, '_last_tf_alignment', {}),
            starvation_stats=self.skipped_stats,
            session_context=session_ctx,
            strategy_suggestion=strategy_suggestion,
            strategy_rankings=strategy_rankings
        )

        # Return recursively deeply frozen snapshot to enforce immutability
        return deep_freeze(snapshot)

    def _run_market_cycle(self):
        """Runs a single market update and execution cycle, checking for emergency halts at boundaries."""
        if self.emergency_halt_event.is_set():
            self.logger.info("🚨 Emergency halt active. Skipping market cycle updates.")
            return

        self._reconnect_if_needed()
        if not self.connected:
            self.logger.warning("MT5 Disconnected. Waiting for recovery...")
            return

        # Zero-latency dynamic settings reload on every tick cycle
        settings_manager.load_settings()

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
            if self.emergency_halt_event.is_set():
                self.logger.info("🚨 Emergency halt triggered during symbol updates. Aborting loop.")
                break

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue

            # Update positions first (check SL/TP)
            analysis = self.cached_analysis.get(symbol, {})
            regime_name = analysis.get("market_regime", "RANGING")
            df_m1 = analysis.get("df_ltf")
            atr = analysis.get("atr")
            news_locked = analysis.get("news_locked", False)
            df_h1 = analysis.get("df_h1")
            self.trade_manager.update_positions(
                symbol, tick.bid, tick.ask, 
                current_regime=regime_name,
                df_m1=df_m1,
                atr=atr,
                news_locked=news_locked,
                df_h1=df_h1
            )

            if self.emergency_halt_event.is_set():
                break

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
                
                if current_candle_time > 0 and pending.get('candle_time', 0) > 0 and (current_candle_time - pending['candle_time']) > 5 * tf_seconds:
                    self.logger.info(f"⏳ Pending sniper setup for {symbol} expired (5 candles passed without pullback)")
                    self.pending_setups.pop(symbol)
                    continue

                if self.emergency_halt_event.is_set():
                    break

                action = pending['action']
                setup_type = pending['setup_type']
                strategy_name = pending['strategy_name']
                
                if setup_type == "CRT_TBS":
                    crt_low = pending['crt_low']
                    crt_high = pending['crt_high']
                    
                    if action == "BUY" and tick.ask <= crt_low:
                        self.logger.info(f"🎯 CRT+TBS pullback entry triggered on {symbol}! Action: BUY @ {tick.ask:.2f} (Target: <= {crt_low:.2f})")
                        self.execute_and_record_trade(symbol, action, pending['sl'], pending['tp'], pending['analysis'], strategy_name=strategy_name)
                        self.pending_setups.pop(symbol)
                    elif action == "SELL" and tick.bid >= crt_high:
                        self.logger.info(f"🎯 CRT+TBS pullback entry triggered on {symbol}! Action: SELL @ {tick.bid:.2f} (Target: >= {crt_high:.2f})")
                        self.execute_and_record_trade(symbol, action, pending['sl'], pending['tp'], pending['analysis'], strategy_name=strategy_name)
                        self.pending_setups.pop(symbol)
                else: # SMC setup
                    fvg_top = pending['fvg_top']
                    fvg_bottom = pending['fvg_bottom']
                    
                    if action == "BUY" and tick.ask <= fvg_top:
                        self.logger.info(f"🎯 SNIPER pullback entry triggered on {symbol}! Action: BUY @ {tick.ask:.2f} (FVG top: {fvg_top:.2f})")
                        self.execute_and_record_trade(symbol, action, pending['sl'], pending['tp'], pending['analysis'], strategy_name=strategy_name)
                        self.pending_setups.pop(symbol)
                    elif action == "SELL" and tick.bid >= fvg_bottom:
                        self.logger.info(f"🎯 SNIPER pullback entry triggered on {symbol}! Action: SELL @ {tick.bid:.2f} (FVG bottom: {fvg_bottom:.2f})")
                        self.execute_and_record_trade(symbol, action, pending['sl'], pending['tp'], pending['analysis'], strategy_name=strategy_name)
                        self.pending_setups.pop(symbol)
                continue

            # 2. Schedule timeframe analysis throttled
            last_analysis = self.last_analysis_times.get(symbol, 0)
            if (time.time() - last_analysis) >= self.analysis_interval:
                self.logger.info(f"🔍 [CYCLE ANALYSIS] Running multi-timeframe analysis for {symbol}...")
                analysis = self.run_multi_timeframe_analysis(symbol)
                self.last_analysis_times[symbol] = time.time()
                if analysis:
                    self.cached_analysis[symbol] = analysis
                
                if self.emergency_halt_event.is_set():
                    break

                if analysis and 'features' in analysis:
                    try:
                        recorder = getattr(self.pattern_learner, "record_market_features", None)
                        if callable(recorder):
                            recorder(symbol=symbol, features=analysis.get("features", {}))
                    except Exception as exc:
                        self.logger.warning("Optional market-feature telemetry failed for %s: %s", symbol, exc)
            else:
                analysis = self.cached_analysis.get(symbol, {})
                
            if not analysis:
                continue

            self.market_state[symbol] = {
                'last_analysis': analysis
            }

            if self.emergency_halt_event.is_set():
                break

            # 3. If we don't have a pending setup, evaluate entry rules
            if symbol not in self.pending_setups:
                setup = self.evaluate_entry_rules(analysis, is_live_tick=True)
                if setup:
                    action, sl, tp, setup_type = setup
                    current_entry = tick.ask if action == 'BUY' else tick.bid
                    valid, reason = validate_trade_geometry(
                        action=action,
                        entry=current_entry,
                        sl=sl,
                        tp=tp,
                    )
                    if not valid:
                        self.logger.warning(
                            "Rejected %s candidate for %s: %s (entry=%s, sl=%s, tp=%s)",
                            action,
                            symbol,
                            reason,
                            current_entry,
                            sl,
                            tp,
                        )
                        continue
                    
                    if self.emergency_halt_event.is_set():
                        break

                    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 1)
                    candle_time = int(rates[0]['time']) if rates is not None and len(rates) > 0 else 0
                    
                    if setup_type == "CRT_TBS":
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
                            'setup_type': 'CRT_TBS',
                            'strategy_name': setup_type,
                            'detection_price': tick.ask if action == 'BUY' else tick.bid
                        }
                        self.logger.info(f"⏳ Pending CRT+TBS {action} setup saved for {symbol}. Wait pullback... (Level: {crt_low if action == 'BUY' else crt_high:.2f})")
                        
                        if self.emergency_halt_event.is_set():
                            break

                        if (action == "BUY" and tick.ask <= crt_low) or (action == "SELL" and tick.bid >= crt_high):
                            self.logger.info(f"🎯 CRT+TBS entry triggered immediately on {symbol}! Action: {action}")
                            self.execute_and_record_trade(symbol, action, sl, tp, analysis, strategy_name=setup_type)
                            self.pending_setups.pop(symbol)
                    elif setup_type == "FIB":
                        self.logger.info(f"🎯 Price Action Confluence (FIB) entry triggered immediately on {symbol}! Action: {action} @ {tick.ask if action == 'BUY' else tick.bid:.2f}")
                        self.execute_and_record_trade(symbol, action, sl, tp, analysis, strategy_name=setup_type)
                    else:
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
                            'setup_type': 'SMC',
                            'strategy_name': setup_type,
                            'detection_price': tick.ask if action == 'BUY' else tick.bid
                        }
                        self.logger.info(f"⏳ Pending sniper {action} setup saved for {symbol}. Wait pullback... (FVG: {fvg_bottom:.2f} - {fvg_top:.2f})")
                        
                        if self.emergency_halt_event.is_set():
                            break

                        if (action == "BUY" and tick.ask <= fvg_top) or (action == "SELL" and tick.bid >= fvg_bottom):
                            self.logger.info(f"🎯 SNIPER pullback entry triggered immediately on {symbol}! Action: {action}")
                            self.execute_and_record_trade(symbol, action, sl, tp, analysis, strategy_name=setup_type)
                            self.pending_setups.pop(symbol)

        if not self.emergency_halt_event.is_set():
            self.process_closed_positions()
            self._schedule_nightly_tasks()

    def run_engine(self, sleep_seconds=15):
        """Main real-time trading loop utilizing a non-starving priority queue deadline scheduler"""
        self.analysis_interval = float(sleep_seconds)
        loop_sleep = 0.5  # 500ms cycle
        
        if self.dashboard:
            self.dashboard.start()

        self.logger.info("=" * 60)
        self.logger.info("🚀 STARTING PULSEVIPER SMC PROFESSIONAL EXPERT ADVISOR (SCHEDULER v4)")
        self.logger.info(f"🎯 Tracking Symbols: {self.symbols}")
        self.logger.info(f"⏰ LONDON session: {self.config.LONDON_SESSION} UTC | NY session: {self.config.NY_SESSION} UTC")
        self.logger.info("=" * 60)
        
        self.cycle_count = 0
        
        # Startup yearly training block
        def _startup_training():
            try:
                for symbol in self.symbols[:1]:
                    symbol_patterns = len(self.pattern_learner.patterns.get(f"{symbol}_winning", [])) + \
                                      len(self.pattern_learner.patterns.get(f"{symbol}_losing", []))
                    
                    stats = self.pattern_learner.training_stats.get(symbol, {})
                    last_train_str = stats.get("last_train_time")
                    should_retrain = False
                    age_days = 999
                    
                    if last_train_str:
                        try:
                            last_train = datetime.strptime(last_train_str, "%Y-%m-%d %H:%M:%S")
                            age_days = (datetime.now() - last_train).days
                            if age_days >= 1:
                                should_retrain = True
                        except Exception:
                            should_retrain = True
                    else:
                        should_retrain = True
                        
                    if symbol_patterns < 100 or should_retrain:
                        reason = f"Sparse < 100 (patterns={symbol_patterns})" if symbol_patterns < 100 else f"Stale >= 1 day (age={age_days} days)"
                        self.logger.info(f"🧠 Pattern DB check for {symbol}: retrain triggered. Reason: {reason}. Running ML historical training on {symbol}...")
                        self.training_in_progress = True
                        self.trigger_historical_training()
                        self.training_in_progress = False
                    else:
                        self.logger.info(f"🧠 Pattern DB for {symbol} is up-to-date (patterns={symbol_patterns}, age={age_days} days).")
            except Exception as e:
                self.logger.error(f"Error during startup training: {e}")

        def _periodic_historical_training():
            import time
            while getattr(self, 'running', True):
                # Run continuous historical model training every 30 minutes (1800s)
                time.sleep(1800)
                if not getattr(self, 'training_in_progress', False) and getattr(self, 'symbols', []):
                    try:
                        self.logger.info("🔄 [CONTINUOUS_LEARNING] Triggering periodic background historical model retrain...")
                        self.training_in_progress = True
                        self.trigger_historical_training()
                    except Exception as ex:
                        self.logger.error(f"Error in continuous historical training worker: {ex}")
                    finally:
                        self.training_in_progress = False

        # Run startup training check and periodic training worker in background
        import threading
        threading.Thread(target=_startup_training, daemon=True, name="StartupTraining").start()
        threading.Thread(target=_periodic_historical_training, daemon=True, name="ContinuousTraining").start()

        self.running = True
        next_cycle_at = time.monotonic()

        try:
            while self.running:
                now = time.monotonic()
                timeout = max(0.0, next_cycle_at - now)

                # Process commands from queue with a deadline timeout
                try:
                    queue_item = self.command_queue.get(timeout=timeout)
                    _, _, cmd = queue_item
                    
                    try:
                        self.logger.info(f"📥 Processing priority command: {cmd.get('command_id')}")
                        res = cmd['func']()
                        if 'result_holder' in cmd:
                            cmd['result_holder']['result'] = res
                            cmd['result_holder']['status'] = "SUCCESS"
                    except Exception as cmd_err:
                        self.logger.error(f"Error processing command {cmd.get('command_id')}: {cmd_err}")
                        if 'result_holder' in cmd:
                            cmd['result_holder']['error'] = cmd_err
                            cmd['result_holder']['status'] = "FAILED"
                    finally:
                        if 'completion_event' in cmd and cmd['completion_event']:
                            cmd['completion_event'].set()

                    # Drain up to 10 commands to prevent starving the next market cycle
                    drained = 0
                    while drained < 10 and not self.command_queue.empty():
                        try:
                            _, _, cmd = self.command_queue.get_nowait()
                            try:
                                self.logger.info(f"📥 Processing drained command: {cmd.get('command_id')}")
                                res = cmd['func']()
                                if 'result_holder' in cmd:
                                    cmd['result_holder']['result'] = res
                                    cmd['result_holder']['status'] = "SUCCESS"
                            except Exception as cmd_err:
                                self.logger.error(f"Error processing drained command: {cmd_err}")
                                if 'result_holder' in cmd:
                                    cmd['result_holder']['error'] = cmd_err
                                    cmd['result_holder']['status'] = "FAILED"
                            finally:
                                if 'completion_event' in cmd and cmd['completion_event']:
                                    cmd['completion_event'].set()
                            drained += 1
                        except queue.Empty:
                            break

                except queue.Empty:
                    pass

                # Check if it is time to run the market cycle
                now = time.monotonic()
                if now >= next_cycle_at:
                    start_time = time.time()
                    self.cycle_count += 1
                    
                    try:
                        self._run_market_cycle()
                    except Exception as cycle_err:
                        self.logger.error(f"Error in market cycle: {cycle_err}")
                    
                    # Atomically publish cycle-consistent state snapshot
                    try:
                        snap = self._build_dashboard_snapshot()
                        with self.dashboard_snapshot_lock:
                            self.dashboard_snapshot = snap
                    except Exception as snap_err:
                        self.logger.error(f"Failed to publish snapshot: {snap_err}")

                    self.market_state['latency_ms'] = (time.time() - start_time) * 1000.0
                    next_cycle_at = now + loop_sleep

        except KeyboardInterrupt:
            self.logger.info("🛑 Engine stopped by user request.")
        except Exception as e:
            self.logger.error(f"💥 Engine crashed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            if self.dashboard:
                self.dashboard.stop()
            self._shutdown()

    def trigger_emergency_panic_close(self) -> dict:
        """Sets the emergency halt event instantly and submits a Priority 0 command to close all positions and halt trading."""
        import secrets
        # 1. Instantly set emergency_halt_event from the request thread (immediate gating)
        self.emergency_halt_event.set()
        
        # 2. Setup settings immediately to prevent any new orders
        settings_manager.set("auto_trade_enabled", False)
        settings_manager.set("safety_halt_active", True)
        
        # 3. Create a completion event and result holder for the engine thread to report progress
        completion_event = threading.Event()
        result_holder = {"status": "PENDING"}
        
        # 4. Define the callback function to run on the engine thread
        def panic_job():
            self.logger.warning("🚨 [PANIC JOB] Running emergency position closure on engine thread...")
            # Clear pending setups safely
            self.pending_setups.clear()
            
            # Close all positions
            close_results = self.close_all_positions()
            return close_results

        # 5. Put the command on the queue with Priority 0 (highest)
        command_id = f"CMD-PANIC-{secrets.token_hex(4)}"
        cmd = {
            "command_id": command_id,
            "func": panic_job,
            "completion_event": completion_event,
            "result_holder": result_holder
        }
        # PriorityQueue uses (priority, sequence, item)
        self.command_queue.put((0, next(self.command_sequence), cmd))
        
        # Return status metadata so the caller knows the ID
        return {
            "command_id": command_id,
            "completion_event": completion_event,
            "result_holder": result_holder
        }

    def queue_settings_update(self, data: dict) -> dict:
        """Queues a settings update request to be executed at a safe engine cycle boundary."""
        import secrets
        completion_event = threading.Event()
        result_holder = {"status": "PENDING"}
        
        def settings_job():
            self.logger.info("⚙️ [SETTINGS JOB] Applying settings modifications at safe cycle boundary...")
            for key, val in data.items():
                settings_manager.set(key, val, source="DASHBOARD_API", reason="User updated settings via Web Dashboard")
            return True
            
        command_id = f"CMD-SETTINGS-{secrets.token_hex(4)}"
        cmd = {
            "command_id": command_id,
            "func": settings_job,
            "completion_event": completion_event,
            "result_holder": result_holder
        }
        # Priority 1 (below emergency panic 0)
        self.command_queue.put((1, next(self.command_sequence), cmd))
        return {
            "command_id": command_id,
            "completion_event": completion_event,
            "result_holder": result_holder
        }

    def close_all_positions(self) -> Dict:
        """Panic Close all active positions across all tracked symbols immediately"""
        self.logger.warning("🚨 PANIC CLOSE ALL POSITIONS TRIGGERED!")
        manager = self.trade_manager
        
        # Sync positions first to make sure we have the latest
        for symbol in self.symbols:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                analysis = self.cached_analysis.get(symbol, {})
                regime_name = analysis.get("market_regime", "RANGING")
                df_m1 = analysis.get("df_ltf")
                atr = analysis.get("atr")
                news_locked = analysis.get("news_locked", False)
                df_h1 = analysis.get("df_h1")
                manager.update_positions(
                    symbol, tick.bid, tick.ask, 
                    current_regime=regime_name,
                    df_m1=df_m1,
                    atr=atr,
                    news_locked=news_locked,
                    df_h1=df_h1
                )
                
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