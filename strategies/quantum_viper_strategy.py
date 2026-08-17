from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from utils.settings_manager import settings_manager


logger = logging.getLogger("PulseViper.QuantumViperStrategy")


class QuantumViperStrategy:
    """
    Multi-timeframe candidate generator.

    Invariants:
      - Gold has no gate bypass.
      - Canonical SMC fields are active_bias and liq_sweep_type.
      - BUY OFI >= +0.15; SELL OFI <= -0.15.
      - Neutral OFI confirms neither direction.
      - Closed candles only.
      - This class creates a candidate only.

    Final authority remains:

        SafetyEngine
            ↓
        RiskEngine
            ↓
        ExecutionValidator
            ↓
        Execution
    """

    STRATEGY_ID = "QUANTUM"

    MODE_RR = {
        "scalping": 1.5,
        "intraday": 2.0,
        "swing": 3.0,
    }

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _finite(
        value: Any,
    ) -> Optional[float]:

        try:
            value = float(value)

            if math.isfinite(value):
                return value

        except (
            TypeError,
            ValueError,
        ):
            pass

        return None

    @staticmethod
    def _normalize_frame(
        frame: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:

        if (
            frame is None
            or len(frame) < 3
        ):
            return None

        required = {
            "open",
            "high",
            "low",
            "close",
        }

        if not required.issubset(
            frame.columns
        ):
            return None

        df = frame.copy()

        try:
            df.index = pd.to_datetime(
                df.index,
                utc=True,
            )

        except Exception:
            return None

        df = (
            df[
                ~df.index.duplicated(
                    keep="last"
                )
            ]
            .sort_index()
        )

        for col in required:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

        df = df.dropna(
            subset=list(
                required
            )
        )

        return (
            df
            if len(df) >= 3
            else None
        )

    @classmethod
    def _closed_frame(
        cls,
        frame: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:
        """
        Remove the currently-forming candle.

        Prevents strategy evaluation from using future information that was
        not available at the decision point.
        """

        df = cls._normalize_frame(
            frame
        )

        if df is None:
            return None

        deltas = np.diff(
            df.index.view(
                "int64"
            )
        )

        deltas = deltas[
            deltas > 0
        ]

        if len(deltas) == 0:
            return None

        bar_ns = int(
            np.median(
                deltas
            )
        )

        if bar_ns <= 0:
            return None

        now_ns = pd.Timestamp.now(
            tz="UTC"
        ).value

        available = (
            df.index.view(
                "int64"
            )
            + bar_ns
            <= now_ns
        )

        df = df.loc[
            available
        ]

        return (
            df
            if len(df) >= 3
            else None
        )

    @classmethod
    def _latest_bias(
        cls,
        frame: Optional[pd.DataFrame],
        fallback: int = 0,
    ) -> float:

        if (
            frame is None
            or len(frame) == 0
        ):
            return float(
                fallback
            )

        # Canonical first.
        # "bias" remains compatibility fallback only.
        for col in (
            "active_bias",
            "bias",
        ):

            if col not in frame.columns:
                continue

            value = cls._finite(
                frame[col].iloc[-1]
            )

            if value is not None:

                return float(
                    np.clip(
                        value,
                        -1.0,
                        1.0,
                    )
                )

        return float(
            fallback
        )

    @classmethod
    def _latest_sweep(
        cls,
        *frames: Optional[pd.DataFrame],
    ) -> int:
        """
        Canonical SMC semantics:

            +1 = bullish / low-side sweep
            -1 = bearish / high-side sweep
        """

        for frame in frames:

            if (
                frame is None
                or len(frame) == 0
            ):
                continue

            # Canonical first.
            for col in (
                "liq_sweep_type",
                "sweep_type",
            ):

                if col not in frame.columns:
                    continue

                values = (
                    frame[col]
                    .tail(10)
                    .to_numpy()
                )

                for raw in reversed(
                    values
                ):

                    value = cls._finite(
                        raw
                    )

                    if value is None:
                        continue

                    if value > 0:
                        return 1

                    if value < 0:
                        return -1

        return 0

    @staticmethod
    def _is_gold(
        symbol: str,
    ) -> bool:

        text = str(
            symbol
            or ""
        ).upper()

        return (
            "XAU"
            in text
            or "GOLD"
            in text
        )

    # =========================================================================
    # VOLUME / ORDER FLOW
    # =========================================================================

    @classmethod
    def _volume_ratio(
        cls,
        frame: pd.DataFrame,
    ) -> float:

        if "volume" in frame.columns:

            column = (
                "volume"
            )

        elif "tick_volume" in frame.columns:

            column = (
                "tick_volume"
            )

        else:

            return 1.0

        if len(frame) < 20:
            return 1.0

        volume = pd.to_numeric(
            frame[column].tail(20),
            errors="coerce",
        )

        current = cls._finite(
            volume.iloc[-1]
        )

        baseline = cls._finite(
            volume.iloc[:-1].mean()
        )

        if (
            current is None
            or baseline is None
            or baseline <= 0.0
        ):
            return 1.0

        return float(
            np.clip(
                current / baseline,
                0.0,
                5.0,
            )
        )

    @classmethod
    def _ofi(
        cls,
        last_bar: pd.Series,
        volume_ratio: float,
        volume_cache: Optional[
            Dict[str, Any]
        ],
    ) -> float:
        """
        Prefer real OrderFlowEngine result.

        Candle-body calculation is fallback only.
        """

        if isinstance(
            volume_cache,
            dict,
        ):

            external = cls._finite(
                volume_cache.get(
                    "ofi"
                )
            )

            if external is not None:

                return float(
                    np.clip(
                        external,
                        -1.0,
                        1.0,
                    )
                )

        candle_range = cls._finite(
            (
                last_bar["high"]
                - last_bar["low"]
            )
        )

        body = cls._finite(
            (
                last_bar["close"]
                - last_bar["open"]
            )
        )

        if (
            candle_range is None
            or body is None
            or candle_range <= 0.0
        ):
            return 0.0

        proxy = (
            (
                body
                / candle_range
            )
            * min(
                max(
                    volume_ratio,
                    0.0,
                ),
                2.0,
            )
        )

        return float(
            np.clip(
                proxy,
                -1.0,
                1.0,
            )
        )

    # =========================================================================
    # MODE
    # =========================================================================

    @classmethod
    def _decision_frame(
        cls,
        trading_mode: str,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:

        candidates = {
            "scalping": (
                df_m1,
                df_m5,
                df_m15,
            ),

            "intraday": (
                df_m5,
                df_m15,
                df_m1,
            ),

            "swing": (
                df_m15,
                df_m5,
                df_m1,
            ),
        }.get(
            trading_mode,
            (
                df_m5,
                df_m15,
                df_m1,
            ),
        )

        for candidate in candidates:

            closed = cls._closed_frame(
                candidate
            )

            if (
                closed is not None
                and len(closed) >= 20
            ):
                return closed

        return None

    # =========================================================================
    # STRATEGY
    # =========================================================================

    @classmethod
    def evaluate_quantum_viper(
        cls,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame],
        df_h1: Optional[pd.DataFrame],
        df_h4: Optional[pd.DataFrame],
        df_d1: Optional[pd.DataFrame],
        current_price: float,
        atr: float,
        htf_bias: int = 0,
        volume_cache: Optional[Dict] = None,
        sentiment_cache: Optional[Dict] = None,
        regime: str = "RANGE",
        symbol: str = "",
    ) -> Tuple[
        Optional[str],
        float,
        float,
        Dict[str, Any],
    ]:

        try:

            price = cls._finite(
                current_price
            )

            atr_value = cls._finite(
                atr
            )

            if (
                price is None
                or price <= 0.0
                or atr_value is None
                or atr_value <= 0.0
            ):

                return (
                    None,
                    0.0,
                    0.0,
                    {},
                )

            trading_mode = str(
                settings_manager.get(
                    "trading_mode",
                    "intraday",
                )
            ).lower()

            ltf = cls._decision_frame(
                trading_mode,
                df_m1,
                df_m5,
                df_m15,
            )

            if (
                ltf is None
                or len(ltf) < 20
            ):

                return (
                    None,
                    0.0,
                    0.0,
                    {},
                )

            m15 = cls._closed_frame(
                df_m15
            )

            h1 = cls._closed_frame(
                df_h1
            )

            h4 = cls._closed_frame(
                df_h4
            )

            d1 = cls._closed_frame(
                df_d1
            )

            last = ltf.iloc[-1]
            prev = ltf.iloc[-2]

            ref_atr = max(
                atr_value,
                1e-12,
            )

            # -----------------------------------------------------------------
            # 1. MULTI-TIMEFRAME CASCADE
            # -----------------------------------------------------------------

            d1_bias = cls._latest_bias(
                d1,
                htf_bias,
            )

            h4_bias = cls._latest_bias(
                h4,
                htf_bias,
            )

            h1_bias = cls._latest_bias(
                h1,
                htf_bias,
            )

            m15_bias = cls._latest_bias(
                m15,
                htf_bias,
            )

            fdc_score = float(
                np.clip(
                    (
                        0.35
                        * d1_bias
                        + 0.30
                        * h4_bias
                        + 0.20
                        * h1_bias
                        + 0.15
                        * m15_bias
                    ),
                    -1.0,
                    1.0,
                )
            )

            htf_direction = (
                1
                if fdc_score >= 0.15
                else (
                    -1
                    if fdc_score <= -0.15
                    else 0
                )
            )

            # -----------------------------------------------------------------
            # 2. LIQUIDITY SWEEP
            # -----------------------------------------------------------------

            sweep_type = cls._latest_sweep(
                ltf,
                m15,
                h1,
            )

            # -----------------------------------------------------------------
            # 3. PRICE ACTION
            # -----------------------------------------------------------------

            open_price = float(
                last["open"]
            )

            close_price = float(
                last["close"]
            )

            high_price = float(
                last["high"]
            )

            low_price = float(
                last["low"]
            )

            candle_body = abs(
                close_price
                - open_price
            )

            candle_range = max(
                high_price
                - low_price,
                1e-12,
            )

            is_bullish_bar = (
                close_price
                > open_price
            )

            is_bearish_bar = (
                close_price
                < open_price
            )

            is_displacement = (
                candle_body
                >= 1.5
                * ref_atr
            )

            # -----------------------------------------------------------------
            # 4. VOLUME + OFI
            # -----------------------------------------------------------------

            volume_ratio = (
                cls._volume_ratio(
                    ltf
                )
            )

            vse_factor = (
                volume_ratio
                * (
                    1.0
                    + min(
                        candle_body
                        / ref_atr,
                        2.5,
                    )
                )
            )

            volume_confirmed = (
                volume_ratio >= 1.25
                or vse_factor >= 2.0
            )

            ofi = cls._ofi(
                last,
                volume_ratio,
                volume_cache,
            )

            # -------------------------------------------------------------
            # EXACT OFI POLICY
            # -------------------------------------------------------------

            buy_order_flow = (
                ofi >= 0.15
            )

            sell_order_flow = (
                ofi <= -0.15
            )

            # OFI == 0 cannot confirm both directions.

            # -----------------------------------------------------------------
            # 5. SWING RANGE / CHOP
            # -----------------------------------------------------------------

            recent = ltf.tail(
                20
            )

            swing_high = float(
                recent[
                    "high"
                ].max()
            )

            swing_low = float(
                recent[
                    "low"
                ].min()
            )

            swing_range = max(
                swing_high
                - swing_low,
                1e-12,
            )

            if "atr" in ltf.columns:

                atr_sum = cls._finite(
                    pd.to_numeric(
                        ltf[
                            "atr"
                        ].tail(14),
                        errors="coerce",
                    ).sum()
                )

            else:

                atr_sum = None

            if (
                atr_sum is None
                or atr_sum <= 0.0
            ):

                atr_sum = (
                    14.0
                    * ref_atr
                )

            chop_index = float(
                np.clip(
                    (
                        100.0
                        * np.log10(
                            max(
                                atr_sum
                                / swing_range,
                                1e-12,
                            )
                        )
                        / np.log10(
                            14.0
                        )
                    ),
                    0.0,
                    100.0,
                )
            )

            is_gold = cls._is_gold(
                symbol
            )

            # Gold can be stricter — never exempt.
            chop_threshold = (
                58.0
                if is_gold
                else 62.0
            )

            is_choppy = (
                chop_index
                >= chop_threshold
            )

            wick_threshold = (
                0.58
                if (
                    is_gold
                    and is_choppy
                )
                else 0.50
            )

            engulf_vse_threshold = (
                2.2
                if (
                    is_gold
                    and is_choppy
                )
                else 1.8
            )

            lower_wick_ratio = (
                (
                    min(
                        open_price,
                        close_price,
                    )
                    - low_price
                )
                / candle_range
            )

            upper_wick_ratio = (
                (
                    high_price
                    - max(
                        open_price,
                        close_price,
                    )
                )
                / candle_range
            )

            bull_engulf = (
                is_bullish_bar
                and close_price
                > float(
                    prev["high"]
                )
                and vse_factor
                >= engulf_vse_threshold
            )

            bear_engulf = (
                is_bearish_bar
                and close_price
                < float(
                    prev["low"]
                )
                and vse_factor
                >= engulf_vse_threshold
            )

            bull_rejection = (
                lower_wick_ratio
                >= wick_threshold
                and price
                <= (
                    swing_low
                    + 0.30
                    * swing_range
                )
            )

            bear_rejection = (
                upper_wick_ratio
                >= wick_threshold
                and price
                >= (
                    swing_high
                    - 0.30
                    * swing_range
                )
            )

            # -----------------------------------------------------------------
            # 6. GOLDEN POCKET
            #
            # NO:
            #
            #     or is_gold
            # -----------------------------------------------------------------

            bull_lower = (
                swing_low
                + 0.214
                * swing_range
            )

            bull_upper = (
                swing_low
                + 0.382
                * swing_range
            )

            bear_lower = (
                swing_high
                - 0.382
                * swing_range
            )

            bear_upper = (
                swing_high
                - 0.214
                * swing_range
            )

            tolerance = (
                0.50
                * ref_atr
            )

            buy_golden_pocket = (
                (
                    bull_lower
                    - tolerance
                )
                <= price
                <= (
                    bull_upper
                    + tolerance
                )
            )

            sell_golden_pocket = (
                (
                    bear_lower
                    - tolerance
                )
                <= price
                <= (
                    bear_upper
                    + tolerance
                )
            )

            # -----------------------------------------------------------------
            # 7. HTF DIRECTION
            #
            # A directional sweep may support a mild reversal.
            #
            # Gold itself cannot bypass HTF.
            # -----------------------------------------------------------------

            buy_htf_valid = (
                fdc_score >= 0.15
                or (
                    sweep_type == 1
                    and fdc_score >= -0.10
                )
            )

            sell_htf_valid = (
                fdc_score <= -0.15
                or (
                    sweep_type == -1
                    and fdc_score <= 0.10
                )
            )

            # -----------------------------------------------------------------
            # 8. DIRECTIONAL CANDIDATES
            # -----------------------------------------------------------------

            buy_price_action = (
                (
                    bull_engulf
                    or bull_rejection
                    or (
                        is_displacement
                        and is_bullish_bar
                        and not is_choppy
                    )
                )
                and buy_order_flow
            )

            sell_price_action = (
                (
                    bear_engulf
                    or bear_rejection
                    or (
                        is_displacement
                        and is_bearish_bar
                        and not is_choppy
                    )
                )
                and sell_order_flow
            )

            buy_valid = (
                buy_htf_valid
                and buy_price_action
                and buy_golden_pocket
            )

            sell_valid = (
                sell_htf_valid
                and sell_price_action
                and sell_golden_pocket
            )

            # Neither or both => fail closed.
            if buy_valid == sell_valid:

                return (
                    None,
                    0.0,
                    0.0,
                    {},
                )

            # -----------------------------------------------------------------
            # 9. MODE-AWARE RR
            # -----------------------------------------------------------------

            configured_rr = cls._finite(
                settings_manager.get(
                    "min_rr_ratio",
                    1.5,
                )
            )

            if configured_rr is None:

                configured_rr = (
                    1.5
                )

            mode_rr = (
                cls.MODE_RR.get(
                    trading_mode,
                    2.0,
                )
            )

            rr_target = max(
                configured_rr,
                mode_rr,
            )

            atr_multiplier = (
                1.8
                if is_choppy
                else (
                    1.2
                    + 0.6
                    * (
                        chop_index
                        / 100.0
                    )
                )
            )

            # -----------------------------------------------------------------
            # 10. GEOMETRY
            # -----------------------------------------------------------------

            if buy_valid:

                action = (
                    "BUY"
                )

                structural_distance = max(
                    price
                    - swing_low,
                    0.0,
                )

                sl_distance = max(
                    (
                        atr_multiplier
                        * ref_atr
                    ),
                    structural_distance,
                )

                if sl_distance <= 0.0:

                    return (
                        None,
                        0.0,
                        0.0,
                        {},
                    )

                sl_price = (
                    price
                    - sl_distance
                )

                tp_price = (
                    price
                    + (
                        rr_target
                        * sl_distance
                    )
                )

                trigger = (
                    "BULLISH_BREAKOUT"
                    if bull_engulf
                    else (
                        "BULLISH_REJECTION"
                        if bull_rejection
                        else (
                            "BULLISH_DISPLACEMENT"
                        )
                    )
                )

            else:

                action = (
                    "SELL"
                )

                structural_distance = max(
                    swing_high
                    - price,
                    0.0,
                )

                sl_distance = max(
                    (
                        atr_multiplier
                        * ref_atr
                    ),
                    structural_distance,
                )

                if sl_distance <= 0.0:

                    return (
                        None,
                        0.0,
                        0.0,
                        {},
                    )

                sl_price = (
                    price
                    + sl_distance
                )

                tp_price = (
                    price
                    - (
                        rr_target
                        * sl_distance
                    )
                )

                trigger = (
                    "BEARISH_BREAKDOWN"
                    if bear_engulf
                    else (
                        "BEARISH_REJECTION"
                        if bear_rejection
                        else (
                            "BEARISH_DISPLACEMENT"
                        )
                    )
                )

            # -----------------------------------------------------------------
            # 11. GEOMETRY VALIDATION
            # -----------------------------------------------------------------

            if action == "BUY":

                if not (
                    sl_price
                    < price
                    < tp_price
                ):

                    return (
                        None,
                        0.0,
                        0.0,
                        {},
                    )

            else:

                if not (
                    tp_price
                    < price
                    < sl_price
                ):

                    return (
                        None,
                        0.0,
                        0.0,
                        {},
                    )

            # Candidate precision only.
            # ExecutionValidator owns real broker precision/stops validation.
            digits = (
                2
                if is_gold
                else 5
            )

            sl_price = round(
                sl_price,
                digits,
            )

            tp_price = round(
                tp_price,
                digits,
            )

            confluence_count = sum(
                [
                    (
                        buy_htf_valid
                        if action == "BUY"
                        else sell_htf_valid
                    ),

                    volume_confirmed,

                    (
                        buy_golden_pocket
                        if action == "BUY"
                        else sell_golden_pocket
                    ),

                    (
                        sweep_type
                        == (
                            1
                            if action == "BUY"
                            else -1
                        )
                    ),

                    (
                        bull_engulf
                        or bear_engulf
                    ),

                    (
                        bull_rejection
                        or bear_rejection
                    ),
                ]
            )

            metadata: Dict[
                str,
                Any,
            ] = {
                # Engine routing identity.
                "strategy": (
                    cls.STRATEGY_ID
                ),

                "strategy_family": (
                    "QUANTUM_VIPER"
                ),

                "trigger": (
                    trigger
                ),

                "symbol_is_gold": (
                    is_gold
                ),

                "trading_mode": (
                    trading_mode
                ),

                "regime": (
                    str(
                        regime
                    ).upper()
                ),

                "fdc_score": round(
                    fdc_score,
                    4,
                ),

                "htf_direction": (
                    htf_direction
                ),

                "sweep_type": (
                    sweep_type
                ),

                "ofi": round(
                    ofi,
                    4,
                ),

                "ofi_buy_threshold": (
                    0.15
                ),

                "ofi_sell_threshold": (
                    -0.15
                ),

                "volume_ratio": round(
                    volume_ratio,
                    4,
                ),

                "vse_factor": round(
                    vse_factor,
                    4,
                ),

                "volume_confirmed": bool(
                    volume_confirmed
                ),

                "chop_index": round(
                    chop_index,
                    2,
                ),

                "is_choppy": bool(
                    is_choppy
                ),

                "golden_pocket": (
                    True
                ),

                "rr_ratio": round(
                    rr_target,
                    4,
                ),

                "confluence_count": int(
                    confluence_count
                ),

                # Explicitly show this strategy does NOT authorize risk.
                "risk_authorized": (
                    False
                ),

                "execution_authorized": (
                    False
                ),
            }

            logger.info(
                (
                    "Quantum candidate | "
                    "symbol=%s action=%s "
                    "mode=%s fdc=%.3f "
                    "sweep=%d ofi=%.3f "
                    "rr=%.2f"
                ),
                symbol,
                action,
                trading_mode,
                fdc_score,
                sweep_type,
                ofi,
                rr_target,
            )

            return (
                action,
                sl_price,
                tp_price,
                metadata,
            )

        except Exception as exc:

            logger.exception(
                (
                    "QuantumViperStrategy "
                    "evaluation failed: %s"
                ),
                exc,
            )

            return (
                None,
                0.0,
                0.0,
                {},
            )