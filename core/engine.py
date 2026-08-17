# core/engine.py

from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import secrets
import threading
import time
import traceback
import uuid

from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple, cast

import numpy as np
import pandas as pd


from configs.config import Config

from core.backtester import AdaptiveBacktester
from core.brain_calibrator import BrainCalibrator
from core.daily_analyzer import DailyAnalyzer
from core.experience_memory import ExperienceMemory
from core.pattern_learner import PatternLearner
from core.prediction_auditor import prediction_auditor
from core.safety_engine import SafetyEngine
from core.session_engine import SessionEngine
from core.starvation_analyzer import StarvationAnalyzer
from core.strategy_optimizer import StrategyOptimizer
from core.trade_brain import BrainResult
from core.trade_journal import trade_journal
from core.trade_manager import (
    LiveTradeManager,
    PaperTradeManager,
    TradeDecisionSnapshot,
    TradePosition,
    deep_freeze,
)

from dashboard.web_dashboard import WebDashboardServer

from strategies.amd import AmdStrategy
from strategies.avc_strategy import AvcStrategy
from strategies.bank_strategy import BankStrategy
from strategies.crt_tbs import CrtTbsStrategy
from strategies.fib_retest import FibRetestStrategy
from strategies.ict_strategy import IctStrategy
from strategies.m1_scalping_strategy import M1ScalpingStrategy
from strategies.quantum_viper_strategy import QuantumViperStrategy
from strategies.raja_strategy import RajaStrategy
from strategies.smc_concepts_strategy import SmcConceptsStrategy
from strategies.src import SrcStrategy
from strategies.vsa_strategy import VsaStrategy
from strategies.vwap_strategy import VwapStrategy

from utils.mt5_data import (
    fetch_ohlcv,
    init_mt5,
    shutdown_mt5,
)
from utils.mt5_gateway import (
    mt5_gateway as mt5,
    set_emergency_halt_event,
)
from utils.sentiment_analyzer import sentiment_analyzer
from utils.settings_manager import (
    settings_manager,
    validate_and_clamp_stops,
)
from utils.smc_indicators import SMCIndicators
from utils.volume_analyzer import VolumeAnalyzer


# =============================================================================
# HELPERS
# =============================================================================


def _finite_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        result = float(value)

        if math.isfinite(result):
            return result

    except (TypeError, ValueError):
        pass

    return default


def _finite_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def _safe_json_value(
    value: Any,
) -> Any:
    """
    Convert common NumPy/Pandas values to basic Python values.

    Intended for immutable dashboard/decision snapshots.
    """
    if isinstance(
        value,
        (
            np.integer,
        ),
    ):
        return int(value)

    if isinstance(
        value,
        (
            np.floating,
        ),
    ):
        result = float(value)

        if math.isfinite(result):
            return result

        return None

    if isinstance(
        value,
        (
            np.bool_,
        ),
    ):
        return bool(value)

    if isinstance(
        value,
        pd.Timestamp,
    ):
        if value.tzinfo is None:
            value = value.tz_localize(
                "UTC"
            )

        return value.isoformat()

    if isinstance(
        value,
        datetime,
    ):
        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        ).isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(k): _safe_json_value(v)
            for k, v in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _safe_json_value(v)
            for v in value
        ]

    if value is pd.NaT:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


def validate_trade_geometry(
    action: str,
    entry: float,
    sl: float,
    tp: float,
) -> Tuple[bool, str]:
    """
    Validate an ordinary SL + TP market trade.

    BUY:
        SL < ENTRY < TP

    SELL:
        TP < ENTRY < SL
    """
    action = str(
        action
    ).upper()

    entry = _finite_float(entry)
    sl = _finite_float(sl)
    tp = _finite_float(tp)

    if (
        entry <= 0.0
        or sl <= 0.0
        or tp <= 0.0
    ):
        return (
            False,
            "NON_FINITE_OR_NON_POSITIVE_PRICE",
        )

    if action == "BUY":
        if not (
            sl
            < entry
            < tp
        ):
            return (
                False,
                "INVALID_BUY_GEOMETRY",
            )

    elif action == "SELL":
        if not (
            tp
            < entry
            < sl
        ):
            return (
                False,
                "INVALID_SELL_GEOMETRY",
            )

    else:
        return (
            False,
            "INVALID_ACTION",
        )

    return (
        True,
        "VALID",
    )


# =============================================================================
# ENGINE
# =============================================================================


