from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np
import pandas as pd

from core.market_regime_hmm import MarketRegimeHMM
from utils.order_flow_engine import OrderFlowEngine
from utils.settings_manager import settings_manager

if TYPE_CHECKING:
    from core.market_context import MarketContext
    from core.candidate_setup import CandidateSetup
    from core.candidate_prediction import CandidatePrediction


logger = logging.getLogger("PulseViper.TradeBrain")


TIER1_MAX = 50.0
TIER2_MAX = 35.0
TIER3_MAX = 15.0

DEFAULT_THRESHOLD = 55.0

REGIME_THRESHOLDS = {
    "TRENDING": 55.0,
    "RANGE": 58.0,
    "COMPRESSION": 62.0,
}

HARD_BLOCKED_REGIMES = {
    "CHAOTIC",
    "ILLIQUID",
}


DEFAULT_T1_WEIGHTS = {
    "d1": 12.0,
    "h4": 10.0,
    "h1": 10.0,
    "m15": 8.0,
    "m5": 6.0,
    "m1": 4.0,
}


DEFAULT_T2_WEIGHTS = {
    "structure": 12.0,
    "fvg": 5.0,
    "vsa": 4.0,
    "volume": 4.0,
    "liquidity": 3.0,
    "statistical_bounds": 3.0,
    "ai_confidence": 4.0,
}


MODE_T1_WEIGHTS = {
    "scalping": {
        "d1": 3.0,
        "h4": 5.0,
        "h1": 10.0,
        "m15": 12.0,
        "m5": 12.0,
        "m1": 8.0,
    },

    "intraday": {
        "d1": 8.0,
        "h4": 9.0,
        "h1": 12.0,
        "m15": 10.0,
        "m5": 7.0,
        "m1": 4.0,
    },

    "swing": {
        "d1": 15.0,
        "h4": 14.0,
        "h1": 11.0,
        "m15": 6.0,
        "m5": 3.0,
        "m1": 1.0,
    },
}


REGIME_QUALITY = {
    "TRENDING": 10.0,
    "RANGE": 6.0,
    "COMPRESSION": 2.0,
}


VSA_BULLISH_SIGNALS = {
    "CLIMACTIC_BUY_EXHAUSTION",
    "DEMAND_ABSORPTION",
    "HIDDEN_BUYING",
    "STOPPING_VOLUME_UP",
    "STOPPING_VOLUME",
    "TEST_OF_SUPPLY",
    "ULTRA_HIGH_VOLUME_BULLISH",
    "NO_SUPPLY",
    "SPRING",
    "SELLING_CLIMAX",
    "EFFORT_VS_RESULT_BULLISH",
}


VSA_BEARISH_SIGNALS = {
    "CLIMACTIC_SELL_EXHAUSTION",
    "SUPPLY_ABSORPTION",
    "HIDDEN_SELLING",
    "STOPPING_VOLUME_DOWN",
    "TEST_OF_DEMAND",
    "ULTRA_HIGH_VOLUME_BEARISH",
    "NO_DEMAND",
    "UPTHRUST",
    "BUYING_CLIMAX",
    "EFFORT_VS_RESULT_BEARISH",
}


BLOCK_REASON_NEWS = "NEWS_LOCKOUT"
BLOCK_REASON_CHAOTIC = "CHAOTIC_REGIME"
BLOCK_REASON_ILLIQUID = "ILLIQUID_REGIME"
BLOCK_REASON_SCORE = "SCORE_BELOW_THRESHOLD"
BLOCK_REASON_CONFLICTED = "DIRECTIONAL_CONFLICT"
BLOCK_REASON_STRATEGY_CONFLICT = "STRATEGY_DIRECTION_CONFLICT"
BLOCK_REASON_NO_STRATEGY = "NO_STRATEGY_CANDIDATE"
BLOCK_REASON_AI_UNAVAILABLE = "AI_MODEL_UNAVAILABLE"
BLOCK_REASON_AI_LOW = "LOW_CONFIDENCE"
BLOCK_REASON_KILLZONE = "KILLZONE_INACTIVE"
BLOCK_REASON_SPREAD = "SPREAD_LIMIT_EXCEEDED"


