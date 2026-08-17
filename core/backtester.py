"""
PulseViper Causal Backtester
============================

Historical evaluation only.

This module DOES NOT promote settings by itself.

Guarantees
----------
1. Decisions use CLOSED information only.
2. HTF/context bars become usable only after their candle closes.
3. Signal is decided on LTF close.
4. Entry occurs at NEXT LTF candle open.
5. Actual SL/TP geometry determines R.
6. Same-bar ambiguity is excluded unless lower-TF data resolves it.
7. Unresolved trades are CENSORED.
8. Costs are not fabricated.
9. Optimizer is shadow-only with chronological holdout.
"""

from __future__ import annotations

import json
import logging
import math
import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from utils.mt5_gateway import (
    mt5_gateway as mt5,
)

from core.outcome_labeler import (
    OutcomeResolver,
)


class AdaptiveBacktester:

    def __init__(self):
        self.logger = logging.getLogger(
            "PulseViper.Backtester"
        )

        self.results_path = (
            "logs/backtest_results.json"
        )

        self.optimization_path = (
            "logs/optimization_log.json"
        )

        self.last_results: Dict[
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
    def _mode_config(
        trading_mode: str,
    ) -> Dict[str, Any]:

        mode = str(
            trading_mode
            or "scalping"
        ).lower().strip()

        if mode == "scalping":

            return {
                "mode": "scalping",

                "htf": (
                    mt5.TIMEFRAME_H1
                ),

                "context": (
                    mt5.TIMEFRAME_M5
                ),

                "ltf": (
                    mt5.TIMEFRAME_M1
                ),

                "htf_seconds": 3600,
                "context_seconds": 300,
                "ltf_seconds": 60,
            }

        if mode == "swing":

            return {
                "mode": "swing",

                "htf": (
                    mt5.TIMEFRAME_D1
                ),

                "context": (
                    mt5.TIMEFRAME_H1
                ),

                "ltf": (
                    mt5.TIMEFRAME_M15
                ),

                "htf_seconds": 86400,
                "context_seconds": 3600,
                "ltf_seconds": 900,
            }

        # intraday
        return {
            "mode": "intraday",

            "htf": (
                mt5.TIMEFRAME_H1
            ),

            "context": (
                mt5.TIMEFRAME_M15
            ),

            "ltf": (
                mt5.TIMEFRAME_M5
            ),

            "htf_seconds": 3600,
            "context_seconds": 900,
            "ltf_seconds": 300,
        }

    @staticmethod
    def _timeframe_seconds(
        timeframe: Any,
    ) -> int:

        pairs = (
            (
                getattr(
                    mt5,
                    "TIMEFRAME_M1",
                    None,
                ),
                60,
            ),
            (
                getattr(
                    mt5,
                    "TIMEFRAME_M5",
                    None,
                ),
                300,
            ),
            (
                getattr(
                    mt5,
                    "TIMEFRAME_M15",
                    None,
                ),
                900,
            ),
            (
                getattr(
                    mt5,
                    "TIMEFRAME_M30",
                    None,
                ),
                1800,
            ),
            (
                getattr(
                    mt5,
                    "TIMEFRAME_H1",
                    None,
                ),
                3600,
            ),
            (
                getattr(
                    mt5,
                    "TIMEFRAME_H4",
                    None,
                ),
                14400,
            ),
            (
                getattr(
                    mt5,
                    "TIMEFRAME_D1",
                    None,
                ),
                86400,
            ),
        )

        for (
            constant,
            seconds,
        ) in pairs:

            if (
                constant
                is not None
                and timeframe
                == constant
            ):
                return seconds

        return 60

    @staticmethod
    def _normalize_frame(
        frame: Optional[
            pd.DataFrame
        ],
    ) -> Optional[
        pd.DataFrame
    ]:

        if (
            frame is None
            or len(
                frame
            )
            == 0
        ):
            return frame

        df = frame.copy()

        if not isinstance(
            df.index,
            pd.DatetimeIndex,
        ):

            if (
                "time"
                not in df.columns
            ):
                return None

            df[
                "time"
            ] = pd.to_datetime(
                df[
                    "time"
                ],
                utc=True,
                errors="coerce",
            )

            df = df.set_index(
                "time"
            )

        if df.index.tz is None:

            df.index = (
                df.index
                .tz_localize(
                    "UTC"
                )
            )

        else:

            df.index = (
                df.index
                .tz_convert(
                    "UTC"
                )
            )

        df = (
            df[
                ~df.index.duplicated(
                    keep="last"
                )
            ]
            .sort_index()
        )

        return df

    @classmethod
    def _closed_only(
        cls,
        frame: Optional[
            pd.DataFrame
        ],
        timeframe_seconds: int,
    ) -> Optional[
        pd.DataFrame
    ]:

        df = cls._normalize_frame(
            frame
        )

        if (
            df is None
            or len(
                df
            )
            == 0
        ):
            return df

        now = pd.Timestamp.now(
            tz="UTC"
        )

        available_at = (
            df.index
            + pd.to_timedelta(
                timeframe_seconds,
                unit="s",
            )
        )

        return df.loc[
            available_at
            <= now
        ].copy()

    @staticmethod
    def _index_ns(
        index: pd.Index,
    ) -> np.ndarray:

        if not isinstance(
            index,
            pd.DatetimeIndex,
        ):
            raise TypeError(
                "BACKTEST_INDEX_MUST_BE_DATETIMEINDEX"
            )

        return np.asarray(
            index.asi8,
            dtype=np.int64,
        )

    @staticmethod
    def _timestamp_ns(
        value: Optional[
            Any
        ],
    ) -> Optional[
        int
    ]:

        if value is None:
            return None

        timestamp = pd.Timestamp(
            value
        )

        if (
            timestamp.tzinfo
            is None
        ):

            timestamp = (
                timestamp
                .tz_localize(
                    "UTC"
                )
            )

        else:

            timestamp = (
                timestamp
                .tz_convert(
                    "UTC"
                )
            )

        return int(
            timestamp.value
        )

    # =========================================================================
    # DATA
    # =========================================================================

    def _fetch_data(
        self,
        symbol: str,
        days: int,
        timeframe,
    ) -> Optional[
        pd.DataFrame
    ]:

        try:
            seconds = (
                self._timeframe_seconds(
                    timeframe
                )
            )

            days = max(
                1,
                int(
                    days
                ),
            )

            bars_per_day = max(
                1,
                int(
                    math.ceil(
                        86400
                        / seconds
                    )
                ),
            )

            # Warmup history for indicators / swing confirmation.
            requested = (
                days
                * bars_per_day
                + 500
            )

            requested = min(
                max(
                    requested,
                    500,
                ),
                50000,
            )

            rates = (
                mt5.copy_rates_from_pos(
                    symbol,
                    timeframe,
                    0,
                    requested,
                )
            )

            if (
                rates is None
                or len(
                    rates
                )
                < 100
            ):

                self.logger.warning(
                    (
                        "Insufficient MT5 "
                        "history for %s "
                        "timeframe=%s"
                    ),
                    symbol,
                    timeframe,
                )

                return None

            df = pd.DataFrame(
                rates
            )

            if (
                "time"
                not in df.columns
            ):
                return None

            df[
                "time"
            ] = pd.to_datetime(
                df[
                    "time"
                ],
                unit="s",
                utc=True,
            )

            df = df.set_index(
                "time"
            )

            if (
                "tick_volume"
                in df.columns
                and "volume"
                not in df.columns
            ):

                df[
                    "volume"
                ] = df[
                    "tick_volume"
                ]

            # Keep broker spread if MT5 supplied it.
            # Do not strip it like old fetch_ohlcv().
            df = (
                self._closed_only(
                    df,
                    seconds,
                )
            )

            if (
                df is None
                or len(
                    df
                )
                < 100
            ):
                return None

            return df

        except Exception as exc:

            self.logger.exception(
                (
                    "Backtest data fetch "
                    "failed: %s"
                ),
                exc,
            )

            return None

    def _symbol_point(
        self,
        symbol: str,
    ) -> float:

        try:
            info = (
                mt5.symbol_info(
                    symbol
                )
            )

            if info is None:
                return 0.0

            point = (
                self._finite(
                    getattr(
                        info,
                        "point",
                        0.0,
                    )
                )
            )

            return max(
                0.0,
                point,
            )

        except Exception:
            return 0.0

    # =========================================================================
    # BACKTEST
    # =========================================================================

    def run_backtest(
        self,
        symbol: str,
        days: int = 30,
        rr_ratio: float = 2.0,
        trading_mode: str = "scalping",
        swing_window: int = 2,
        lookback_sweep: int = 20,
        lookback_mss: int = 10,
        lookback_fvg: int = 5,
    ) -> Dict[str, Any]:

        from utils.smc_indicators import (
            SMCIndicators,
        )

        config = (
            self._mode_config(
                trading_mode
            )
        )

        df_htf = (
            self._fetch_data(
                symbol,
                days,
                config[
                    "htf"
                ],
            )
        )

        df_context = (
            self._fetch_data(
                symbol,
                days,
                config[
                    "context"
                ],
            )
        )

        df_ltf = (
            self._fetch_data(
                symbol,
                days,
                config[
                    "ltf"
                ],
            )
        )

        if (
            df_htf is None
            or df_context is None
            or df_ltf is None
        ):

            return {
                "error": (
                    "FAILED_TO_FETCH_BACKTEST_DATA"
                ),
                "symbol": symbol,
                "trading_mode": (
                    config[
                        "mode"
                    ]
                ),
            }

        if (
            len(
                df_htf
            )
            < 50
            or len(
                df_context
            )
            < 50
            or len(
                df_ltf
            )
            < 100
        ):

            return {
                "error": (
                    "NOT_ENOUGH_CLOSED_HISTORICAL_BARS"
                ),
                "symbol": symbol,
                "trading_mode": (
                    config[
                        "mode"
                    ]
                ),
            }

        try:

            htf_smc = (
                SMCIndicators.compute_smc_features(
                    df_htf,
                    window=int(
                        swing_window
                    ),
                )
            )

            context_smc = (
                SMCIndicators.compute_smc_features(
                    df_context,
                    window=int(
                        swing_window
                    ),
                )
            )

            ltf_smc = (
                SMCIndicators.compute_smc_features(
                    df_ltf,
                    window=int(
                        swing_window
                    ),
                )
            )

        except Exception as exc:

            return {
                "error": (
                    f"SMC_COMPUTE_FAILED:{exc}"
                ),
                "symbol": symbol,
                "trading_mode": (
                    config[
                        "mode"
                    ]
                ),
            }

        lower_tf_bars = None

        # M1 evidence for resolving M5/M15 same-bar ambiguity.
        if (
            config[
                "ltf_seconds"
            ]
            > 60
        ):

            lower_tf_bars = (
                self._fetch_data(
                    symbol,
                    days,
                    mt5.TIMEFRAME_M1,
                )
            )

        return (
            self.run_backtest_simulation(
                symbol=(
                    symbol
                ),
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
                    days
                ),
                rr_ratio=(
                    rr_ratio
                ),
                trading_mode=(
                    config[
                        "mode"
                    ]
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
                lower_tf_bars=(
                    lower_tf_bars
                ),
            )
        )

    # =========================================================================
    # SIMULATION
    # =========================================================================

    def run_backtest_simulation(
        self,
        symbol: str,
        htf_smc: pd.DataFrame,
        context_smc: pd.DataFrame,
        ltf_smc: pd.DataFrame,
        days: int,
        rr_ratio: float,
        trading_mode: str,
        lookback_sweep: int,
        lookback_mss: int,
        lookback_fvg: int,
        verbose: bool = True,
        lower_tf_bars: Optional[
            pd.DataFrame
        ] = None,
        evaluation_start: Optional[
            Any
        ] = None,
        evaluation_end: Optional[
            Any
        ] = None,
        max_holding_bars: int = 200,
        commission_r: float = 0.0,
        slippage_r: float = 0.0,
    ) -> Dict[str, Any]:

        config = (
            self._mode_config(
                trading_mode
            )
        )

        normalized_htf = (
            self._normalize_frame(
                htf_smc
            )
        )

        normalized_context = (
            self._normalize_frame(
                context_smc
            )
        )

        normalized_ltf = (
            self._normalize_frame(
                ltf_smc
            )
        )

        lower_tf_bars = (
            self._normalize_frame(
                lower_tf_bars
            )
        )

        if (
            normalized_htf is None
            or normalized_context is None
            or normalized_ltf is None
        ):

            return {
                "error": (
                    "INVALID_BACKTEST_FRAMES"
                ),
                "symbol": symbol,
            }

        htf_smc = normalized_htf
        context_smc = normalized_context
        ltf_smc = normalized_ltf

        required_htf = {
            "active_bias",
        }

        required_context = {
            "liq_sweep_type",
        }

        required_ltf = {
            "open",
            "high",
            "low",
            "close",
            "atr",
            "support",
            "resistance",
            "fvg_class",
            "mss_signal",
        }

        if not required_htf.issubset(
            htf_smc.columns
        ):

            return {
                "error": (
                    "HTF_FEATURES_MISSING"
                ),
                "missing": sorted(
                    required_htf
                    - set(
                        htf_smc.columns
                    )
                ),
            }

        if not required_context.issubset(
            context_smc.columns
        ):

            return {
                "error": (
                    "CONTEXT_FEATURES_MISSING"
                ),
                "missing": sorted(
                    required_context
                    - set(
                        context_smc.columns
                    )
                ),
            }

        if not required_ltf.issubset(
            ltf_smc.columns
        ):

            return {
                "error": (
                    "LTF_FEATURES_MISSING"
                ),
                "missing": sorted(
                    required_ltf
                    - set(
                        ltf_smc.columns
                    )
                ),
            }

        n = len(
            ltf_smc
        )

        if n < 150:

            return {
                "error": (
                    "INSUFFICIENT_LTF_BARS"
                ),
                "symbol": symbol,
            }

        ltf_index_ns = (
            self._index_ns(
                ltf_smc.index
            )
        )

        htf_index_ns = (
            self._index_ns(
                htf_smc.index
            )
        )

        context_index_ns = (
            self._index_ns(
                context_smc.index
            )
        )

        # ---------------------------------------------------------------------
        # CAUSAL MTF AVAILABILITY
        # ---------------------------------------------------------------------

        htf_available_ns = (
            htf_index_ns
            + int(
                config[
                    "htf_seconds"
                ]
                * 1_000_000_000
            )
        )

        context_available_ns = (
            context_index_ns
            + int(
                config[
                    "context_seconds"
                ]
                * 1_000_000_000
            )
        )

        ltf_close_delta_ns = int(
            config[
                "ltf_seconds"
            ]
            * 1_000_000_000
        )

        ltf_open = (
            ltf_smc[
                "open"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_high = (
            ltf_smc[
                "high"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_low = (
            ltf_smc[
                "low"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_close = (
            ltf_smc[
                "close"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_atr = (
            ltf_smc[
                "atr"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_support = (
            ltf_smc[
                "support"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_resistance = (
            ltf_smc[
                "resistance"
            ].to_numpy(
                dtype=float
            )
        )

        ltf_fvg_class = (
            ltf_smc[
                "fvg_class"
            ].to_numpy()
        )

        ltf_mss_signal = (
            ltf_smc[
                "mss_signal"
            ].to_numpy()
        )

        htf_active_bias = (
            htf_smc[
                "active_bias"
            ].to_numpy()
        )

        context_sweeps = (
            context_smc[
                "liq_sweep_type"
            ].to_numpy()
        )

        # ---------------------------------------------------------------------
        # HISTORICAL SPREAD
        # ---------------------------------------------------------------------

        if (
            "spread"
            in ltf_smc.columns
        ):

            ltf_spread = (
                ltf_smc[
                    "spread"
                ].to_numpy(
                    dtype=float
                )
            )

            historical_spread_available = (
                True
            )

        else:

            ltf_spread = np.zeros(
                n,
                dtype=float,
            )

            historical_spread_available = (
                False
            )

        point = (
            self._symbol_point(
                symbol
            )
        )

        # ---------------------------------------------------------------------
        # LOWER-TF DATA
        # ---------------------------------------------------------------------

        lower_index_ns = None

        if (
            lower_tf_bars
            is not None
            and len(
                lower_tf_bars
            )
            > 0
            and {
                "high",
                "low",
            }.issubset(
                lower_tf_bars.columns
            )
        ):

            lower_index_ns = (
                self._index_ns(
                    lower_tf_bars.index
                )
            )

        start_ns = (
            self._timestamp_ns(
                evaluation_start
            )
        )

        end_ns = (
            self._timestamp_ns(
                evaluation_end
            )
        )

        warmup = max(
            100,
            int(
                lookback_sweep
            )
            + 5,
            int(
                lookback_mss
            )
            + 5,
            int(
                lookback_fvg
            )
            + 5,
        )

        max_holding_bars = max(
            1,
            min(
                int(
                    max_holding_bars
                ),
                5000,
            ),
        )

        rr_ratio = max(
            0.1,
            self._finite(
                rr_ratio,
                2.0,
            ),
        )

        resolved_trades: List[
            Dict[str, Any]
        ] = []

        candidate_count = 0
        ambiguous_count = 0
        censored_count = 0
        invalid_count = 0

        trade_exit_bar = -1

        # =====================================================================
        # MAIN SIMULATION LOOP
        # =====================================================================

        for i in range(
            warmup,
            n - 1,
        ):

            if (
                i
                <= trade_exit_bar
            ):
                continue

            # Decision only exists when LTF bar closes.
            decision_ns = (
                int(
                    ltf_index_ns[
                        i
                    ]
                )
                + ltf_close_delta_ns
            )

            if (
                start_ns
                is not None
                and decision_ns
                < start_ns
            ):
                continue

            if (
                end_ns
                is not None
                and decision_ns
                >= end_ns
            ):
                continue

            # Only HTF/context candles whose CLOSE time has passed.
            idx_htf = int(
                np.searchsorted(
                    htf_available_ns,
                    decision_ns,
                    side="right",
                )
            )

            idx_context = int(
                np.searchsorted(
                    context_available_ns,
                    decision_ns,
                    side="right",
                )
            )

            if (
                idx_htf <= 0
                or idx_context <= 0
            ):
                continue

            htf_row = (
                idx_htf - 1
            )

            context_last_row = (
                idx_context - 1
            )

            htf_bias = int(
                self._finite(
                    htf_active_bias[
                        htf_row
                    ],
                    0.0,
                )
            )

            # -----------------------------------------------------------------
            # CONTEXT SWEEP
            # -----------------------------------------------------------------

            context_sweep = 0

            sweep_start = max(
                0,
                idx_context
                - int(
                    lookback_sweep
                ),
            )

            for k in range(
                context_last_row,
                sweep_start - 1,
                -1,
            ):

                value = int(
                    self._finite(
                        context_sweeps[
                            k
                        ],
                        0.0,
                    )
                )

                if value != 0:
                    context_sweep = (
                        value
                    )
                    break

            # -----------------------------------------------------------------
            # LTF MSS
            # -----------------------------------------------------------------

            ltf_mss = 0

            mss_start = max(
                0,
                i
                - int(
                    lookback_mss
                )
                + 1,
            )

            for k in range(
                i,
                mss_start - 1,
                -1,
            ):

                value = int(
                    self._finite(
                        ltf_mss_signal[
                            k
                        ],
                        0.0,
                    )
                )

                if value != 0:
                    ltf_mss = value
                    break

            # -----------------------------------------------------------------
            # FVG CONTEXT
            # -----------------------------------------------------------------

            fvg_class = "none"

            fvg_start = max(
                0,
                i
                - int(
                    lookback_fvg
                )
                + 1,
            )

            for k in range(
                i,
                fvg_start - 1,
                -1,
            ):

                value = str(
                    ltf_fvg_class[
                        k
                    ]
                ).lower()

                if value not in (
                    "none",
                    "rfvg",
                    "",
                    "nan",
                ):

                    fvg_class = value
                    break

            atr = (
                self._finite(
                    ltf_atr[
                        i
                    ]
                )
            )

            if atr <= 0.0:
                continue

            bullish = (
                htf_bias == 1
                and context_sweep
                == 1
                and ltf_mss
                == 1
            )

            bearish = (
                htf_bias == -1
                and context_sweep
                == -1
                and ltf_mss
                == -1
            )

            if (
                not bullish
                and not bearish
            ):
                continue

            # -----------------------------------------------------------------
            # NEXT BAR ENTRY
            # -----------------------------------------------------------------

            entry_idx = (
                i + 1
            )

            entry = (
                self._finite(
                    ltf_open[
                        entry_idx
                    ]
                )
            )

            if entry <= 0.0:
                continue

            support = (
                self._finite(
                    ltf_support[
                        i
                    ],
                    float(
                        "nan"
                    ),
                )
            )

            resistance = (
                self._finite(
                    ltf_resistance[
                        i
                    ],
                    float(
                        "nan"
                    ),
                )
            )

            # -----------------------------------------------------------------
            # BUY
            # -----------------------------------------------------------------

            if bullish:

                action = "BUY"

                base_sl = (
                    entry
                    - 1.5
                    * atr
                )

                if math.isfinite(
                    support
                ):

                    sl = min(
                        support
                        - 0.2
                        * atr,
                        base_sl,
                    )

                else:
                    sl = base_sl

                risk_distance = (
                    entry
                    - sl
                )

                if (
                    risk_distance
                    <= 0.0
                ):

                    invalid_count += 1
                    continue

                tp = (
                    entry
                    + rr_ratio
                    * risk_distance
                )

                if (
                    math.isfinite(
                        resistance
                    )
                    and resistance
                    > entry
                ):

                    # Structural TP can extend reward,
                    # but actual R is calculated later.
                    tp = max(
                        tp,
                        resistance,
                    )

            # -----------------------------------------------------------------
            # SELL
            # -----------------------------------------------------------------

            else:

                action = "SELL"

                base_sl = (
                    entry
                    + 1.5
                    * atr
                )

                if math.isfinite(
                    resistance
                ):

                    sl = max(
                        resistance
                        + 0.2
                        * atr,
                        base_sl,
                    )

                else:
                    sl = (
                        base_sl
                    )

                risk_distance = (
                    sl
                    - entry
                )

                if (
                    risk_distance
                    <= 0.0
                ):

                    invalid_count += 1
                    continue

                tp = (
                    entry
                    - rr_ratio
                    * risk_distance
                )

                if (
                    math.isfinite(
                        support
                    )
                    and support
                    < entry
                ):

                    tp = min(
                        tp,
                        support,
                    )

            if (
                sl <= 0.0
                or tp <= 0.0
            ):

                invalid_count += 1
                continue

            candidate_count += 1

            horizon_end = min(
                n,
                entry_idx
                + max_holding_bars,
            )

            bars_future = [
                {
                    "open": (
                        self._finite(
                            ltf_open[
                                j
                            ]
                        )
                    ),
                    "high": (
                        self._finite(
                            ltf_high[
                                j
                            ]
                        )
                    ),
                    "low": (
                        self._finite(
                            ltf_low[
                                j
                            ]
                        )
                    ),
                    "close": (
                        self._finite(
                            ltf_close[
                                j
                            ]
                        )
                    ),
                }
                for j
                in range(
                    entry_idx,
                    horizon_end,
                )
            ]

            spread_points = max(
                0.0,
                self._finite(
                    ltf_spread[
                        entry_idx
                    ],
                    0.0,
                ),
            )

            candidate_id = (
                f"BT-{symbol}-"
                f"{int(ltf_index_ns[i])}"
            )

            # -----------------------------------------------------------------
            # PRIMARY TF OUTCOME
            # -----------------------------------------------------------------

            outcome = (
                OutcomeResolver.resolve(
                    candidate_id=(
                        candidate_id
                    ),
                    entry_price=(
                        entry
                    ),
                    stop_price=(
                        sl
                    ),
                    target_price=(
                        tp
                    ),
                    action=(
                        action
                    ),
                    bars_future=(
                        bars_future
                    ),
                    lower_tf_bars=None,
                    spread_points=(
                        spread_points
                    ),
                    point=(
                        point
                    ),
                    commission_r=(
                        commission_r
                    ),
                    slippage_r=(
                        slippage_r
                    ),
                    force_time_exit=False,
                )
            )

            # -----------------------------------------------------------------
            # LOWER-TF AMBIGUITY RESOLUTION
            # -----------------------------------------------------------------

            if (
                outcome.outcome_type
                == "AMBIGUOUS_SAME_BAR"
                and lower_index_ns
                is not None
                and lower_tf_bars
                is not None
            ):

                lower_start_ns = int(
                    ltf_index_ns[
                        entry_idx
                    ]
                )

                lower_end_ns = int(
                    ltf_index_ns[
                        min(
                            horizon_end - 1,
                            n - 1,
                        )
                    ]
                    + ltf_close_delta_ns
                )

                lo = int(
                    np.searchsorted(
                        lower_index_ns,
                        lower_start_ns,
                        side="left",
                    )
                )

                hi = int(
                    np.searchsorted(
                        lower_index_ns,
                        lower_end_ns,
                        side="left",
                    )
                )

                lower_slice = (
                    lower_tf_bars.iloc[
                        lo:hi
                    ]
                )

                lower_records = [
                    {
                        "high": (
                            self._finite(
                                row[
                                    "high"
                                ]
                            )
                        ),
                        "low": (
                            self._finite(
                                row[
                                    "low"
                                ]
                            )
                        ),
                    }
                    for _,
                    row
                    in lower_slice.iterrows()
                ]

                outcome = (
                    OutcomeResolver.resolve(
                        candidate_id=(
                            candidate_id
                        ),
                        entry_price=(
                            entry
                        ),
                        stop_price=(
                            sl
                        ),
                        target_price=(
                            tp
                        ),
                        action=(
                            action
                        ),
                        bars_future=(
                            bars_future
                        ),
                        lower_tf_bars=(
                            lower_records
                        ),
                        spread_points=(
                            spread_points
                        ),
                        point=(
                            point
                        ),
                        commission_r=(
                            commission_r
                        ),
                        slippage_r=(
                            slippage_r
                        ),
                        force_time_exit=False,
                    )
                )

            # One trade at a time.
            if (
                outcome.holding_bars
                > 0
            ):

                trade_exit_bar = min(
                    n - 1,
                    entry_idx
                    + outcome.holding_bars
                    - 1,
                )

            else:

                trade_exit_bar = (
                    entry_idx
                )

            if (
                outcome.outcome_type
                == "AMBIGUOUS_SAME_BAR"
            ):

                ambiguous_count += 1
                continue

            if (
                outcome.outcome_type
                == "CENSORED"
            ):

                censored_count += 1

                trade_exit_bar = max(
                    trade_exit_bar,
                    horizon_end - 1,
                )

                continue

            if (
                outcome.outcome_type
                == "INVALID_GEOMETRY"
                or outcome.net_r
                is None
            ):

                invalid_count += 1
                continue

            net_r = float(
                outcome.net_r
            )

            if (
                outcome.outcome_type
                == "TP_FIRST"
            ):
                close_price = tp

            else:
                close_price = sl

            resolved_trades.append(
                {
                    "candidate_id": (
                        candidate_id
                    ),

                    "action": (
                        action
                    ),

                    "decision_time_utc": (
                        pd.Timestamp(
                            decision_ns,
                            tz="UTC",
                        ).isoformat()
                    ),

                    "entry_time_utc": (
                        ltf_smc.index[
                            entry_idx
                        ].isoformat()
                    ),

                    "entry": round(
                        float(
                            entry
                        ),
                        8,
                    ),

                    "close": round(
                        float(
                            close_price
                        ),
                        8,
                    ),

                    "sl": round(
                        float(
                            sl
                        ),
                        8,
                    ),

                    "tp": round(
                        float(
                            tp
                        ),
                        8,
                    ),

                    "planned_rr": round(
                        rr_ratio,
                        4,
                    ),

                    "actual_target_r": round(
                        abs(
                            tp
                            - entry
                        )
                        / risk_distance,
                        4,
                    ),

                    "net_r": round(
                        net_r,
                        5,
                    ),

                    # Existing compatibility aliases.
                    "rr": round(
                        net_r,
                        5,
                    ),

                    "outcome": round(
                        net_r,
                        5,
                    ),

                    "outcome_type": (
                        outcome.outcome_type
                    ),

                    "bars_held": (
                        outcome.holding_bars
                    ),

                    "win": bool(
                        net_r > 0.0
                    ),

                    "mfe_r": round(
                        outcome.mfe_r,
                        5,
                    ),

                    "mae_r": round(
                        outcome.mae_r,
                        5,
                    ),

                    "spread_r": round(
                        outcome.spread_r,
                        5,
                    ),

                    "commission_r": round(
                        outcome.commission_r,
                        5,
                    ),

                    "slippage_r": round(
                        outcome.slippage_r,
                        5,
                    ),

                    "setup": (
                        "SHARP_TURN"
                        if (
                            context_sweep
                            != 0
                            and ltf_mss
                            != 0
                        )
                        else "MSS_ONLY"
                    ),

                    "fvg_class": (
                        fvg_class
                    ),

                    "data_source": (
                        outcome.data_source
                    ),

                    "source_quality": (
                        outcome.source_quality
                    ),

                    "label_version": (
                        outcome.label_version
                    ),
                }
            )

        return (
            self._build_results(
                symbol=(
                    symbol
                ),
                days=(
                    days
                ),
                rr_ratio=(
                    rr_ratio
                ),
                trading_mode=(
                    config[
                        "mode"
                    ]
                ),
                trades=(
                    resolved_trades
                ),
                candidate_count=(
                    candidate_count
                ),
                ambiguous_count=(
                    ambiguous_count
                ),
                censored_count=(
                    censored_count
                ),
                invalid_count=(
                    invalid_count
                ),
                historical_spread_available=(
                    historical_spread_available
                ),
                point_available=(
                    point > 0.0
                ),
                commission_r=(
                    commission_r
                ),
                slippage_r=(
                    slippage_r
                ),
                verbose=(
                    verbose
                ),
            )
        )

    # =========================================================================
    # RESULTS
    # =========================================================================

    def _build_results(
        self,
        symbol: str,
        days: int,
        rr_ratio: float,
        trading_mode: str,
        trades: List[
            Dict[str, Any]
        ],
        candidate_count: int,
        ambiguous_count: int,
        censored_count: int,
        invalid_count: int,
        historical_spread_available: bool,
        point_available: bool,
        commission_r: float,
        slippage_r: float,
        verbose: bool,
    ) -> Dict[str, Any]:

        if not trades:

            results = {
                "symbol": symbol,
                "days": days,
                "rr_ratio": rr_ratio,
                "trading_mode": (
                    trading_mode
                ),

                "timestamp_utc": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),

                "candidate_count": (
                    candidate_count
                ),

                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakeven": 0,

                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy_r": 0.0,

                "avg_rr_achieved": 0.0,
                "avg_bars_held": 0.0,
                "max_drawdown_r": 0.0,

                "ambiguous_excluded": (
                    ambiguous_count
                ),

                "censored_excluded": (
                    censored_count
                ),

                "invalid_excluded": (
                    invalid_count
                ),

                "historical_spread_available": (
                    historical_spread_available
                    and point_available
                ),

                "commission_r_assumption": (
                    commission_r
                ),

                "slippage_r_assumption": (
                    slippage_r
                ),

                "message": (
                    "NO_RESOLVED_CAUSAL_TRADES"
                ),

                "trades_sample": [],
            }

            if verbose:
                self.last_results = (
                    results
                )

                self._save_results(
                    results
                )

            return results

        r_values = np.asarray(
            [
                self._finite(
                    trade[
                        "net_r"
                    ]
                )
                for trade
                in trades
            ],
            dtype=float,
        )

        wins_mask = (
            r_values > 0.0
        )

        losses_mask = (
            r_values < 0.0
        )

        flat_mask = np.isclose(
            r_values,
            0.0,
            atol=1e-12,
        )

        wins = int(
            np.sum(
                wins_mask
            )
        )

        losses = int(
            np.sum(
                losses_mask
            )
        )

        breakeven = int(
            np.sum(
                flat_mask
            )
        )

        resolved_directional = (
            wins
            + losses
        )

        if (
            resolved_directional
            > 0
        ):

            win_rate = (
                wins
                / resolved_directional
                * 100.0
            )

        else:
            win_rate = 0.0

        gross_profit = float(
            np.sum(
                r_values[
                    wins_mask
                ]
            )
        )

        gross_loss = abs(
            float(
                np.sum(
                    r_values[
                        losses_mask
                    ]
                )
            )
        )

        if gross_loss > 0.0:

            profit_factor: Optional[
                float
            ] = (
                gross_profit
                / gross_loss
            )

        elif gross_profit > 0.0:

            # No fake finite PF.
            profit_factor = None

        else:

            profit_factor = 0.0

        expectancy = float(
            np.mean(
                r_values
            )
        )

        equity_curve = np.concatenate(
            (
                np.asarray(
                    [
                        0.0
                    ]
                ),
                np.cumsum(
                    r_values
                ),
            )
        )

        running_peak = (
            np.maximum.accumulate(
                equity_curve
            )
        )

        drawdown = (
            running_peak
            - equity_curve
        )

        max_drawdown_r = float(
            np.max(
                drawdown
            )
        )

        avg_bars = float(
            np.mean(
                [
                    self._finite(
                        trade[
                            "bars_held"
                        ]
                    )
                    for trade
                    in trades
                ]
            )
        )

        avg_mfe = float(
            np.mean(
                [
                    self._finite(
                        trade[
                            "mfe_r"
                        ]
                    )
                    for trade
                    in trades
                ]
            )
        )

        avg_mae = float(
            np.mean(
                [
                    self._finite(
                        trade[
                            "mae_r"
                        ]
                    )
                    for trade
                    in trades
                ]
            )
        )

        results = {
            "symbol": symbol,
            "days": days,

            "rr_ratio": (
                rr_ratio
            ),

            "trading_mode": (
                trading_mode
            ),

            "timestamp_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "candidate_count": (
                candidate_count
            ),

            "total_trades": len(
                trades
            ),

            "wins": wins,
            "losses": losses,
            "breakeven": (
                breakeven
            ),

            "win_rate": round(
                win_rate,
                2,
            ),

            "profit_factor": (
                round(
                    profit_factor,
                    4,
                )
                if profit_factor
                is not None
                else None
            ),

            "gross_profit_r": round(
                gross_profit,
                5,
            ),

            "gross_loss_r": round(
                gross_loss,
                5,
            ),

            "expectancy_r": round(
                expectancy,
                5,
            ),

            # Legacy name retained.
            "avg_rr_achieved": round(
                expectancy,
                5,
            ),

            "avg_bars_held": round(
                avg_bars,
                2,
            ),

            "avg_mfe_r": round(
                avg_mfe,
                5,
            ),

            "avg_mae_r": round(
                avg_mae,
                5,
            ),

            "max_drawdown_r": round(
                max_drawdown_r,
                5,
            ),

            "ambiguous_excluded": (
                ambiguous_count
            ),

            "censored_excluded": (
                censored_count
            ),

            "invalid_excluded": (
                invalid_count
            ),

            "historical_spread_available": (
                historical_spread_available
                and point_available
            ),

            "commission_r_assumption": (
                commission_r
            ),

            "slippage_r_assumption": (
                slippage_r
            ),

            "trades_sample": (
                trades[
                    -10:
                ]
            ),
        }

        if verbose:

            self.last_results = (
                results
            )

            self._save_results(
                results
            )

            self.logger.info(
                (
                    "Causal backtest done | "
                    "%s %s | "
                    "candidates=%d "
                    "resolved=%d "
                    "WR=%.1f%% "
                    "Expectancy=%.3fR "
                    "PF=%s "
                    "DD=%.3fR "
                    "ambiguous=%d "
                    "censored=%d"
                ),
                symbol,
                trading_mode,
                candidate_count,
                len(
                    trades
                ),
                win_rate,
                expectancy,
                (
                    f"{profit_factor:.2f}"
                    if profit_factor
                    is not None
                    else "INF"
                ),
                max_drawdown_r,
                ambiguous_count,
                censored_count,
            )

        return results

    # =========================================================================
    # SHADOW OPTIMIZER
    # =========================================================================

    def self_optimize(
        self,
        symbol: str,
        trading_mode: str = "scalping",
    ) -> Dict[str, Any]:

        """
        Shadow-only optimizer.

        First 70%:
            development

        Final 30%:
            holdout validation

        Production settings are NEVER changed here.
        """

        from utils.smc_indicators import (
            SMCIndicators,
        )

        from utils.settings_manager import (
            settings_manager,
        )

        config = (
            self._mode_config(
                trading_mode
            )
        )

        days = 30

        df_htf = (
            self._fetch_data(
                symbol,
                days,
                config[
                    "htf"
                ],
            )
        )

        df_context = (
            self._fetch_data(
                symbol,
                days,
                config[
                    "context"
                ],
            )
        )

        df_ltf = (
            self._fetch_data(
                symbol,
                days,
                config[
                    "ltf"
                ],
            )
        )

        if (
            df_htf is None
            or df_context is None
            or df_ltf is None
            or len(
                df_ltf
            )
            < 500
        ):

            return {
                "symbol": symbol,

                "trading_mode": (
                    config[
                        "mode"
                    ]
                ),

                "applied": False,

                "promotion_status": (
                    "INSUFFICIENT_DATA"
                ),

                "error": (
                    "FAILED_TO_FETCH_OPTIMIZATION_DATA"
                ),
            }

        lower_tf = None

        if (
            config[
                "ltf_seconds"
            ]
            > 60
        ):

            lower_tf = (
                self._fetch_data(
                    symbol,
                    days,
                    mt5.TIMEFRAME_M1,
                )
            )

        split_idx = int(
            len(
                df_ltf
            )
            * 0.70
        )

        split_idx = max(
            200,
            min(
                split_idx,
                len(
                    df_ltf
                )
                - 100,
            ),
        )

        validation_start = (
            df_ltf.index[
                split_idx
            ]
        )

        development_start = (
            df_ltf.index[
                100
            ]
        )

        validation_end = (
            df_ltf.index[
                -1
            ]
            + pd.to_timedelta(
                config[
                    "ltf_seconds"
                ],
                unit="s",
            )
        )

        swing_options = [
            2,
            3,
        ]

        sweep_options = [
            15,
            20,
            30,
        ]

        mss_options = [
            8,
            10,
            15,
        ]

        rr_options = [
            1.5,
            2.0,
            2.5,
        ]

        smc_cache: Dict[
            int,
            Dict[
                str,
                pd.DataFrame,
            ],
        ] = {}

        for swing_window in (
            swing_options
        ):

            try:

                smc_cache[
                    swing_window
                ] = {
                    "htf": (
                        SMCIndicators.compute_smc_features(
                            df_htf,
                            window=(
                                swing_window
                            ),
                        )
                    ),

                    "context": (
                        SMCIndicators.compute_smc_features(
                            df_context,
                            window=(
                                swing_window
                            ),
                        )
                    ),

                    "ltf": (
                        SMCIndicators.compute_smc_features(
                            df_ltf,
                            window=(
                                swing_window
                            ),
                        )
                    ),
                }

            except Exception as exc:

                self.logger.error(
                    (
                        "SMC optimization cache "
                        "failed window=%s: %s"
                    ),
                    swing_window,
                    exc,
                )

        candidates: List[
            Dict[str, Any]
        ] = []

        for swing_window in (
            swing_options
        ):

            for sweep in (
                sweep_options
            ):

                for mss in (
                    mss_options
                ):

                    for rr in (
                        rr_options
                    ):

                        candidates.append(
                            {
                                "swing_window": (
                                    swing_window
                                ),

                                "lookback_sweep": (
                                    sweep
                                ),

                                "lookback_mss": (
                                    mss
                                ),

                                "lookback_fvg": 5,

                                "rr": rr,
                            }
                        )

        evaluated: List[
            Dict[str, Any]
        ] = []

        best: Optional[
            Dict[str, Any]
        ] = None

        best_score = float(
            "-inf"
        )

        for cfg in candidates:

            cache = (
                smc_cache.get(
                    cfg[
                        "swing_window"
                    ]
                )
            )

            if cache is None:
                continue

            try:

                development = (
                    self.run_backtest_simulation(
                        symbol=(
                            symbol
                        ),

                        htf_smc=(
                            cache[
                                "htf"
                            ]
                        ),

                        context_smc=(
                            cache[
                                "context"
                            ]
                        ),

                        ltf_smc=(
                            cache[
                                "ltf"
                            ]
                        ),

                        days=(
                            days
                        ),

                        rr_ratio=(
                            cfg[
                                "rr"
                            ]
                        ),

                        trading_mode=(
                            config[
                                "mode"
                            ]
                        ),

                        lookback_sweep=(
                            cfg[
                                "lookback_sweep"
                            ]
                        ),

                        lookback_mss=(
                            cfg[
                                "lookback_mss"
                            ]
                        ),

                        lookback_fvg=(
                            cfg[
                                "lookback_fvg"
                            ]
                        ),

                        verbose=False,

                        lower_tf_bars=(
                            lower_tf
                        ),

                        evaluation_start=(
                            development_start
                        ),

                        evaluation_end=(
                            validation_start
                        ),
                    )
                )

                validation = (
                    self.run_backtest_simulation(
                        symbol=(
                            symbol
                        ),

                        htf_smc=(
                            cache[
                                "htf"
                            ]
                        ),

                        context_smc=(
                            cache[
                                "context"
                            ]
                        ),

                        ltf_smc=(
                            cache[
                                "ltf"
                            ]
                        ),

                        days=(
                            days
                        ),

                        rr_ratio=(
                            cfg[
                                "rr"
                            ]
                        ),

                        trading_mode=(
                            config[
                                "mode"
                            ]
                        ),

                        lookback_sweep=(
                            cfg[
                                "lookback_sweep"
                            ]
                        ),

                        lookback_mss=(
                            cfg[
                                "lookback_mss"
                            ]
                        ),

                        lookback_fvg=(
                            cfg[
                                "lookback_fvg"
                            ]
                        ),

                        verbose=False,

                        lower_tf_bars=(
                            lower_tf
                        ),

                        evaluation_start=(
                            validation_start
                        ),

                        evaluation_end=(
                            validation_end
                        ),
                    )
                )

            except Exception as exc:

                self.logger.error(
                    (
                        "Optimization candidate "
                        "failed %s: %s"
                    ),
                    cfg,
                    exc,
                )

                continue

            dev_trades = int(
                development.get(
                    "total_trades",
                    0,
                )
            )

            val_trades = int(
                validation.get(
                    "total_trades",
                    0,
                )
            )

            dev_expectancy = (
                self._finite(
                    development.get(
                        "expectancy_r",
                        0.0,
                    )
                )
            )

            val_expectancy = (
                self._finite(
                    validation.get(
                        "expectancy_r",
                        0.0,
                    )
                )
            )

            val_dd = (
                self._finite(
                    validation.get(
                        "max_drawdown_r",
                        0.0,
                    )
                )
            )

            raw_pf = (
                validation.get(
                    "profit_factor",
                    0.0,
                )
            )

            if raw_pf is None:

                # Mathematically infinite PF.
                # Cap its contribution to fitness so tiny samples
                # cannot dominate.
                val_pf = 3.0

            else:

                val_pf = min(
                    3.0,
                    max(
                        0.0,
                        self._finite(
                            raw_pf
                        ),
                    ),
                )

            enough_samples = (
                dev_trades >= 8
                and val_trades >= 4
            )

            consistent_positive = (
                dev_expectancy > 0.0
                and val_expectancy > 0.0
            )

            sample_factor = min(
                1.0,
                val_trades
                / 20.0,
            )

            score = (
                (
                    val_expectancy
                    * 2.0
                )
                + (
                    val_pf
                    * 0.25
                )
                - (
                    val_dd
                    * 0.10
                )
            ) * sample_factor

            eligible = bool(
                enough_samples
                and consistent_positive
            )

            item = {
                "settings": (
                    cfg
                ),

                "development": {
                    "trades": (
                        dev_trades
                    ),

                    "expectancy_r": (
                        dev_expectancy
                    ),

                    "profit_factor": (
                        development.get(
                            "profit_factor"
                        )
                    ),

                    "max_drawdown_r": (
                        development.get(
                            "max_drawdown_r",
                            0.0,
                        )
                    ),
                },

                "validation": {
                    "trades": (
                        val_trades
                    ),

                    "expectancy_r": (
                        val_expectancy
                    ),

                    "profit_factor": (
                        validation.get(
                            "profit_factor"
                        )
                    ),

                    "max_drawdown_r": (
                        val_dd
                    ),
                },

                "eligible": (
                    eligible
                ),

                "score": round(
                    score,
                    6,
                ),
            }

            evaluated.append(
                item
            )

            if (
                eligible
                and score
                > best_score
            ):

                best_score = (
                    score
                )

                best = item

        previous_settings = {
            "swing_window": (
                settings_manager.get(
                    "smc_swing_window",
                    2,
                )
            ),

            "lookback_sweep": (
                settings_manager.get(
                    "smc_lookback_sweep",
                    20,
                )
            ),

            "lookback_mss": (
                settings_manager.get(
                    "smc_lookback_mss",
                    10,
                )
            ),

            "lookback_fvg": (
                settings_manager.get(
                    "smc_fvg_lookback",
                    5,
                )
            ),

            "min_rr_ratio": (
                settings_manager.get(
                    "min_rr_ratio",
                    2.0,
                )
            ),
        }

        optimization = {
            "symbol": (
                symbol
            ),

            "trading_mode": (
                config[
                    "mode"
                ]
            ),

            "timestamp_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "selection_method": (
                "70_30_CHRONOLOGICAL_HOLDOUT"
            ),

            "previous_settings": (
                previous_settings
            ),

            "best_settings": (
                best[
                    "settings"
                ]
                if best
                else None
            ),

            "best_score": (
                round(
                    best_score,
                    6,
                )
                if best
                else None
            ),

            "best_evidence": (
                {
                    "development": (
                        best[
                            "development"
                        ]
                    ),

                    "validation": (
                        best[
                            "validation"
                        ]
                    ),
                }
                if best
                else None
            ),

            "eligible_candidates": sum(
                1
                for item
                in evaluated
                if item[
                    "eligible"
                ]
            ),

            "evaluated_candidates": len(
                evaluated
            ),

            # NEVER automatically applied.
            "applied": False,

            "promotion_status": (
                "SHADOW_RECOMMENDATION_ONLY"
                if best
                else "NO_CANDIDATE_PASSED_HOLDOUT"
            ),
        }

        self._append_optimization_log(
            optimization
        )

        if best:

            self.logger.info(
                (
                    "Shadow optimizer "
                    "recommendation %s %s: %s | "
                    "validation expectancy=%.3fR "
                    "score=%.3f"
                ),
                symbol,
                config[
                    "mode"
                ],
                best[
                    "settings"
                ],
                best[
                    "validation"
                ][
                    "expectancy_r"
                ],
                best_score,
            )

        else:

            self.logger.warning(
                (
                    "Shadow optimizer: no "
                    "candidate passed causal holdout."
                )
            )

        return optimization

    # =========================================================================
    # STORAGE
    # =========================================================================

    def get_last_results(
        self,
    ) -> Dict[str, Any]:

        if self.last_results:

            return dict(
                self.last_results
            )

        return (
            self._load_results()
        )

    def _save_results(
        self,
        results: Dict[str, Any],
    ) -> None:

        try:

            os.makedirs(
                os.path.dirname(
                    self.results_path
                )
                or ".",
                exist_ok=True,
            )

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
                    results,
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
                    "Failed to save "
                    "backtest results: %s"
                ),
                exc,
            )

    def _load_results(
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
                    "Failed loading "
                    "backtest results: %s"
                ),
                exc,
            )

        return {}

    def _append_optimization_log(
        self,
        record: Dict[str, Any],
    ) -> None:

        try:

            existing: List[
                Dict[str, Any]
            ] = []

            if os.path.exists(
                self.optimization_path
            ):

                with open(
                    self.optimization_path,
                    "r",
                    encoding="utf-8",
                ) as handle:

                    loaded = (
                        json.load(
                            handle
                        )
                    )

                if isinstance(
                    loaded,
                    list,
                ):
                    existing = loaded

            existing.append(
                record
            )

            existing = (
                existing[
                    -200:
                ]
            )

            temp_path = (
                self.optimization_path
                + ".tmp"
            )

            with open(
                temp_path,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    existing,
                    handle,
                    indent=2,
                    default=str,
                )

            os.replace(
                temp_path,
                self.optimization_path,
            )

        except Exception as exc:

            self.logger.error(
                (
                    "Failed to save "
                    "optimization log: %s"
                ),
                exc,
            )