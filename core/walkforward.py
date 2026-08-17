# core/walkforward.py

"""
PulseViper Walk-Forward Validation
=================================

Evidence-only chronological stability validation.

This module NEVER fabricates metrics and NEVER promotes model weights or
settings by itself.

A passing walk-forward result means only:

    "the currently tested configuration showed acceptable historical
    out-of-sample stability."

Actual model promotion requires separate frozen challenger-vs-champion
validation.
"""

from __future__ import annotations

import json
import logging
import math
import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from utils.settings_manager import settings_manager


class WalkForwardValidator:
    """
    Chronological rolling walk-forward validator.

    Compatibility
    -------------
    Existing callers may continue to use:

        run_walk_forward_check(symbol)

    Rules
    -----

    - Uses causal AdaptiveBacktester.
    - Uses rolling train -> forward windows.
    - Uses a purge/embargo equal to max_holding_bars.
    - Never fabricates Sharpe.
    - Never changes settings.
    - Never promotes weights/models.
    """

    def __init__(
        self,
        train_window_days: int = 60,
        forward_window_days: int = 14,
        fold_count: int = 3,
        min_forward_trades_per_fold: int = 4,
        min_total_forward_trades: int = 20,
        min_positive_fold_ratio: float = 0.67,
        min_forward_expectancy_r: float = 0.0,
        min_forward_profit_factor: float = 1.0,
        max_forward_drawdown_r: float = 8.0,
        max_holding_bars: int = 200,
    ):
        self.logger = logging.getLogger(
            "PulseViper.WalkForward"
        )

        self.train_window_days = max(
            14,
            int(train_window_days),
        )

        self.forward_window_days = max(
            3,
            int(forward_window_days),
        )

        self.fold_count = max(
            2,
            min(
                12,
                int(fold_count),
            ),
        )

        self.min_forward_trades_per_fold = max(
            1,
            int(
                min_forward_trades_per_fold
            ),
        )

        self.min_total_forward_trades = max(
            self.min_forward_trades_per_fold,
            int(
                min_total_forward_trades
            ),
        )

        self.min_positive_fold_ratio = (
            self._clamp(
                float(
                    min_positive_fold_ratio
                ),
                0.0,
                1.0,
            )
        )

        self.min_forward_expectancy_r = float(
            min_forward_expectancy_r
        )

        self.min_forward_profit_factor = max(
            0.0,
            float(
                min_forward_profit_factor
            ),
        )

        self.max_forward_drawdown_r = max(
            0.0,
            float(
                max_forward_drawdown_r
            ),
        )

        self.max_holding_bars = max(
            1,
            min(
                5000,
                int(
                    max_holding_bars
                ),
            ),
        )

        self.results_path = (
            "logs/walkforward_results.json"
        )

        self.last_result: Dict[
            str,
            Any,
        ] = {}

        os.makedirs(
            "logs",
            exist_ok=True,
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(
            minimum,
            min(
                maximum,
                value,
            ),
        )

    @staticmethod
    def _finite(
        value: Any,
        default: float = 0.0,
    ) -> float:
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

        return default

    @staticmethod
    def _profit_factor_for_gate(
        value: Any,
    ) -> float:
        """
        AdaptiveBacktester returns None for mathematically infinite
        profit factor:

            positive gross profit
            zero gross loss

        For validation gates this is treated as +infinity.

        Sample-size gates still prevent one or two lucky trades from
        passing validation.
        """

        if value is None:
            return float(
                "inf"
            )

        try:
            result = float(
                value
            )

            if math.isfinite(
                result
            ):
                return max(
                    0.0,
                    result,
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

        return 0.0

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def run_walk_forward_check(
        self,
        symbol: str,
        trading_mode: Optional[
            str
        ] = None,
    ) -> Dict[str, Any]:
        """
        Run real chronological walk-forward validation.

        NEVER:

        - writes settings
        - writes model weights
        - changes champion model
        - fabricates Sharpe
        - fabricates win rate
        - fabricates trade count
        - automatically promotes anything
        """

        symbol = str(
            symbol
            or ""
        ).strip()

        if not symbol:
            result = (
                self._not_validated(
                    symbol="",
                    trading_mode=str(
                        trading_mode
                        or "UNKNOWN"
                    ),
                    reason=(
                        "INVALID_SYMBOL"
                    ),
                )
            )

            self.last_result = (
                result
            )

            return result

        if trading_mode is None:
            trading_mode = str(
                settings_manager.get(
                    "trading_mode",
                    "scalping",
                )
                or "scalping"
            )

        trading_mode = (
            trading_mode
            .lower()
            .strip()
        )

        if trading_mode not in (
            "scalping",
            "intraday",
            "swing",
        ):
            result = (
                self._not_validated(
                    symbol=symbol,
                    trading_mode=(
                        trading_mode
                    ),
                    reason=(
                        "INVALID_TRADING_MODE"
                    ),
                )
            )

            self.last_result = (
                result
            )

            return result

        try:
            result = self._run(
                symbol=symbol,
                trading_mode=(
                    trading_mode
                ),
            )

        except Exception as exc:
            self.logger.exception(
                (
                    "Walk-forward validation "
                    "failed for %s: %s"
                ),
                symbol,
                exc,
            )

            result = (
                self._not_validated(
                    symbol=symbol,
                    trading_mode=(
                        trading_mode
                    ),
                    reason=(
                        "WALK_FORWARD_EXCEPTION:"
                        f"{type(exc).__name__}"
                    ),
                )
            )

        self.last_result = dict(
            result
        )

        self._save_result(
            result
        )

        return result

    # =========================================================================
    # WALK-FORWARD CORE
    # =========================================================================

    def _run(
        self,
        symbol: str,
        trading_mode: str,
    ) -> Dict[str, Any]:

        from core.backtester import (
            AdaptiveBacktester,
        )

        from utils.smc_indicators import (
            SMCIndicators,
        )

        backtester = (
            AdaptiveBacktester()
        )

        mode = (
            backtester._mode_config(
                trading_mode
            )
        )

        ltf_seconds = int(
            mode[
                "ltf_seconds"
            ]
        )

        # ---------------------------------------------------------------------
        # PURGE / EMBARGO
        #
        # If a candidate can remain alive for 200 bars, decisions near the
        # edge of the training window must not consume candles from the
        # forward validation region.
        # ---------------------------------------------------------------------

        purge_seconds = (
            self.max_holding_bars
            * ltf_seconds
        )

        purge_delta = (
            pd.to_timedelta(
                purge_seconds,
                unit="s",
            )
        )

        # ---------------------------------------------------------------------
        # REQUIRED HISTORY
        # ---------------------------------------------------------------------

        requested_days = (
            self.train_window_days
            + (
                self.forward_window_days
                * self.fold_count
            )
            + 10
        )

        df_htf = (
            backtester._fetch_data(
                symbol,
                requested_days,
                mode[
                    "htf"
                ],
            )
        )

        df_context = (
            backtester._fetch_data(
                symbol,
                requested_days,
                mode[
                    "context"
                ],
            )
        )

        df_ltf = (
            backtester._fetch_data(
                symbol,
                requested_days,
                mode[
                    "ltf"
                ],
            )
        )

        if (
            df_htf is None
            or df_context is None
            or df_ltf is None
        ):
            return (
                self._not_validated(
                    symbol,
                    trading_mode,
                    (
                        "HISTORICAL_DATA_"
                        "UNAVAILABLE"
                    ),
                )
            )

        if len(
            df_ltf
        ) < 500:
            return (
                self._not_validated(
                    symbol,
                    trading_mode,
                    (
                        "INSUFFICIENT_"
                        "LTF_HISTORY"
                    ),
                )
            )

        # ---------------------------------------------------------------------
        # LOWER TF
        #
        # M1 can resolve same-bar ambiguity for M5/M15 trade tests.
        # ---------------------------------------------------------------------

        lower_tf = None

        if ltf_seconds > 60:
            lower_tf = (
                backtester._fetch_data(
                    symbol,
                    requested_days,
                    (
                        backtester
                        ._mode_config(
                            "scalping"
                        )[
                            "ltf"
                        ]
                    ),
                )
            )

        # ---------------------------------------------------------------------
        # CURRENT CONFIG
        # ---------------------------------------------------------------------

        swing_window = int(
            settings_manager.get(
                "smc_swing_window",
                2,
            )
            or 2
        )

        lookback_sweep = int(
            settings_manager.get(
                "smc_lookback_sweep",
                20,
            )
            or 20
        )

        lookback_mss = int(
            settings_manager.get(
                "smc_lookback_mss",
                10,
            )
            or 10
        )

        lookback_fvg = int(
            settings_manager.get(
                "smc_fvg_lookback",
                5,
            )
            or 5
        )

        rr_ratio = (
            self._finite(
                settings_manager.get(
                    "min_rr_ratio",
                    1.5,
                ),
                1.5,
            )
        )

        # ---------------------------------------------------------------------
        # CAUSAL SMC FEATURES
        #
        # Backtester will align them by availability-at-close time.
        # ---------------------------------------------------------------------

        htf_smc = (
            SMCIndicators
            .compute_smc_features(
                df_htf,
                window=(
                    swing_window
                ),
            )
        )

        context_smc = (
            SMCIndicators
            .compute_smc_features(
                df_context,
                window=(
                    swing_window
                ),
            )
        )

        ltf_smc = (
            SMCIndicators
            .compute_smc_features(
                df_ltf,
                window=(
                    swing_window
                ),
            )
        )

        # ---------------------------------------------------------------------
        # BUILD ROLLING WINDOWS
        # ---------------------------------------------------------------------

        final_available = (
            df_ltf.index[
                -1
            ]
            + pd.to_timedelta(
                ltf_seconds,
                unit="s",
            )
        )

        total_span = (
            pd.to_timedelta(
                (
                    self.train_window_days
                    + (
                        self.forward_window_days
                        * self.fold_count
                    )
                ),
                unit="D",
            )
        )

        first_train_start = (
            final_available
            - total_span
        )

        if (
            first_train_start
            < df_ltf.index[
                0
            ]
        ):
            return (
                self._not_validated(
                    symbol,
                    trading_mode,
                    (
                        "REQUESTED_WALK_FORWARD_"
                        "WINDOWS_NOT_AVAILABLE"
                    ),
                )
            )

        folds: List[
            Dict[str, Any]
        ] = []

        # =====================================================================
        # FOLDS
        # =====================================================================

        for fold_index in range(
            self.fold_count
        ):

            train_start = (
                first_train_start
                + pd.to_timedelta(
                    (
                        fold_index
                        * self.forward_window_days
                    ),
                    unit="D",
                )
            )

            train_boundary = (
                train_start
                + pd.to_timedelta(
                    self.train_window_days,
                    unit="D",
                )
            )

            forward_start = (
                train_boundary
            )

            forward_end = (
                forward_start
                + pd.to_timedelta(
                    self.forward_window_days,
                    unit="D",
                )
            )

            # -----------------------------------------------------------------
            # Purged decision boundaries.
            # -----------------------------------------------------------------

            train_eval_end = (
                train_boundary
                - purge_delta
            )

            forward_eval_end = (
                forward_end
                - purge_delta
            )

            if (
                train_eval_end
                <= train_start
                or forward_eval_end
                <= forward_start
            ):
                return (
                    self._not_validated(
                        symbol,
                        trading_mode,
                        (
                            "PURGE_WINDOW_TOO_LARGE_"
                            "FOR_CONFIGURED_FOLDS"
                        ),
                    )
                )

            # -----------------------------------------------------------------
            # TRAIN REGION METRICS
            #
            # No learning/promotion occurs here.
            # This is stability comparison only.
            # -----------------------------------------------------------------

            train_result = (
                backtester
                .run_backtest_simulation(
                    symbol=symbol,
                    htf_smc=(
                        htf_smc
                    ),
                    context_smc=(
                        context_smc
                    ),
                    ltf_smc=(
                        ltf_smc
                    ),
                    days=(
                        self.train_window_days
                    ),
                    rr_ratio=(
                        rr_ratio
                    ),
                    trading_mode=(
                        trading_mode
                    ),
                    lookback_sweep=(
                        lookback_sweep
                    ),
                    lookback_mss=(
                        lookback_mss
                    ),
                    lookback_fvg=(
                        lookback_fvg
                    ),
                    verbose=False,
                    lower_tf_bars=(
                        lower_tf
                    ),
                    evaluation_start=(
                        train_start
                    ),
                    evaluation_end=(
                        train_eval_end
                    ),
                    max_holding_bars=(
                        self.max_holding_bars
                    ),
                    commission_r=0.0,
                    slippage_r=0.0,
                )
            )

            # -----------------------------------------------------------------
            # TRUE FORWARD REGION
            # -----------------------------------------------------------------

            forward_result = (
                backtester
                .run_backtest_simulation(
                    symbol=symbol,
                    htf_smc=(
                        htf_smc
                    ),
                    context_smc=(
                        context_smc
                    ),
                    ltf_smc=(
                        ltf_smc
                    ),
                    days=(
                        self.forward_window_days
                    ),
                    rr_ratio=(
                        rr_ratio
                    ),
                    trading_mode=(
                        trading_mode
                    ),
                    lookback_sweep=(
                        lookback_sweep
                    ),
                    lookback_mss=(
                        lookback_mss
                    ),
                    lookback_fvg=(
                        lookback_fvg
                    ),
                    verbose=False,
                    lower_tf_bars=(
                        lower_tf
                    ),
                    evaluation_start=(
                        forward_start
                    ),
                    evaluation_end=(
                        forward_eval_end
                    ),
                    max_holding_bars=(
                        self.max_holding_bars
                    ),
                    commission_r=0.0,
                    slippage_r=0.0,
                )
            )

            train_metrics = (
                self._compact_metrics(
                    train_result
                )
            )

            forward_metrics = (
                self._compact_metrics(
                    forward_result
                )
            )

            forward_trades = int(
                forward_metrics.get(
                    "total_trades",
                    0,
                )
                or 0
            )

            forward_expectancy = (
                self._finite(
                    forward_metrics.get(
                        "expectancy_r",
                        0.0,
                    )
                )
            )

            forward_pf = (
                self._profit_factor_for_gate(
                    forward_metrics.get(
                        "profit_factor"
                    )
                )
            )

            forward_dd = (
                self._finite(
                    forward_metrics.get(
                        "max_drawdown_r",
                        0.0,
                    )
                )
            )

            # -----------------------------------------------------------------
            # FOLD GATES
            # -----------------------------------------------------------------

            sample_ok = (
                forward_trades
                >= (
                    self
                    .min_forward_trades_per_fold
                )
            )

            expectancy_ok = (
                forward_expectancy
                > (
                    self
                    .min_forward_expectancy_r
                )
            )

            profit_factor_ok = (
                forward_pf
                >= (
                    self
                    .min_forward_profit_factor
                )
            )

            drawdown_ok = (
                forward_dd
                <= (
                    self
                    .max_forward_drawdown_r
                )
            )

            fold_passed = bool(
                sample_ok
                and expectancy_ok
                and profit_factor_ok
                and drawdown_ok
            )

            folds.append(
                {
                    "fold": (
                        fold_index + 1
                    ),

                    "train_window": {
                        "start_utc": (
                            train_start
                            .isoformat()
                        ),

                        "decision_end_utc": (
                            train_eval_end
                            .isoformat()
                        ),

                        "natural_boundary_utc": (
                            train_boundary
                            .isoformat()
                        ),
                    },

                    "forward_window": {
                        "start_utc": (
                            forward_start
                            .isoformat()
                        ),

                        "decision_end_utc": (
                            forward_eval_end
                            .isoformat()
                        ),

                        "natural_boundary_utc": (
                            forward_end
                            .isoformat()
                        ),
                    },

                    "purge_seconds": (
                        purge_seconds
                    ),

                    "train_metrics": (
                        train_metrics
                    ),

                    "forward_metrics": (
                        forward_metrics
                    ),

                    "gates": {
                        "sample_ok": (
                            sample_ok
                        ),

                        "expectancy_ok": (
                            expectancy_ok
                        ),

                        "profit_factor_ok": (
                            profit_factor_ok
                        ),

                        "drawdown_ok": (
                            drawdown_ok
                        ),
                    },

                    "passed": (
                        fold_passed
                    ),
                }
            )

        return (
            self._aggregate(
                symbol=symbol,
                trading_mode=(
                    trading_mode
                ),
                folds=(
                    folds
                ),
                configuration={
                    "swing_window": (
                        swing_window
                    ),

                    "lookback_sweep": (
                        lookback_sweep
                    ),

                    "lookback_mss": (
                        lookback_mss
                    ),

                    "lookback_fvg": (
                        lookback_fvg
                    ),

                    "rr_ratio": (
                        rr_ratio
                    ),

                    "max_holding_bars": (
                        self
                        .max_holding_bars
                    ),
                },
            )
        )

    # =========================================================================
    # AGGREGATE FOLD RESULTS
    # =========================================================================

    def _aggregate(
        self,
        symbol: str,
        trading_mode: str,
        folds: List[
            Dict[str, Any]
        ],
        configuration: Dict[
            str,
            Any,
        ],
    ) -> Dict[str, Any]:

        total_forward_trades = 0
        total_wins = 0
        total_losses = 0

        positive_folds = 0

        max_forward_dd = 0.0

        expectancy_weighted_sum = (
            0.0
        )

        expectancy_weight = 0

        for fold in folds:
            metrics = (
                fold[
                    "forward_metrics"
                ]
            )

            trades = int(
                metrics.get(
                    "total_trades",
                    0,
                )
                or 0
            )

            wins = int(
                metrics.get(
                    "wins",
                    0,
                )
                or 0
            )

            losses = int(
                metrics.get(
                    "losses",
                    0,
                )
                or 0
            )

            expectancy = (
                self._finite(
                    metrics.get(
                        "expectancy_r",
                        0.0,
                    )
                )
            )

            drawdown = (
                self._finite(
                    metrics.get(
                        "max_drawdown_r",
                        0.0,
                    )
                )
            )

            total_forward_trades += (
                trades
            )

            total_wins += wins
            total_losses += losses

            max_forward_dd = max(
                max_forward_dd,
                drawdown,
            )

            if trades > 0:
                expectancy_weighted_sum += (
                    expectancy
                    * trades
                )

                expectancy_weight += (
                    trades
                )

            if fold.get(
                "passed",
                False,
            ):
                positive_folds += 1

        if expectancy_weight > 0:
            aggregate_expectancy = (
                expectancy_weighted_sum
                / expectancy_weight
            )

        else:
            aggregate_expectancy = (
                0.0
            )

        directional = (
            total_wins
            + total_losses
        )

        if directional > 0:
            aggregate_win_rate = (
                total_wins
                / directional
                * 100.0
            )

        else:
            aggregate_win_rate = (
                0.0
            )

        if folds:
            positive_fold_ratio = (
                positive_folds
                / len(
                    folds
                )
            )

        else:
            positive_fold_ratio = (
                0.0
            )

        # ---------------------------------------------------------------------
        # AGGREGATE VALIDATION GATES
        # ---------------------------------------------------------------------

        enough_samples = (
            total_forward_trades
            >= (
                self
                .min_total_forward_trades
            )
        )

        fold_stability_ok = (
            positive_fold_ratio
            >= (
                self
                .min_positive_fold_ratio
            )
        )

        aggregate_edge_ok = (
            aggregate_expectancy
            > (
                self
                .min_forward_expectancy_r
            )
        )

        aggregate_drawdown_ok = (
            max_forward_dd
            <= (
                self
                .max_forward_drawdown_r
            )
        )

        validation_passed = bool(
            enough_samples
            and fold_stability_ok
            and aggregate_edge_ok
            and aggregate_drawdown_ok
        )

        reasons: List[
            str
        ] = []

        if not enough_samples:
            reasons.append(
                (
                    "INSUFFICIENT_TOTAL_"
                    "FORWARD_TRADES"
                )
            )

        if not fold_stability_ok:
            reasons.append(
                (
                    "INSUFFICIENT_POSITIVE_"
                    "FOLD_RATIO"
                )
            )

        if not aggregate_edge_ok:
            reasons.append(
                (
                    "NON_POSITIVE_FORWARD_"
                    "EXPECTANCY"
                )
            )

        if not aggregate_drawdown_ok:
            reasons.append(
                (
                    "FORWARD_DRAWDOWN_"
                    "LIMIT_EXCEEDED"
                )
            )

        if not reasons:
            reasons.append(
                (
                    "WALK_FORWARD_"
                    "STABILITY_VALIDATED"
                )
            )

        result = {
            "symbol": (
                symbol
            ),

            "trading_mode": (
                trading_mode
            ),

            "timestamp_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "train_window_days": (
                self.train_window_days
            ),

            "forward_window_days": (
                self.forward_window_days
            ),

            "fold_count": (
                self.fold_count
            ),

            "configuration": (
                configuration
            ),

            # -----------------------------------------------------------------
            # Compatibility + real metrics
            # -----------------------------------------------------------------

            "metrics": {
                # Previous API expected this key.
                #
                # We deliberately return None instead of fabricating a Sharpe.
                "forward_sharpe": (
                    None
                ),

                "forward_win_rate": (
                    round(
                        aggregate_win_rate,
                        3,
                    )
                ),

                "trades_count": (
                    total_forward_trades
                ),

                "forward_expectancy_r": (
                    round(
                        aggregate_expectancy,
                        6,
                    )
                ),

                "positive_folds": (
                    positive_folds
                ),

                "positive_fold_ratio": (
                    round(
                        positive_fold_ratio,
                        6,
                    )
                ),

                "max_forward_drawdown_r": (
                    round(
                        max_forward_dd,
                        6,
                    )
                ),
            },

            "thresholds": {
                "min_sharpe": (
                    None
                ),

                "min_forward_trades_per_fold": (
                    self
                    .min_forward_trades_per_fold
                ),

                "min_total_forward_trades": (
                    self
                    .min_total_forward_trades
                ),

                "min_positive_fold_ratio": (
                    self
                    .min_positive_fold_ratio
                ),

                "min_forward_expectancy_r": (
                    self
                    .min_forward_expectancy_r
                ),

                "min_forward_profit_factor": (
                    self
                    .min_forward_profit_factor
                ),

                "max_forward_drawdown_r": (
                    self
                    .max_forward_drawdown_r
                ),
            },

            "folds": (
                folds
            ),

            # -----------------------------------------------------------------
            # Distinguish VALIDATION from PROMOTION.
            # -----------------------------------------------------------------

            "validation_passed": (
                validation_passed
            ),

            # WalkForwardValidator never has authority to promote.
            "passed_promotion": (
                False
            ),

            "reason": (
                "|".join(
                    reasons
                )
            ),

            "action_taken": (
                "VALIDATION_ONLY_"
                "NO_AUTO_PROMOTION"
            ),

            "promotion_required_next": (
                "CHALLENGER_VS_CHAMPION_"
                "FROZEN_VALIDATION"
            ),
        }

        self.logger.info(
            (
                "Walk-forward complete | "
                "%s %s | "
                "folds=%d/%d passed | "
                "trades=%d | "
                "expectancy=%.4fR | "
                "validation=%s | "
                "promotion=DISABLED"
            ),
            symbol,
            trading_mode,
            positive_folds,
            self.fold_count,
            total_forward_trades,
            aggregate_expectancy,
            validation_passed,
        )

        return result

    # =========================================================================
    # BACKTEST RESULT COMPACTION
    # =========================================================================

    @staticmethod
    def _compact_metrics(
        result: Dict[
            str,
            Any,
        ],
    ) -> Dict[str, Any]:

        return {
            "candidate_count": (
                result.get(
                    "candidate_count",
                    0,
                )
            ),

            "total_trades": (
                result.get(
                    "total_trades",
                    0,
                )
            ),

            "wins": (
                result.get(
                    "wins",
                    0,
                )
            ),

            "losses": (
                result.get(
                    "losses",
                    0,
                )
            ),

            "breakeven": (
                result.get(
                    "breakeven",
                    0,
                )
            ),

            "win_rate": (
                result.get(
                    "win_rate",
                    0.0,
                )
            ),

            "profit_factor": (
                result.get(
                    "profit_factor"
                )
            ),

            "expectancy_r": (
                result.get(
                    "expectancy_r",
                    0.0,
                )
            ),

            "max_drawdown_r": (
                result.get(
                    "max_drawdown_r",
                    0.0,
                )
            ),

            "ambiguous_excluded": (
                result.get(
                    "ambiguous_excluded",
                    0,
                )
            ),

            "censored_excluded": (
                result.get(
                    "censored_excluded",
                    0,
                )
            ),

            "invalid_excluded": (
                result.get(
                    "invalid_excluded",
                    0,
                )
            ),
        }

    # =========================================================================
    # FAIL CLOSED
    # =========================================================================

    def _not_validated(
        self,
        symbol: str,
        trading_mode: str,
        reason: str,
    ) -> Dict[str, Any]:

        return {
            "symbol": (
                symbol
            ),

            "trading_mode": (
                trading_mode
            ),

            "timestamp_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "train_window_days": (
                self.train_window_days
            ),

            "forward_window_days": (
                self.forward_window_days
            ),

            "fold_count": (
                self.fold_count
            ),

            "metrics": {
                "forward_sharpe": (
                    None
                ),

                "forward_win_rate": (
                    None
                ),

                "trades_count": (
                    0
                ),

                "forward_expectancy_r": (
                    None
                ),

                "positive_folds": (
                    0
                ),

                "positive_fold_ratio": (
                    0.0
                ),

                "max_forward_drawdown_r": (
                    None
                ),
            },

            "folds": [],

            "validation_passed": (
                False
            ),

            "passed_promotion": (
                False
            ),

            "reason": (
                reason
            ),

            "action_taken": (
                "NO_PROMOTION"
            ),

            "promotion_required_next": (
                "REAL_CAUSAL_"
                "VALIDATION_DATA"
            ),
        }

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def get_last_result(
        self,
    ) -> Dict[str, Any]:

        if self.last_result:
            return dict(
                self.last_result
            )

        return (
            self._load_result()
        )

    def _save_result(
        self,
        result: Dict[
            str,
            Any,
        ],
    ) -> None:

        try:
            temp_path = (
                self.results_path
                + ".tmp"
            )

            with open(
                temp_path,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    result,
                    handle,
                    indent=2,
                    default=str,
                )

                handle.flush()

                try:
                    os.fsync(
                        handle.fileno()
                    )

                except OSError:
                    pass

            os.replace(
                temp_path,
                self.results_path,
            )

        except Exception as exc:
            self.logger.error(
                (
                    "Failed saving "
                    "walk-forward result: %s"
                ),
                exc,
            )

    def _load_result(
        self,
    ) -> Dict[str, Any]:

        if not os.path.exists(
            self.results_path
        ):
            return {}

        try:
            with open(
                self.results_path,
                "r",
                encoding="utf-8",
            ) as handle:

                result = json.load(
                    handle
                )

            if isinstance(
                result,
                dict,
            ):
                return result

        except Exception as exc:
            self.logger.warning(
                (
                    "Failed loading "
                    "walk-forward result: %s"
                ),
                exc,
            )

        return {}