class BrainResult:
    __slots__ = (
        "brain_score",
        "brain_direction",
        "threshold",
        "reason_map",
        "passed",
        "regime",
        "block_reason",
        "tier1_score",
        "tier2_score",
        "tier3_score",
    )

    def __init__(
        self,
        brain_score: float,
        brain_direction: Optional[str],
        threshold: float,
        reason_map: Dict[str, Any],
        regime: str,
        block_reason: Optional[str] = None,
        tier1_score: float = 0.0,
        tier2_score: float = 0.0,
        tier3_score: float = 0.0,
    ):
        self.brain_score = float(
            np.clip(
                brain_score,
                0.0,
                100.0,
            )
        )

        self.brain_direction = (
            brain_direction
        )

        self.threshold = float(
            threshold
        )

        self.reason_map = dict(
            reason_map
        )

        self.regime = str(
            regime
        )

        self.block_reason = (
            block_reason
        )

        self.tier1_score = float(
            np.clip(
                tier1_score,
                0.0,
                TIER1_MAX,
            )
        )

        self.tier2_score = float(
            np.clip(
                tier2_score,
                0.0,
                TIER2_MAX,
            )
        )

        self.tier3_score = float(
            np.clip(
                tier3_score,
                0.0,
                TIER3_MAX,
            )
        )

        # Absolutely no exploration override.
        self.passed = bool(
            self.brain_score
            >= self.threshold
            and self.brain_direction
            in {
                "BUY",
                "SELL",
            }
            and self.block_reason
            is None
        )

    @property
    def is_chaotic(
        self,
    ) -> bool:

        return (
            self.block_reason
            == BLOCK_REASON_CHAOTIC
        )

    @property
    def is_news_blocked(
        self,
    ) -> bool:

        return (
            self.block_reason
            == BLOCK_REASON_NEWS
        )

    def to_dict(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        return {
            "brain_score": round(
                self.brain_score,
                2,
            ),

            "brain_direction": (
                self.brain_direction
            ),

            "threshold": round(
                self.threshold,
                2,
            ),

            "reason_map": (
                self.reason_map
            ),

            "passed": (
                self.passed
            ),

            "regime": (
                self.regime
            ),

            "block_reason": (
                self.block_reason
            ),

            "tier1_score": round(
                self.tier1_score,
                2,
            ),

            "tier2_score": round(
                self.tier2_score,
                2,
            ),

            "tier3_score": round(
                self.tier3_score,
                2,
            ),
        }

    def __repr__(
        self,
    ) -> str:

        return (
            f"BrainResult("
            f"score={self.brain_score:.1f}/"
            f"{self.threshold:.1f} "
            f"dir={self.brain_direction} "
            f"passed={self.passed} "
            f"regime={self.regime} "
            f"block={self.block_reason})"
        )


class TradeBrain:
    """
    Deterministic candidate ranking / confirmation layer.

    Invariants
    ----------

    - Paper mode and live mode use the SAME decision gates.
    - No exploration can force passed=True.
    - No fabricated strategy performance.
    - No 3-trade routing boosts.
    - FXStreet/general sentiment has zero execution authority.
    - Gold has no permission bypass.
    - Strategy identity does not fill Tier 2 by itself.
    - Missing validated AI is never silently treated as 50%.
    - TradeBrain never authorizes money risk or execution.

    Final chain remains:

        TradeBrain
            ↓
        SafetyEngine
            ↓
        RiskEngine
            ↓
        ExecutionValidator
            ↓
        Execution
    """

    PERFORMANCE_MATRIX_PATH = (
        "data/performance_matrix.json"
    )

    MIN_EMPIRICAL_TRADES = (
        30
    )

    KNOWN_STRATEGIES = {
        "QUANTUM",
        "QUANTUM_VIPER",

        "CRT",
        "CRT_TBS",

        "FIB",
        "FIB_RETEST",

        "ICT",

        "SMC",
        "SMC_CONCEPTS",

        "RAJA",
        "RAJA_BANKS",

        "BANK",
        "BANK_TO_BANK",

        "VSA",
        "AVC",

        "M1_SCALPING",

        "VWAP",
        "VWAP_VAS",

        "AMD",
        "SRC",
    }

    def __init__(
        self,
        base_threshold: float = (
            DEFAULT_THRESHOLD
        ),
        order_flow_engine: Optional[
            OrderFlowEngine
        ] = None,
        market_regime_hmm: Optional[
            MarketRegimeHMM
        ] = None,
    ):
        self.base_threshold = float(
            base_threshold
        )

        self.logger = logging.getLogger(
            "PulseViper.TradeBrain"
        )

        self._eval_count = (
            0
        )

        self.of_engine = (
            order_flow_engine
            or OrderFlowEngine()
        )

        self.hmm_detector = (
            market_regime_hmm
            or MarketRegimeHMM()
        )

        # Runtime learned weight files are not trusted until they gain their
        # own frozen validation/promotion mechanism.
        self.t1_weights = dict(
            DEFAULT_T1_WEIGHTS
        )

        self.t2_weights = dict(
            DEFAULT_T2_WEIGHTS
        )

    # =========================================================================
    # BASIC HELPERS
    # =========================================================================

    @staticmethod
    def _finite(
        value: Any,
    ) -> Optional[
        float
    ]:

        try:
            result = float(
                value
            )

            if math.isfinite(
                result
            ):

                return result

        except (
            TypeError,
            ValueError,
        ):
            pass

        return None

    @classmethod
    def _direction(
        cls,
        value: Any,
    ) -> int:

        value = cls._finite(
            value
        )

        if value is None:
            return 0

        if value > 0:
            return 1

        if value < 0:
            return -1

        return 0

    @classmethod
    def _safe_probability(
        cls,
        value: Any,
    ) -> Optional[
        float
    ]:

        value = cls._finite(
            value
        )

        if (
            value is not None
            and 0.0
            <= value
            <= 1.0
        ):

            return value

        return None

    @staticmethod
    def _canonical_strategy(
        name: Optional[
            str
        ],
    ) -> str:

        return (
            str(
                name
                or ""
            )
            .strip()
            .upper()
        )

    # =========================================================================
    # WEIGHTS
    # =========================================================================

    def _load_calibrated_weights(
        self,
        regime: str = "RANGE",
    ) -> None:
        """
        Compatibility API.

        Unvalidated data/brain_weights.json is intentionally ignored.
        """

        self.t1_weights = dict(
            DEFAULT_T1_WEIGHTS
        )

        self.t2_weights = dict(
            DEFAULT_T2_WEIGHTS
        )

    # =========================================================================
    # EMPIRICAL STRATEGY ROUTING
    # =========================================================================

    def _load_performance_matrix(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        if not os.path.isfile(
            self.PERFORMANCE_MATRIX_PATH
        ):

            return {}

        try:

            with open(
                self.PERFORMANCE_MATRIX_PATH,
                "r",
                encoding="utf-8",
            ) as handle:

                data = json.load(
                    handle
                )

            if isinstance(
                data,
                dict,
            ):

                return data

        except Exception as exc:

            self.logger.warning(
                (
                    "Performance "
                    "matrix rejected: %s"
                ),
                exc,
            )

        return {}

    def _find_empirical_stats(
        self,
        strategy_name: str,
        mode: str,
        weekday: int,
        session: str,
        regime: str,
    ) -> Optional[
        Dict[
            str,
            Any,
        ]
    ]:

        matrix = (
            self._load_performance_matrix()
        )

        if not matrix:
            return None

        strategy = (
            self
            ._canonical_strategy(
                strategy_name
            )
            .lower()
        )

        mode = str(
            mode
        ).lower()

        session = (
            str(
                session
            )
            .replace(
                "GOLD_",
                "",
            )
            .upper()
        )

        regime = str(
            regime
        ).upper()

        candidates: List[
            Dict[
                str,
                Any,
            ]
        ] = []

        # Specific condition evidence.
        try:

            rows = (
                matrix
                .get(
                    "matrix",
                    {},
                )
                .get(
                    mode,
                    {},
                )
                .get(
                    str(
                        weekday
                    ),
                    {},
                )
                .get(
                    session,
                    {},
                )
                .get(
                    regime,
                    [],
                )
            )

            if isinstance(
                rows,
                list,
            ):

                candidates.extend(
                    row
                    for row
                    in rows
                    if (
                        isinstance(
                            row,
                            dict,
                        )
                        and str(
                            row.get(
                                "strategy",
                                "",
                            )
                        ).lower()
                        == strategy
                    )
                )

        except Exception:

            pass

        # A general row is accepted only when it still contains real
        # realized-R evidence and a meaningful sample.
        try:

            rows = (
                matrix
                .get(
                    "fallback_rankings",
                    {},
                )
                .get(
                    mode,
                    [],
                )
            )

            if isinstance(
                rows,
                list,
            ):

                candidates.extend(
                    row
                    for row
                    in rows
                    if (
                        isinstance(
                            row,
                            dict,
                        )
                        and str(
                            row.get(
                                "strategy",
                                "",
                            )
                        ).lower()
                        == strategy
                    )
                )

        except Exception:

            pass

        for stats in candidates:

            trades = (
                self._finite(
                    stats.get(
                        "total_trades"
                    )
                )
            )

            expectancy = (
                self._finite(
                    stats.get(
                        "expectancy_r",
                        stats.get(
                            "avg_r"
                        ),
                    )
                )
            )

            profit_factor = (
                self._finite(
                    stats.get(
                        "profit_factor"
                    )
                )
            )

            if (
                trades is not None
                and int(
                    trades
                )
                >= self.MIN_EMPIRICAL_TRADES
                and expectancy
                is not None
                and profit_factor
                is not None
            ):

                return stats

        return None

    def _get_strategy_routing_adjustment(
        self,
        strategy_name: str,
        mode: str,
        weekday: int,
        session: str,
        regime: str,
    ) -> Tuple[
        float,
        str,
    ]:
        """
        Missing/undersampled evidence:

            adjustment = 0
            reason = NO_EMPIRICAL_DATA

        No fake WR/PF values.
        """

        if not strategy_name:

            return (
                0.0,
                "NO_STRATEGY",
            )

        stats = (
            self._find_empirical_stats(
                strategy_name,
                mode,
                weekday,
                session,
                regime,
            )
        )

        if stats is None:

            return (
                0.0,
                "NO_EMPIRICAL_DATA",
            )

        trades_value = self._finite(
            stats.get(
                "total_trades"
            )
        )

        expectancy_value = self._finite(
            stats.get(
                "expectancy_r",
                stats.get(
                    "avg_r"
                ),
            )
        )

        profit_factor_value = self._finite(
            stats.get(
                "profit_factor"
            )
        )

        if (
            trades_value is None
            or expectancy_value is None
            or profit_factor_value is None
        ):
            return (
                0.0,
                "NO_EMPIRICAL_DATA",
            )

        trades = int(
            trades_value
        )

        expectancy = float(
            expectancy_value
        )

        profit_factor = float(
            profit_factor_value
        )

        if (
            trades
            < self.MIN_EMPIRICAL_TRADES
        ):
            return (
                0.0,
                "NO_EMPIRICAL_DATA",
            )

        # Empirical routing can only have a small influence.
        if (
            expectancy > 0.20
            and profit_factor
            >= 1.25
        ):

            return (
                3.0,
                (
                    "EMPIRICAL_POSITIVE:"
                    f"n={trades},"
                    f"E={expectancy:.3f}R,"
                    f"PF={profit_factor:.2f}"
                ),
            )

        if (
            expectancy > 0.0
            and profit_factor
            >= 1.0
        ):

            return (
                1.0,
                (
                    "EMPIRICAL_WEAK_POSITIVE:"
                    f"n={trades},"
                    f"E={expectancy:.3f}R,"
                    f"PF={profit_factor:.2f}"
                ),
            )

        return (
            -5.0,
            (
                "EMPIRICAL_NON_POSITIVE:"
                f"n={trades},"
                f"E={expectancy:.3f}R,"
                f"PF={profit_factor:.2f}"
            ),
        )

    # =========================================================================
    # OPTIONAL ORDER-FLOW TELEMETRY
    # =========================================================================

    def enrich_smc_signals_with_order_flow(
        self,
        symbol: str,
        current_features: Dict,
    ) -> Dict[
        str,
        float,
    ]:
        """
        Compatibility helper.

        Footprint information is telemetry only.
        It is NOT auto-added to execution score.
        """

        try:

            now = datetime.now(
                timezone.utc
            )

            footprint = (
                self.of_engine
                .fetch_and_build_footprint(
                    symbol,
                    (
                        now
                        - timedelta(
                            minutes=15
                        )
                    ),
                    now,
                )
            )

            return {
                "order_flow_boost": 0.0,

                "poc_at_execution": float(
                    footprint.get(
                        "poc_price",
                        0.0,
                    )
                    or 0.0
                ),

                "net_order_flow_delta": float(
                    footprint.get(
                        "total_delta",
                        0.0,
                    )
                    or 0.0
                ),
            }

        except Exception as exc:

            self.logger.debug(
                (
                    "Order-flow "
                    "telemetry unavailable: %s"
                ),
                exc,
            )

            return {
                "order_flow_boost": 0.0,
                "poc_at_execution": 0.0,
                "net_order_flow_delta": 0.0,
            }

    # =========================================================================
    # REGIME
    # =========================================================================

    def resolve_dynamic_regime_gating(
        self,
        df_m1_history: pd.DataFrame,
        symbol: str,
    ) -> str:

        try:

            if (
                df_m1_history is None
                or len(
                    df_m1_history
                )
                < 30
            ):

                return "RANGE"

            lookback = (
                df_m1_history
                .tail(
                    30
                )
                .copy()
            )

            cvd = (
                self.of_engine
                .compute_cumulative_volume_delta_vectorized(
                    lookback,
                    symbol,
                )
            )

            imbalance = (
                self.of_engine
                .compute_imbalance_density_vector(
                    lookback,
                    symbol,
                )
            )

            if "volume" in (
                lookback.columns
            ):

                volume_col = (
                    "volume"
                )

            elif "tick_volume" in (
                lookback.columns
            ):

                volume_col = (
                    "tick_volume"
                )

            else:

                return "RANGE"

            hmm_features = pd.DataFrame(
                {
                    "cvd_roc": (
                        pd.Series(
                            cvd
                        )
                        .pct_change(
                            3
                        )
                    ),

                    "imbalance_density": (
                        pd.Series(
                            imbalance
                        )
                    ),

                    "tick_frequency": (
                        pd.to_numeric(
                            lookback[
                                volume_col
                            ],
                            errors="coerce",
                        )
                        .reset_index(
                            drop=True
                        )
                    ),
                }
            )

            hmm_features = (
                hmm_features
                .replace(
                    [
                        np.inf,
                        -np.inf,
                    ],
                    np.nan,
                )
                .ffill()
                .fillna(
                    0.0
                )
            )

            (
                state,
                posteriors,
            ) = (
                self.hmm_detector
                .decode_current_regime(
                    hmm_features
                )
            )

            probability = (
                self._finite(
                    posteriors[
                        state
                    ]
                    if posteriors
                    is not None
                    else None
                )
            )

            if (
                probability is None
                or probability < 0.75
            ):

                return "RANGE"

            return {
                0: "COMPRESSION",
                1: "TRENDING",
                2: "CHAOTIC",
            }.get(
                state,
                "RANGE",
            )

        except Exception as exc:

            self.logger.debug(
                (
                    "Dynamic regime "
                    "unavailable: %s"
                ),
                exc,
            )

            return "RANGE"

    # =========================================================================
    # MAIN EVALUATION API
    # =========================================================================

    def evaluate(
        self,
        analysis: Dict[
            str,
            Any,
        ],
        strategy_action: Optional[
            str
        ] = None,
        ai_confidence: Optional[
            float
        ] = None,
        session_score: float = 0.0,
        strategy_name: Optional[
            str
        ] = None,
    ) -> BrainResult:

        self._eval_count += 1

        if not isinstance(
            analysis,
            dict,
        ):

            return BrainResult(
                0.0,
                None,
                self.base_threshold,
                {
                    "error": (
                        "INVALID_ANALYSIS"
                    )
                },
                "UNKNOWN",
                block_reason=(
                    "INVALID_ANALYSIS"
                ),
            )

        features = analysis.get(
            "features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):

            features = {}

        regime = str(
            analysis.get(
                "market_regime",
                features.get(
                    "market_regime",
                    "RANGE",
                ),
            )
        ).upper()

        # Optional HMM classification.
        if bool(
            settings_manager.get(
                "dynamic_regime_filter",
                False,
            )
        ):

            df_ltf = (
                analysis.get(
                    "df_ltf"
                )
            )

            if (
                df_ltf is not None
                and len(
                    df_ltf
                )
                >= 30
            ):

                regime = (
                    self
                    .resolve_dynamic_regime_gating(
                        df_ltf,
                        str(
                            analysis.get(
                                "symbol",
                                "",
                            )
                        ),
                    )
                    .upper()
                )

        threshold = float(
            REGIME_THRESHOLDS.get(
                regime,
                self.base_threshold,
            )
        )

        reason_map: Dict[
            str,
            Any,
        ] = {
            "paper_mode_threshold_relaxation": False,
            "exploration_override": False,
            "news_sentiment_execution_authority": False,
        }

        news_locked = bool(
            analysis.get(
                "news_locked",
                features.get(
                    "news_locked",
                    False,
                ),
            )
        )

        if (
            bool(
                settings_manager.get(
                    "news_filter_enabled",
                    True,
                )
            )
            and news_locked
        ):

            return BrainResult(
                0.0,
                None,
                threshold,
                reason_map,
                regime,
                block_reason=(
                    BLOCK_REASON_NEWS
                ),
            )

        if regime == "CHAOTIC":

            return BrainResult(
                0.0,
                None,
                threshold,
                reason_map,
                regime,
                block_reason=(
                    BLOCK_REASON_CHAOTIC
                ),
            )

        if regime == "ILLIQUID":

            return BrainResult(
                0.0,
                None,
                threshold,
                reason_map,
                regime,
                block_reason=(
                    BLOCK_REASON_ILLIQUID
                ),
            )

        if bool(
            settings_manager.get(
                "killzone_filter_enabled",
                False,
            )
        ):

            if not bool(
                analysis.get(
                    "killzone_active",
                    True,
                )
            ):

                return BrainResult(
                    0.0,
                    None,
                    threshold,
                    reason_map,
                    regime,
                    block_reason=(
                        BLOCK_REASON_KILLZONE
                    ),
                )

        spread_points = (
            self._finite(
                analysis.get(
                    "spread_points",
                    features.get(
                        "spread_points"
                    ),
                )
            )
        )

        max_spread = (
            self._finite(
                settings_manager.get(
                    "max_spread_points",
                    120,
                )
            )
        )

        if (
            spread_points
            is not None
            and max_spread
            is not None
            and spread_points
            > max_spread
        ):

            return BrainResult(
                0.0,
                None,
                threshold,
                {
                    **reason_map,
                    "spread_points": (
                        spread_points
                    ),
                    "max_spread_points": (
                        max_spread
                    ),
                },
                regime,
                block_reason=(
                    BLOCK_REASON_SPREAD
                ),
            )

        ai_required = bool(
            settings_manager.get(
                "self_learning_filter",
                True,
            )
        )

        ai_prob = (
            self._safe_probability(
                ai_confidence
            )
        )

        if ai_required:

            if ai_prob is None:

                return BrainResult(
                    0.0,
                    None,
                    threshold,
                    {
                        **reason_map,
                        "ai_confidence": None,
                    },
                    regime,
                    block_reason=(
                        BLOCK_REASON_AI_UNAVAILABLE
                    ),
                )

            min_conf = float(
                settings_manager.get(
                    "min_ai_confidence",
                    0.75,
                )
            )

            if ai_prob < min_conf:

                return BrainResult(
                    0.0,
                    None,
                    threshold,
                    {
                        **reason_map,
                        "ai_confidence": (
                            ai_prob
                        ),
                        "min_ai_confidence": (
                            min_conf
                        ),
                    },
                    regime,
                    block_reason=(
                        BLOCK_REASON_AI_LOW
                    ),
                )

        else:

            ai_prob = None

        (
            bull_t1,
            bear_t1,
            t1_map,
        ) = (
            self._score_tier1_directional(
                analysis
            )
        )

        (
            bull_t2,
            bear_t2,
            t2_map,
        ) = (
            self._score_tier2_execution(
                analysis,
                ai_prob,
            )
        )

        bull_total = (
            bull_t1
            + bull_t2
        )

        bear_total = (
            bear_t1
            + bear_t2
        )

        conviction_gap = (
            6.0
            if regime
            in {
                "RANGE",
                "COMPRESSION",
            }
            else 8.0
        )

        if (
            bull_total
            - bear_total
            >= conviction_gap
        ):

            brain_direction = (
                "BUY"
            )

            t1_score = (
                bull_t1
            )

            t2_score = (
                bull_t2
            )

        elif (
            bear_total
            - bull_total
            >= conviction_gap
        ):

            brain_direction = (
                "SELL"
            )

            t1_score = (
                bear_t1
            )

            t2_score = (
                bear_t2
            )

        else:

            brain_direction = (
                None
            )

            t1_score = max(
                bull_t1,
                bear_t1,
            )

            t2_score = max(
                bull_t2,
                bear_t2,
            )

        t3_score = float(
            np.clip(
                (
                    REGIME_QUALITY.get(
                        regime,
                        0.0,
                    )
                    + max(
                        0.0,
                        min(
                            5.0,
                            float(
                                session_score
                                or 0.0
                            ),
                        ),
                    )
                ),
                0.0,
                TIER3_MAX,
            )
        )

        reason_map.update(
            t1_map
        )

        reason_map.update(
            t2_map
        )

        reason_map.update(
            {
                "_tier1": round(
                    t1_score,
                    3,
                ),
                "_tier2": round(
                    t2_score,
                    3,
                ),
                "_tier3": round(
                    t3_score,
                    3,
                ),
                "bull_total_pre_t3": round(
                    bull_total,
                    3,
                ),
                "bear_total_pre_t3": round(
                    bear_total,
                    3,
                ),
            }
        )

        base_score = float(
            np.clip(
                (
                    t1_score
                    + t2_score
                    + t3_score
                ),
                0.0,
                100.0,
            )
        )

        if brain_direction is None:

            return BrainResult(
                base_score,
                None,
                threshold,
                reason_map,
                regime,
                block_reason=(
                    BLOCK_REASON_CONFLICTED
                ),
                tier1_score=t1_score,
                tier2_score=t2_score,
                tier3_score=t3_score,
            )

        normalized_action = (
            str(
                strategy_action
            ).upper()
            if strategy_action
            is not None
            else None
        )

        if normalized_action not in {
            "BUY",
            "SELL",
        }:

            return BrainResult(
                base_score,
                brain_direction,
                threshold,
                reason_map,
                regime,
                block_reason=(
                    BLOCK_REASON_NO_STRATEGY
                ),
                tier1_score=t1_score,
                tier2_score=t2_score,
                tier3_score=t3_score,
            )

        if (
            normalized_action
            != brain_direction
        ):

            return BrainResult(
                base_score,
                brain_direction,
                threshold,
                {
                    **reason_map,
                    "strategy_action": (
                        normalized_action
                    ),
                },
                regime,
                block_reason=(
                    BLOCK_REASON_STRATEGY_CONFLICT
                ),
                tier1_score=t1_score,
                tier2_score=t2_score,
                tier3_score=t3_score,
            )

        routing_adjustment = (
            0.0
        )

        routing_reason = (
            "NO_EMPIRICAL_DATA"
        )

        if strategy_name:

            (
                routing_adjustment,
                routing_reason,
            ) = (
                self
                ._get_strategy_routing_adjustment(
                    strategy_name=(
                        strategy_name
                    ),

                    mode=str(
                        settings_manager.get(
                            "trading_mode",
                            "intraday",
                        )
                    ).lower(),

                    weekday=(
                        datetime.now(
                            timezone.utc
                        ).weekday()
                    ),

                    session=str(
                        analysis.get(
                            "session_name",
                            "",
                        )
                    ),

                    regime=(
                        regime
                    ),
                )
            )

        reason_map[
            "routing_reason"
        ] = (
            routing_reason
        )

        reason_map[
            "routing_adjustment"
        ] = (
            routing_adjustment
        )

        brain_score = float(
            np.clip(
                (
                    base_score
                    + routing_adjustment
                ),
                0.0,
                100.0,
            )
        )

        block_reason = (
            None
            if brain_score
            >= threshold
            else BLOCK_REASON_SCORE
        )

        if (
            self._eval_count
            % 5
            == 0
        ):

            self._log(
                brain_score,
                brain_direction,
                regime,
                threshold,
                reason_map,
                block_reason,
            )

        return BrainResult(
            brain_score,
            brain_direction,
            threshold,
            reason_map,
            regime,
            block_reason=(
                block_reason
            ),
            tier1_score=(
                t1_score
            ),
            tier2_score=(
                t2_score
            ),
            tier3_score=(
                t3_score
            ),
        )

    # =========================================================================
    # TIER 1 — DIRECTION
    # =========================================================================

    def _score_tier1_directional(
        self,
        analysis: Dict,
    ) -> Tuple[
        float,
        float,
        Dict[
            str,
            float,
        ],
    ]:

        mode = str(
            settings_manager.get(
                "trading_mode",
                "intraday",
            )
        ).lower()

        weights = (
            MODE_T1_WEIGHTS.get(
                mode,
                DEFAULT_T1_WEIGHTS,
            )
        )

        values = {
            "d1": self._direction(
                analysis.get(
                    "d1_bias",
                    0,
                )
            ),

            "h4": self._direction(
                analysis.get(
                    "h4_bias",
                    0,
                )
            ),

            "h1": self._direction(
                analysis.get(
                    "h1_bias",
                    0,
                )
            ),

            "m15": self._direction(
                analysis.get(
                    "m15_bias",
                    0,
                )
            ),

            "m5": self._direction(
                analysis.get(
                    "m5_bias",
                    0,
                )
            ),

            "m1": self._direction(
                analysis.get(
                    "m1_bias",
                    0,
                )
            ),
        }

        bull = sum(
            weights.get(
                key,
                0.0,
            )
            for key, direction
            in values.items()
            if direction > 0
        )

        bear = sum(
            weights.get(
                key,
                0.0,
            )
            for key, direction
            in values.items()
            if direction < 0
        )

        bull = float(
            np.clip(
                bull,
                0.0,
                TIER1_MAX,
            )
        )

        bear = float(
            np.clip(
                bear,
                0.0,
                TIER1_MAX,
            )
        )

        return (
            bull,
            bear,
            {
                "t1_bull": round(
                    bull,
                    3,
                ),
                "t1_bear": round(
                    bear,
                    3,
                ),
            },
        )

    # =========================================================================
    # TIER 2 — EXECUTION QUALITY
    # =========================================================================

    def _score_tier2_execution(
        self,
        analysis: Dict,
        ai_confidence: Optional[
            float
        ],
    ) -> Tuple[
        float,
        float,
        Dict[
            str,
            float,
        ],
    ]:

        (
            bull_structure,
            bear_structure,
        ) = (
            self._score_structure(
                analysis
            )
        )

        (
            bull_fvg,
            bear_fvg,
        ) = (
            self._score_fvg(
                analysis
            )
        )

        (
            bull_vsa,
            bear_vsa,
        ) = (
            self._score_vsa(
                analysis
            )
        )

        (
            bull_volume,
            bear_volume,
        ) = (
            self._score_volume_pressure(
                analysis
            )
        )

        (
            bull_liq,
            bear_liq,
        ) = (
            self._score_liquidity(
                analysis
            )
        )

        features = analysis.get(
            "features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):

            features = {}

        ofi = (
            self._finite(
                analysis.get(
                    "ofi_imbalance",
                    features.get(
                        "ofi",
                        0.0,
                    ),
                )
            )
            or 0.0
        )

        bull_ofi = (
            2.0
            if ofi >= 0.15
            else 0.0
        )

        bear_ofi = (
            2.0
            if ofi <= -0.15
            else 0.0
        )

        zscore = (
            self._finite(
                analysis.get(
                    "regression_zscore"
                )
            )
            or 0.0
        )

        bull_stats = (
            3.0
        )

        bear_stats = (
            3.0
        )

        if zscore > 1.0:

            bull_stats = max(
                0.0,
                (
                    3.0
                    - (
                        zscore
                        - 1.0
                    )
                    * 1.5
                ),
            )

        if zscore < -1.0:

            bear_stats = max(
                0.0,
                (
                    3.0
                    - (
                        -zscore
                        - 1.0
                    )
                    * 1.5
                ),
            )

        ai_points = (
            self._score_ai_confidence(
                ai_confidence
            )
        )

        bull = float(
            np.clip(
                (
                    bull_structure
                    + bull_fvg
                    + bull_vsa
                    + bull_volume
                    + bull_liq
                    + bull_ofi
                    + bull_stats
                    + ai_points
                ),
                0.0,
                TIER2_MAX,
            )
        )

        bear = float(
            np.clip(
                (
                    bear_structure
                    + bear_fvg
                    + bear_vsa
                    + bear_volume
                    + bear_liq
                    + bear_ofi
                    + bear_stats
                    + ai_points
                ),
                0.0,
                TIER2_MAX,
            )
        )

        return (
            bull,
            bear,
            {
                "t2_bull": round(
                    bull,
                    3,
                ),

                "t2_bear": round(
                    bear,
                    3,
                ),

                "t2_ai": round(
                    ai_points,
                    3,
                ),

                "t2_ofi_bull": (
                    bull_ofi
                ),

                "t2_ofi_bear": (
                    bear_ofi
                ),
            },
        )

    def _score_structure(
        self,
        analysis: Dict,
    ) -> Tuple[
        float,
        float,
    ]:

        features = analysis.get(
            "features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):

            features = {}

        mss = self._direction(
            analysis.get(
                "m5_mss_signal",
                analysis.get(
                    "mss_signal",
                    features.get(
                        "mss_signal",
                        0,
                    ),
                ),
            )
        )

        sweep = self._direction(
            analysis.get(
                "m15_sweep_type",
                analysis.get(
                    "liq_sweep_type",
                    features.get(
                        "liq_sweep_type",
                        0,
                    ),
                ),
            )
        )

        bull = (
            (
                6.0
                if mss > 0
                else 0.0
            )
            + (
                6.0
                if sweep > 0
                else 0.0
            )
        )

        bear = (
            (
                6.0
                if mss < 0
                else 0.0
            )
            + (
                6.0
                if sweep < 0
                else 0.0
            )
        )

        return (
            min(
                bull,
                12.0,
            ),

            min(
                bear,
                12.0,
            ),
        )

    def _score_fvg(
        self,
        analysis: Dict,
    ) -> Tuple[
        float,
        float,
    ]:

        features = analysis.get(
            "features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):

            features = {}

        fvg_type = str(
            analysis.get(
                "m5_fvg_type",
                analysis.get(
                    "fvg_type",
                    "",
                ),
            )
        ).lower()

        fvg_class = str(
            analysis.get(
                "m5_fvg_class",
                analysis.get(
                    "fvg_class",
                    features.get(
                        "fvg_class",
                        "",
                    ),
                ),
            )
        ).lower()

        if any(
            token
            in fvg_class
            for token
            in (
                "fresh",
                "institutional",
                "active",
                "pfvg",
            )
        ):

            quality = (
                5.0
            )

        elif fvg_class not in {
            "",
            "none",
            "nan",
        }:

            quality = (
                2.5
            )

        else:

            quality = (
                0.0
            )

        if "bull" in fvg_type:

            return (
                quality,
                0.0,
            )

        if "bear" in fvg_type:

            return (
                0.0,
                quality,
            )

        return (
            0.0,
            0.0,
        )

    def _score_vsa(
        self,
        analysis: Dict,
    ) -> Tuple[
        float,
        float,
    ]:

        features = analysis.get(
            "features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):

            features = {}

        signals = (
            analysis.get(
                "vsa_signals",
                features.get(
                    "vsa_signals",
                    [],
                ),
            )
            or []
        )

        normalized = {
            str(
                signal
            )
            .strip()
            .upper()
            for signal
            in signals
        }

        bull = (
            4.0
            if (
                normalized
                & VSA_BULLISH_SIGNALS
            )
            else 0.0
        )

        bear = (
            4.0
            if (
                normalized
                & VSA_BEARISH_SIGNALS
            )
            else 0.0
        )

        return (
            bull,
            bear,
        )

    def _score_volume_pressure(
        self,
        analysis: Dict,
    ) -> Tuple[
        float,
        float,
    ]:

        features = analysis.get(
            "features",
            {},
        )

        if not isinstance(
            features,
            dict,
        ):

            features = {}

        buy = (
            self._finite(
                analysis.get(
                    "buy_pressure",
                    features.get(
                        "buy_pressure"
                    ),
                )
            )
        )

        sell = (
            self._finite(
                analysis.get(
                    "sell_pressure",
                    features.get(
                        "sell_pressure"
                    ),
                )
            )
        )

        if (
            buy is None
            or sell is None
            or (
                buy
                + sell
            )
            <= 0.0
        ):

            return (
                0.0,
                0.0,
            )

        total = (
            buy
            + sell
        )

        buy_pct = (
            100.0
            * buy
            / total
        )

        sell_pct = (
            100.0
            * sell
            / total
        )

        bull = float(
            np.clip(
                (
                    (
                        buy_pct
                        - 55.0
                    )
                    / 45.0
                    * 4.0
                ),
                0.0,
                4.0,
            )
        )

        bear = float(
            np.clip(
                (
                    (
                        sell_pct
                        - 55.0
                    )
                    / 45.0
                    * 4.0
                ),
                0.0,
                4.0,
            )
        )

        return (
            bull,
            bear,
        )

    def _score_ai_confidence(
        self,
        confidence: Optional[
            float
        ],
    ) -> float:

        if confidence is None:

            return 0.0

        confidence = float(
            np.clip(
                confidence,
                0.0,
                1.0,
            )
        )

        if confidence < 0.5:

            return 0.0

        return float(
            np.clip(
                (
                    (
                        confidence
                        - 0.5
                    )
                    * 8.0
                ),
                0.0,
                4.0,
            )
        )

    def _score_liquidity(
        self,
        analysis: Dict,
    ) -> Tuple[
        float,
        float,
    ]:

        bull = (
            0.0
        )

        bear = (
            0.0
        )

        for pool in (
            analysis.get(
                "swept_pools",
                [],
            )
            or []
        ):

            if not isinstance(
                pool,
                dict,
            ):

                continue

            text = " ".join(
                [
                    str(
                        pool.get(
                            "type",
                            "",
                        )
                    ),

                    str(
                        pool.get(
                            "pool_id",
                            "",
                        )
                    ),

                    str(
                        pool.get(
                            "description",
                            "",
                        )
                    ),
                ]
            ).lower()

            if any(
                token
                in text
                for token
                in (
                    "sell_stop",
                    "support",
                    "pdl",
                    "eql",
                    "low",
                )
            ):

                bull += (
                    3.0
                )

            elif any(
                token
                in text
                for token
                in (
                    "buy_stop",
                    "resistance",
                    "pdh",
                    "eqh",
                    "high",
                )
            ):

                bear += (
                    3.0
                )

        return (
            float(
                np.clip(
                    bull,
                    0.0,
                    3.0,
                )
            ),

            float(
                np.clip(
                    bear,
                    0.0,
                    3.0,
                )
            ),
        )

    # =========================================================================
    # LEGACY COMPATIBILITY UTILITIES
    # =========================================================================

    def _calculate_final_score(
        self,
        raw_score: float,
        penalties_map: Dict[
            str,
            float,
        ],
        scaling_factor: float = 1.0,
    ) -> Tuple[
        float,
        Dict[
            str,
            float,
        ],
    ]:

        score = float(
            raw_score
        )

        for value in (
            penalties_map.values()
        ):

            value = (
                self._finite(
                    value
                )
            )

            if value is not None:

                score += value

        return (
            float(
                np.clip(
                    (
                        score
                        * float(
                            scaling_factor
                        )
                    ),
                    0.0,
                    100.0,
                )
            ),

            dict(
                penalties_map
            ),
        )

    def _compute_m1_intraday_shift(
        self,
        df_ltf,
    ) -> int:
        """
        Telemetry only.

        It never overrides HTF direction or execution gates.
        """

        try:

            if (
                df_ltf is None
                or len(
                    df_ltf
                )
                < 12
            ):

                return 0

            recent = (
                df_ltf.tail(
                    12
                )
            )

            closes = (
                pd.to_numeric(
                    recent[
                        "close"
                    ],
                    errors="coerce",
                )
                .to_numpy()
            )

            opens = (
                pd.to_numeric(
                    recent[
                        "open"
                    ],
                    errors="coerce",
                )
                .to_numpy()
            )

            bull = int(
                np.sum(
                    closes
                    > opens
                )
            )

            bear = int(
                np.sum(
                    closes
                    < opens
                )
            )

            if bull >= 8:

                return 1

            if bear >= 8:

                return -1

        except Exception:

            pass

        return 0

    def _get_dow_modifier(
        self,
    ) -> Tuple[
        float,
        float,
    ]:
        """
        Compatibility API.

        No arbitrary Friday threshold reduction.
        """

        return (
            0.0,
            0.0,
        )

    # =========================================================================
    # OPERATIONAL HELPERS
    # =========================================================================

    def is_market_velocity_favorable(
        self,
        symbol: str,
    ) -> Tuple[
        bool,
        str,
    ]:
        """
        Hardcoded Gold/FX session permissions removed.

        Keep only toxic broker rollover protection.
        """

        current = (
            datetime.now(
                timezone.utc
            ).time()
        )

        symbol_upper = str(
            symbol
        ).upper()

        is_crypto = any(
            name
            in symbol_upper
            for name
            in (
                "BTC",
                "ETH",
                "SOL",
                "XRP",
            )
        )

        if (
            not is_crypto
            and time(
                21,
                55,
            )
            <= current
            <= time(
                22,
                15,
            )
        ):

            return (
                False,
                "ROLLOVER_LIQUIDITY_GAP",
            )

        return (
            True,
            "VELOCITY_APPROVED",
        )

    def _is_price_near_htf_levels(
        self,
        price: float,
        atr: float,
        df_h1: Optional[
            pd.DataFrame
        ],
        df_h4: Optional[
            pd.DataFrame
        ],
        df_m15: Optional[
            pd.DataFrame
        ] = None,
        df_m5: Optional[
            pd.DataFrame
        ] = None,
        is_scalping: bool = False,
        analysis: Optional[
            Dict
        ] = None,
    ) -> Tuple[
        bool,
        str,
    ]:

        price = float(
            price
        )

        atr = float(
            atr
        )

        if (
            price <= 0.0
            or atr <= 0.0
        ):

            return (
                False,
                "INVALID_PRICE_OR_ATR",
            )

        envelope = (
            (
                0.35
                if is_scalping
                else 0.25
            )
            * atr
        )

        frames: List[
            Tuple[
                str,
                Optional[
                    pd.DataFrame
                ],
                int,
            ]
        ] = []

        if is_scalping:

            frames.extend(
                [
                    (
                        "M5",
                        df_m5,
                        30,
                    ),

                    (
                        "M15",
                        df_m15,
                        30,
                    ),
                ]
            )

        frames.extend(
            [
                (
                    "H1",
                    df_h1,
                    60,
                ),

                (
                    "H4",
                    df_h4,
                    40,
                ),
            ]
        )

        for (
            label,
            frame,
            lookback,
        ) in frames:

            if (
                frame is None
                or len(
                    frame
                )
                < 3
            ):

                continue

            history = frame.iloc[
                -min(
                    len(
                        frame
                    ),
                    (
                        lookback
                        + 1
                    ),
                )
                :
                -1
            ]

            for column in (
                "support",
                "resistance",
                "ob_top",
                "ob_bottom",
            ):

                if column not in (
                    history.columns
                ):

                    continue

                values = (
                    pd.to_numeric(
                        history[
                            column
                        ],
                        errors="coerce",
                    )
                    .dropna()
                )

                if any(
                    abs(
                        price
                        - float(
                            level
                        )
                    )
                    <= envelope
                    for level
                    in values
                ):

                    return (
                        True,
                        (
                            f"{label}_"
                            f"{column.upper()}_"
                            f"CONFLUENCE"
                        ),
                    )

        return (
            False,
            "NO_STRUCTURAL_LEVEL",
        )

    # =========================================================================
    # DISPLAY / LOGGING
    # =========================================================================

    def _log(
        self,
        score: float,
        direction: Optional[
            str
        ],
        regime: str,
        threshold: float,
        reason_map: Dict,
        block_reason: Optional[
            str
        ],
    ) -> None:

        self.logger.info(
            (
                "Brain=%.1f/%.1f "
                "dir=%s regime=%s "
                "T1=%.1f T2=%.1f "
                "T3=%.1f block=%s"
            ),
            score,
            threshold,
            direction,
            regime,
            float(
                reason_map.get(
                    "_tier1",
                    0.0,
                )
            ),
            float(
                reason_map.get(
                    "_tier2",
                    0.0,
                )
            ),
            float(
                reason_map.get(
                    "_tier3",
                    0.0,
                )
            ),
            (
                block_reason
                or "none"
            ),
        )

    def get_score_label(
        self,
        score: float,
    ) -> str:

        score = float(
            score
        )

        if score >= 80.0:

            return (
                "ULTRA_CONVICTION"
            )

        if score >= 65.0:

            return (
                "HIGH_CONVICTION"
            )

        if score >= 55.0:

            return (
                "STANDARD"
            )

        if score >= 40.0:

            return (
                "LOW"
            )

        return (
            "BLOCKED"
        )

    def get_color_zone(
        self,
        score: float,
    ) -> str:

        score = float(
            score
        )

        if score >= 75.0:

            return (
                "#00ff88"
            )

        if score >= 55.0:

            return (
                "#ffcc00"
            )

        if score >= 40.0:

            return (
                "#ff8800"
            )

        return (
            "#ff3366"
        )

    def get_tier_summary(
        self,
        result: BrainResult,
    ) -> str:

        return (
            f"T1(dir)="
            f"{result.tier1_score:.0f}/50 "
            f"T2(exec)="
            f"{result.tier2_score:.0f}/35 "
            f"T3(context)="
            f"{result.tier3_score:.0f}/15"
        )

    # =========================================================================
    # NEW CANDIDATE PIPELINE
    # =========================================================================

    def route_experts(
        self,
        regime: str,
    ) -> set:
        """
        Capability allowlist only.

        This does NOT claim one strategy is empirically better than another.
        """

        if (
            str(
                regime
            ).upper()
            in HARD_BLOCKED_REGIMES
        ):

            return set()

        return set(
            self.KNOWN_STRATEGIES
        )

    def evaluate_candidates(
        self,
        context: "MarketContext",
        candidates: List[
            Tuple[
                "CandidateSetup",
                "CandidatePrediction",
            ]
        ],
        mode_profile,
        prediction_guard,
    ) -> List[
        Tuple[
            "CandidateSetup",
            "CandidatePrediction",
            float,
        ]
    ]:
        """
        Conservative expected-value candidate filter.

        No synthetic routing values.
        No model promotion.
        No execution authority.
        """

        from core.candidate_setup import (
            CandidateLifecycle,
            CandidateState,
        )

        regime = str(
            getattr(
                context,
                "regime_label",
                "RANGE",
            )
        ).upper()

        probabilities = (
            getattr(
                context,
                "regime_probabilities",
                {},
            )
            or {}
        )

        max_probability = (
            max(
                probabilities.values()
            )
            if probabilities
            else 0.0
        )

        if regime in (
            HARD_BLOCKED_REGIMES
        ):

            return []

        if (
            bool(
                settings_manager.get(
                    "dynamic_regime_filter",
                    False,
                )
            )
            and max_probability
            < 0.30
        ):

            return []

        active_experts = (
            self.route_experts(
                regime
            )
        )

        eligible = []

        for (
            candidate,
            prediction,
        ) in candidates:

            lifecycle = (
                CandidateLifecycle(
                    candidate
                )
            )

            strategy = (
                self._canonical_strategy(
                    getattr(
                        candidate,
                        "strategy_name",
                        "",
                    )
                )
            )

            if strategy not in (
                active_experts
            ):

                continue

            abstain_reason = (
                prediction_guard
                .should_abstain(
                    prediction,
                    context,
                )
            )

            if abstain_reason:

                try:

                    lifecycle.transition_to(
                        CandidateState
                        .CONTEXT_VALIDATED
                    )

                    lifecycle.transition_to(
                        CandidateState
                        .GEOMETRY_VALIDATED
                    )

                    lifecycle.transition_to(
                        CandidateState
                        .FEATURED
                    )

                    lifecycle.transition_to(
                        CandidateState
                        .ABSTAINED
                    )

                except Exception:

                    pass

                continue

            planned_rr = (
                self._finite(
                    getattr(
                        candidate,
                        "planned_rr",
                        None,
                    )
                )
            )

            minimum_rr = (
                self._finite(
                    getattr(
                        mode_profile,
                        "minimum_rr",
                        None,
                    )
                )
            )

            probability_lower = (
                self._safe_probability(
                    getattr(
                        prediction,
                        "probability_lower_bound",
                        None,
                    )
                )
            )

            uncertainty = (
                self._finite(
                    getattr(
                        prediction,
                        "epistemic_uncertainty",
                        None,
                    )
                )
            )

            execution_cost_r = (
                self._finite(
                    getattr(
                        prediction,
                        "execution_cost_r",
                        None,
                    )
                )
            )

            if (
                planned_rr is None
                or minimum_rr is None
                or planned_rr
                < minimum_rr
                or probability_lower
                is None
                or uncertainty
                is None
                or execution_cost_r
                is None
            ):

                continue

            conservative_ev = (
                probability_lower
                * planned_rr
                - (
                    1.0
                    - probability_lower
                )
                - execution_cost_r
                - (
                    0.10
                    * uncertainty
                )
            )

            if conservative_ev < 0.15:

                continue

            try:

                lifecycle.transition_to(
                    CandidateState
                    .CONTEXT_VALIDATED
                )

                lifecycle.transition_to(
                    CandidateState
                    .GEOMETRY_VALIDATED
                )

                lifecycle.transition_to(
                    CandidateState
                    .FEATURED
                )

                lifecycle.transition_to(
                    CandidateState
                    .PREDICTED
                )

                lifecycle.transition_to(
                    CandidateState
                    .ELIGIBLE
                )

            except Exception:

                pass

            eligible.append(
                (
                    candidate,
                    prediction,
                    float(
                        conservative_ev
                    ),
                )
            )

        eligible.sort(
            key=lambda row: (
                row[
                    2
                ]
            ),
            reverse=True,
        )

        return eligible