class AdvancedTradingEngine:
    """
    PulseViper production orchestration layer.

    Core invariants
    ---------------

    1. Structural trading features are generated from CLOSED candles.
    2. One analysis cycle produces one decision state.
    3. Dashboard reads never trigger trading/model decision logic.
    4. Final stops are normalized BEFORE ExecutionValidator.
    5. Validator produces an exact immutable request.
    6. LiveTradeManager receives that exact validated request.
    7. Existing-position management is separate from new-entry execution.
    8. Background learning does not silently promote a model.
    """

    STRATEGY_PREFIXES = (
        "quantum",
        "crt",
        "fib",
        "ict",
        "smc",
        "raja",
        "bank",
        "vsa",
        "avc",
        "m1_scalping",
        "vwap",
        "amd",
        "src",
    )

    TREND_STRATEGIES = {
        "QUANTUM",
        "ICT",
        "SMC",
        "RAJA",
        "BANK",
        "VWAP",
        "AVC",
        "FIB",
        "M1_SCALPING",
    }

    RANGE_STRATEGIES = {
        "QUANTUM",
        "CRT",
        "VSA",
        "AMD",
        "SRC",
        "M1_SCALPING",
        "SMC",
        "VWAP",
    }

    TIMEFRAME_CONFIG = {
        "D1": (
            mt5.TIMEFRAME_D1,
            500,
            3600.0,
        ),
        "H4": (
            mt5.TIMEFRAME_H4,
            400,
            900.0,
        ),
        "H1": (
            mt5.TIMEFRAME_H1,
            400,
            300.0,
        ),
        "M30": (
            mt5.TIMEFRAME_M30,
            300,
            120.0,
        ),
        "M15": (
            mt5.TIMEFRAME_M15,
            300,
            60.0,
        ),
        "M5": (
            mt5.TIMEFRAME_M5,
            300,
            15.0,
        ),
        "M1": (
            mt5.TIMEFRAME_M1,
            350,
            3.0,
        ),
    }

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        strategy_mode: str = "smc",
        enable_dashboard: bool = True,
        port: int = 8000,
    ):
        self.config = Config()

        self.strategy_mode = str(
            strategy_mode
        )

        self._configure_logging()

        self.logger = logging.getLogger(
            "PulseViper.Engine"
        )

        # ---------------------------------------------------------------------
        # Main lifecycle state
        # ---------------------------------------------------------------------

        self.connected = False
        self.running = False
        self.cycle_count = 0

        self.analysis_interval = 15.0

        self.market_state: Dict[
            str,
            Any,
        ] = {}

        self.analyzed_trades: Dict[
            str,
            Dict[str, Any],
        ] = {}

        # Retained for frontend/API compatibility.
        # Production execution does not use stale pending requests.
        self.pending_setups: Dict[
            str,
            Dict[str, Any],
        ] = {}

        self.cached_analysis: Dict[
            str,
            Dict[str, Any],
        ] = {}

        self.last_analysis_times: Dict[
            str,
            float,
        ] = {}

        self.last_candle_times: Dict[
            str,
            int,
        ] = {}

        self.last_entry_candle: Dict[
            str,
            int,
        ] = {}

        self.last_close_candle: Dict[
            str,
            int,
        ] = {}

        self.last_blocked_candle: Dict[
            str,
            int,
        ] = {}

        self.last_target_setup: Dict[
            str,
            Dict[str, Any],
        ] = {}

        self.broker_symbols: List[
            str
        ] = []

        # ---------------------------------------------------------------------
        # TF cache
        # ---------------------------------------------------------------------

        self._tf_feature_cache: Dict[
            str,
            pd.DataFrame,
        ] = {}

        self._tf_closed_time: Dict[
            str,
            int,
        ] = {}

        self._last_tf_check_times: Dict[
            str,
            float,
        ] = {}

        # ---------------------------------------------------------------------
        # Market context caches used by dashboard
        # ---------------------------------------------------------------------

        self.pdh_cache: Dict[
            str,
            float,
        ] = {}

        self.pdl_cache: Dict[
            str,
            float,
        ] = {}

        self.pwh_cache: Dict[
            str,
            float,
        ] = {}

        self.pwl_cache: Dict[
            str,
            float,
        ] = {}

        self._last_daily_levels_time: Dict[
            str,
            float,
        ] = {}

        self.sentiment_cache: Dict[
            str,
            float,
        ] = {
            "d1": 0.0,
            "h4": 0.0,
            "h1": 0.0,
            "m30": 0.0,
            "m15": 0.0,
            "m5": 0.0,
            "m1": 0.0,
        }

        self.sentiment_cache_expiry: Dict[
            str,
            float,
        ] = {}

        self.volume_cache: Dict[
            str,
            Any,
        ] = {
            "rvol": 1.0,
            "buy_pressure": 50.0,
            "sell_pressure": 50.0,
            "profile": {},
            "ofi": 0.0,
        }

        self._last_volume_calc_time: Dict[
            str,
            float,
        ] = {}

        self._last_tf_alignment: Dict[
            str,
            Any,
        ] = {}

        # ---------------------------------------------------------------------
        # Dashboard / command scheduler
        # ---------------------------------------------------------------------

        self.boot_id = (
            secrets.token_hex(6)
        )

        self.dashboard_snapshot = None

        self.dashboard_snapshot_lock = (
            threading.Lock()
        )

        self.command_queue: queue.PriorityQueue = (
            queue.PriorityQueue()
        )

        self.command_sequence = iter(
            range(
                10**12
            )
        )

        self.emergency_halt_event = (
            threading.Event()
        )

        set_emergency_halt_event(
            self.emergency_halt_event
        )

        # ---------------------------------------------------------------------
        # Connect MT5
        # ---------------------------------------------------------------------

        self._initialize_connection()

        if symbols is None:
            self.symbols = (
                self._auto_detect_symbols()
            )

        else:
            self.symbols = (
                self._validate_symbols(
                    symbols
                )
            )

        if self.symbols:
            try:
                settings_manager.set(
                    "active_symbol",
                    self.symbols[0],
                    source="ENGINE",
                    reason=(
                        "Initial active broker symbol"
                    ),
                )
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # Trade managers
        # ---------------------------------------------------------------------

        self.paper_trade_manager = (
            PaperTradeManager(
                self.config
            )
        )

        self.live_trade_manager = (
            LiveTradeManager(
                self.config
            )
        )

        # ---------------------------------------------------------------------
        # Learning/model services
        # ---------------------------------------------------------------------

        self.experience_memory = (
            ExperienceMemory(
                capacity=5000
            )
        )

        self.pattern_learner = (
            PatternLearner(
                self.experience_memory
            )
        )

        prediction_auditor.pattern_learner = (
            self.pattern_learner
        )

        from core.execution_validator import (
            ExecutionValidator,
        )

        self.execution_validator = (
            ExecutionValidator()
        )

        self.performance_history = deque(
            maxlen=100
        )

        self.daily_analyzer = (
            DailyAnalyzer(
                pattern_learner=(
                    self.pattern_learner
                )
            )
        )

        # Retained for dashboard read endpoints.
        # Auto-promotion is disabled below.
        self.backtester = (
            AdaptiveBacktester()
        )

        self.strategy_optimizer = (
            StrategyOptimizer()
        )

        self._last_nightly_date = None

        # ---------------------------------------------------------------------
        # Intelligence services
        # ---------------------------------------------------------------------

        from core.liquidity_map import (
            LiquidityMap,
        )
        from core.market_regime import (
            MarketRegimeDetector,
        )
        from core.news_engine import (
            NewsIntelligenceEngine,
        )
        from core.risk_engine import (
            DynamicRiskEngine,
        )
        from core.trade_brain import (
            TradeBrain,
        )

        self.regime_detector = (
            MarketRegimeDetector()
        )

        self.liquidity_map = (
            LiquidityMap()
        )

        # Retained for compatibility.
        # execute_and_record_trade currently applies a conservative wrapper
        # instead of trusting the old conflicting RiskEngine policies.
        self.risk_engine = (
            DynamicRiskEngine()
        )

        self.news_engine = (
            NewsIntelligenceEngine()
        )

        try:
            self.news_engine.start()

        except Exception as exc:
            self.logger.warning(
                "News engine failed to start: %s",
                exc,
            )

        self.safety_engine = (
            SafetyEngine()
        )

        self.session_engine = (
            SessionEngine()
        )

        self.brain_calibrator = (
            BrainCalibrator()
        )

        brain_threshold = (
            _finite_float(
                settings_manager.get(
                    "brain_threshold",
                    55.0,
                ),
                55.0,
            )
        )

        self.trade_brain = (
            TradeBrain(
                base_threshold=(
                    brain_threshold
                )
            )
        )

        self.starvation_analyzer = (
            StarvationAnalyzer()
        )

        self.skipped_stats = {
            "high_spread": 0,
            "news_filter": 0,
            "low_confidence": 0,
            "positions_limit": 0,
            "killzone_inactive": 0,
            "regime_filter": 0,
            "brain_filter": 0,
            "safety_halt": 0,
            "validator": 0,
        }

        self.training_in_progress = False

        self._closed_trades_count = 0

        self._sync_performance_stats()
        self._load_sentiment_cache()

        try:
            sentiment_analyzer.start()

        except Exception:
            pass

        self.dashboard = None

        if enable_dashboard:
            try:
                self.dashboard = (
                    WebDashboardServer(
                        self,
                        port=port,
                    )
                )

            except Exception as exc:
                self.logger.warning(
                    (
                        "Dashboard initialization "
                        "failed: %s"
                    ),
                    exc,
                )

        # ---------------------------------------------------------------------
        # IMPORTANT:
        #
        # Historical/background trainer intentionally not started.
        #
        # Existing trainer has causal/MTF validation problems and must not
        # automatically modify production model state.
        # ---------------------------------------------------------------------

        self._start_background_pattern_learning()

        self.logger.info(
            (
                "PulseViper engine initialized | "
                "paper_mode=%s | symbols=%s"
            ),
            settings_manager.get(
                "paper_mode",
                True,
            ),
            self.symbols,
        )

    # =========================================================================
    # LOGGING
    # =========================================================================

    @staticmethod
    def _configure_logging() -> None:
        os.makedirs(
            "logs",
            exist_ok=True,
        )

        root = logging.getLogger()

        if getattr(
            root,
            "_pulse_viper_configured",
            False,
        ):
            return

        formatter = logging.Formatter(
            (
                "%(asctime)s "
                "[%(levelname)s] "
                "%(name)s: %(message)s"
            )
        )

        stream_handler = (
            logging.StreamHandler()
        )

        stream_handler.setFormatter(
            formatter
        )

        file_handler = (
            RotatingFileHandler(
                "logs/engine.log",
                maxBytes=(
                    10 * 1024 * 1024
                ),
                backupCount=5,
                encoding="utf-8",
            )
        )

        file_handler.setFormatter(
            formatter
        )

        root.setLevel(
            logging.INFO
        )

        root.addHandler(
            stream_handler
        )

        root.addHandler(
            file_handler
        )

        setattr(
            root,
            "_pulse_viper_configured",
            True,
        )

    # =========================================================================
    # MANAGER
    # =========================================================================

    @property
    def trade_manager(self):
        if settings_manager.get(
            "paper_mode",
            True,
        ):
            return (
                self.paper_trade_manager
            )

        return (
            self.live_trade_manager
        )

    # =========================================================================
    # MT5 CONNECTION / SYMBOLS
    # =========================================================================

    def _initialize_connection(
        self,
    ) -> None:
        try:
            if not init_mt5():
                self.connected = False

                raise ConnectionError(
                    (
                        "Failed to initialize "
                        "MetaTrader 5"
                    )
                )

            self.connected = True

            account = mt5.account_info()

            if account is not None:
                self.logger.info(
                    (
                        "Connected MT5 account "
                        "%s | %s"
                    ),
                    getattr(
                        account,
                        "login",
                        "UNKNOWN",
                    ),
                    getattr(
                        account,
                        "server",
                        "UNKNOWN",
                    ),
                )

            symbols = mt5.symbols_get()

            self.broker_symbols = (
                [
                    str(s.name)
                    for s in symbols
                ]
                if symbols
                else []
            )

        except Exception:
            self.connected = False
            raise

    def _reconnect_if_needed(
        self,
    ) -> None:
        now = time.time()

        last = getattr(
            self,
            "_last_reconnect_check",
            0.0,
        )

        if now - last < 10.0:
            return

        self._last_reconnect_check = (
            now
        )

        try:
            if mt5.account_info() is None:
                self.connected = False

                self.logger.warning(
                    (
                        "MT5 connection lost; "
                        "attempting reconnect."
                    )
                )

                self._initialize_connection()

            else:
                self.connected = True

        except Exception as exc:
            self.connected = False

            self.logger.warning(
                "Reconnect failed: %s",
                exc,
            )

    def _auto_detect_symbols(
        self,
    ) -> List[str]:
        available = list(
            self.broker_symbols
        )

        if not available:
            symbols = mt5.symbols_get()

            available = (
                [
                    str(s.name)
                    for s in symbols
                ]
                if symbols
                else []
            )

            self.broker_symbols = (
                available
            )

        if not available:
            return [
                "EURUSD"
            ]

        account = mt5.account_info()

        currency = str(
            getattr(
                account,
                "currency",
                "USD",
            )
            if account
            else "USD"
        ).upper()

        server = str(
            getattr(
                account,
                "server",
                "",
            )
            if account
            else ""
        ).upper()

        is_cent = (
            currency == "USC"
            or "CENT" in server
        )

        gold = [
            symbol
            for symbol in available
            if (
                "XAUUSD"
                in symbol.upper()
                or "GOLD"
                in symbol.upper()
            )
        ]

        if gold:
            if is_cent:
                cent = [
                    s
                    for s in gold
                    if (
                        s.lower().endswith(
                            "c"
                        )
                        or s.lower().endswith(
                            ".c"
                        )
                    )
                ]

                if cent:
                    mt5.symbol_select(
                        cent[0],
                        True,
                    )

                    return [
                        cent[0]
                    ]

            preferred = (
                "XAUUSDm",
                "XAUUSD",
                "GOLD",
            )

            for pref in preferred:
                match = next(
                    (
                        symbol
                        for symbol in gold
                        if symbol.upper()
                        == pref.upper()
                    ),
                    None,
                )

                if match:
                    mt5.symbol_select(
                        match,
                        True,
                    )

                    return [
                        match
                    ]

            mt5.symbol_select(
                gold[0],
                True,
            )

            return [
                gold[0]
            ]

        for base in (
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "USDCHF",
        ):
            match = next(
                (
                    s
                    for s in available
                    if base
                    in s.upper()
                ),
                None,
            )

            if match:
                mt5.symbol_select(
                    match,
                    True,
                )

                return [
                    match
                ]

        return [
            available[0]
        ]

    def find_equivalent_symbol(
        self,
        requested: str,
        available_symbols: List[str],
    ) -> Optional[str]:
        if not requested:
            return None

        requested = str(
            requested
        ).strip()

        if requested in available_symbols:
            return requested

        req_upper = (
            requested.upper()
        )

        for symbol in available_symbols:
            if (
                symbol.upper()
                == req_upper
            ):
                return symbol

        is_gold = (
            "XAU"
            in req_upper
            or "GOLD"
            in req_upper
        )

        if is_gold:
            for symbol in (
                available_symbols
            ):
                upper = (
                    symbol.upper()
                )

                if (
                    (
                        "XAU"
                        in upper
                        and "USD"
                        in upper
                    )
                    or "GOLD"
                    in upper
                ):
                    return symbol

        req_clean = re.sub(
            r"[^A-Z0-9]",
            "",
            req_upper,
        )

        for symbol in available_symbols:
            clean = re.sub(
                r"[^A-Z0-9]",
                "",
                symbol.upper(),
            )

            if (
                clean == req_clean
                or clean.startswith(
                    req_clean
                )
                or req_clean.startswith(
                    clean
                )
            ):
                return symbol

        return None

    def _validate_symbols(
        self,
        symbols: List[str],
    ) -> List[str]:
        if not self.broker_symbols:
            broker = mt5.symbols_get()

            self.broker_symbols = (
                [
                    str(s.name)
                    for s in broker
                ]
                if broker
                else []
            )

        valid: List[
            str
        ] = []

        for requested in symbols:
            equivalent = (
                self.find_equivalent_symbol(
                    requested,
                    self.broker_symbols,
                )
            )

            candidate = (
                equivalent
                or str(requested)
            )

            if mt5.symbol_select(
                candidate,
                True,
            ):
                if (
                    candidate
                    not in valid
                ):
                    valid.append(
                        candidate
                    )

        if not valid:
            return (
                self._auto_detect_symbols()
            )

        return valid

    # =========================================================================
    # HISTORICAL PERFORMANCE CACHE
    # =========================================================================

    def _sync_performance_stats(
        self,
    ) -> None:
        try:
            memory = getattr(
                self.experience_memory,
                "memory",
                [],
            )

            for exp in memory:
                metadata = (
                    exp.get(
                        "metadata",
                        {},
                    )
                    if isinstance(
                        exp,
                        dict,
                    )
                    else {}
                )

                self.performance_history.append(
                    {
                        "timestamp": (
                            exp.get(
                                "timestamp"
                            )
                            if isinstance(
                                exp,
                                dict,
                            )
                            else None
                        ),
                        "symbol": (
                            metadata.get(
                                "symbol",
                                "UNKNOWN",
                            )
                        ),
                        "action": (
                            "BUY"
                            if (
                                isinstance(
                                    exp,
                                    dict,
                                )
                                and exp.get(
                                    "action"
                                )
                                == 1
                            )
                            else "SELL"
                        ),
                        "pnl": (
                            exp.get(
                                "reward",
                                0.0,
                            )
                            if isinstance(
                                exp,
                                dict,
                            )
                            else 0.0
                        ),
                        "close_reason": (
                            metadata.get(
                                "close_reason",
                                "CLOSED",
                            )
                        ),
                    }
                )

        except Exception as exc:
            self.logger.debug(
                (
                    "Performance cache "
                    "sync skipped: %s"
                ),
                exc,
            )

    # =========================================================================
    # SENTIMENT CACHE
    # =========================================================================

    def _load_sentiment_cache(
        self,
    ) -> None:
        path = (
            "configs/"
            "sentiment_cache.json"
        )

        try:
            if not os.path.exists(
                path
            ):
                return

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as handle:
                payload = json.load(
                    handle
                )

            if not isinstance(
                payload,
                dict,
            ):
                return

            for key in (
                self.sentiment_cache
            ):
                self.sentiment_cache[
                    key
                ] = _finite_float(
                    payload.get(
                        key,
                        self.sentiment_cache[
                            key
                        ],
                    ),
                    self.sentiment_cache[
                        key
                    ],
                )

        except Exception as exc:
            self.logger.debug(
                (
                    "Sentiment cache "
                    "load failed: %s"
                ),
                exc,
            )

    # =========================================================================
    # SESSION HELPERS
    # =========================================================================

    def get_active_sessions(
        self,
    ) -> list:
        hour = datetime.now(
            timezone.utc
        ).hour

        sessions = []

        if (
            hour >= 22
            or hour < 7
        ):
            sessions.append(
                "Sydney"
            )

        if 0 <= hour < 9:
            sessions.append(
                "Asian"
            )

        if 8 <= hour < 17:
            sessions.append(
                "London"
            )

        if 13 <= hour < 22:
            sessions.append(
                "New York"
            )

        return sessions

    def is_killzone_active(
        self,
        symbol: Optional[str] = None,
    ) -> bool:
        if not bool(
            settings_manager.get(
                "killzone_filter_enabled",
                False,
            )
        ):
            return True

        symbol_upper = (
            str(symbol).upper()
            if symbol
            else ""
        )

        if any(
            crypto
            in symbol_upper
            for crypto in (
                "BTC",
                "ETH",
                "SOL",
                "LTC",
                "XRP",
                "ADA",
            )
        ):
            return True

        hour = datetime.now(
            timezone.utc
        ).hour

        london_start, london_end = (
            self.config.LONDON_SESSION
        )

        ny_start, ny_end = (
            self.config.NY_SESSION
        )

        asian_start, asian_end = (
            getattr(
                self.config,
                "ASIAN_SESSION",
                (
                    0,
                    8,
                ),
            )
        )

        london = (
            london_start
            <= hour
            < london_end
        )

        ny = (
            ny_start
            <= hour
            < ny_end
        )

        asian = (
            asian_start
            <= hour
            < asian_end
        )

        london_enabled = bool(
            settings_manager.get(
                "london_session_enabled",
                True,
            )
        )

        ny_enabled = bool(
            settings_manager.get(
                "ny_session_enabled",
                True,
            )
        )

        asian_enabled = bool(
            settings_manager.get(
                "asian_session_enabled",
                False,
            )
        )

        if (
            not london_enabled
            and not ny_enabled
            and not asian_enabled
        ):
            return True

        return (
            (
                london
                and london_enabled
            )
            or (
                ny
                and ny_enabled
            )
            or (
                asian
                and asian_enabled
            )
        )

    # =========================================================================
    # REGRESSION
    # =========================================================================

    @staticmethod
    def calculate_regression_zscore(
        df_h1: pd.DataFrame,
        period: int = 100,
    ) -> float:
        try:
            if (
                df_h1 is None
                or len(df_h1)
                < period
            ):
                return 0.0

            prices = np.asarray(
                df_h1[
                    "close"
                ]
                .tail(period)
                .to_numpy(
                    dtype=np.float64
                ),
                dtype=np.float64,
            )

            x = np.arange(
                prices.size,
                dtype=np.float64,
            )

            coefficients = np.polyfit(
                x,
                prices,
                1,
            )

            slope = float(
                coefficients[0]
            )

            intercept = float(
                coefficients[1]
            )

            fitted = (
                slope * x
                + intercept
            )

            deviation = (
                prices
                - fitted
            )

            std = float(
                np.std(
                    deviation
                )
            )

            if std <= 1e-12:
                return 0.0

            return float(
                (
                    prices[-1]
                    - fitted[-1]
                )
                / std
            )

        except Exception:
            return 0.0

    # =========================================================================
    # CLOSED-CANDLE FEATURE FRAME
    # =========================================================================

    def _get_closed_feature_frame(
        self,
        symbol: str,
        timeframe_name: str,
    ) -> Optional[
        pd.DataFrame
    ]:
        """
        Return SMC feature frame generated strictly from CLOSED candles.

        Active forming candle is never passed into SMCIndicators.
        """
        config = (
            self.TIMEFRAME_CONFIG.get(
                timeframe_name
            )
        )

        if config is None:
            return None

        timeframe, bars, cooldown = (
            config
        )

        cache_key = (
            f"{symbol}_{timeframe_name}"
        )

        now = time.time()

        if (
            cache_key
            in self._tf_feature_cache
            and now
            - self._last_tf_check_times.get(
                cache_key,
                0.0,
            )
            < cooldown
        ):
            return (
                self._tf_feature_cache[
                    cache_key
                ]
            )

        self._last_tf_check_times[
            cache_key
        ] = now

        latest_closed = (
            mt5.copy_rates_from_pos(
                symbol,
                timeframe,
                1,
                1,
            )
        )

        latest_closed_time = (
            int(
                latest_closed[0][
                    "time"
                ]
            )
            if (
                latest_closed
                is not None
                and len(
                    latest_closed
                )
                > 0
            )
            else 0
        )

        if (
            latest_closed_time > 0
            and self._tf_closed_time.get(
                cache_key
            )
            == latest_closed_time
            and cache_key
            in self._tf_feature_cache
        ):
            return (
                self._tf_feature_cache[
                    cache_key
                ]
            )

        raw = fetch_ohlcv(
            symbol,
            timeframe,
            n=bars,
        )

        if (
            raw is None
            or len(raw) < 25
        ):
            return None

        # fetch_ohlcv includes current forming candle.
        closed = (
            raw.iloc[:-1]
            .copy()
        )

        if len(closed) < 20:
            return None

        swing_window = max(
            2,
            _finite_int(
                settings_manager.get(
                    "smc_swing_window",
                    3,
                ),
                3,
            ),
        )

        try:
            features = (
                SMCIndicators
                .compute_smc_features(
                    closed,
                    window=swing_window,
                )
            )

        except Exception as exc:
            self.logger.warning(
                (
                    "%s %s SMC feature "
                    "calculation failed: %s"
                ),
                symbol,
                timeframe_name,
                exc,
            )

            return None

        # ---------------------------------------------------------------------
        # Compatibility aliases.
        #
        # Current Quantum strategy still references old names.
        # Its dedicated replacement will remove this shim.
        # ---------------------------------------------------------------------

        if (
            "active_bias"
            in features.columns
        ):
            features[
                "bias"
            ] = features[
                "active_bias"
            ]

        if (
            "liq_sweep_type"
            in features.columns
        ):
            features[
                "sweep_type"
            ] = features[
                "liq_sweep_type"
            ]

        self._tf_feature_cache[
            cache_key
        ] = features

        if latest_closed_time > 0:
            self._tf_closed_time[
                cache_key
            ] = latest_closed_time

        return features

    # =========================================================================
    # LEVEL CACHE
    # =========================================================================

    def _update_daily_levels(
        self,
        symbol: str,
        df_d1: Optional[
            pd.DataFrame
        ],
    ) -> None:
        now = time.time()

        if (
            symbol
            in self.pdh_cache
            and now
            - self._last_daily_levels_time.get(
                symbol,
                0.0,
            )
            < 900.0
        ):
            return

        try:
            if (
                df_d1 is not None
                and len(df_d1) >= 1
            ):
                # df_d1 is already CLOSED only.
                previous_day = (
                    df_d1.iloc[-1]
                )

                self.pdh_cache[
                    symbol
                ] = _finite_float(
                    previous_day[
                        "high"
                    ]
                )

                self.pdl_cache[
                    symbol
                ] = _finite_float(
                    previous_day[
                        "low"
                    ]
                )

            weekly = (
                mt5.copy_rates_from_pos(
                    symbol,
                    mt5.TIMEFRAME_W1,
                    1,
                    1,
                )
            )

            if (
                weekly is not None
                and len(weekly) > 0
            ):
                self.pwh_cache[
                    symbol
                ] = _finite_float(
                    weekly[0][
                        "high"
                    ]
                )

                self.pwl_cache[
                    symbol
                ] = _finite_float(
                    weekly[0][
                        "low"
                    ]
                )

            self._last_daily_levels_time[
                symbol
            ] = now

        except Exception as exc:
            self.logger.debug(
                (
                    "Daily/weekly level "
                    "update failed: %s"
                ),
                exc,
            )

    # =========================================================================
    # TECHNICAL SENTIMENT
    # =========================================================================

    def _update_technical_sentiment(
        self,
        symbol: str,
        frames: Dict[
            str,
            Optional[pd.DataFrame],
        ],
    ) -> None:
        ttl = {
            "d1": 3600.0,
            "h4": 1200.0,
            "h1": 600.0,
            "m30": 300.0,
            "m15": 60.0,
            "m5": 30.0,
            "m1": 15.0,
        }

        now = time.time()

        changed = False

        for key in (
            "d1",
            "h4",
            "h1",
            "m30",
            "m15",
            "m5",
            "m1",
        ):
            frame = frames.get(
                key.upper()
            )

            cache_key = (
                f"{symbol}_{key}"
            )

            if (
                now
                < self.sentiment_cache_expiry.get(
                    cache_key,
                    0.0,
                )
            ):
                continue

            if (
                frame is None
                or len(frame) < 50
            ):
                continue

            try:
                self.sentiment_cache[
                    key
                ] = _finite_float(
                    sentiment_analyzer
                    .calculate_technical_sentiment(
                        frame
                    )
                )

                self.sentiment_cache_expiry[
                    cache_key
                ] = (
                    now
                    + ttl[key]
                )

                changed = True

            except Exception:
                continue

        if not changed:
            return

        try:
            with open(
                "configs/"
                "sentiment_cache.json",
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    self.sentiment_cache,
                    handle,
                    indent=2,
                )

        except Exception:
            pass

    # =========================================================================
    # VOLUME / ORDER FLOW CACHE
    # =========================================================================

    def _update_volume_cache(
        self,
        symbol: str,
        df_m1: pd.DataFrame,
    ) -> None:
        now = time.time()

        if (
            now
            - self._last_volume_calc_time.get(
                symbol,
                0.0,
            )
            < 10.0
        ):
            return

        try:
            rvol = (
                VolumeAnalyzer
                .calculate_rvol_latest(
                    df_m1,
                    period=20,
                )
            )

            buy_raw, sell_raw = (
                VolumeAnalyzer
                .calculate_buying_selling_pressure_latest(
                    df_m1
                )
            )

            total = (
                _finite_float(
                    buy_raw
                )
                + _finite_float(
                    sell_raw
                )
            )

            if total > 0.0:
                buy_pct = (
                    _finite_float(
                        buy_raw
                    )
                    / total
                    * 100.0
                )

                sell_pct = (
                    _finite_float(
                        sell_raw
                    )
                    / total
                    * 100.0
                )

            else:
                buy_pct = 50.0
                sell_pct = 50.0

            # Keep profile available for API compatibility.
            # Frontend replacement will keep it OFF by default.
            profile = (
                VolumeAnalyzer
                .calculate_volume_profile(
                    df_m1,
                    lookback=min(
                        100,
                        len(df_m1),
                    ),
                    bins=20,
                )
            )

            try:
                ofi = (
                    self.liquidity_map
                    .calculate_order_flow_imbalance(
                        symbol,
                        lookback_seconds=300,
                    )
                )

            except Exception:
                ofi = 0.0

            self.volume_cache = {
                "rvol": (
                    _finite_float(
                        rvol,
                        1.0,
                    )
                ),
                "buy_pressure": (
                    _finite_float(
                        buy_pct,
                        50.0,
                    )
                ),
                "sell_pressure": (
                    _finite_float(
                        sell_pct,
                        50.0,
                    )
                ),
                "profile": (
                    profile
                    if isinstance(
                        profile,
                        dict,
                    )
                    else {}
                ),
                "ofi": (
                    _finite_float(
                        ofi
                    )
                ),
            }

            self._last_volume_calc_time[
                symbol
            ] = now

        except Exception as exc:
            self.logger.debug(
                (
                    "Volume cache update "
                    "failed: %s"
                ),
                exc,
            )

    # =========================================================================
    # STRATEGY EVALUATION
    # =========================================================================

    def _evaluate_strategies(
        self,
        symbol: str,
        frames: Dict[
            str,
            Optional[pd.DataFrame],
        ],
        current_price: float,
        atr: float,
        htf_bias: int,
        regime_name: str,
        sentiment_payload: Dict[
            str,
            Any,
        ],
    ) -> Dict[str, Any]:
        """
        Run each existing strategy independently.

        A single strategy exception cannot crash the market cycle.
        """
        df_d1 = frames.get(
            "D1"
        )
        df_h4 = frames.get(
            "H4"
        )
        df_h1 = frames.get(
            "H1"
        )
        df_m30 = frames.get(
            "M30"
        )
        df_m15 = frames.get(
            "M15"
        )
        df_m5 = frames.get(
            "M5"
        )
        df_m1 = frames.get(
            "M1"
        )

        result: Dict[
            str,
            Any,
        ] = {}

        def store(
            prefix: str,
            action: Any,
            sl: Any,
            tp: Any,
            metadata: Any,
            strategy_regime: Any = None,
        ) -> None:
            result[
                f"{prefix}_action"
            ] = (
                str(action).upper()
                if action
                in (
                    "BUY",
                    "SELL",
                )
                else None
            )

            result[
                f"{prefix}_sl"
            ] = _finite_float(
                sl
            )

            result[
                f"{prefix}_tp"
            ] = _finite_float(
                tp
            )

            result[
                f"{prefix}_metadata"
            ] = (
                metadata
                if isinstance(
                    metadata,
                    dict,
                )
                else {}
            )

            if (
                strategy_regime
                is not None
            ):
                result[
                    f"{prefix}_regime"
                ] = str(
                    strategy_regime
                )

        # ---------------------------------------------------------------------
        # Fib
        # ---------------------------------------------------------------------

        try:
            action, strategy_regime, sl, tp, meta = (
                FibRetestStrategy
                .evaluate_retest(
                    df_context=cast(
                        pd.DataFrame,
                        df_m15,
                    ),
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    sentiment_cache=(
                        sentiment_payload
                    ),
                    htf_bias=htf_bias,
                    df_ltf=df_m1,
                )
            )

            store(
                "fib",
                action,
                sl,
                tp,
                meta,
                strategy_regime,
            )

        except Exception as exc:
            self.logger.debug(
                "Fib strategy: %s",
                exc,
            )

            store(
                "fib",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # CRT
        # ---------------------------------------------------------------------

        try:
            action, strategy_regime, sl, tp, meta = (
                CrtTbsStrategy
                .evaluate_crt_tbs(
                    df_d1=df_d1,
                    df_h4=df_h4,
                    df_h1=df_h1,
                    df_m15=df_m15,
                    df_m5=df_m5,
                    df_m1=df_m1,
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    sentiment_cache=(
                        sentiment_payload
                    ),
                    htf_bias=htf_bias,
                    symbol=symbol,
                    regime=regime_name,
                )
            )

            store(
                "crt",
                action,
                sl,
                tp,
                meta,
                strategy_regime,
            )

        except Exception as exc:
            self.logger.debug(
                "CRT strategy: %s",
                exc,
            )

            store(
                "crt",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # Raja
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                RajaStrategy.evaluate_raja(
                    df_m15=df_m15,
                    df_m30=df_m30,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "raja",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "Raja strategy: %s",
                exc,
            )

            store(
                "raja",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # ICT
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                IctStrategy.evaluate_ict(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=current_price,
                    atr=atr,
                    htf_bias=htf_bias,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "ict",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "ICT strategy: %s",
                exc,
            )

            store(
                "ict",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # Bank
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                BankStrategy.evaluate_bank(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "bank",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "Bank strategy: %s",
                exc,
            )

            store(
                "bank",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # VSA
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                VsaStrategy.evaluate_vsa(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_h1=df_h1,
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "vsa",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "VSA strategy: %s",
                exc,
            )

            store(
                "vsa",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # AVC
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                AvcStrategy.evaluate_avc(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "avc",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "AVC strategy: %s",
                exc,
            )

            store(
                "avc",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # M1 scalp
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                M1ScalpingStrategy
                .evaluate_m1_scalping(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    current_price=current_price,
                    atr=atr,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "m1_scalping",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "M1 strategy: %s",
                exc,
            )

            store(
                "m1_scalping",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # VWAP
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                VwapStrategy.evaluate_vwap(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_h1=df_h1,
                    current_price=current_price,
                    atr=atr,
                    regime=regime_name,
                    htf_bias=htf_bias,
                )
            )

            store(
                "vwap",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "VWAP strategy: %s",
                exc,
            )

            store(
                "vwap",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # SMC
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                SmcConceptsStrategy
                .evaluate_smc(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=current_price,
                    atr=atr,
                    htf_bias=htf_bias,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "smc",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "SMC strategy: %s",
                exc,
            )

            store(
                "smc",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # AMD
        # ---------------------------------------------------------------------

        try:
            action, strategy_regime, sl, tp, meta = (
                AmdStrategy.evaluate_amd(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=current_price,
                    atr=atr,
                    htf_bias=htf_bias,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "amd",
                action,
                sl,
                tp,
                meta,
                strategy_regime,
            )

        except Exception as exc:
            self.logger.debug(
                "AMD strategy: %s",
                exc,
            )

            store(
                "amd",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # SRC
        # ---------------------------------------------------------------------

        try:
            action, strategy_regime, sl, tp, meta = (
                SrcStrategy.evaluate_src(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    current_price=current_price,
                    atr=atr,
                    htf_bias=htf_bias,
                    volume_cache=(
                        self.volume_cache
                    ),
                    regime=regime_name,
                )
            )

            store(
                "src",
                action,
                sl,
                tp,
                meta,
                strategy_regime,
            )

        except Exception as exc:
            self.logger.debug(
                "SRC strategy: %s",
                exc,
            )

            store(
                "src",
                None,
                0,
                0,
                {},
            )

        # ---------------------------------------------------------------------
        # Quantum
        # ---------------------------------------------------------------------

        try:
            action, sl, tp, meta = (
                QuantumViperStrategy
                .evaluate_quantum_viper(
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m15=df_m15,
                    df_h1=df_h1,
                    df_h4=df_h4,
                    df_d1=df_d1,
                    current_price=current_price,
                    atr=atr,
                    htf_bias=htf_bias,
                    volume_cache=(
                        self.volume_cache
                    ),
                    sentiment_cache=(
                        sentiment_payload
                    ),
                    regime=regime_name,
                    symbol=symbol,
                )
            )

            store(
                "quantum",
                action,
                sl,
                tp,
                meta,
            )

        except Exception as exc:
            self.logger.debug(
                "Quantum strategy: %s",
                exc,
            )

            store(
                "quantum",
                None,
                0,
                0,
                {},
            )

        return result

    # =========================================================================
    # FULL ANALYSIS
    # =========================================================================

    def run_multi_timeframe_analysis(
        self,
        symbol: str,
    ) -> Optional[
        Dict[str, Any]
    ]:
        try:
            cycle_id = (
                f"PV-CYCLE-{symbol}-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-"
                f"{uuid.uuid4().hex[:8]}"
            )

            frames: Dict[
                str,
                Optional[pd.DataFrame],
            ] = {}

            for timeframe_name in (
                self.TIMEFRAME_CONFIG
            ):
                frames[
                    timeframe_name
                ] = (
                    self._get_closed_feature_frame(
                        symbol,
                        timeframe_name,
                    )
                )

            df_d1 = frames.get(
                "D1"
            )
            df_h4 = frames.get(
                "H4"
            )
            df_h1 = frames.get(
                "H1"
            )
            df_m30 = frames.get(
                "M30"
            )
            df_m15 = frames.get(
                "M15"
            )
            df_m5 = frames.get(
                "M5"
            )
            df_m1 = frames.get(
                "M1"
            )

            if (
                df_m1 is None
                or len(df_m1) < 50
            ):
                return None

            if (
                df_h1 is None
                or len(df_h1) < 50
            ):
                return None

            tick = (
                mt5.symbol_info_tick(
                    symbol
                )
            )

            if tick is None:
                return None

            bid = _finite_float(
                tick.bid
            )

            ask = _finite_float(
                tick.ask
            )

            if (
                bid <= 0.0
                or ask <= 0.0
            ):
                return None

            market_mid = (
                bid + ask
            ) / 2.0

            # -----------------------------------------------------------------
            # News
            # -----------------------------------------------------------------

            news_locked = False
            news_reason = None

            if bool(
                settings_manager.get(
                    "news_filter_enabled",
                    True,
                )
            ):
                try:
                    news_locked, news_reason = (
                        self.news_engine
                        .is_execution_locked(
                            datetime.now(
                                timezone.utc
                            ),
                            _finite_int(
                                settings_manager.get(
                                    "news_lockout_minutes",
                                    5,
                                ),
                                5,
                            ),
                            _finite_int(
                                settings_manager.get(
                                    "news_cooldown_minutes",
                                    5,
                                ),
                                5,
                            ),
                            symbol=symbol,
                        )
                    )

                except Exception as exc:
                    self.logger.debug(
                        (
                            "News lock check "
                            "failed: %s"
                        ),
                        exc,
                    )

            # -----------------------------------------------------------------
            # Pair structure memory
            # -----------------------------------------------------------------

            try:
                from core.pair_structure_memory import (
                    pair_structure_memory,
                )

                pair_structure_memory.update_pair_structure(
                    symbol,
                    df_h1,
                    df_d1,
                )

            except Exception:
                pass

            # -----------------------------------------------------------------
            # Regime
            # -----------------------------------------------------------------

            try:
                regime = (
                    self.regime_detector
                    .detect_regime(
                        (
                            df_m15
                            if df_m15
                            is not None
                            else pd.DataFrame()
                        ),
                        _finite_float(
                            self.volume_cache.get(
                                "rvol",
                                1.0,
                            ),
                            1.0,
                        ),
                    )
                )

                regime_name = str(
                    getattr(
                        regime,
                        "name",
                        regime,
                    )
                ).upper()

            except Exception:
                regime_name = "RANGE"

            try:
                self.regime_detector.current_regime = (
                    regime_name
                )

            except Exception:
                pass

            # -----------------------------------------------------------------
            # Session
            # -----------------------------------------------------------------

            try:
                session_ctx = (
                    self.session_engine
                    .get_session_context(
                        symbol=symbol
                    )
                    or {}
                )

            except Exception:
                session_ctx = {}

            session_name = str(
                session_ctx.get(
                    "session_name",
                    "OFF",
                )
            )

            session_score = (
                _finite_float(
                    session_ctx.get(
                        "session_score",
                        0.0,
                    )
                )
            )

            # -----------------------------------------------------------------
            # Latest rows
            # -----------------------------------------------------------------

            def latest(
                name: str,
            ):
                frame = frames.get(
                    name
                )

                if (
                    frame is None
                    or len(frame) == 0
                ):
                    return None

                return frame.iloc[-1]

            latest_d1 = latest(
                "D1"
            )
            latest_h4 = latest(
                "H4"
            )
            latest_h1 = latest(
                "H1"
            )
            latest_m30 = latest(
                "M30"
            )
            latest_m15 = latest(
                "M15"
            )
            latest_m5 = latest(
                "M5"
            )
            latest_m1 = latest(
                "M1"
            )

            def bias_value(
                row: Any,
            ) -> int:
                if row is None:
                    return 0

                return _finite_int(
                    row.get(
                        "active_bias",
                        0,
                    )
                )

            d1_bias = bias_value(
                latest_d1
            )

            h4_bias = bias_value(
                latest_h4
            )

            h1_bias = bias_value(
                latest_h1
            )

            m30_bias = bias_value(
                latest_m30
            )

            m15_bias = bias_value(
                latest_m15
            )

            m5_bias = bias_value(
                latest_m5
            )

            m1_bias = bias_value(
                latest_m1
            )

            # -----------------------------------------------------------------
            # Conservative HTF hierarchy
            # -----------------------------------------------------------------

            if (
                d1_bias != 0
                and h4_bias
                == d1_bias
            ):
                htf_bias = d1_bias

            elif h4_bias != 0:
                htf_bias = h4_bias

            else:
                htf_bias = h1_bias

            # -----------------------------------------------------------------
            # Recent sweep
            # -----------------------------------------------------------------

            sweep_type = 0
            sweep_level = 0.0

            sweep_lookback = max(
                1,
                _finite_int(
                    settings_manager.get(
                        "smc_lookback_sweep",
                        20,
                    ),
                    20,
                ),
            )

            for name in (
                "M15",
                "H1",
            ):
                frame = frames.get(
                    name
                )

                if (
                    frame is None
                    or "liq_sweep_type"
                    not in frame.columns
                ):
                    continue

                recent = (
                    frame.tail(
                        sweep_lookback
                    )
                )

                for _, row in reversed(
                    list(
                        recent.iterrows()
                    )
                ):
                    value = _finite_int(
                        row.get(
                            "liq_sweep_type",
                            0,
                        )
                    )

                    if value == 0:
                        continue

                    sweep_type = value

                    sweep_level = (
                        _finite_float(
                            row.get(
                                "liq_sweep_level",
                                0.0,
                            )
                        )
                    )

                    break

                if sweep_type != 0:
                    break

            # -----------------------------------------------------------------
            # Recent MSS
            # -----------------------------------------------------------------

            mss_signal = 0

            mss_lookback = max(
                1,
                _finite_int(
                    settings_manager.get(
                        "smc_lookback_mss",
                        10,
                    ),
                    10,
                ),
            )

            for name in (
                "M5",
                "M1",
            ):
                frame = frames.get(
                    name
                )

                if (
                    frame is None
                    or "mss_signal"
                    not in frame.columns
                ):
                    continue

                recent = (
                    frame.tail(
                        mss_lookback
                    )
                )

                for _, row in reversed(
                    list(
                        recent.iterrows()
                    )
                ):
                    value = _finite_int(
                        row.get(
                            "mss_signal",
                            0,
                        )
                    )

                    if value != 0:
                        mss_signal = (
                            value
                        )

                        break

                if mss_signal != 0:
                    break

            # -----------------------------------------------------------------
            # Recent FVG
            # -----------------------------------------------------------------

            fvg_class = "none"
            fvg_type: Any = "none"
            fvg_top = 0.0
            fvg_bottom = 0.0

            if (
                df_m1 is not None
                and "fvg_class"
                in df_m1.columns
            ):
                lookback = max(
                    1,
                    _finite_int(
                        settings_manager.get(
                            "smc_fvg_lookback",
                            5,
                        ),
                        5,
                    ),
                )

                recent = (
                    df_m1.tail(
                        lookback
                    )
                )

                valid_fvg = recent[
                    recent[
                        "fvg_class"
                    ].astype(str)
                    .str.lower()
                    .ne("none")
                ]

                if len(valid_fvg) > 0:
                    row = (
                        valid_fvg.iloc[-1]
                    )

                    fvg_class = str(
                        row.get(
                            "fvg_class",
                            "none",
                        )
                    )

                    fvg_type = (
                        row.get(
                            "fvg_type",
                            "none",
                        )
                    )

                    fvg_top = (
                        _finite_float(
                            row.get(
                                "fvg_top",
                                0.0,
                            )
                        )
                    )

                    fvg_bottom = (
                        _finite_float(
                            row.get(
                                "fvg_bottom",
                                0.0,
                            )
                        )
                    )

            ref_row = (
                latest_m1
                if latest_m1
                is not None
                else latest_h1
            )

            atr = (
                _finite_float(
                    ref_row.get(
                        "atr",
                        0.0,
                    )
                    if ref_row
                    is not None
                    else 0.0
                )
            )

            if atr <= 0.0:
                info = mt5.symbol_info(
                    symbol
                )

                point = (
                    _finite_float(
                        getattr(
                            info,
                            "point",
                            0.01,
                        ),
                        0.01,
                    )
                )

                atr = max(
                    point * 15.0,
                    point,
                )

            # -----------------------------------------------------------------
            # Volume / technical context
            # -----------------------------------------------------------------

            self._update_volume_cache(
                symbol,
                df_m1,
            )

            self._update_technical_sentiment(
                symbol,
                frames,
            )

            self._update_daily_levels(
                symbol,
                df_d1,
            )

            # -----------------------------------------------------------------
            # Liquidity map
            # -----------------------------------------------------------------

            try:
                swept_pools = (
                    self.liquidity_map
                    .check_sweeps(
                        bid,
                        atr,
                    )
                )

            except Exception:
                swept_pools = []

            try:
                resting_pools = (
                    self.liquidity_map
                    .get_resting_pools()
                )

            except Exception:
                resting_pools = []

            # -----------------------------------------------------------------
            # VSA context
            # -----------------------------------------------------------------

            vsa_signals: List[
                str
            ] = []

            for frame in (
                df_m1,
                df_m5,
            ):
                if (
                    frame is None
                    or "atr"
                    not in frame.columns
                ):
                    continue

                try:
                    detected = (
                        VolumeAnalyzer
                        .detect_vsa_signals(
                            frame,
                            frame[
                                "atr"
                            ],
                            lookback=3,
                        )
                    )

                    for item in detected:
                        if isinstance(
                            item,
                            dict,
                        ):
                            label = str(
                                item.get(
                                    "pattern",
                                    "",
                                )
                            )

                        else:
                            label = str(
                                item
                            )

                        if (
                            label
                            and label
                            not in vsa_signals
                        ):
                            vsa_signals.append(
                                label
                            )

                except Exception:
                    continue

            # -----------------------------------------------------------------
            # TF alignment
            # -----------------------------------------------------------------

            def bias_label(
                value: int,
            ) -> str:
                if value > 0:
                    return "BULLISH"

                if value < 0:
                    return "BEARISH"

                return "NEUTRAL"

            tf_alignment = {
                "D1": {
                    "bias": d1_bias,
                    "label": (
                        bias_label(
                            d1_bias
                        )
                    ),
                },
                "H4": {
                    "bias": h4_bias,
                    "label": (
                        bias_label(
                            h4_bias
                        )
                    ),
                },
                "H1": {
                    "bias": h1_bias,
                    "label": (
                        bias_label(
                            h1_bias
                        )
                    ),
                },
                "M30": {
                    "bias": m30_bias,
                    "label": (
                        bias_label(
                            m30_bias
                        )
                    ),
                },
                "M15": {
                    "bias": m15_bias,
                    "label": (
                        "SWEEP"
                        if sweep_type
                        != 0
                        else bias_label(
                            m15_bias
                        )
                    ),
                },
                "M5": {
                    "bias": m5_bias,
                    "label": (
                        "MSS"
                        if mss_signal
                        != 0
                        else bias_label(
                            m5_bias
                        )
                    ),
                },
                "M1": {
                    "bias": m1_bias,
                    "label": (
                        bias_label(
                            m1_bias
                        )
                    ),
                },
                "htf_bias": (
                    htf_bias
                ),
                "aligned": bool(
                    htf_bias != 0
                    and mss_signal
                    == htf_bias
                ),
            }

            self._last_tf_alignment = (
                tf_alignment
            )

            # -----------------------------------------------------------------
            # Support/resistance/OB
            # -----------------------------------------------------------------

            support = (
                _finite_float(
                    ref_row.get(
                        "support",
                        0.0,
                    )
                    if ref_row
                    is not None
                    else 0.0
                )
            )

            resistance = (
                _finite_float(
                    ref_row.get(
                        "resistance",
                        0.0,
                    )
                    if ref_row
                    is not None
                    else 0.0
                )
            )

            ob_meta: Dict[
                str,
                Any,
            ] = {}

            if latest_h1 is not None:
                ob_top = _finite_float(
                    latest_h1.get(
                        "ob_top",
                        0.0,
                    )
                )

                ob_bottom = (
                    _finite_float(
                        latest_h1.get(
                            "ob_bottom",
                            0.0,
                        )
                    )
                )

                if (
                    ob_top > 0.0
                    and ob_bottom > 0.0
                ):
                    ob_meta = {
                        "ob_top": (
                            max(
                                ob_top,
                                ob_bottom,
                            )
                        ),
                        "ob_bottom": (
                            min(
                                ob_top,
                                ob_bottom,
                            )
                        ),
                        "ob_direction": (
                            str(
                                latest_h1.get(
                                    "ob_direction",
                                    (
                                        "bullish"
                                        if htf_bias
                                        > 0
                                        else "bearish"
                                    ),
                                )
                            )
                        ),
                    }

            sentiment_payload = dict(
                self.sentiment_cache
            )

            sentiment_payload.update(
                {
                    "pdh": (
                        self.pdh_cache.get(
                            symbol,
                            0.0,
                        )
                    ),
                    "pdl": (
                        self.pdl_cache.get(
                            symbol,
                            0.0,
                        )
                    ),
                    "pwh": (
                        self.pwh_cache.get(
                            symbol,
                            0.0,
                        )
                    ),
                    "pwl": (
                        self.pwl_cache.get(
                            symbol,
                            0.0,
                        )
                    ),
                }
            )

            strategy_outputs = (
                self._evaluate_strategies(
                    symbol=symbol,
                    frames=frames,
                    current_price=market_mid,
                    atr=atr,
                    htf_bias=htf_bias,
                    regime_name=(
                        regime_name
                    ),
                    sentiment_payload=(
                        sentiment_payload
                    ),
                )
            )

            features = {
                "active_bias": (
                    htf_bias
                ),
                "d1_bias": d1_bias,
                "h4_bias": h4_bias,
                "h1_bias": h1_bias,
                "m15_bias": m15_bias,
                "m5_bias": m5_bias,
                "m1_bias": m1_bias,
                "liq_sweep_type": (
                    sweep_type
                ),
                "mss_signal": (
                    mss_signal
                ),
                "fvg_class": (
                    fvg_class
                ),
                "support": support,
                "resistance": (
                    resistance
                ),
                "atr": atr,
                "atr_pct": (
                    _finite_float(
                        ref_row.get(
                            "atr_pct",
                            0.0,
                        )
                        if ref_row
                        is not None
                        else 0.0
                    )
                ),
                "volatility": (
                    _finite_float(
                        ref_row.get(
                            "volatility",
                            0.0,
                        )
                        if ref_row
                        is not None
                        else 0.0
                    )
                ),
                "ob_reaction_signal": (
                    _finite_float(
                        ref_row.get(
                            "ob_reaction_signal",
                            0.0,
                        )
                        if ref_row
                        is not None
                        else 0.0
                    )
                ),
                "sr_reaction_signal": (
                    _finite_float(
                        ref_row.get(
                            "sr_reaction_signal",
                            0.0,
                        )
                        if ref_row
                        is not None
                        else 0.0
                    )
                ),
                "retest_pullback_signal": (
                    _finite_float(
                        ref_row.get(
                            "retest_pullback_signal",
                            0.0,
                        )
                        if ref_row
                        is not None
                        else 0.0
                    )
                ),
                "trend_shift_signal": (
                    _finite_float(
                        ref_row.get(
                            "trend_shift_signal",
                            0.0,
                        )
                        if ref_row
                        is not None
                        else 0.0
                    )
                ),
                "rvol": (
                    _finite_float(
                        self.volume_cache.get(
                            "rvol",
                            1.0,
                        ),
                        1.0,
                    )
                ),
                "buy_pressure": (
                    _finite_float(
                        self.volume_cache.get(
                            "buy_pressure",
                            50.0,
                        ),
                        50.0,
                    )
                ),
                "sell_pressure": (
                    _finite_float(
                        self.volume_cache.get(
                            "sell_pressure",
                            50.0,
                        ),
                        50.0,
                    )
                ),
                "ofi_imbalance": (
                    _finite_float(
                        self.volume_cache.get(
                            "ofi",
                            0.0,
                        )
                    )
                ),
                "hour": (
                    datetime.now(
                        timezone.utc
                    ).hour
                ),
                "price": market_mid,
                "tf_aligned": (
                    tf_alignment[
                        "aligned"
                    ]
                ),
                "market_regime": (
                    regime_name
                ),
                "news_locked": bool(
                    news_locked
                ),
                "vsa_signals": (
                    list(
                        vsa_signals
                    )
                ),
                "timestamp": (
                    int(
                        df_m1.index[
                            -1
                        ].timestamp()
                    )
                    if isinstance(
                        df_m1.index[-1],
                        pd.Timestamp,
                    )
                    else time.time()
                ),
            }

            analysis: Dict[
                str,
                Any,
            ] = {
                "cycle_id": (
                    cycle_id
                ),
                "symbol": symbol,
                "price": (
                    market_mid
                ),
                "bid": bid,
                "ask": ask,
                "news_locked": (
                    bool(
                        news_locked
                    )
                ),
                "news_lockout_reason": (
                    news_reason
                ),
                "market_regime": (
                    regime_name
                ),
                "swept_pools": (
                    swept_pools
                ),
                "resting_pools": (
                    resting_pools
                ),
                "regression_zscore": (
                    self.calculate_regression_zscore(
                        df_h1
                    )
                ),
                "ofi_imbalance": (
                    _finite_float(
                        self.volume_cache.get(
                            "ofi",
                            0.0,
                        )
                    )
                ),
                "htf_bias": (
                    htf_bias
                ),
                "d1_bias": d1_bias,
                "h4_bias": h4_bias,
                "h1_bias": h1_bias,
                "m30_bias": (
                    m30_bias
                ),
                "m15_bias": (
                    m15_bias
                ),
                "m5_bias": (
                    m5_bias
                ),
                "m1_bias": (
                    m1_bias
                ),
                "m15_sweep_type": (
                    sweep_type
                ),
                "m15_sweep_level": (
                    sweep_level
                ),
                "m5_mss_signal": (
                    mss_signal
                ),
                "m5_fvg_class": (
                    fvg_class
                ),
                "m5_fvg_type": (
                    fvg_type
                ),
                "m5_fvg_top": (
                    fvg_top
                ),
                "m5_fvg_bottom": (
                    fvg_bottom
                ),
                "support": support,
                "resistance": (
                    resistance
                ),
                "atr": atr,
                "atr_pct": (
                    features[
                        "atr_pct"
                    ]
                ),
                "volatility": (
                    features[
                        "volatility"
                    ]
                ),
                "buy_pressure": (
                    features[
                        "buy_pressure"
                    ]
                ),
                "sell_pressure": (
                    features[
                        "sell_pressure"
                    ]
                ),
                "vsa_signals": (
                    vsa_signals
                ),
                "session_name": (
                    session_name
                ),
                "session_score": (
                    session_score
                ),
                "tf_alignment": (
                    tf_alignment
                ),
                "ob_metadata": (
                    ob_meta
                ),
                "features": (
                    features
                ),
                # Closed feature frames.
                "df_ltf": df_m1,
                "df_m1": df_m1,
                "df_m5": df_m5,
                "df_m15": df_m15,
                "df_m30": df_m30,
                "df_h1": df_h1,
                "df_h4": df_h4,
                "df_d1": df_d1,
                # Decision state: populated ONCE later.
                "ai_signal_snapshot": None,
                "target_setup": None,
                "entry_decision": None,
                "decision_evaluated": (
                    False
                ),
                "brain_score": 0.0,
                "brain_direction": (
                    None
                ),
                "brain_threshold": (
                    _finite_float(
                        settings_manager.get(
                            "brain_threshold",
                            55.0,
                        ),
                        55.0,
                    )
                ),
                "brain_reason_map": {},
                "brain_label": (
                    "SCANNING"
                ),
                "brain_color": (
                    "#8b9bb4"
                ),
                "brain_tier1": 0.0,
                "brain_tier2": 0.0,
                "brain_tier3": 0.0,
                "brain_block_reason": (
                    None
                ),
            }

            analysis.update(
                strategy_outputs
            )

            # Dashboard compatibility.
            crt_meta = (
                analysis.get(
                    "crt_metadata",
                    {}
                )
                or {}
            )

            analysis[
                "crt_low"
            ] = _finite_float(
                crt_meta.get(
                    "crt_low",
                    0.0,
                )
            )

            analysis[
                "crt_high"
            ] = _finite_float(
                crt_meta.get(
                    "crt_high",
                    0.0,
                )
            )

            return analysis

        except Exception as exc:
            self.logger.exception(
                (
                    "Multi-timeframe "
                    "analysis failed for %s: %s"
                ),
                symbol,
                exc,
            )

            return None

    # =========================================================================
    # AI SNAPSHOT
    # =========================================================================

    def _get_ai_signal_once(
        self,
        analysis: Dict[
            str,
            Any,
        ],
        strategy_name: Optional[
            str
        ] = None,
        action: Optional[
            str
        ] = None,
    ) -> Dict[str, Any]:
        existing = analysis.get(
            "ai_signal_snapshot"
        )

        if isinstance(
            existing,
            dict,
        ):
            return existing

        try:
            signal = (
                self.pattern_learner
                .get_trading_signal(
                    analysis[
                        "symbol"
                    ],
                    analysis.get(
                        "features",
                        {},
                    ),
                    df_ltf=(
                        analysis.get(
                            "df_ltf"
                        )
                    ),
                    df_m5=(
                        analysis.get(
                            "df_m5"
                        )
                    ),
                    df_h1=(
                        analysis.get(
                            "df_h1"
                        )
                    ),
                    candidate_strategy=(
                        strategy_name
                    ),
                    candidate_action=(
                        action
                    ),
                )
            )

            if not isinstance(
                signal,
                dict,
            ):
                signal = {}

        except TypeError:
            # Compatibility with older signature.
            try:
                signal = (
                    self.pattern_learner
                    .get_trading_signal(
                        analysis[
                            "symbol"
                        ],
                        analysis.get(
                            "features",
                            {},
                        ),
                        df_ltf=(
                            analysis.get(
                                "df_ltf"
                            )
                        ),
                        df_m5=(
                            analysis.get(
                                "df_m5"
                            )
                        ),
                        df_h1=(
                            analysis.get(
                                "df_h1"
                            )
                        ),
                    )
                )

                if not isinstance(
                    signal,
                    dict,
                ):
                    signal = {}

            except Exception:
                signal = {}

        except Exception as exc:
            self.logger.debug(
                "AI snapshot failed: %s",
                exc,
            )

            signal = {}

        signal.setdefault(
            "confidence",
            0.5,
        )

        signal.setdefault(
            "model_ready",
            False,
        )

        signal.setdefault(
            "model_source",
            "NO_VALID_MODEL",
        )

        signal.setdefault(
            "detected_patterns",
            [],
        )

        signal.setdefault(
            "smc_patterns",
            [],
        )

        analysis[
            "ai_signal_snapshot"
        ] = signal

        return signal

    # =========================================================================
    # CANDIDATES
    # =========================================================================

    def _collect_strategy_candidates(
        self,
        analysis: Dict[
            str,
            Any,
        ],
    ) -> List[
        Dict[str, Any]
    ]:
        candidates = []

        regime = str(
            analysis.get(
                "market_regime",
                "RANGE",
            )
        ).upper()

        for prefix in (
            self.STRATEGY_PREFIXES
        ):
            name = (
                prefix.upper()
            )

            action = analysis.get(
                f"{prefix}_action"
            )

            if action not in (
                "BUY",
                "SELL",
            ):
                continue

            # -----------------------------------------------------------------
            # Regime preference.
            #
            # Gold does NOT bypass these filters anymore.
            # -----------------------------------------------------------------

            if (
                regime == "TRENDING"
                and name
                not in self.TREND_STRATEGIES
            ):
                continue

            if (
                regime in (
                    "RANGE",
                    "RANGING",
                )
                and name
                not in self.RANGE_STRATEGIES
            ):
                continue

            sl = _finite_float(
                analysis.get(
                    f"{prefix}_sl",
                    0.0,
                )
            )

            tp = _finite_float(
                analysis.get(
                    f"{prefix}_tp",
                    0.0,
                )
            )

            if (
                sl <= 0.0
                or tp <= 0.0
            ):
                continue

            metadata = analysis.get(
                f"{prefix}_metadata",
                {},
            )

            candidates.append(
                {
                    "name": name,
                    "prefix": prefix,
                    "action": action,
                    "sl": sl,
                    "tp": tp,
                    "metadata": (
                        metadata
                        if isinstance(
                            metadata,
                            dict,
                        )
                        else {}
                    ),
                }
            )

        return candidates

    def _can_trade_direction(
        self,
        symbol: str,
        action: str,
    ) -> bool:
        positions = (
            self.trade_manager
            .positions
        )

        if not settings_manager.get(
            "hedging_mode",
            False,
        ):
            return len(
                positions
            ) == 0

        return not any(
            (
                pos.symbol
                == symbol
                and pos.action
                == action
            )
            for pos
            in positions.values()
        )

    # =========================================================================
    # ENTRY DECISION
    # =========================================================================

    def evaluate_entry_rules(
        self,
        analysis: Dict[
            str,
            Any,
        ],
        is_live_tick: bool = False,
    ) -> Optional[
        Tuple[
            str,
            float,
            float,
            str,
        ]
    ]:
        """
        Evaluate one cached analysis object ONCE.

        Calling again for the same analysis returns the existing immutable
        decision state instead of executing PatternLearner/TradeBrain again.
        """
        if not analysis:
            return None

        # ---------------------------------------------------------------------
        # Already evaluated this exact market analysis.
        # ---------------------------------------------------------------------

        if bool(
            analysis.get(
                "decision_evaluated",
                False,
            )
        ):
            existing = analysis.get(
                "entry_decision"
            )

            if not isinstance(
                existing,
                dict,
            ):
                return None

            if not existing.get(
                "allowed",
                False,
            ):
                return None

            return (
                str(
                    existing[
                        "action"
                    ]
                ),
                float(
                    existing[
                        "sl"
                    ]
                ),
                float(
                    existing[
                        "tp"
                    ]
                ),
                str(
                    existing[
                        "strategy"
                    ]
                ),
            )

        analysis[
            "decision_evaluated"
        ] = True

        symbol = str(
            analysis.get(
                "symbol",
                "",
            )
        )

        bid = _finite_float(
            analysis.get(
                "bid",
                0.0,
            )
        )

        ask = _finite_float(
            analysis.get(
                "ask",
                0.0,
            )
        )

        if (
            not symbol
            or bid <= 0.0
            or ask <= 0.0
        ):
            analysis[
                "entry_decision"
            ] = {
                "allowed": False,
                "reason": (
                    "INVALID_MARKET_PRICE"
                ),
            }

            return None

        # ---------------------------------------------------------------------
        # Candle-level duplicate guard
        # ---------------------------------------------------------------------

        candle = (
            self.last_candle_times.get(
                symbol,
                0,
            )
        )

        if (
            candle > 0
            and (
                candle
                == self.last_entry_candle.get(
                    symbol,
                    0,
                )
                or candle
                == self.last_close_candle.get(
                    symbol,
                    0,
                )
            )
        ):
            analysis[
                "entry_decision"
            ] = {
                "allowed": False,
                "reason": (
                    "CANDLE_COOLDOWN"
                ),
            }

            return None

        ai_signal = (
            self._get_ai_signal_once(
                analysis
            )
        )

        confidence = (
            _finite_float(
                ai_signal.get(
                    "confidence",
                    0.5,
                ),
                0.5,
            )
        )

        candidates = (
            self._collect_strategy_candidates(
                analysis
            )
        )

        scored: List[
            Dict[str, Any]
        ] = []

        for candidate in candidates:
            action = str(
                candidate[
                    "action"
                ]
            )

            if not (
                self._can_trade_direction(
                    symbol,
                    action,
                )
            ):
                continue

            try:
                brain = (
                    self.trade_brain
                    .evaluate(
                        analysis=analysis,
                        strategy_action=(
                            action
                        ),
                        ai_confidence=(
                            confidence
                        ),
                        session_score=(
                            _finite_float(
                                analysis.get(
                                    "session_score",
                                    0.0,
                                )
                            )
                        ),
                        strategy_name=(
                            str(
                                candidate[
                                    "name"
                                ]
                            )
                        ),
                    )
                )

            except Exception as exc:
                self.logger.debug(
                    "TradeBrain error: %s",
                    exc,
                )

                continue

            if (
                brain is not None
                and brain.passed
            ):
                scored.append(
                    {
                        "candidate": (
                            candidate
                        ),
                        "brain": brain,
                    }
                )

        scored.sort(
            key=lambda item: (
                item[
                    "brain"
                ].brain_score
            ),
            reverse=True,
        )

        selected = (
            scored[0]
            if scored
            else None
        )

        # ---------------------------------------------------------------------
        # Brain telemetry even when no candidate passed.
        # ---------------------------------------------------------------------

        brain_result: Optional[
            BrainResult
        ] = None

        if selected is not None:
            brain_result = cast(
                BrainResult,
                selected[
                    "brain"
                ],
            )

        else:
            try:
                brain_result = (
                    self.trade_brain
                    .evaluate(
                        analysis=analysis,
                        strategy_action=None,
                        ai_confidence=(
                            confidence
                        ),
                        session_score=(
                            _finite_float(
                                analysis.get(
                                    "session_score",
                                    0.0,
                                )
                            )
                        ),
                    )
                )

            except Exception:
                brain_result = None

        if brain_result is not None:
            analysis[
                "brain_score"
            ] = _finite_float(
                brain_result.brain_score
            )

            analysis[
                "brain_direction"
            ] = (
                brain_result
                .brain_direction
            )

            analysis[
                "brain_threshold"
            ] = _finite_float(
                brain_result.threshold
            )

            analysis[
                "brain_reason_map"
            ] = (
                brain_result.reason_map
            )

            analysis[
                "brain_tier1"
            ] = _finite_float(
                brain_result.tier1_score
            )

            analysis[
                "brain_tier2"
            ] = _finite_float(
                brain_result.tier2_score
            )

            analysis[
                "brain_tier3"
            ] = _finite_float(
                brain_result.tier3_score
            )

            analysis[
                "brain_block_reason"
            ] = (
                brain_result
                .block_reason
            )

            try:
                analysis[
                    "brain_label"
                ] = (
                    self.trade_brain
                    .get_score_label(
                        brain_result
                        .brain_score
                    )
                )

                analysis[
                    "brain_color"
                ] = (
                    self.trade_brain
                    .get_color_zone(
                        brain_result
                        .brain_score
                    )
                )

            except Exception:
                pass

        # ---------------------------------------------------------------------
        # Block helper
        # ---------------------------------------------------------------------

        def block(
            reason: str,
        ):
            analysis[
                "brain_block_reason"
            ] = reason

            analysis[
                "target_setup"
            ] = None

            analysis[
                "entry_decision"
            ] = {
                "allowed": False,
                "reason": reason,
            }

            if is_live_tick:
                try:
                    self.starvation_analyzer.record_signal_blocked(
                        reason
                    )
                except Exception:
                    pass

            return None

        # ---------------------------------------------------------------------
        # Hard safety gates BEFORE publishing target setup.
        # ---------------------------------------------------------------------

        try:
            allowed, safety_reason = (
                self.safety_engine
                .check_entry_allowed()
            )

        except Exception as exc:
            self.logger.error(
                (
                    "SafetyEngine failed; "
                    "entry blocked: %s"
                ),
                exc,
            )

            allowed = False
            safety_reason = (
                "SAFETY_ENGINE_ERROR"
            )

        if not allowed:
            self.skipped_stats[
                "safety_halt"
            ] += 1

            analysis[
                "brain_label"
            ] = "SAFETY HALT"

            return block(
                str(
                    safety_reason
                    or "SAFETY_HALT"
                )
            )

        strict_mode = bool(
            settings_manager.get(
                "strict_mode",
                False,
            )
        )

        if (
            strict_mode
            and not settings_manager.get(
                "paper_mode",
                True,
            )
            and not self.is_killzone_active(
                symbol
            )
        ):
            self.skipped_stats[
                "killzone_inactive"
            ] += 1

            return block(
                "KILLZONE_INACTIVE"
            )

        if (
            strict_mode
            and analysis.get(
                "news_locked",
                False,
            )
        ):
            self.skipped_stats[
                "news_filter"
            ] += 1

            return block(
                "NEWS_LOCKOUT"
            )

        regime = str(
            analysis.get(
                "market_regime",
                "RANGE",
            )
        ).upper()

        if (
            strict_mode
            and bool(
                settings_manager.get(
                    "dynamic_regime_filter",
                    False,
                )
            )
            and regime == "CHAOTIC"
        ):
            self.skipped_stats[
                "regime_filter"
            ] += 1

            return block(
                "CHAOTIC_REGIME"
            )

        if selected is None:
            analysis[
                "brain_label"
            ] = "SCANNING"

            analysis[
                "entry_decision"
            ] = {
                "allowed": False,
                "reason": (
                    "NO_VALID_STRATEGY"
                ),
            }

            return None

        candidate = cast(
            Dict[str, Any],
            selected[
                "candidate"
            ],
        )

        setup_name = str(
            candidate[
                "name"
            ]
        )

        disabled = [
            str(item).upper()
            for item
            in (
                settings_manager.get(
                    "disabled_setups",
                    [],
                )
                or []
            )
        ]

        if (
            setup_name.upper()
            in disabled
        ):
            return block(
                "DISABLED_SETUP"
            )

        action = str(
            candidate[
                "action"
            ]
        ).upper()

        sl = _finite_float(
            candidate[
                "sl"
            ]
        )

        tp = _finite_float(
            candidate[
                "tp"
            ]
        )

        # Correct execution side:
        # BUY = ASK
        # SELL = BID
        entry = (
            ask
            if action == "BUY"
            else bid
        )

        valid, reason = (
            validate_trade_geometry(
                action,
                entry,
                sl,
                tp,
            )
        )

        if not valid:
            return block(
                reason
            )

        # ---------------------------------------------------------------------
        # Mean reversion premium / discount.
        # ---------------------------------------------------------------------

        support = _finite_float(
            analysis.get(
                "support",
                0.0,
            )
        )

        resistance = (
            _finite_float(
                analysis.get(
                    "resistance",
                    0.0,
                )
            )
        )

        if (
            setup_name
            in {
                "SMC",
                "VWAP",
                "RAJA",
            }
            and support > 0.0
            and resistance
            > support
        ):
            midpoint = (
                support
                + resistance
            ) / 2.0

            if (
                action == "BUY"
                and entry
                > midpoint
            ):
                return block(
                    "PREMIUM_ZONE_BUY_BLOCK"
                )

            if (
                action == "SELL"
                and entry
                < midpoint
            ):
                return block(
                    "DISCOUNT_ZONE_SELL_BLOCK"
                )

        # ---------------------------------------------------------------------
        # Publish final candidate ONLY AFTER all gates.
        # ---------------------------------------------------------------------

        target = {
            "action": action,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "strategy": (
                setup_name
            ),
            "cycle_id": (
                analysis.get(
                    "cycle_id"
                )
            ),
        }

        analysis[
            "target_setup"
        ] = target

        analysis[
            "entry_decision"
        ] = {
            "allowed": True,
            **target,
        }

        self.last_target_setup[
            symbol
        ] = dict(
            target
        )

        if is_live_tick:
            try:
                self.starvation_analyzer.record_signal_found()

            except Exception:
                pass

            # Auditor is write-side telemetry.
            # Dashboard reads never call this function.
            if brain_result is not None:
                try:
                    audit_id = (
                        prediction_auditor
                        .log_evaluation(
                            analysis,
                            brain_result,
                            strategy_action=(
                                action
                            ),
                        )
                    )

                    analysis[
                        "audit_id"
                    ] = audit_id

                except Exception:
                    pass

        now = time.time()

        last_log = getattr(
            self,
            "_last_selected_setup_log",
            {},
        )

        if not isinstance(
            last_log,
            dict,
        ):
            last_log = {}

        if (
            now
            - last_log.get(
                symbol,
                0.0,
            )
            >= 10.0
        ):
            self.logger.info(
                (
                    "Selected %s %s %s | "
                    "entry=%.5f SL=%.5f "
                    "TP=%.5f Brain=%.1f"
                ),
                symbol,
                setup_name,
                action,
                entry,
                sl,
                tp,
                _finite_float(
                    analysis.get(
                        "brain_score",
                        0.0,
                    )
                ),
            )

            last_log[
                symbol
            ] = now

            self._last_selected_setup_log = (
                last_log
            )

        return (
            action,
            sl,
            tp,
            setup_name,
        )

    # =========================================================================
    # CONSERVATIVE RISK WRAPPER
    # =========================================================================

    def _calculate_conservative_risk(
        self,
        analysis: Dict[
            str,
            Any,
        ],
        spread_points: float,
        max_spread_points: float,
        confidence: float,
    ) -> float:
        """
        Temporary conservative risk policy.

        The old DynamicRiskEngine contains conflicting drawdown/loss policies.
        Until core/risk_engine.py is replaced, this function can ONLY REDUCE
        the configured base risk.
        """
        base = max(
            0.0,
            _finite_float(
                settings_manager.get(
                    "risk_percent",
                    0.05,
                ),
                0.05,
            ),
        )

        if base <= 0.0:
            return 0.0

        multiplier = 1.0

        # AI can only reduce.
        if confidence < 0.55:
            multiplier *= 0.50

        elif confidence < 0.70:
            multiplier *= 0.75

        # Spread can only reduce.
        if max_spread_points > 0.0:
            ratio = (
                spread_points
                / max_spread_points
            )

            if ratio >= 0.90:
                multiplier *= 0.50

            elif ratio >= 0.75:
                multiplier *= 0.75

        # High volatility can only reduce.
        df_ltf = analysis.get(
            "df_ltf"
        )

        if (
            isinstance(
                df_ltf,
                pd.DataFrame,
            )
            and "atr"
            in df_ltf.columns
            and len(df_ltf) >= 10
        ):
            current_atr = _finite_float(
                df_ltf[
                    "atr"
                ].iloc[-1]
            )

            median_atr = _finite_float(
                df_ltf[
                    "atr"
                ]
                .tail(
                    min(
                        100,
                        len(df_ltf),
                    )
                )
                .median()
            )

            if (
                current_atr > 0.0
                and median_atr > 0.0
                and current_atr
                > median_atr
            ):
                multiplier *= min(
                    1.0,
                    median_atr
                    / current_atr,
                )

        return max(
            0.0,
            min(
                base,
                base
                * multiplier,
            ),
        )

    # =========================================================================
    # EXECUTE TRADE
    # =========================================================================

    def execute_and_record_trade(
        self,
        symbol: str,
        action: str,
        sl: float,
        tp: float,
        analysis: Dict[
            str,
            Any,
        ],
        strategy_name: str = (
            "UNKNOWN"
        ),
    ) -> Optional[
        TradePosition
    ]:
        """
        Final entry pipeline:

        fresh tick
          -> normalize stops
          -> risk size
          -> ExecutionValidator
          -> exact validated_request
          -> TradeManager
          -> MT5ExecutionService
        """
        action = str(
            action
        ).upper()

        if action not in (
            "BUY",
            "SELL",
        ):
            return None

        if (
            self.emergency_halt_event
            .is_set()
        ):
            self.logger.warning(
                (
                    "Entry blocked: "
                    "emergency halt active."
                )
            )

            return None

        tick = (
            mt5.symbol_info_tick(
                symbol
            )
        )

        info = mt5.symbol_info(
            symbol
        )

        if (
            tick is None
            or info is None
        ):
            return None

        point = _finite_float(
            getattr(
                info,
                "point",
                0.0,
            )
        )

        bid = _finite_float(
            tick.bid
        )

        ask = _finite_float(
            tick.ask
        )

        if (
            point <= 0.0
            or bid <= 0.0
            or ask <= 0.0
        ):
            return None

        spread_points = (
            ask - bid
        ) / point

        max_spread = (
            _finite_float(
                settings_manager.get(
                    "max_spread_points",
                    getattr(
                        self.config,
                        "MAX_SPREAD_POINTS",
                        60,
                    ),
                ),
                60.0,
            )
        )

        if (
            spread_points
            > max_spread
        ):
            self.skipped_stats[
                "high_spread"
            ] += 1

            try:
                self.starvation_analyzer.record_signal_blocked(
                    "HIGH_SPREAD"
                )

            except Exception:
                pass

            return None

        entry_price = (
            ask
            if action == "BUY"
            else bid
        )

        # ---------------------------------------------------------------------
        # Normalize broker stop geometry BEFORE validator/token.
        # ---------------------------------------------------------------------

        try:
            final_sl, final_tp = (
                validate_and_clamp_stops(
                    symbol,
                    action,
                    entry_price,
                    float(sl),
                    float(tp),
                )
            )

        except Exception as exc:
            self.logger.warning(
                (
                    "Stop normalization "
                    "failed: %s"
                ),
                exc,
            )

            return None

        final_sl = _finite_float(
            final_sl
        )

        final_tp = _finite_float(
            final_tp
        )

        geometry_ok, reason = (
            validate_trade_geometry(
                action,
                entry_price,
                final_sl,
                final_tp,
            )
        )

        if not geometry_ok:
            self.logger.warning(
                (
                    "Normalized trade "
                    "geometry rejected: %s"
                ),
                reason,
            )

            return None

        # Keep dashboard state truthful.
        analysis[
            "target_setup"
        ] = {
            "action": action,
            "entry": (
                entry_price
            ),
            "sl": final_sl,
            "tp": final_tp,
            "strategy": (
                strategy_name
            ),
            "cycle_id": (
                analysis.get(
                    "cycle_id"
                )
            ),
        }

        self.last_target_setup[
            symbol
        ] = dict(
            analysis[
                "target_setup"
            ]
        )

        # ---------------------------------------------------------------------
        # Analysis-only mode
        # ---------------------------------------------------------------------

        if not bool(
            settings_manager.get(
                "auto_trade_enabled",
                False,
            )
        ):
            self.analyzed_trades[
                symbol
            ] = {
                "entry": (
                    entry_price
                ),
                "sl": final_sl,
                "tp": final_tp,
                "action": action,
                "strategy": (
                    strategy_name
                ),
                "time": time.time(),
                "entry_features": (
                    _safe_json_value(
                        analysis.get(
                            "features",
                            {},
                        )
                    )
                ),
            }

            self.last_entry_candle[
                symbol
            ] = (
                self.last_candle_times.get(
                    symbol,
                    0,
                )
            )

            try:
                self.starvation_analyzer.record_signal_blocked(
                    "AUTO_TRADE_OFF"
                )

            except Exception:
                pass

            return None

        # ---------------------------------------------------------------------
        # Safety recheck directly before sizing.
        # ---------------------------------------------------------------------

        try:
            safety_allowed, safety_reason = (
                self.safety_engine
                .check_entry_allowed()
            )

        except Exception:
            safety_allowed = False
            safety_reason = (
                "SAFETY_ENGINE_ERROR"
            )

        if not safety_allowed:
            self.logger.warning(
                (
                    "Entry blocked by "
                    "SafetyEngine: %s"
                ),
                safety_reason,
            )

            return None

        # ---------------------------------------------------------------------
        # AI snapshot already generated by evaluate_entry_rules.
        # Do not call model again.
        # ---------------------------------------------------------------------

        raw_ai_signal = (
            analysis.get(
                "ai_signal_snapshot"
            )
        )

        ai_signal: Dict[
            str,
            Any,
        ] = (
            cast(
                Dict[str, Any],
                raw_ai_signal,
            )
            if isinstance(
                raw_ai_signal,
                dict,
            )
            else {}
        )

        confidence = (
            _finite_float(
                ai_signal.get(
                    "confidence",
                    0.5,
                ),
                0.5,
            )
        )

        df_ltf = analysis.get("df_ltf")

        if (
            isinstance(df_ltf, pd.DataFrame)
            and "atr" in df_ltf.columns
            and len(df_ltf) > 0
        ):
            current_atr = _finite_float(
                df_ltf["atr"].iloc[-1],
                analysis.get("atr", 0.0),
            )

            median_atr = _finite_float(
                df_ltf["atr"]
                .tail(min(100, len(df_ltf)))
                .median(),
                current_atr,
            )
        else:
            current_atr = _finite_float(
                analysis.get("atr", 0.0)
            )

            median_atr = current_atr


        open_portfolio_heat = sum(
            max(
                0.0,
                _finite_float(
                    getattr(
                        position,
                        "risk_percent",
                        0.0,
                    )
                ),
            )
            for position
            in self.trade_manager.positions.values()
        )


        risk_percent = (
            self.risk_engine
            .calculate_risk_percent(
                current_atr=current_atr,
                median_atr=median_atr,
                current_spread=spread_points,
                max_spread=max_spread,
                confidence=confidence,
                active_positions=len(
                    self.trade_manager.positions
                ),
                base_risk=_finite_float(
                    settings_manager.get(
                        "risk_percent",
                        0.05,
                    ),
                    0.05,
                ),
                strategy_name=strategy_name,
                open_portfolio_heat_pct=(
                    open_portfolio_heat
                ),
                model_ready=bool(
                    ai_signal.get(
                        "model_ready",
                        False,
                    )
                ),
            )
        )

        if risk_percent <= 0.0:
            self.logger.warning(
                (
                    "Risk sizing returned "
                    "zero; entry blocked."
                )
            )

            return None

        planned_volume = (
            self.trade_manager
            .calculate_lot_size(
                symbol=symbol,
                sl_price=final_sl,
                entry_price=(
                    entry_price
                ),
                risk_percent=(
                    risk_percent
                ),
                brain_score=(
                    _finite_float(
                        analysis.get(
                            "brain_score",
                            0.0,
                        )
                    )
                ),
            )
        )

        if planned_volume <= 0.0:
            self.logger.warning(
                (
                    "Calculated broker "
                    "volume is zero."
                )
            )

            return None

        decision_id = (
            f"PV-DEC-"
            f"{strategy_name.upper()}-"
            f"{action}-"
            f"{uuid.uuid4().hex[:12]}"
        )

        validation = (
            self.execution_validator
            .validate(
                symbol=symbol,
                action=action,
                sl=final_sl,
                tp=final_tp,
                volume=(
                    planned_volume
                ),
                analysis=analysis,
                trade_manager=(
                    self.trade_manager
                ),
                decision_id=(
                    decision_id
                ),
                candidate_id=(
                    str(
                        analysis.get(
                            "cycle_id",
                            "UNKNOWN",
                        )
                    )
                ),
            )
        )

        if not validation.allowed:
            self.skipped_stats[
                "validator"
            ] += 1

            self.logger.warning(
                (
                    "ExecutionValidator "
                    "blocked %s %s: %s"
                ),
                symbol,
                action,
                validation.reason,
            )

            try:
                self.starvation_analyzer.record_signal_blocked(
                    (
                        "VALIDATOR_"
                        f"{validation.reason}"
                    )
                )

            except Exception:
                pass

            self.last_entry_candle[
                symbol
            ] = (
                self.last_candle_times.get(
                    symbol,
                    0,
                )
            )

            return None

        if not isinstance(
            validation.validated_request,
            dict,
        ):
            self.logger.error(
                (
                    "Validator allowed entry "
                    "without immutable request."
                )
            )

            return None

        # ---------------------------------------------------------------------
        # Decision snapshot built from ACTUAL VALIDATED trade.
        # ---------------------------------------------------------------------

        validated_entry = (
            _finite_float(
                validation
                .actual_entry_price
            )
        )

        validated_request = dict(
            validation.validated_request
        )

        validated_sl = (
            _finite_float(
                validated_request.get(
                    "sl",
                    final_sl,
                )
            )
        )

        validated_tp = (
            _finite_float(
                validated_request.get(
                    "tp",
                    final_tp,
                )
            )
        )

        sl_distance = abs(
            validated_entry
            - validated_sl
        )

        tp_distance = abs(
            validated_tp
            - validated_entry
        )

        effective_rr = (
            tp_distance
            / sl_distance
            if sl_distance > 0.0
            else 0.0
        )

        model_version = str(
            getattr(
                self.pattern_learner,
                "model_version",
                "UNKNOWN",
            )
        )

        strategy_meta = analysis.get(
            f"{strategy_name.lower()}_metadata",
            {},
        )

        if not isinstance(
            strategy_meta,
            dict,
        ):
            strategy_meta = {}

        decision_snapshot = (
            TradeDecisionSnapshot(
                schema_version=4,
                feature_schema_version=4,
                model_version=(
                    model_version
                ),
                cycle_id=str(
                    analysis.get(
                        "cycle_id",
                        "UNKNOWN",
                    )
                ),
                decision_id=(
                    decision_id
                ),
                symbol=symbol,
                timestamp_utc=(
                    datetime.now(
                        timezone.utc
                    )
                ),
                strategy_name=(
                    strategy_name
                ),
                strategy_action=(
                    action
                ),
                decision_price=(
                    validated_entry
                ),
                planned_entry=(
                    validated_entry
                ),
                initial_sl=(
                    validated_sl
                ),
                initial_tp=(
                    validated_tp
                ),
                effective_rr=(
                    effective_rr
                ),
                brain_score=(
                    _finite_float(
                        analysis.get(
                            "brain_score",
                            0.0,
                        )
                    )
                ),
                brain_threshold=(
                    _finite_float(
                        analysis.get(
                            "brain_threshold",
                            55.0,
                        ),
                        55.0,
                    )
                ),
                brain_direction=(
                    analysis.get(
                        "brain_direction"
                    )
                ),
                model_probability=(
                    confidence
                ),
                model_source=str(
                    ai_signal.get(
                        "model_source",
                        "NO_VALID_MODEL",
                    )
                ),
                regime=str(
                    analysis.get(
                        "market_regime",
                        "RANGE",
                    )
                ),
                regime_confidence=(
                    _finite_float(
                        analysis.get(
                            "regime_confidence",
                            0.0,
                        )
                    )
                ),
                session=str(
                    analysis.get(
                        "session_name",
                        "OFF",
                    )
                ),
                entry_features=(
                    deep_freeze(
                        _safe_json_value(
                            analysis.get(
                                "features",
                                {},
                            )
                        )
                    )
                ),
                strategy_metadata=(
                    deep_freeze(
                        _safe_json_value(
                            strategy_meta
                        )
                    )
                ),
            )
        )

        position = (
            self._send_validated_order(
                validation=validation,
                decision_snapshot=(
                    decision_snapshot
                ),
                symbol=symbol,
                action=action,
                risk_percent=(
                    risk_percent
                ),
                brain_score=(
                    _finite_float(
                        analysis.get(
                            "brain_score",
                            0.0,
                        )
                    )
                ),
            )
        )

        self.last_entry_candle[
            symbol
        ] = (
            self.last_candle_times.get(
                symbol,
                0,
            )
        )

        if position is None:
            return None

        # ---------------------------------------------------------------------
        # Attach immutable entry metadata.
        # ---------------------------------------------------------------------

        position.entry_features = (
            _safe_json_value(
                analysis.get(
                    "features",
                    {},
                )
            )
        )

        position.strategy_name = (
            strategy_name
        )

        # Only retain compact context, not huge DataFrames.
        position.entry_analysis = {
            "symbol": symbol,
            "cycle_id": (
                analysis.get(
                    "cycle_id"
                )
            ),
            "market_regime": (
                analysis.get(
                    "market_regime"
                )
            ),
            "session_name": (
                analysis.get(
                    "session_name"
                )
            ),
            "brain_score": (
                analysis.get(
                    "brain_score"
                )
            ),
            "features": (
                _safe_json_value(
                    analysis.get(
                        "features",
                        {},
                    )
                )
            ),
        }

        metadata = (
            strategy_meta
        )

        position.entry_pattern = str(
            metadata.get(
                "pattern",
                metadata.get(
                    "source",
                    strategy_name,
                ),
            )
        )

        position.brain_score = (
            _finite_float(
                analysis.get(
                    "brain_score",
                    0.0,
                )
            )
        )

        position.brain_tier1 = (
            _finite_float(
                analysis.get(
                    "brain_tier1",
                    0.0,
                )
            )
        )

        position.brain_tier2 = (
            _finite_float(
                analysis.get(
                    "brain_tier2",
                    0.0,
                )
            )
        )

        position.brain_tier3 = (
            _finite_float(
                analysis.get(
                    "brain_tier3",
                    0.0,
                )
            )
        )

        position.brain_direction = (
            analysis.get(
                "brain_direction"
            )
        )

        position.brain_block_reason = (
            analysis.get(
                "brain_block_reason"
            )
        )

        position.brain_reason_map = (
            _safe_json_value(
                analysis.get(
                    "brain_reason_map",
                    {},
                )
            )
        )

        position.session = str(
            analysis.get(
                "session_name",
                "OFF",
            )
        )

        position.volatility_regime = (
            str(
                analysis.get(
                    "market_regime",
                    "RANGE",
                )
            )
        )

        position.audit_id = (
            analysis.get(
                "audit_id"
            )
        )

        try:
            self.starvation_analyzer.record_signal_executed()

        except Exception:
            pass

        audit_id = getattr(
            position,
            "audit_id",
            None,
        )

        if audit_id is not None:
            try:
                prediction_auditor.update_evaluation_executed(
                    int(audit_id),
                    executed=True,
                    status="EXECUTED",
                )

            except Exception:
                pass

        return position

    # =========================================================================
    # EXACT VALIDATED HANDOFF
    # =========================================================================

    def _send_validated_order(
        self,
        validation,
        decision_snapshot: TradeDecisionSnapshot,
        symbol: str,
        action: str,
        risk_percent: float,
        brain_score: float = 0.0,
    ) -> Optional[
        TradePosition
    ]:
        if (
            self.emergency_halt_event
            .is_set()
        ):
            return None

        if (
            validation.decision_id
            != decision_snapshot
            .decision_id
        ):
            self.logger.error(
                (
                    "Validation/decision ID "
                    "mismatch."
                )
            )

            return None

        now = datetime.now(
            timezone.utc
        )

        age_ms = (
            now
            - validation
            .validated_at_utc
        ).total_seconds() * 1000.0

        max_age = (
            _finite_float(
                settings_manager.get(
                    "max_validation_token_age_ms",
                    5000.0,
                ),
                5000.0,
            )
        )

        if age_ms > max_age:
            self.logger.warning(
                (
                    "Validation expired before "
                    "manager handoff: %.0f ms"
                ),
                age_ms,
            )

            return None

        validated_request = (
            validation
            .validated_request
        )

        if not isinstance(
            validated_request,
            dict,
        ):
            return None

        request = dict(
            validated_request
        )

        return (
            self.trade_manager
            .open_position(
                symbol=symbol,
                action=action,
                entry_price=(
                    _finite_float(
                        request.get(
                            "price",
                            validation
                            .actual_entry_price,
                        )
                    )
                ),
                sl_price=(
                    _finite_float(
                        request.get(
                            "sl",
                            0.0,
                        )
                    )
                ),
                tp_price=(
                    _finite_float(
                        request.get(
                            "tp",
                            0.0,
                        )
                    )
                ),
                risk_percent=(
                    risk_percent
                ),
                brain_score=(
                    brain_score
                ),
                decision_snapshot=(
                    decision_snapshot
                ),
                execution_id=(
                    validation
                    .validation_id
                ),
                # CRITICAL:
                # Exact validator-produced request.
                validated_request=(
                    request
                ),
            )
        )

    # =========================================================================
    # CLOSED TRADES
    # =========================================================================

    def process_closed_positions(
        self,
    ) -> None:
        """
        Process BOTH managers so changing paper/live mode cannot strand a closed
        position in the inactive manager's queue.
        """
        for manager in (
            self.paper_trade_manager,
            self.live_trade_manager,
        ):
            while (
                manager.closed_positions
            ):
                position = (
                    manager
                    .closed_positions
                    .pop(0)
                )

                self._process_one_closed_position(
                    position
                )

    def _process_one_closed_position(
        self,
        pos: TradePosition,
    ) -> None:
        self.last_close_candle[
            pos.symbol
        ] = (
            self.last_candle_times.get(
                pos.symbol,
                0,
            )
        )

        self.performance_history.append(
            {
                "timestamp": (
                    pos.close_time
                ),
                "symbol": pos.symbol,
                "action": pos.action,
                "pnl": pos.pnl,
                "close_reason": (
                    pos.close_reason
                ),
            }
        )

        features = getattr(
            pos,
            "entry_features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):
            features = {}

        # ---------------------------------------------------------------------
        # Raw outcome feedback
        # ---------------------------------------------------------------------

        try:
            self.pattern_learner.learn_from_trade(
                {
                    "symbol": (
                        pos.symbol
                    ),
                    "outcome": (
                        pos.pnl
                    ),
                    "features": (
                        features
                    ),
                }
            )

        except Exception as exc:
            self.logger.debug(
                (
                    "Pattern outcome "
                    "feedback failed: %s"
                ),
                exc,
            )

        try:
            self.experience_memory.store(
                state=features,
                action=(
                    1
                    if pos.action
                    == "BUY"
                    else 2
                ),
                reward=(
                    pos.pnl
                ),
                next_state={},
                done=True,
                metadata={
                    "symbol": (
                        pos.symbol
                    ),
                    "close_reason": (
                        pos.close_reason
                    ),
                    "lots": (
                        pos.volume
                    ),
                },
            )

        except Exception:
            pass

        entry_price = (
            _finite_float(
                pos.entry_price
            )
        )

        close_price = (
            _finite_float(
                pos.close_price,
                entry_price,
            )
        )

        initial_risk = (
            _finite_float(
                getattr(
                    pos,
                    "initial_risk_distance",
                    getattr(
                        pos,
                        "initial_sl_dist",
                        0.0,
                    ),
                )
            )
        )

        if initial_risk > 0.0:
            movement_r = (
                abs(
                    close_price
                    - entry_price
                )
                / initial_risk
            )

            if pos.pnl < 0.0:
                realized_r = (
                    -movement_r
                )

            elif pos.pnl > 0.0:
                realized_r = (
                    movement_r
                )

            else:
                realized_r = 0.0

        else:
            realized_r = 0.0

        realized_r = round(
            realized_r,
            3,
        )

        entry_time = getattr(
            pos,
            "entry_time",
            None,
        )

        close_time = getattr(
            pos,
            "close_time",
            None,
        )

        if (
            not isinstance(
                entry_time,
                datetime,
            )
        ):
            entry_time = (
                datetime.now(
                    timezone.utc
                )
            )

        if (
            entry_time.tzinfo
            is None
        ):
            entry_time = (
                entry_time.replace(
                    tzinfo=timezone.utc
                )
            )

        if (
            not isinstance(
                close_time,
                datetime,
            )
        ):
            close_time = (
                datetime.now(
                    timezone.utc
                )
            )

        if (
            close_time.tzinfo
            is None
        ):
            close_time = (
                close_time.replace(
                    tzinfo=timezone.utc
                )
            )

        duration = max(
            0.0,
            (
                close_time
                - entry_time
            ).total_seconds()
            / 60.0,
        )

        strategy_name = str(
            getattr(
                pos,
                "strategy_name",
                "UNKNOWN",
            )
        ).upper()

        bias = _finite_int(
            features.get(
                "active_bias",
                0,
            )
        )

        bias_label = (
            "BULLISH"
            if bias > 0
            else (
                "BEARISH"
                if bias < 0
                else "NEUTRAL"
            )
        )

        setup_type = (
            strategy_name
        )

        if "SMC" in strategy_name:
            sweep = (
                _finite_int(
                    features.get(
                        "liq_sweep_type",
                        0,
                    )
                )
                != 0
            )

            mss = (
                _finite_int(
                    features.get(
                        "mss_signal",
                        0,
                    )
                )
                != 0
            )

            if sweep and mss:
                setup_type = (
                    "SHARP_TURN"
                )

            elif mss:
                setup_type = (
                    "MSS_ONLY"
                )

            elif sweep:
                setup_type = (
                    "SWEEP_ONLY"
                )

            else:
                setup_type = (
                    "CONTINUATION"
                )

        decision_snapshot = getattr(
            pos,
            "decision_snapshot",
            None,
        )

        try:
            decision_snapshot_json = (
                json.dumps(
                    (
                        decision_snapshot
                        .__dict__
                        if decision_snapshot
                        is not None
                        else None
                    ),
                    default=str,
                )
            )

        except Exception:
            decision_snapshot_json = (
                None
            )

        # ---------------------------------------------------------------------
        # IMPORTANT:
        #
        # date/time = CLOSE time because realized PnL belongs to close day.
        #
        # Extra UTC/original-risk fields will be persisted after the upcoming
        # trade_journal.py replacement. Current journal safely ignores extras.
        # ---------------------------------------------------------------------

        journal_record = {
            "date": (
                close_time
                .astimezone(
                    timezone.utc
                )
                .strftime(
                    "%Y-%m-%d"
                )
            ),
            "time": (
                close_time
                .astimezone(
                    timezone.utc
                )
                .strftime(
                    "%H:%M:%S"
                )
            ),
            "entry_time_utc": (
                entry_time
                .astimezone(
                    timezone.utc
                )
                .isoformat()
            ),
            "close_time_utc": (
                close_time
                .astimezone(
                    timezone.utc
                )
                .isoformat()
            ),
            "symbol": pos.symbol,
            "action": pos.action,
            "entry_price": (
                entry_price
            ),
            "close_price": (
                close_price
            ),
            "sl": (
                _finite_float(
                    getattr(
                        pos,
                        "initial_sl",
                        pos.sl,
                    )
                )
            ),
            "initial_sl": (
                _finite_float(
                    getattr(
                        pos,
                        "initial_sl",
                        pos.sl,
                    )
                )
            ),
            "initial_risk_distance": (
                initial_risk
            ),
            "tp": (
                _finite_float(
                    getattr(
                        pos,
                        "initial_tp",
                        pos.tp,
                    )
                )
            ),
            "lot_size": (
                _finite_float(
                    pos.volume
                )
            ),
            "pnl": round(
                _finite_float(
                    pos.pnl
                ),
                2,
            ),
            "rr_achieved": (
                realized_r
            ),
            "close_reason": (
                pos.close_reason
            ),
            "duration_mins": round(
                duration,
                2,
            ),
            "setup_type": (
                setup_type
            ),
            "fvg_class": str(
                features.get(
                    "fvg_class",
                    "none",
                )
            ).upper(),
            "bias": bias_label,
            "volatility_regime": (
                getattr(
                    pos,
                    "volatility_regime",
                    "RANGE",
                )
            ),
            # Captured when order opened.
            "spread_at_entry": (
                _finite_float(
                    getattr(
                        pos,
                        "entry_spread_points",
                        0.0,
                    )
                )
            ),
            "brain_score": (
                _finite_float(
                    getattr(
                        pos,
                        "brain_score",
                        0.0,
                    )
                )
            ),
            "brain_tier1": (
                _finite_float(
                    getattr(
                        pos,
                        "brain_tier1",
                        0.0,
                    )
                )
            ),
            "brain_tier2": (
                _finite_float(
                    getattr(
                        pos,
                        "brain_tier2",
                        0.0,
                    )
                )
            ),
            "brain_tier3": (
                _finite_float(
                    getattr(
                        pos,
                        "brain_tier3",
                        0.0,
                    )
                )
            ),
            "brain_direction": (
                getattr(
                    pos,
                    "brain_direction",
                    None,
                )
            ),
            "brain_block_reason": (
                getattr(
                    pos,
                    "brain_block_reason",
                    None,
                )
            ),
            "session": getattr(
                pos,
                "session",
                "OFF",
            ),
            "vsa_signals": (
                features.get(
                    "vsa_signals",
                    [],
                )
            ),
            "entry_features": (
                features
            ),
            "audit_id": (
                getattr(
                    pos,
                    "audit_id",
                    None,
                )
            ),
            "strategy_name": (
                strategy_name
            ),
            "entry_pattern": (
                getattr(
                    pos,
                    "entry_pattern",
                    "UNKNOWN",
                )
            ),
            "decision_id": (
                getattr(
                    pos,
                    "decision_id",
                    None,
                )
            ),
            "decision_snapshot": (
                decision_snapshot_json
            ),
            "cycle_id": (
                getattr(
                    pos,
                    "cycle_id",
                    None,
                )
            ),
            "execution_id": (
                getattr(
                    pos,
                    "execution_id",
                    None,
                )
            ),
        }

        try:
            trade_journal.append_trade(
                journal_record
            )

        except Exception as exc:
            self.logger.error(
                (
                    "Trade journal write "
                    "failed: %s"
                ),
                exc,
            )

        # ---------------------------------------------------------------------
        # Auditor / calibrator feedback.
        #
        # No direct model promotion here.
        # ---------------------------------------------------------------------

        audit_id = getattr(
            pos,
            "audit_id",
            None,
        )

        if audit_id is not None:
            try:
                prediction_auditor.resolve_executed_trade(
                    audit_id,
                    won=(
                        pos.pnl > 0.0
                    ),
                    rr=(
                        realized_r
                    ),
                )

            except Exception:
                pass

        try:
            self.safety_engine.record_trade_result(
                pos.pnl
            )

        except Exception:
            pass

        try:
            self.brain_calibrator.record_outcome(
                reason_map=(
                    getattr(
                        pos,
                        "brain_reason_map",
                        {},
                    )
                ),
                outcome=(
                    "WIN"
                    if pos.pnl > 0.0
                    else (
                        "LOSS"
                        if pos.pnl < 0.0
                        else "BE"
                    )
                ),
                pnl=(
                    pos.pnl
                ),
                regime=(
                    getattr(
                        pos,
                        "volatility_regime",
                        "RANGE",
                    )
                ),
            )

        except Exception:
            pass

        try:
            from core.trade_pattern_memory import (
                trade_pattern_memory,
            )

            entry_analysis = getattr(
                pos,
                "entry_analysis",
                None,
            )

            if not isinstance(
                entry_analysis,
                dict,
            ):
                entry_analysis = {
                    "symbol": (
                        pos.symbol
                    ),
                    "close": (
                        pos.entry_price
                    ),
                    "bid": (
                        pos.entry_price
                    ),
                    "atr": (
                        _finite_float(
                            features.get(
                                "atr",
                                0.0,
                            )
                        )
                    ),
                    "market_regime": (
                        getattr(
                            pos,
                            "volatility_regime",
                            "RANGE",
                        )
                    ),
                    "session_score": 0.0,
                    "features": (
                        features
                    ),
                }

            trade_pattern_memory.record_outcome(
                entry_analysis,
                pos.pnl,
            )

        except Exception:
            pass

        self._closed_trades_count += (
            1
        )

        self.logger.info(
            (
                "Closed trade recorded | "
                "%s %s #%s | PnL %.2f | "
                "R %.3f | %s"
            ),
            pos.symbol,
            pos.action,
            pos.id,
            pos.pnl,
            realized_r,
            pos.close_reason,
        )

    # =========================================================================
    # INCREMENTAL LEARNING
    # =========================================================================

    def check_and_run_incremental_learning(
        self,
    ) -> dict:
        """
        Fail closed until the causal training/promotion layer is replaced.
        """
        result = {
            "started": False,
            "promoted": False,
            "reason": (
                "CAUSAL_INCREMENTAL_"
                "VALIDATOR_NOT_YET_PROMOTED"
            ),
        }

        self.logger.info(
            (
                "Incremental model promotion "
                "skipped: %s"
            ),
            result[
                "reason"
            ],
        )

        return result

    # =========================================================================
    # READ-ONLY DASHBOARD PREDICTION
    # =========================================================================

    def get_prediction_data(
        self,
        symbol: str,
    ) -> dict:
        """
        PURE READ.

        Does NOT call:
            PatternLearner.get_trading_signal()
            TradeBrain.evaluate()
            evaluate_entry_rules()

        This eliminates UI polling from changing trading state.
        """
        analysis = (
            self.cached_analysis.get(
                symbol
            )
        )

        if not analysis:
            return {}

        tick = (
            mt5.symbol_info_tick(
                symbol
            )
        )

        bid = (
            _finite_float(
                getattr(
                    tick,
                    "bid",
                    analysis.get(
                        "bid",
                        0.0,
                    ),
                )
            )
            if tick
            is not None
            else _finite_float(
                analysis.get(
                    "bid",
                    0.0,
                )
            )
        )

        ask = (
            _finite_float(
                getattr(
                    tick,
                    "ask",
                    analysis.get(
                        "ask",
                        0.0,
                    ),
                )
            )
            if tick
            is not None
            else _finite_float(
                analysis.get(
                    "ask",
                    0.0,
                )
            )
        )

        ai_signal = (
            analysis.get(
                "ai_signal_snapshot"
            )
        )

        if not isinstance(
            ai_signal,
            dict,
        ):
            ai_signal = {}

        target = analysis.get(
            "target_setup"
        )

        if not isinstance(
            target,
            dict,
        ):
            target = None

        detected = list(
            ai_signal.get(
                "detected_patterns",
                [],
            )
            or []
        )

        if not detected:
            sweep = _finite_int(
                analysis.get(
                    "m15_sweep_type",
                    0,
                )
            )

            mss = _finite_int(
                analysis.get(
                    "m5_mss_signal",
                    0,
                )
            )

            if (
                sweep == 1
                and mss == 1
            ):
                detected = [
                    (
                        "BULLISH "
                        "SWEEP + MSS"
                    )
                ]

            elif (
                sweep == -1
                and mss == -1
            ):
                detected = [
                    (
                        "BEARISH "
                        "SWEEP + MSS"
                    )
                ]

            elif mss == 1:
                detected = [
                    (
                        "BULLISH "
                        "STRUCTURE SHIFT"
                    )
                ]

            elif mss == -1:
                detected = [
                    (
                        "BEARISH "
                        "STRUCTURE SHIFT"
                    )
                ]

            else:
                detected = [
                    "NO CONFIRMED SETUP"
                ]

        crt_meta = (
            analysis.get(
                "crt_metadata",
                {}
            )
            or {}
        )

        safety_allowed = True
        safety_reason = (
            "Allowed"
        )

        try:
            (
                safety_allowed,
                safety_reason,
            ) = (
                self.safety_engine
                .check_entry_allowed()
            )

        except Exception:
            safety_allowed = False
            safety_reason = (
                "SAFETY_ENGINE_ERROR"
            )

        result = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "active_sessions": (
                self.get_active_sessions()
            ),
            "news_locked": (
                bool(
                    analysis.get(
                        "news_locked",
                        False,
                    )
                )
            ),
            "news_lockout_reason": (
                analysis.get(
                    "news_lockout_reason"
                )
            ),
            "market_regime": (
                analysis.get(
                    "market_regime",
                    "RANGE",
                )
            ),
            "resting_pools": (
                _safe_json_value(
                    analysis.get(
                        "resting_pools",
                        [],
                    )
                )
            ),
            "setup": None,
            "action": None,
            "entry": None,
            "sl": None,
            "tp": None,
            "confidence": round(
                _finite_float(
                    ai_signal.get(
                        "confidence",
                        0.0,
                    )
                )
                * 100.0,
                1,
            ),
            "setup_type": None,
            "detected_patterns": (
                detected
            ),
            "vsa_patterns": (
                list(
                    analysis.get(
                        "vsa_signals",
                        [],
                    )
                    or []
                )
            ),
            "smc_patterns": (
                list(
                    ai_signal.get(
                        "smc_patterns",
                        [],
                    )
                    or []
                )
            ),
            "smc_confidence": (
                _finite_float(
                    ai_signal.get(
                        "smc_confidence",
                        0.0,
                    )
                )
            ),
            "cluster_id": (
                _finite_int(
                    ai_signal.get(
                        "cluster_id",
                        0,
                    )
                )
            ),
            "training_stats": (
                getattr(
                    self.pattern_learner,
                    "training_stats",
                    {},
                ).get(
                    symbol,
                    {},
                )
            ),
            "htf_bias": (
                _finite_int(
                    analysis.get(
                        "htf_bias",
                        0,
                    )
                )
            ),
            "d1_bias": (
                _finite_int(
                    analysis.get(
                        "d1_bias",
                        0,
                    )
                )
            ),
            "h4_bias": (
                _finite_int(
                    analysis.get(
                        "h4_bias",
                        0,
                    )
                )
            ),
            "h1_bias": (
                _finite_int(
                    analysis.get(
                        "h1_bias",
                        0,
                    )
                )
            ),
            "m15_bias": (
                _finite_int(
                    analysis.get(
                        "m15_bias",
                        0,
                    )
                )
            ),
            "m5_bias": (
                _finite_int(
                    analysis.get(
                        "m5_bias",
                        0,
                    )
                )
            ),
            "m1_bias": (
                _finite_int(
                    analysis.get(
                        "m1_bias",
                        0,
                    )
                )
            ),
            "m15_sweep_type": (
                _finite_int(
                    analysis.get(
                        "m15_sweep_type",
                        0,
                    )
                )
            ),
            "m5_mss_signal": (
                _finite_int(
                    analysis.get(
                        "m5_mss_signal",
                        0,
                    )
                )
            ),
            "tf_alignment": (
                _safe_json_value(
                    analysis.get(
                        "tf_alignment",
                        {},
                    )
                )
            ),
            "crt_low": (
                _finite_float(
                    crt_meta.get(
                        "crt_low",
                        analysis.get(
                            "crt_low",
                            0.0,
                        ),
                    )
                )
            ),
            "crt_high": (
                _finite_float(
                    crt_meta.get(
                        "crt_high",
                        analysis.get(
                            "crt_high",
                            0.0,
                        ),
                    )
                )
            ),
            "ob_metadata": (
                _safe_json_value(
                    analysis.get(
                        "ob_metadata",
                        {},
                    )
                )
            ),
            "brain_score": (
                _finite_float(
                    analysis.get(
                        "brain_score",
                        0.0,
                    )
                )
            ),
            "brain_direction": (
                analysis.get(
                    "brain_direction"
                )
            ),
            "brain_threshold": (
                _finite_float(
                    analysis.get(
                        "brain_threshold",
                        55.0,
                    )
                )
            ),
            "brain_reason_map": (
                _safe_json_value(
                    analysis.get(
                        "brain_reason_map",
                        {},
                    )
                )
            ),
            "brain_label": (
                analysis.get(
                    "brain_label",
                    "SCANNING",
                )
            ),
            "brain_color": (
                analysis.get(
                    "brain_color",
                    "#8b9bb4",
                )
            ),
            "brain_tier1": (
                _finite_float(
                    analysis.get(
                        "brain_tier1",
                        0.0,
                    )
                )
            ),
            "brain_tier2": (
                _finite_float(
                    analysis.get(
                        "brain_tier2",
                        0.0,
                    )
                )
            ),
            "brain_tier3": (
                _finite_float(
                    analysis.get(
                        "brain_tier3",
                        0.0,
                    )
                )
            ),
            "brain_block_reason": (
                analysis.get(
                    "brain_block_reason"
                )
            ),
            "session_name": (
                analysis.get(
                    "session_name",
                    "OFF",
                )
            ),
            "session_score": (
                _finite_float(
                    analysis.get(
                        "session_score",
                        0.0,
                    )
                )
            ),
            "safety_halt": (
                not safety_allowed
            ),
            "safety_halt_reason": (
                safety_reason
            ),
            "safety_stats": (
                _safe_json_value(
                    self.safety_engine
                    .get_stats()
                )
            ),
        }

        if target is not None:
            action = str(
                target.get(
                    "action",
                    "",
                )
            )

            result.update(
                {
                    "setup": (
                        f"{action} SETUP"
                    ),
                    "action": (
                        action
                    ),
                    "entry": (
                        _finite_float(
                            target.get(
                                "entry",
                                0.0,
                            )
                        )
                    ),
                    "sl": (
                        _finite_float(
                            target.get(
                                "sl",
                                0.0,
                            )
                        )
                    ),
                    "tp": (
                        _finite_float(
                            target.get(
                                "tp",
                                0.0,
                            )
                        )
                    ),
                    "setup_type": (
                        target.get(
                            "strategy"
                        )
                    ),
                }
            )

        return result

    # =========================================================================
    # ASIAN RANGE
    # =========================================================================

    def get_asian_range(
        self,
        symbol: str,
    ) -> Optional[
        Tuple[float, float]
    ]:
        try:
            rates = (
                mt5.copy_rates_from_pos(
                    symbol,
                    mt5.TIMEFRAME_M15,
                    1,
                    64,
                )
            )

            if not rates:
                return None

            highs = []
            lows = []

            for rate in rates:
                timestamp = (
                    datetime.fromtimestamp(
                        int(
                            rate[
                                "time"
                            ]
                        ),
                        timezone.utc,
                    )
                )

                if (
                    0
                    <= timestamp.hour
                    < 9
                ):
                    highs.append(
                        _finite_float(
                            rate[
                                "high"
                            ]
                        )
                    )

                    lows.append(
                        _finite_float(
                            rate[
                                "low"
                            ]
                        )
                    )

            if highs and lows:
                return (
                    max(highs),
                    min(lows),
                )

        except Exception:
            pass

        return None

    # =========================================================================
    # ROUTING — REAL DATA ONLY
    # =========================================================================

    def _get_strategy_routing_info(
        self,
        symbol: str,
    ) -> dict:
        """
        No fabricated fallback win rates / PF / PnL.

        If performance matrix has no validated sample, UI explicitly says so.
        """
        del symbol

        regime = str(
            getattr(
                self.regime_detector,
                "current_regime",
                "RANGE",
            )
        ).upper()

        active_sessions = (
            self.get_active_sessions()
        )

        session = (
            active_sessions[0]
            if active_sessions
            else "OFF"
        )

        mode = str(
            settings_manager.get(
                "trading_mode",
                "intraday",
            )
        )

        suggestions: List[
            Dict[str, Any]
        ] = []

        path = (
            "data/"
            "performance_matrix.json"
        )

        if os.path.exists(
            path
        ):
            try:
                with open(
                    path,
                    "r",
                    encoding="utf-8",
                ) as handle:
                    matrix = json.load(
                        handle
                    )

                weekday = str(
                    datetime.now(
                        timezone.utc
                    ).weekday()
                )

                matrix_data = (
                    matrix.get(
                        "matrix",
                        {}
                    )
                    if isinstance(
                        matrix,
                        dict,
                    )
                    else {}
                )

                suggestions = (
                    matrix_data.get(
                        mode,
                        {}
                    )
                    .get(
                        weekday,
                        {}
                    )
                    .get(
                        session,
                        {}
                    )
                    .get(
                        regime,
                        [],
                    )
                )

                if not suggestions:
                    suggestions = (
                        matrix.get(
                            "fallback_rankings",
                            {}
                        )
                        .get(
                            mode,
                            [],
                        )
                    )

            except Exception as exc:
                self.logger.debug(
                    (
                        "Performance matrix "
                        "read failed: %s"
                    ),
                    exc,
                )

        formatted = []

        for item in suggestions:
            if not isinstance(
                item,
                dict,
            ):
                continue

            total = _finite_int(
                item.get(
                    "total_trades",
                    0,
                )
            )

            # Do not advertise tiny/unknown samples as empirical routing.
            if total <= 0:
                continue

            formatted.append(
                {
                    "strategy": str(
                        item.get(
                            "strategy",
                            "UNKNOWN",
                        )
                    ).upper(),
                    "total_trades": (
                        total
                    ),
                    "win_rate": (
                        _finite_float(
                            item.get(
                                "win_rate",
                                0.0,
                            )
                        )
                    ),
                    "profit_factor": (
                        _finite_float(
                            item.get(
                                "profit_factor",
                                0.0,
                            )
                        )
                    ),
                    "net_pnl_R": (
                        _finite_float(
                            item.get(
                                "net_pnl_R",
                                0.0,
                            )
                        )
                    ),
                    "routing_adjustment": (
                        _finite_float(
                            item.get(
                                "routing_adjustment",
                                0.0,
                            )
                        )
                    ),
                    "reason": str(
                        item.get(
                            "reason",
                            (
                                "Empirical "
                                "performance sample"
                            ),
                        )
                    ),
                }
            )

        if formatted:
            best = formatted[0]

        else:
            best = {
                "strategy": (
                    "NO_EMPIRICAL_DATA"
                ),
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "net_pnl_R": 0.0,
                "routing_adjustment": 0.0,
                "reason": (
                    "No validated performance "
                    "sample exists for this "
                    "mode/session/regime."
                ),
            }

            formatted = [
                dict(
                    best
                )
            ]

        best = {
            **best,
            "mode": mode,
            "session": session,
            "regime": regime,
        }

        return {
            "suggestions": best,
            "rankings": tuple(
                formatted
            ),
        }

    # =========================================================================
    # DASHBOARD SNAPSHOT
    # =========================================================================

    def get_dashboard_snapshot(
        self,
    ):
        with (
            self.dashboard_snapshot_lock
        ):
            return (
                self.dashboard_snapshot
            )

    def _build_dashboard_snapshot(
        self,
    ):
        from utils.snapshot_helper import (
            DashboardStateSnapshot,
            deep_freeze as freeze_dashboard,
        )

        account_data: Dict[
            str,
            Any,
        ] = {}

        try:
            account = mt5.account_info()

            if account is not None:
                account_data = {
                    "broker": (
                        getattr(
                            account,
                            "company",
                            "UNKNOWN",
                        )
                    ),
                    "server": (
                        getattr(
                            account,
                            "server",
                            "",
                        )
                    ),
                    "login": (
                        getattr(
                            account,
                            "login",
                            0,
                        )
                    ),
                    "balance": (
                        _finite_float(
                            getattr(
                                account,
                                "balance",
                                0.0,
                            )
                        )
                    ),
                    "equity": (
                        _finite_float(
                            getattr(
                                account,
                                "equity",
                                0.0,
                            )
                        )
                    ),
                    "profit": (
                        _finite_float(
                            getattr(
                                account,
                                "profit",
                                0.0,
                            )
                        )
                    ),
                    "margin": (
                        _finite_float(
                            getattr(
                                account,
                                "margin",
                                0.0,
                            )
                        )
                    ),
                    "free_margin": (
                        _finite_float(
                            getattr(
                                account,
                                "margin_free",
                                0.0,
                            )
                        )
                    ),
                    "margin_level": (
                        _finite_float(
                            getattr(
                                account,
                                "margin_level",
                                0.0,
                            )
                        )
                    ),
                    "leverage": (
                        _finite_int(
                            getattr(
                                account,
                                "leverage",
                                0,
                            )
                        )
                    ),
                    "currency": str(
                        getattr(
                            account,
                            "currency",
                            "",
                        )
                    ),
                }

        except Exception:
            account_data = {
                "broker": "ERROR",
            }

        positions = []

        now_utc = datetime.now(
            timezone.utc
        )

        for pos in list(
            self.trade_manager
            .positions.values()
        ):
            entry_time = getattr(
                pos,
                "entry_time",
                None,
            )

            age_seconds = 0

            if isinstance(
                entry_time,
                datetime,
            ):
                if (
                    entry_time.tzinfo
                    is None
                ):
                    entry_time = (
                        entry_time.replace(
                            tzinfo=timezone.utc
                        )
                    )

                age_seconds = max(
                    0,
                    int(
                        (
                            now_utc
                            - entry_time
                        )
                        .total_seconds()
                    ),
                )

            positions.append(
                {
                    "ticket": (
                        pos.id
                    ),
                    "symbol": (
                        pos.symbol
                    ),
                    "action": (
                        pos.action
                    ),
                    "volume": (
                        pos.volume
                    ),
                    "entry": (
                        pos.entry_price
                    ),
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "pnl": (
                        getattr(
                            pos,
                            "pnl",
                            0.0,
                        )
                    ),
                    "age_seconds": (
                        age_seconds
                    ),
                    "initial_sl": (
                        getattr(
                            pos,
                            "initial_sl",
                            pos.sl,
                        )
                    ),
                    "risk_percent": (
                        getattr(
                            pos,
                            "risk_percent",
                            0.0,
                        )
                    ),
                }
            )

        active_symbol = (
            self.symbols[0]
            if self.symbols
            else ""
        )

        market: Dict[
            str,
            Any,
        ] = {
            "regime": str(
                getattr(
                    self.regime_detector,
                    "current_regime",
                    "RANGE",
                )
            ),
            "symbols_count": (
                len(
                    self.symbols
                )
            ),
            "bid": 0.0,
            "ask": 0.0,
            "current_price": 0.0,
            "spread_points": 0.0,
            "latency_ms": (
                _finite_float(
                    self.market_state.get(
                        "latency_ms",
                        0.0,
                    )
                )
            ),
        }

        if active_symbol:
            try:
                tick = (
                    mt5.symbol_info_tick(
                        active_symbol
                    )
                )

                info = mt5.symbol_info(
                    active_symbol
                )

                if (
                    tick is not None
                    and info is not None
                ):
                    bid = (
                        _finite_float(
                            tick.bid
                        )
                    )

                    ask = (
                        _finite_float(
                            tick.ask
                        )
                    )

                    point = (
                        _finite_float(
                            info.point
                        )
                    )

                    market.update(
                        {
                            "bid": bid,
                            "ask": ask,
                            "current_price": (
                                (
                                    bid + ask
                                )
                                / 2.0
                            ),
                            "spread_points": (
                                (
                                    ask - bid
                                )
                                / point
                                if point > 0.0
                                else 0.0
                            ),
                        }
                    )

            except Exception:
                pass

        prediction = (
            self.get_prediction_data(
                active_symbol
            )
            if active_symbol
            else {}
        )

        safety_allowed = True
        safety_reason = (
            "Allowed"
        )

        safety_stats: Dict[
            str,
            Any,
        ] = {}

        try:
            (
                safety_allowed,
                safety_reason,
            ) = (
                self.safety_engine
                .check_entry_allowed()
            )

            safety_stats = (
                self.safety_engine
                .get_stats()
            )

        except Exception:
            safety_allowed = False
            safety_reason = (
                "SAFETY_ENGINE_ERROR"
            )

        route = (
            self._get_strategy_routing_info(
                active_symbol
            )
            if active_symbol
            else {
                "suggestions": {},
                "rankings": (),
            }
        )

        try:
            session_context = (
                self.session_engine
                .get_session_context(
                    symbol=(
                        active_symbol
                    )
                )
                if active_symbol
                else {}
            )

            if not isinstance(
                session_context,
                dict,
            ):
                session_context = {}

        except Exception:
            session_context = {}

        session_name = str(
            session_context.get(
                "session_name",
                "",
            )
        )

        active_sessions = (
            ()
            if session_name
            in (
                "",
                "OFF",
                "CLOSED",
                "NONE",
            )
            else (
                session_name.replace(
                    "GOLD_",
                    "",
                ),
            )
        )

        snapshot = (
            DashboardStateSnapshot(
                snapshot_version=2,
                boot_id=(
                    self.boot_id
                ),
                cycle_number=(
                    self.cycle_count
                ),
                cycle_id=(
                    f"PV-CYCLE-"
                    f"{self.boot_id}-"
                    f"{self.cycle_count:08d}"
                ),
                generated_at_utc=(
                    datetime.now(
                        timezone.utc
                    )
                ),
                generated_monotonic=(
                    time.monotonic()
                ),
                connected=(
                    self.connected
                ),
                symbols=tuple(
                    self.symbols
                ),
                account=(
                    account_data
                ),
                positions=tuple(
                    positions
                ),
                market=market,
                model_status={
                    "automatic_promotion": (
                        False
                    ),
                    "training_mode": (
                        "SHADOW_ONLY"
                    ),
                },
                prediction=(
                    prediction
                ),
                risk_status={
                    "risk_percent": (
                        settings_manager.get(
                            "risk_percent",
                            0.05,
                        )
                    ),
                    "max_portfolio_heat": (
                        settings_manager.get(
                            "max_portfolio_heat",
                            5.0,
                        )
                    ),
                    "max_daily_trades": (
                        settings_manager.get(
                            "max_daily_trades",
                            100,
                        )
                    ),
                    "auto_trade_enabled": (
                        settings_manager.get(
                            "auto_trade_enabled",
                            False,
                        )
                    ),
                    "paper_mode": (
                        settings_manager.get(
                            "paper_mode",
                            True,
                        )
                    ),
                },
                diagnostics={
                    "allowed": (
                        safety_allowed
                    ),
                    "reason": (
                        safety_reason
                    ),
                    "safety_halt": (
                        not safety_allowed
                    ),
                    "daily_trades": (
                        self.trade_manager
                        .daily_trade_count
                    ),
                    "daily_pnl": (
                        safety_stats.get(
                            "daily_pnl",
                            0.0,
                        )
                    ),
                    "weekly_pnl": (
                        safety_stats.get(
                            "weekly_pnl",
                            0.0,
                        )
                    ),
                    "consecutive_losses": (
                        safety_stats.get(
                            "consecutive_losses",
                            0,
                        )
                    ),
                },
                routing={
                    "active_strategy": (
                        self.strategy_mode
                    ),
                    "suggestions": (
                        route.get(
                            "suggestions",
                            {},
                        )
                    ),
                },
                active_sessions=(
                    tuple(
                        active_sessions
                    )
                ),
                tf_alignment=(
                    self._last_tf_alignment
                ),
                starvation_stats=(
                    dict(
                        self.skipped_stats
                    )
                ),
                session_context=(
                    session_context
                ),
                strategy_suggestion=(
                    route.get(
                        "suggestions",
                        {},
                    )
                ),
                strategy_rankings=tuple(
                    route.get(
                        "rankings",
                        (),
                    )
                ),
            )
        )

        return (
            freeze_dashboard(
                snapshot
            )
        )

    # =========================================================================
    # ANALYSIS-ONLY TRACKING
    # =========================================================================

    def _update_analysis_only_trade(
        self,
        symbol: str,
        tick: Any,
    ) -> None:
        trade = (
            self.analyzed_trades.get(
                symbol
            )
        )

        if not trade:
            return

        action = str(
            trade.get(
                "action",
                ""
            )
        ).upper()

        entry = _finite_float(
            trade.get(
                "entry",
                0.0,
            )
        )

        sl = _finite_float(
            trade.get(
                "sl",
                0.0,
            )
        )

        tp = _finite_float(
            trade.get(
                "tp",
                0.0,
            )
        )

        # BUY exits against BID.
        # SELL exits against ASK.
        price = (
            _finite_float(
                tick.bid
            )
            if action == "BUY"
            else _finite_float(
                tick.ask
            )
        )

        reason = None

        if action == "BUY":
            if (
                sl > 0.0
                and price <= sl
            ):
                reason = "SL"

            elif (
                tp > 0.0
                and price >= tp
            ):
                reason = "TP"

        elif action == "SELL":
            if (
                sl > 0.0
                and price >= sl
            ):
                reason = "SL"

            elif (
                tp > 0.0
                and price <= tp
            ):
                reason = "TP"

        if reason is None:
            return

        pnl_distance = (
            price - entry
            if action == "BUY"
            else entry - price
        )

        self.logger.info(
            (
                "[ANALYSIS ONLY] %s %s "
                "closed by %s | "
                "distance=%.5f"
            ),
            symbol,
            action,
            reason,
            pnl_distance,
        )

        self.last_close_candle[
            symbol
        ] = (
            self.last_candle_times.get(
                symbol,
                0,
            )
        )

        self.analyzed_trades.pop(
            symbol,
            None,
        )

    # =========================================================================
    # MARKET CYCLE
    # =========================================================================

    def _run_market_cycle(
        self,
    ) -> None:
        if (
            self.emergency_halt_event
            .is_set()
        ):
            # Entry analysis is paused during panic halt.
            # Panic-management command still closes positions separately.
            return

        self._reconnect_if_needed()

        if not self.connected:
            return

        settings_manager.load_settings()

        active_symbol = (
            settings_manager.get(
                "active_symbol",
                None,
            )
        )

        if (
            active_symbol
            and self.symbols
            and self.symbols[0]
            != active_symbol
        ):
            validated = (
                self._validate_symbols(
                    [
                        str(
                            active_symbol
                        )
                    ]
                )
            )

            if validated:
                self.symbols = (
                    validated
                )

                self.cached_analysis.clear()
                self.pending_setups.clear()
                self.last_analysis_times.clear()

        for symbol in list(
            self.symbols
        ):
            if (
                self.emergency_halt_event
                .is_set()
            ):
                break

            tick = (
                mt5.symbol_info_tick(
                    symbol
                )
            )

            if tick is None:
                continue

            # -----------------------------------------------------------------
            # Keep M1 candle ID current.
            # -----------------------------------------------------------------

            try:
                latest = (
                    mt5.copy_rates_from_pos(
                        symbol,
                        mt5.TIMEFRAME_M1,
                        0,
                        1,
                    )
                )

                if (
                    latest is not None
                    and len(latest) > 0
                ):
                    self.last_candle_times[
                        symbol
                    ] = int(
                        latest[0][
                            "time"
                        ]
                    )

            except Exception:
                pass

            # -----------------------------------------------------------------
            # Position management happens every fast cycle.
            # -----------------------------------------------------------------

            previous = (
                self.cached_analysis.get(
                    symbol,
                    {}
                )
            )

            self.trade_manager.update_positions(
                symbol,
                _finite_float(
                    tick.bid
                ),
                _finite_float(
                    tick.ask
                ),
                current_regime=str(
                    previous.get(
                        "market_regime",
                        "RANGING",
                    )
                ),
                df_m1=(
                    previous.get(
                        "df_ltf"
                    )
                ),
                atr=(
                    previous.get(
                        "atr"
                    )
                ),
                news_locked=bool(
                    previous.get(
                        "news_locked",
                        False,
                    )
                ),
                df_h1=(
                    previous.get(
                        "df_h1"
                    )
                ),
            )

            self._update_analysis_only_trade(
                symbol,
                tick,
            )

            # -----------------------------------------------------------------
            # Decision logic ONLY after a NEW analysis refresh.
            # -----------------------------------------------------------------

            now = time.time()

            if (
                now
                - self.last_analysis_times.get(
                    symbol,
                    0.0,
                )
                < self.analysis_interval
            ):
                continue

            analysis = (
                self.run_multi_timeframe_analysis(
                    symbol
                )
            )

            self.last_analysis_times[
                symbol
            ] = now

            if not analysis:
                continue

            self.cached_analysis[
                symbol
            ] = analysis

            self.market_state[
                symbol
            ] = {
                "last_analysis": (
                    analysis
                )
            }

            try:
                recorder = getattr(
                    self.pattern_learner,
                    "record_market_features",
                    None,
                )

                if callable(
                    recorder
                ):
                    recorder(
                        symbol=symbol,
                        features=(
                            analysis.get(
                                "features",
                                {},
                            )
                        ),
                    )

            except Exception:
                pass

            if (
                self.emergency_halt_event
                .is_set()
            ):
                break

            decision = (
                self.evaluate_entry_rules(
                    analysis,
                    is_live_tick=True,
                )
            )

            if decision is None:
                continue

            (
                action,
                sl,
                tp,
                strategy,
            ) = decision

            # -----------------------------------------------------------------
            # No stale pending pullback queue.
            #
            # If a strategy returns a trade now and passes the current-market
            # validator, execute it now. If price later changes, a fresh cycle
            # must produce a fresh decision + token.
            # -----------------------------------------------------------------

            self.execute_and_record_trade(
                symbol=symbol,
                action=action,
                sl=sl,
                tp=tp,
                analysis=analysis,
                strategy_name=(
                    strategy
                ),
            )

        self.process_closed_positions()
        self._schedule_nightly_tasks()

    # =========================================================================
    # SCHEDULER
    # =========================================================================

    def _execute_queued_command(
        self,
        cmd: Dict[str, Any],
    ) -> None:
        try:
            function = cmd.get(
                "func"
            )

            if not callable(
                function
            ):
                raise RuntimeError(
                    "COMMAND_FUNCTION_INVALID"
                )

            result = function()

            holder = cmd.get(
                "result_holder"
            )

            if isinstance(
                holder,
                dict,
            ):
                holder[
                    "result"
                ] = result

                holder[
                    "status"
                ] = "SUCCESS"

        except Exception as exc:
            self.logger.exception(
                (
                    "Queued command failed: %s"
                ),
                exc,
            )

            holder = cmd.get(
                "result_holder"
            )

            if isinstance(
                holder,
                dict,
            ):
                holder[
                    "error"
                ] = str(
                    exc
                )

                holder[
                    "status"
                ] = "FAILED"

        finally:
            completion = cmd.get(
                "completion_event"
            )

            if isinstance(
                completion,
                threading.Event,
            ):
                completion.set()

    def run_engine(
        self,
        sleep_seconds: float = 15,
    ) -> None:
        self.analysis_interval = max(
            1.0,
            float(
                sleep_seconds
            ),
        )

        if self.dashboard:
            self.dashboard.start()

        self.running = True

        self.logger.info(
            (
                "PulseViper started | "
                "symbols=%s | "
                "analysis_interval=%.1fs"
            ),
            self.symbols,
            self.analysis_interval,
        )

        next_cycle = (
            time.monotonic()
        )

        loop_interval = 0.5

        try:
            while self.running:
                now = time.monotonic()

                timeout = max(
                    0.0,
                    next_cycle - now,
                )

                try:
                    (
                        _priority,
                        _sequence,
                        command,
                    ) = (
                        self.command_queue.get(
                            timeout=timeout
                        )
                    )

                    self._execute_queued_command(
                        command
                    )

                    # Limited drain.
                    for _ in range(10):
                        try:
                            (
                                _priority,
                                _sequence,
                                command,
                            ) = (
                                self.command_queue
                                .get_nowait()
                            )

                        except queue.Empty:
                            break

                        self._execute_queued_command(
                            command
                        )

                except queue.Empty:
                    pass

                now = time.monotonic()

                if now < next_cycle:
                    continue

                started = time.time()

                self.cycle_count += (
                    1
                )

                try:
                    self._run_market_cycle()

                except Exception as exc:
                    self.logger.exception(
                        (
                            "Market cycle "
                            "failed: %s"
                        ),
                        exc,
                    )

                self.market_state[
                    "latency_ms"
                ] = (
                    time.time()
                    - started
                ) * 1000.0

                try:
                    snapshot = (
                        self._build_dashboard_snapshot()
                    )

                    with (
                        self.dashboard_snapshot_lock
                    ):
                        self.dashboard_snapshot = (
                            snapshot
                        )

                except Exception as exc:
                    self.logger.warning(
                        (
                            "Snapshot publication "
                            "failed: %s"
                        ),
                        exc,
                    )

                next_cycle = (
                    now
                    + loop_interval
                )

        except KeyboardInterrupt:
            self.logger.info(
                (
                    "Engine stopped "
                    "by keyboard interrupt."
                )
            )

        finally:
            self.running = False

            if self.dashboard:
                try:
                    self.dashboard.stop()

                except Exception:
                    pass

            self._shutdown()

    # =========================================================================
    # SETTINGS COMMAND
    # =========================================================================

    def queue_settings_update(
        self,
        data: dict,
    ) -> dict:
        completion = (
            threading.Event()
        )

        holder = {
            "status": "PENDING",
        }

        command_id = (
            f"CMD-SETTINGS-"
            f"{secrets.token_hex(4)}"
        )

        def apply_settings():
            for key, value in (
                data.items()
            ):
                settings_manager.set(
                    key,
                    value,
                    source="DASHBOARD_API",
                    reason=(
                        "Queued dashboard "
                        "settings update"
                    ),
                )

            return True

        command = {
            "command_id": (
                command_id
            ),
            "func": (
                apply_settings
            ),
            "completion_event": (
                completion
            ),
            "result_holder": (
                holder
            ),
        }

        self.command_queue.put(
            (
                1,
                next(
                    self.command_sequence
                ),
                command,
            )
        )

        return {
            "command_id": (
                command_id
            ),
            "completion_event": (
                completion
            ),
            "result_holder": (
                holder
            ),
        }

    # =========================================================================
    # PANIC
    # =========================================================================

    def trigger_emergency_panic_close(
        self,
    ) -> dict:
        """
        Immediately block new entries, then queue a priority-0 risk-reducing
        close job.

        management_transaction() intentionally still permits exits while the
        emergency halt event is set.
        """
        self.emergency_halt_event.set()

        try:
            settings_manager.set(
                "auto_trade_enabled",
                False,
                source="PANIC",
                reason=(
                    "Emergency panic halt"
                ),
            )

        except Exception:
            pass

        self.pending_setups.clear()

        completion = (
            threading.Event()
        )

        holder = {
            "status": "PENDING",
        }

        command_id = (
            f"CMD-PANIC-"
            f"{secrets.token_hex(4)}"
        )

        command = {
            "command_id": (
                command_id
            ),
            "func": (
                self.close_all_positions
            ),
            "completion_event": (
                completion
            ),
            "result_holder": (
                holder
            ),
        }

        self.command_queue.put(
            (
                0,
                next(
                    self.command_sequence
                ),
                command,
            )
        )

        return {
            "command_id": (
                command_id
            ),
            "completion_event": (
                completion
            ),
            "result_holder": (
                holder
            ),
        }

    def close_all_positions(
        self,
    ) -> Dict[str, Any]:
        manager = (
            self.trade_manager
        )

        tickets = list(
            manager.positions.keys()
        )

        closed = []
        errors = []

        for ticket in tickets:
            pos = (
                manager.positions.get(
                    ticket
                )
            )

            if pos is None:
                continue

            tick = (
                mt5.symbol_info_tick(
                    pos.symbol
                )
            )

            if tick is None:
                errors.append(
                    (
                        f"No tick for "
                        f"{pos.symbol} "
                        f"ticket {ticket}"
                    )
                )

                continue

            price = (
                _finite_float(
                    tick.bid
                )
                if pos.action
                == "BUY"
                else _finite_float(
                    tick.ask
                )
            )

            result = (
                manager.close_position(
                    ticket,
                    price,
                    "PANIC CLOSE",
                )
            )

            if result is not None:
                closed.append(
                    ticket
                )

            else:
                errors.append(
                    (
                        f"Failed to close "
                        f"ticket {ticket}"
                    )
                )

        self.process_closed_positions()

        return {
            "success": (
                len(errors) == 0
            ),
            "closed": closed,
            "errors": errors,
        }

    # =========================================================================
    # AUTOMATION / LEARNING
    # =========================================================================

    def _start_background_pattern_learning(
        self,
    ) -> None:
        """
        Disabled intentionally.

        Historical trainer needs causal MTF availability + validation/promotion
        fixes before it may automatically modify a production model.
        """
        self.logger.info(
            (
                "Automatic background model "
                "promotion is disabled "
                "(shadow-only mode)."
            )
        )

    def trigger_historical_training(
        self,
    ) -> dict:
        """
        Dashboard-compatible guarded endpoint.

        Do not call old train_on_history until the historical data availability
        and promotion validator files are replaced.
        """
        result = {
            "started": False,
            "promoted": False,
            "reason": (
                "CAUSAL_HISTORICAL_TRAINER_"
                "NOT_YET_PROMOTED"
            ),
        }

        self.logger.warning(
            (
                "Historical training "
                "blocked: %s"
            ),
            result[
                "reason"
            ],
        )

        return result

    def self_configure_automation(
        self,
    ) -> dict:
        """
        Recommendation-only.

        Never silently changes live spread/risk settings.
        """
        recommendations = []

        spread_skips = (
            _finite_int(
                self.skipped_stats.get(
                    "high_spread",
                    0,
                )
            )
        )

        if spread_skips >= 50:
            recommendations.append(
                {
                    "type": (
                        "SPREAD_REVIEW"
                    ),
                    "reason": (
                        f"{spread_skips} "
                        "signals were blocked "
                        "by spread."
                    ),
                }
            )

        try:
            summary = (
                trade_journal
                .get_daily_summary()
            )

            total = _finite_int(
                summary.get(
                    "total_trades",
                    0,
                )
            )

            wins = _finite_int(
                summary.get(
                    "wins",
                    0,
                )
            )

            if total >= 10:
                recommendations.append(
                    {
                        "type": (
                            "RISK_REVIEW"
                        ),
                        "sample_size": (
                            total
                        ),
                        "win_rate": (
                            wins
                            / total
                        ),
                        "reason": (
                            "Review risk only "
                            "after validated "
                            "out-of-sample evidence."
                        ),
                    }
                )

        except Exception:
            pass

        return {
            "applied": False,
            "recommendations": (
                recommendations
            ),
        }

    def _schedule_nightly_tasks(
        self,
    ) -> None:
        """
        Safe nightly tasks only.

        No self-optimize / weight promotion / disconnected HMM promotion.
        """
        now = datetime.now(
            timezone.utc
        )

        if (
            self._last_nightly_date
            == now.date()
        ):
            return

        if not (
            now.hour == 0
            and now.minute < 5
        ):
            return

        self._last_nightly_date = (
            now.date()
        )

        def nightly():
            try:
                self.daily_analyzer.analyze_yesterday()

            except Exception as exc:
                self.logger.warning(
                    (
                        "Daily analyzer "
                        "failed: %s"
                    ),
                    exc,
                )

            try:
                self.self_configure_automation()

            except Exception:
                pass

        threading.Thread(
            target=nightly,
            daemon=True,
            name="NightlySafeTasks",
        ).start()

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    def _shutdown(
        self,
    ) -> None:
        try:
            if (
                getattr(
                    self,
                    "news_engine",
                    None
                )
                is not None
            ):
                self.news_engine.stop()

        except Exception:
            pass

        try:
            sentiment_analyzer.stop()

        except Exception:
            pass

        try:
            shutdown_mt5()

        except Exception:
            pass

        self.connected = False

        self.logger.info(
            "PulseViper stopped safely."
        )