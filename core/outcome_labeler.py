from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CandidateOutcome:
    candidate_id: str
    outcome_type: str
    tp_before_sl: Optional[bool]

    net_r: Optional[float]
    mfe_r: float
    mae_r: float
    holding_bars: int

    spread_r: float
    commission_r: float
    slippage_r: float

    same_bar_ambiguous: bool
    data_source: str
    source_quality: float

    label_version: str


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


class OutcomeResolver:
    """
    Conservative historical outcome resolver.

    Rules:
    - Uses actual entry / SL / TP geometry.
    - Does not substitute configured RR for actual TP distance.
    - Same-bar TP + SL is ambiguous unless lower-TF data resolves order.
    - Transaction costs are explicit inputs.
    - No fabricated commission/slippage.
    - Untouched horizon = CENSORED unless caller explicitly defines a
      time-based exit using force_time_exit=True.
    """

    LABEL_VERSION = "v5.0-causal"

    @classmethod
    def resolve(
        cls,
        candidate_id: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        action: str,
        bars_future: List[Dict[str, Any]],
        lower_tf_bars: Optional[List[Dict[str, Any]]] = None,
        spread_points: float = 0.0,
        point: float = 0.0,
        commission_r: float = 0.0,
        slippage_r: float = 0.0,
        force_time_exit: bool = False,
    ) -> CandidateOutcome:

        entry = _finite(entry_price)
        stop = _finite(stop_price)
        target = _finite(target_price)

        action = str(
            action or ""
        ).upper().strip()

        risk = abs(
            entry - stop
        )

        valid = (
            action in ("BUY", "SELL")
            and entry > 0.0
            and stop > 0.0
            and target > 0.0
            and risk > 0.0
        )

        if valid:
            if action == "BUY":
                valid = (
                    stop
                    < entry
                    < target
                )
            else:
                valid = (
                    target
                    < entry
                    < stop
                )

        if not valid:
            return cls._invalid(
                candidate_id
            )

        point = max(
            0.0,
            _finite(
                point
            ),
        )

        spread_points = max(
            0.0,
            _finite(
                spread_points
            ),
        )

        if point > 0.0:
            spread_r = (
                spread_points
                * point
                / risk
            )
        else:
            spread_r = 0.0

        commission_r = max(
            0.0,
            _finite(
                commission_r
            ),
        )

        slippage_r = max(
            0.0,
            _finite(
                slippage_r
            ),
        )

        costs = (
            spread_r
            + commission_r
            + slippage_r
        )

        mfe_price = entry
        mae_price = entry

        holding_bars = 0

        hit: Optional[str] = None

        for idx, bar in enumerate(
            bars_future or []
        ):
            high = _finite(
                bar.get("high"),
                float("nan"),
            )

            low = _finite(
                bar.get("low"),
                float("nan"),
            )

            if (
                not math.isfinite(
                    high
                )
                or not math.isfinite(
                    low
                )
            ):
                continue

            holding_bars = (
                idx + 1
            )

            if action == "BUY":
                mfe_price = max(
                    mfe_price,
                    high,
                )

                mae_price = min(
                    mae_price,
                    low,
                )

                tp_hit = (
                    high >= target
                )

                sl_hit = (
                    low <= stop
                )

            else:
                mfe_price = min(
                    mfe_price,
                    low,
                )

                mae_price = max(
                    mae_price,
                    high,
                )

                tp_hit = (
                    low <= target
                )

                sl_hit = (
                    high >= stop
                )

            if (
                tp_hit
                and sl_hit
            ):
                hit = "AMBIGUOUS"
                break

            if tp_hit:
                hit = "TP"
                break

            if sl_hit:
                hit = "SL"
                break

        if action == "BUY":
            mfe_r = max(
                0.0,
                (
                    mfe_price
                    - entry
                )
                / risk,
            )

            mae_r = max(
                0.0,
                (
                    entry
                    - mae_price
                )
                / risk,
            )

        else:
            mfe_r = max(
                0.0,
                (
                    entry
                    - mfe_price
                )
                / risk,
            )

            mae_r = max(
                0.0,
                (
                    mae_price
                    - entry
                )
                / risk,
            )

        # ---------------------------------------------------------------------
        # SAME-BAR AMBIGUITY
        # ---------------------------------------------------------------------

        if hit == "AMBIGUOUS":

            lower = (
                cls._resolve_lower_timeframe(
                    action,
                    stop,
                    target,
                    lower_tf_bars,
                )
            )

            if lower == "TP":

                if action == "BUY":
                    gross_r = (
                        target
                        - entry
                    ) / risk

                else:
                    gross_r = (
                        entry
                        - target
                    ) / risk

                return cls._result(
                    candidate_id,
                    "TP_FIRST",
                    True,
                    gross_r - costs,
                    mfe_r,
                    mae_r,
                    holding_bars,
                    spread_r,
                    commission_r,
                    slippage_r,
                    False,
                    "LOWER_TF_RESOLVED",
                    0.95,
                )

            if lower == "SL":

                return cls._result(
                    candidate_id,
                    "SL_FIRST",
                    False,
                    -1.0 - costs,
                    mfe_r,
                    mae_r,
                    holding_bars,
                    spread_r,
                    commission_r,
                    slippage_r,
                    False,
                    "LOWER_TF_RESOLVED",
                    0.95,
                )

            return cls._result(
                candidate_id,
                "AMBIGUOUS_SAME_BAR",
                None,
                None,
                mfe_r,
                mae_r,
                holding_bars,
                spread_r,
                commission_r,
                slippage_r,
                True,
                (
                    "LOWER_TF_AMBIGUOUS"
                    if lower_tf_bars
                    else "PRIMARY_TF_ONLY"
                ),
                (
                    0.25
                    if lower_tf_bars
                    else 0.10
                ),
            )

        # ---------------------------------------------------------------------
        # TP
        # ---------------------------------------------------------------------

        if hit == "TP":

            if action == "BUY":
                gross_r = (
                    target
                    - entry
                ) / risk

            else:
                gross_r = (
                    entry
                    - target
                ) / risk

            return cls._result(
                candidate_id,
                "TP_FIRST",
                True,
                gross_r - costs,
                mfe_r,
                mae_r,
                holding_bars,
                spread_r,
                commission_r,
                slippage_r,
                False,
                "PRIMARY_TF",
                1.0,
            )

        # ---------------------------------------------------------------------
        # SL
        # ---------------------------------------------------------------------

        if hit == "SL":

            return cls._result(
                candidate_id,
                "SL_FIRST",
                False,
                -1.0 - costs,
                mfe_r,
                mae_r,
                holding_bars,
                spread_r,
                commission_r,
                slippage_r,
                False,
                "PRIMARY_TF",
                1.0,
            )

        # ---------------------------------------------------------------------
        # EXPLICIT TIME EXIT
        # ---------------------------------------------------------------------

        if (
            force_time_exit
            and bars_future
        ):

            last_close = _finite(
                bars_future[
                    min(
                        max(
                            holding_bars,
                            1,
                        ),
                        len(
                            bars_future
                        ),
                    )
                    - 1
                ].get(
                    "close"
                ),
                entry,
            )

            if action == "BUY":
                gross_r = (
                    last_close
                    - entry
                ) / risk

            else:
                gross_r = (
                    entry
                    - last_close
                ) / risk

            return cls._result(
                candidate_id,
                "TIME_EXIT",
                None,
                gross_r - costs,
                mfe_r,
                mae_r,
                holding_bars,
                spread_r,
                commission_r,
                slippage_r,
                False,
                "PRIMARY_TF",
                0.90,
            )

        # ---------------------------------------------------------------------
        # CENSORED
        # ---------------------------------------------------------------------

        return cls._result(
            candidate_id,
            "CENSORED",
            None,
            None,
            mfe_r,
            mae_r,
            holding_bars,
            spread_r,
            commission_r,
            slippage_r,
            False,
            "PRIMARY_TF",
            0.0,
        )

    @staticmethod
    def _resolve_lower_timeframe(
        action: str,
        stop: float,
        target: float,
        lower_tf_bars: Optional[
            List[
                Dict[
                    str,
                    Any,
                ]
            ]
        ],
    ) -> Optional[str]:

        if not lower_tf_bars:
            return None

        for bar in lower_tf_bars:

            high = _finite(
                bar.get(
                    "high"
                ),
                float("nan"),
            )

            low = _finite(
                bar.get(
                    "low"
                ),
                float("nan"),
            )

            if (
                not math.isfinite(
                    high
                )
                or not math.isfinite(
                    low
                )
            ):
                continue

            if action == "BUY":
                tp_hit = (
                    high >= target
                )

                sl_hit = (
                    low <= stop
                )

            else:
                tp_hit = (
                    low <= target
                )

                sl_hit = (
                    high >= stop
                )

            # If the first lower-TF candle touching the trade contains
            # both boundaries, sequence is still unknowable.
            if (
                tp_hit
                and sl_hit
            ):
                return None

            if tp_hit:
                return "TP"

            if sl_hit:
                return "SL"

        return None

    @classmethod
    def _result(
        cls,
        candidate_id: str,
        outcome_type: str,
        tp_before_sl: Optional[
            bool
        ],
        net_r: Optional[
            float
        ],
        mfe_r: float,
        mae_r: float,
        holding_bars: int,
        spread_r: float,
        commission_r: float,
        slippage_r: float,
        same_bar_ambiguous: bool,
        data_source: str,
        source_quality: float,
    ) -> CandidateOutcome:

        return CandidateOutcome(
            candidate_id=(
                candidate_id
            ),
            outcome_type=(
                outcome_type
            ),
            tp_before_sl=(
                tp_before_sl
            ),
            net_r=(
                net_r
            ),
            mfe_r=(
                mfe_r
            ),
            mae_r=(
                mae_r
            ),
            holding_bars=(
                holding_bars
            ),
            spread_r=(
                spread_r
            ),
            commission_r=(
                commission_r
            ),
            slippage_r=(
                slippage_r
            ),
            same_bar_ambiguous=(
                same_bar_ambiguous
            ),
            data_source=(
                data_source
            ),
            source_quality=(
                source_quality
            ),
            label_version=(
                cls.LABEL_VERSION
            ),
        )

    @classmethod
    def _invalid(
        cls,
        candidate_id: str,
    ) -> CandidateOutcome:

        return cls._result(
            candidate_id,
            "INVALID_GEOMETRY",
            None,
            None,
            0.0,
            0.0,
            0,
            0.0,
            0.0,
            0.0,
            False,
            "NONE",
            0.0,
        )