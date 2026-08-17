# core/trade_manager.py

from __future__ import annotations

import logging
import math
import os
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd

from utils.mt5_gateway import mt5_gateway as mt5
from utils.settings_manager import settings_manager


# =============================================================================
# IMMUTABLE DECISION SNAPSHOT HELPERS
# =============================================================================


def deep_freeze(value: Any) -> Any:
    """
    Recursively freeze mutable containers used inside a decision snapshot.
    """
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: deep_freeze(val)
                for key, val in deepcopy(value).items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(
            deep_freeze(item)
            for item in value
        )

    if isinstance(value, set):
        return frozenset(
            deep_freeze(item)
            for item in value
        )

    return value


@dataclass(frozen=True)
class TradeDecisionSnapshot:
    schema_version: int
    feature_schema_version: int
    model_version: str
    cycle_id: str
    decision_id: str
    symbol: str
    timestamp_utc: datetime

    strategy_name: str
    strategy_action: str

    decision_price: float
    planned_entry: float
    initial_sl: float
    initial_tp: float
    effective_rr: float

    brain_score: float
    brain_threshold: float
    brain_direction: Optional[str]

    model_probability: Optional[float]
    model_source: str

    regime: str
    regime_confidence: float
    session: str

    entry_features: Mapping[str, Any]
    strategy_metadata: Mapping[str, Any]


# =============================================================================
# REGIME STATE MACHINE
# =============================================================================


class RegimeStateMachine:
    """
    Require repeated confirmation before changing exit-management parameters.

    This state machine is ONLY used for trade-management behaviour.
    It does not create or approve entries.
    """

    REGIME_PARAMS = {
        "trending": {
            "trail_r": 0.65,
            "breakeven_r": 1.00,
        },
        "compression": {
            "trail_r": 0.45,
            "breakeven_r": 1.00,
        },
        "chaotic": {
            "trail_r": 0.35,
            "breakeven_r": 1.00,
        },
        "ranging": {
            "trail_r": 0.55,
            "breakeven_r": 1.00,
        },
        "range": {
            "trail_r": 0.55,
            "breakeven_r": 1.00,
        },
    }

    def __init__(
        self,
        confirm_ticks: int = 3,
        blend_ticks: int = 5,
    ):
        self.confirm_ticks = max(
            1,
            int(confirm_ticks),
        )

        self.blend_ticks = max(
            1,
            int(blend_ticks),
        )

        self.current_regime = "ranging"

        self.candidate_regime: Optional[str] = None
        self.candidate_count = 0

        self.transition_from = "ranging"
        self.transition_to: Optional[str] = None
        self.transition_progress = 0

    def update(
        self,
        classifier_output: str,
    ) -> None:
        value = str(
            classifier_output or "ranging"
        ).lower()

        if value == "range":
            value = "ranging"

        if value not in self.REGIME_PARAMS:
            value = "ranging"

        if self.transition_to is not None:
            if value == self.transition_to:
                self.transition_progress += 1

                if (
                    self.transition_progress
                    >= self.blend_ticks
                ):
                    self.current_regime = (
                        self.transition_to
                    )

                    self.transition_to = None
                    self.transition_progress = 0
                    self.candidate_regime = None
                    self.candidate_count = 0

                return

            self.transition_to = None
            self.transition_progress = 0
            self.candidate_regime = None
            self.candidate_count = 0

        if value == self.current_regime:
            self.candidate_regime = None
            self.candidate_count = 0
            return

        if value == self.candidate_regime:
            self.candidate_count += 1

        else:
            self.candidate_regime = value
            self.candidate_count = 1

        if (
            self.candidate_count
            >= self.confirm_ticks
        ):
            self.transition_from = (
                self.current_regime
            )

            self.transition_to = value
            self.transition_progress = 1

    def get_exit_params(
        self,
    ) -> dict:
        base = self.REGIME_PARAMS[
            self.current_regime
        ]

        if self.transition_to is None:
            return dict(base)

        target = self.REGIME_PARAMS[
            self.transition_to
        ]

        t = min(
            1.0,
            self.transition_progress
            / float(self.blend_ticks),
        )

        return {
            "trail_r": (
                base["trail_r"]
                + (
                    target["trail_r"]
                    - base["trail_r"]
                )
                * t
            ),
            "breakeven_r": (
                base["breakeven_r"]
                + (
                    target["breakeven_r"]
                    - base["breakeven_r"]
                )
                * t
            ),
        }


# =============================================================================
# POSITION STATE
# =============================================================================


class TradePosition:
    def __init__(
        self,
        ticket_id: int,
        symbol: str,
        action: str,
        entry_price: float,
        volume: float,
        sl: float,
        tp: float,
        timestamp: datetime,
        magic: int = 123456,
    ):
        self.id = int(ticket_id)
        self.symbol = str(symbol)
        self.action = str(action).upper()

        self.entry_price = float(
            entry_price
        )

        self.volume = float(
            volume
        )

        self.sl = float(
            sl or 0.0
        )

        self.tp = float(
            tp or 0.0
        )

        self.entry_time = (
            self._utc_datetime(
                timestamp
            )
        )

        self.magic = int(
            magic
        )

        # ---------------------------------------------------------------------
        # Lifecycle
        # ---------------------------------------------------------------------

        self.status = "OPEN"

        self.pnl = 0.0

        self.close_price = 0.0
        self.close_time: Optional[
            datetime
        ] = None

        self.close_reason = ""

        self.max_profit_points = 0.0

        # ---------------------------------------------------------------------
        # Immutable decision linkage
        # ---------------------------------------------------------------------

        self.decision_snapshot: Optional[
            TradeDecisionSnapshot
        ] = None

        self.decision_id: Optional[
            str
        ] = None

        self.execution_id: Optional[
            str
        ] = None

        self.cycle_id = "UNKNOWN"

        # ---------------------------------------------------------------------
        # ORIGINAL RISK GEOMETRY
        #
        # Never overwrite these when trailing / break-even changes current SL.
        # ---------------------------------------------------------------------

        self.initial_sl = self.sl
        self.initial_tp = self.tp

        self.initial_sl_dist = (
            abs(
                self.entry_price
                - self.initial_sl
            )
            if self.initial_sl != 0.0
            else 0.0
        )

        self.initial_risk_distance = (
            self.initial_sl_dist
        )

        self.entry_spread_points = 0.0

        # ---------------------------------------------------------------------
        # Compatibility metadata
        #
        # Live execution no longer creates TP1/TP2 child orders from a single
        # validation token.
        # ---------------------------------------------------------------------

        self.tp1 = self.tp
        self.tp2 = self.tp

        self.sibling_id: Optional[
            int
        ] = None

        self.is_tp1_target = False
        self.is_tp2_target = True

        self.moved_to_be = False
        self.has_booked_50pct = False

        self.volatility_regime = (
            "RANGING"
        )

        self.strategy_name = (
            "UNKNOWN"
        )

        self.entry_pattern = (
            "UNKNOWN"
        )

        self.risk_percent = 0.0

        # ---------------------------------------------------------------------
        # Legacy hedge metadata
        #
        # Retained only so old broker positions can be recovered/closed.
        # This manager DOES NOT open new emergency hedges.
        # ---------------------------------------------------------------------

        self.hedge_ticket: Optional[
            int
        ] = None

        self.is_hedge = False

        self.parent_position_id: Optional[
            int
        ] = None

        self.saved_sl = 0.0
        self.saved_tp = 0.0

    @staticmethod
    def _utc_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )


# =============================================================================
# BASE TRADE MANAGER
# =============================================================================


class BaseTradeManager:
    def __init__(
        self,
        config,
    ):
        self.config = config

        self.positions: Dict[
            int,
            TradePosition,
        ] = {}

        self.closed_positions: List[
            TradePosition
        ] = []

        self.logger = logging.getLogger(
            "PulseViper.TradeManager"
        )

        self.last_trade_date = (
            datetime.now(
                timezone.utc
            ).date()
        )

        self.daily_trade_count = (
            self._load_today_trade_count()
        )

        self.regime_state_machine = (
            RegimeStateMachine()
        )

        self._warned_live_hedge_disabled = (
            False
        )

    # =========================================================================
    # ACCOUNT HELPERS
    # =========================================================================

    def _load_today_trade_count(
        self,
    ) -> int:
        """
        Restore today's executed-entry count after restart.
        """
        db_path = (
            "data/pulse_viper.db"
        )

        if not os.path.exists(
            db_path
        ):
            return 0

        today = (
            datetime.now(
                timezone.utc
            )
            .date()
            .isoformat()
        )

        try:
            with sqlite3.connect(
                db_path
            ) as conn:
                cursor = (
                    conn.cursor()
                )

                cursor.execute(
                    (
                        "SELECT COUNT(*) "
                        "FROM audit_evaluations "
                        "WHERE executed=1 "
                        "AND DATE(datetime)=?"
                    ),
                    (today,),
                )

                row = (
                    cursor.fetchone()
                )

                return (
                    int(row[0])
                    if row
                    else 0
                )

        except Exception as exc:
            self.logger.debug(
                "Could not restore daily "
                "trade count: %s",
                exc,
            )

            return 0

    def get_win_streak(
        self,
    ) -> int:
        streak = 0

        for pos in reversed(
            self.closed_positions
        ):
            if pos.pnl > 0:
                streak += 1

            else:
                break

        return streak

    def get_capital(
        self,
    ) -> float:
        return float(
            getattr(
                self.config,
                "INITIAL_BALANCE",
                10000.0,
            )
        )

    def get_balance(
        self,
    ) -> float:
        return float(
            getattr(
                self.config,
                "INITIAL_BALANCE",
                10000.0,
            )
        )

    def _check_daily_trade_limit(
        self,
    ) -> bool:
        max_daily = int(
            settings_manager.get(
                "max_daily_trades",
                3,
            )
        )

        if max_daily >= 999:
            return True

        today = datetime.now(
            timezone.utc
        ).date()

        if (
            today
            != self.last_trade_date
        ):
            self.last_trade_date = (
                today
            )

            self.daily_trade_count = 0

        if (
            self.daily_trade_count
            >= max_daily
        ):
            self.logger.warning(
                (
                    "Daily trade limit reached "
                    "(%s trades/day). "
                    "Entry blocked."
                ),
                max_daily,
            )

            return False

        return True

    # =========================================================================
    # LOT SIZE / ACTUAL RISK
    # =========================================================================

    def calculate_lot_size(
        self,
        symbol: str,
        sl_price: float,
        entry_price: float,
        balance: Optional[
            float
        ] = None,
        risk_percent: Optional[
            float
        ] = None,
        brain_score: float = 0.0,
    ) -> float:
        """
        Calculate volume from the FINAL allowed risk percentage.

        Design rules:

        1. This function never increases the caller's risk percentage.
        2. Brain score cannot increase risk here.
        3. RiskEngine should decide allowed risk upstream.
        4. Manual-lot mode must still respect the same risk/heat budget.
        5. Broker minimum volume is NOT forced when it exceeds risk budget.
        """

        # Retained for backwards-compatible function signature.
        del brain_score

        try:
            info = mt5.symbol_info(
                symbol
            )

            if info is None:
                self.logger.error(
                    "No symbol info for %s",
                    symbol,
                )

                return 0.0

            entry_price = (
                self._finite_float(
                    entry_price
                )
            )

            sl_price = (
                self._finite_float(
                    sl_price
                )
            )

            if (
                entry_price <= 0.0
                or sl_price <= 0.0
                or entry_price == sl_price
            ):
                self.logger.warning(
                    (
                        "Invalid risk geometry "
                        "for sizing %s"
                    ),
                    symbol,
                )

                return 0.0

            requested_risk = (
                self._finite_float(
                    risk_percent,
                    self._finite_float(
                        settings_manager.get(
                            "risk_percent",
                            0.05,
                        ),
                        0.05,
                    ),
                )
            )

            configured_risk = (
                self._finite_float(
                    settings_manager.get(
                        "risk_percent",
                        requested_risk,
                    ),
                    requested_risk,
                )
            )

            allowed_trade_risk = max(
                0.0,
                min(
                    requested_risk,
                    configured_risk,
                ),
            )

            max_heat = (
                self._finite_float(
                    settings_manager.get(
                        "max_portfolio_heat",
                        5.0,
                    ),
                    5.0,
                )
            )

            open_heat = sum(
                max(
                    0.0,
                    self._finite_float(
                        p.risk_percent
                    ),
                )
                for p
                in self.positions.values()
            )

            remaining_heat = max(
                0.0,
                max_heat - open_heat,
            )

            allowed_trade_risk = min(
                allowed_trade_risk,
                remaining_heat,
            )

            if (
                allowed_trade_risk
                <= 0.0
            ):
                self.logger.warning(
                    (
                        "No remaining risk budget: "
                        "open_heat=%.4f%% "
                        "max_heat=%.4f%%"
                    ),
                    open_heat,
                    max_heat,
                )

                return 0.0

            capital = (
                self._finite_float(
                    balance
                )
            )

            if capital <= 0.0:
                capital = (
                    self._finite_float(
                        self.get_capital()
                    )
                )

            if capital <= 0.0:
                return 0.0

            volume_min = (
                self._finite_float(
                    getattr(
                        info,
                        "volume_min",
                        0.01,
                    ),
                    0.01,
                )
            )

            volume_max = (
                self._finite_float(
                    getattr(
                        info,
                        "volume_max",
                        100.0,
                    ),
                    100.0,
                )
            )

            volume_step = (
                self._finite_float(
                    getattr(
                        info,
                        "volume_step",
                        0.01,
                    ),
                    0.01,
                )
            )

            if volume_step <= 0.0:
                volume_step = 0.01

            inferred_action = (
                "BUY"
                if sl_price < entry_price
                else "SELL"
            )

            order_type = (
                self._order_type_for_direction(
                    inferred_action
                )
            )

            risk_per_lot = (
                self._loss_for_volume(
                    symbol=symbol,
                    order_type=order_type,
                    volume=1.0,
                    entry_price=entry_price,
                    stop_price=sl_price,
                )
            )

            if risk_per_lot <= 0.0:
                self.logger.error(
                    (
                        "Could not calculate "
                        "broker risk-per-lot "
                        "for %s"
                    ),
                    symbol,
                )

                return 0.0

            if bool(
                settings_manager.get(
                    "use_manual_lot",
                    False,
                )
            ):
                requested_volume = (
                    self._finite_float(
                        settings_manager.get(
                            "manual_lot_size",
                            volume_min,
                        ),
                        volume_min,
                    )
                )

                candidate = (
                    self._normalize_volume_down(
                        requested_volume,
                        volume_min,
                        volume_max,
                        volume_step,
                    )
                )

            else:
                risk_amount = (
                    capital
                    * (
                        allowed_trade_risk
                        / 100.0
                    )
                )

                raw_volume = (
                    risk_amount
                    / risk_per_lot
                )

                candidate = (
                    self._normalize_volume_down(
                        raw_volume,
                        volume_min,
                        volume_max,
                        volume_step,
                    )
                )

            if candidate <= 0.0:
                return 0.0

            actual_risk_pct = (
                self._loss_for_volume(
                    symbol=symbol,
                    order_type=order_type,
                    volume=candidate,
                    entry_price=entry_price,
                    stop_price=sl_price,
                )
                / capital
                * 100.0
            )

            tolerance = max(
                0.005,
                allowed_trade_risk
                * 0.02,
            )

            if (
                actual_risk_pct
                > allowed_trade_risk
                + tolerance
            ):
                self.logger.warning(
                    (
                        "Volume rejected: "
                        "%.4f lots risks %.4f%% "
                        "> allowed %.4f%% "
                        "on %s"
                    ),
                    candidate,
                    actual_risk_pct,
                    allowed_trade_risk,
                    symbol,
                )

                return 0.0

            margin = (
                mt5.order_calc_margin(
                    order_type,
                    symbol,
                    candidate,
                    entry_price,
                )
            )

            if margin is not None:
                margin = (
                    self._finite_float(
                        margin
                    )
                )

                if (
                    margin
                    > capital * 0.90
                ):
                    self.logger.warning(
                        (
                            "Volume rejected: "
                            "required margin %.2f "
                            "exceeds 90%% of "
                            "capital %.2f"
                        ),
                        margin,
                        capital,
                    )

                    return 0.0

            return candidate

        except Exception as exc:
            self.logger.exception(
                (
                    "Lot-size calculation "
                    "failed: %s"
                ),
                exc,
            )

            return 0.0

    def estimate_risk_percent(
        self,
        symbol: str,
        action: str,
        volume: float,
        entry_price: float,
        sl_price: float,
        capital: Optional[
            float
        ] = None,
    ) -> float:
        capital_value = (
            self._finite_float(
                capital
            )
        )

        if capital_value <= 0.0:
            capital_value = (
                self._finite_float(
                    self.get_capital()
                )
            )

        if (
            capital_value <= 0.0
            or sl_price <= 0.0
        ):
            return 0.0

        loss = (
            self._loss_for_volume(
                symbol=symbol,
                order_type=(
                    self._order_type_for_direction(
                        action
                    )
                ),
                volume=volume,
                entry_price=entry_price,
                stop_price=sl_price,
            )
        )

        if loss <= 0.0:
            return 0.0

        return (
            loss
            / capital_value
            * 100.0
        )

    def _loss_for_volume(
        self,
        symbol: str,
        order_type: int,
        volume: float,
        entry_price: float,
        stop_price: float,
    ) -> float:
        try:
            pnl = (
                mt5.order_calc_profit(
                    order_type,
                    symbol,
                    float(volume),
                    float(entry_price),
                    float(stop_price),
                )
            )

            if pnl is not None:
                return abs(
                    float(pnl)
                )

        except Exception:
            pass

        info = mt5.symbol_info(
            symbol
        )

        if info is None:
            return 0.0

        tick_value = (
            self._finite_float(
                getattr(
                    info,
                    "trade_tick_value",
                    0.0,
                )
            )
        )

        tick_size = (
            self._finite_float(
                getattr(
                    info,
                    "trade_tick_size",
                    0.0,
                )
            )
        )

        if (
            tick_value <= 0.0
            or tick_size <= 0.0
        ):
            return 0.0

        ticks = (
            abs(
                entry_price
                - stop_price
            )
            / tick_size
        )

        return (
            ticks
            * tick_value
            * float(volume)
        )

    @staticmethod
    def _normalize_volume_down(
        volume: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
    ) -> float:
        if (
            volume <= 0.0
            or volume_step <= 0.0
            or volume_max <= 0.0
        ):
            return 0.0

        volume = min(
            volume,
            volume_max,
        )

        steps = math.floor(
            (
                volume
                + 1e-12
            )
            / volume_step
        )

        normalized = (
            steps
            * volume_step
        )

        if (
            normalized
            + 1e-12
            < volume_min
        ):
            normalized = volume_min

        if (
            normalized
            > volume_max
            + 1e-12
        ):
            return 0.0

        step_text = str(
            volume_step
        )

        decimals = (
            len(
                step_text.split(
                    "."
                )[-1]
            )
            if "." in step_text
            else 0
        )

        decimals = max(
            0,
            min(
                8,
                decimals,
            ),
        )

        return round(
            normalized,
            decimals,
        )

    @staticmethod
    def _finite_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            number = float(
                value
            )

            if math.isfinite(
                number
            ):
                return number

            return default

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _order_type_for_direction(
        action: str,
    ) -> int:
        if (
            str(action).upper()
            == "BUY"
        ):
            return mt5.ORDER_TYPE_BUY

        return mt5.ORDER_TYPE_SELL

    # =========================================================================
    # SESSION / MARKET HELPERS
    # =========================================================================

    def is_velocity_stable(
        self,
        symbol: str,
    ) -> bool:
        now_utc = datetime.now(
            timezone.utc
        ).time()

        symbol_upper = str(
            symbol
        ).upper()

        # Rollover lock.
        if (
            "BTC"
            not in symbol_upper
            and time(21, 55)
            <= now_utc
            <= time(22, 15)
        ):
            return False

        if (
            "XAU"
            in symbol_upper
            or "GOLD"
            in symbol_upper
        ):
            return (
                time(7, 0)
                <= now_utc
                <= time(18, 0)
            )

        if any(
            pair in symbol_upper
            for pair in (
                "EURUSD",
                "GBPUSD",
                "USDJPY",
                "USDCHF",
            )
        ):
            # Correct overnight logic.
            if (
                now_utc
                >= time(19, 0)
                or now_utc
                <= time(6, 0)
            ):
                return False

        return True

    def find_touched_h1_ob(
        self,
        price: float,
        df_h1: Optional[
            pd.DataFrame
        ],
        atr: float,
    ) -> Tuple[
        bool,
        Optional[float],
        Optional[float],
    ]:
        if (
            df_h1 is None
            or len(df_h1) < 3
        ):
            return (
                False,
                None,
                None,
            )

        # Closed bars only.
        closed = (
            df_h1
            .iloc[:-1]
            .tail(50)
        )

        envelope = max(
            0.0,
            0.15
            * self._finite_float(
                atr
            ),
        )

        if (
            "ob_top"
            in closed.columns
            and "ob_bottom"
            in closed.columns
        ):
            valid = (
                closed[
                    [
                        "ob_top",
                        "ob_bottom",
                    ]
                ]
                .dropna()
            )

            for _, row in (
                valid.iterrows()
            ):
                top = float(
                    row["ob_top"]
                )

                bottom = float(
                    row["ob_bottom"]
                )

                lower = min(
                    bottom,
                    top,
                )

                upper = max(
                    bottom,
                    top,
                )

                if (
                    lower
                    - envelope
                    <= price
                    <= upper
                    + envelope
                ):
                    return (
                        True,
                        upper,
                        lower,
                    )

        if (
            "support"
            in closed.columns
        ):
            for value in (
                closed[
                    "support"
                ]
                .dropna()
                .values
            ):
                level = float(
                    value
                )

                if (
                    abs(
                        price
                        - level
                    )
                    <= envelope
                ):
                    return (
                        True,
                        level,
                        level,
                    )

        if (
            "resistance"
            in closed.columns
        ):
            for value in (
                closed[
                    "resistance"
                ]
                .dropna()
                .values
            ):
                level = float(
                    value
                )

                if (
                    abs(
                        price
                        - level
                    )
                    <= envelope
                ):
                    return (
                        True,
                        level,
                        level,
                    )

        return (
            False,
            None,
            None,
        )

    # =========================================================================
    # POSITION METADATA
    # =========================================================================

    def _attach_decision_metadata(
        self,
        pos: TradePosition,
        decision_snapshot: Optional[
            TradeDecisionSnapshot
        ],
        execution_id: Optional[
            str
        ],
    ) -> None:
        pos.execution_id = (
            execution_id
        )

        if (
            decision_snapshot
            is None
        ):
            return

        pos.decision_snapshot = (
            decision_snapshot
        )

        pos.decision_id = (
            decision_snapshot
            .decision_id
        )

        pos.volatility_regime = (
            decision_snapshot
            .regime
        )

        pos.strategy_name = (
            decision_snapshot
            .strategy_name
        )

        pos.cycle_id = getattr(
            decision_snapshot,
            "cycle_id",
            "UNKNOWN",
        )

    def _entry_spread_points(
        self,
        symbol: str,
    ) -> float:
        try:
            info = mt5.symbol_info(
                symbol
            )

            tick = (
                mt5.symbol_info_tick(
                    symbol
                )
            )

            if (
                info is None
                or tick is None
            ):
                return 0.0

            point = (
                self._finite_float(
                    getattr(
                        info,
                        "point",
                        0.0,
                    )
                )
            )

            bid = (
                self._finite_float(
                    getattr(
                        tick,
                        "bid",
                        0.0,
                    )
                )
            )

            ask = (
                self._finite_float(
                    getattr(
                        tick,
                        "ask",
                        0.0,
                    )
                )
            )

            if (
                point <= 0.0
                or ask < bid
            ):
                return 0.0

            return (
                ask - bid
            ) / point

        except Exception:
            return 0.0


# =============================================================================
# PAPER TRADE MANAGER
# =============================================================================


class PaperTradeManager(
    BaseTradeManager
):
    def __init__(
        self,
        config,
    ):
        super().__init__(
            config
        )

        self.virtual_balance = float(
            getattr(
                config,
                "INITIAL_BALANCE",
                10000.0,
            )
        )

        self.virtual_equity = (
            self.virtual_balance
        )

        self.simulated_ticket = (
            100000
        )

        self.magic_number = (
            999999
        )

    def get_capital(
        self,
    ) -> float:
        return self.virtual_equity

    def get_balance(
        self,
    ) -> float:
        return self.virtual_balance

    def open_position(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        sl_price: float,
        tp1_price: Optional[
            float
        ] = None,
        tp2_price: Optional[
            float
        ] = None,
        tp_price: Optional[
            float
        ] = None,
        risk_percent: Optional[
            float
        ] = None,
        brain_score: float = 0.0,
        decision_snapshot: Optional[
            TradeDecisionSnapshot
        ] = None,
        execution_id: Optional[
            str
        ] = None,
        validated_request: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Optional[
        TradePosition
    ]:
        # Paper mode does not need
        # an execution token.
        del validated_request

        action = str(
            action
        ).upper()

        if (
            action
            not in {
                "BUY",
                "SELL",
            }
        ):
            return None

        if not self._check_daily_trade_limit():
            return None

        final_tp = tp_price

        if final_tp is None:
            final_tp = (
                tp2_price
                if tp2_price
                is not None
                else tp1_price
            )

        if final_tp is None:
            final_tp = 0.0

        volume = (
            self.calculate_lot_size(
                symbol=symbol,
                sl_price=sl_price,
                entry_price=entry_price,
                risk_percent=risk_percent,
                brain_score=brain_score,
            )
        )

        if volume <= 0.0:
            self.logger.warning(
                (
                    "Paper entry blocked "
                    "because calculated "
                    "volume is zero."
                )
            )

            return None

        self.simulated_ticket += 1

        pos = TradePosition(
            ticket_id=(
                self.simulated_ticket
            ),
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            volume=volume,
            sl=sl_price,
            tp=float(
                final_tp
            ),
            timestamp=datetime.now(
                timezone.utc
            ),
            magic=self.magic_number,
        )

        pos.tp1 = (
            float(tp1_price)
            if tp1_price
            is not None
            else pos.tp
        )

        pos.tp2 = (
            float(tp2_price)
            if tp2_price
            is not None
            else pos.tp
        )

        pos.entry_spread_points = (
            self._entry_spread_points(
                symbol
            )
        )

        pos.risk_percent = (
            self.estimate_risk_percent(
                symbol=symbol,
                action=action,
                volume=volume,
                entry_price=entry_price,
                sl_price=sl_price,
                capital=(
                    self.virtual_equity
                ),
            )
        )

        self._attach_decision_metadata(
            pos,
            decision_snapshot,
            execution_id,
        )

        self.positions[
            pos.id
        ] = pos

        self.daily_trade_count += 1

        self.logger.info(
            (
                "Opened paper %s #%s "
                "%s @ %.5f | "
                "vol=%.4f SL=%.5f "
                "TP=%.5f risk=%.4f%%"
            ),
            action,
            pos.id,
            symbol,
            entry_price,
            volume,
            sl_price,
            pos.tp,
            pos.risk_percent,
        )

        return pos

    def update_positions(
        self,
        symbol: str,
        bid: float,
        ask: float,
        current_regime: str = (
            "RANGING"
        ),
        df_m1: Optional[
            pd.DataFrame
        ] = None,
        atr: Optional[
            float
        ] = None,
        news_locked: bool = False,
        df_h1: Optional[
            pd.DataFrame
        ] = None,
    ) -> None:
        # These no longer create
        # emergency hedge positions.
        del news_locked
        del df_h1

        info = mt5.symbol_info(
            symbol
        )

        if info is None:
            return

        point = (
            self._finite_float(
                getattr(
                    info,
                    "point",
                    0.0,
                )
            )
        )

        if point <= 0.0:
            return

        atr_value = (
            self._resolve_atr(
                df_m1,
                atr,
                point,
            )
        )

        self.regime_state_machine.update(
            current_regime
        )

        exit_params = (
            self.regime_state_machine
            .get_exit_params()
        )

        break_even_enabled = bool(
            settings_manager.get(
                "break_even_enabled",
                True,
            )
        )

        trailing_enabled = bool(
            settings_manager.get(
                "trailing_stop_enabled",
                True,
            )
        )

        to_close: List[
            Tuple[
                int,
                float,
                str,
            ]
        ] = []

        for pos in list(
            self.positions.values()
        ):
            if pos.symbol != symbol:
                continue

            current_price = (
                bid
                if pos.action
                == "BUY"
                else ask
            )

            pos.pnl = (
                self._paper_pnl(
                    pos,
                    current_price,
                )
            )

            pnl_points = (
                (
                    current_price
                    - pos.entry_price
                )
                / point
                if pos.action
                == "BUY"
                else (
                    pos.entry_price
                    - current_price
                )
                / point
            )

            pos.max_profit_points = max(
                pos.max_profit_points,
                pnl_points,
            )

            initial_risk = (
                pos.initial_sl_dist
            )

            if initial_risk > 0.0:
                be_pips = (
                    self._finite_float(
                        settings_manager.get(
                            "break_even_pips",
                            8.0,
                        ),
                        8.0,
                    )
                )

                be_trigger = max(
                    (
                        initial_risk
                        * exit_params[
                            "breakeven_r"
                        ]
                    ),
                    be_pips * point,
                )

                floating_distance = (
                    bid
                    - pos.entry_price
                    if pos.action
                    == "BUY"
                    else (
                        pos.entry_price
                        - ask
                    )
                )

                # -------------------------------------------------------------
                # BREAK EVEN
                # -------------------------------------------------------------

                if (
                    break_even_enabled
                    and not pos.moved_to_be
                    and floating_distance
                    >= be_trigger
                ):
                    buffer = max(
                        ask - bid,
                        point,
                    )

                    target = (
                        pos.entry_price
                        + buffer
                        if pos.action
                        == "BUY"
                        else (
                            pos.entry_price
                            - buffer
                        )
                    )

                    target = round(
                        target,
                        int(
                            getattr(
                                info,
                                "digits",
                                5,
                            )
                        ),
                    )

                    if self._sl_improves(
                        pos,
                        target,
                    ):
                        pos.sl = target
                        pos.moved_to_be = (
                            True
                        )

                        self.logger.info(
                            (
                                "Paper position #%s "
                                "moved to BE %.5f"
                            ),
                            pos.id,
                            pos.sl,
                        )

                # -------------------------------------------------------------
                # TRAILING
                #
                # Only activate after >= 1R.
                # -------------------------------------------------------------

                if (
                    trailing_enabled
                    and floating_distance
                    >= initial_risk
                ):
                    trail_pips = (
                        self._finite_float(
                            settings_manager.get(
                                "trailing_stop_pips",
                                10.0,
                            ),
                            10.0,
                        )
                    )

                    trail_distance = max(
                        (
                            atr_value
                            * max(
                                1.0,
                                exit_params[
                                    "trail_r"
                                ]
                                * 2.0,
                            )
                        ),
                        trail_pips
                        * point,
                    )

                    target = (
                        bid
                        - trail_distance
                        if pos.action
                        == "BUY"
                        else (
                            ask
                            + trail_distance
                        )
                    )

                    target = (
                        self._clamp_sl_to_market(
                            pos,
                            target,
                            bid,
                            ask,
                            info,
                        )
                    )

                    if (
                        target is not None
                        and self._sl_improves(
                            pos,
                            target,
                        )
                    ):
                        pos.sl = target

            # -----------------------------------------------------------------
            # PAPER SL / TP HIT
            # -----------------------------------------------------------------

            if pos.action == "BUY":
                if (
                    pos.sl
                    and bid
                    <= pos.sl
                ):
                    to_close.append(
                        (
                            pos.id,
                            pos.sl,
                            "SL",
                        )
                    )

                elif (
                    pos.tp
                    and bid
                    >= pos.tp
                ):
                    to_close.append(
                        (
                            pos.id,
                            pos.tp,
                            "TP",
                        )
                    )

            else:
                if (
                    pos.sl
                    and ask
                    >= pos.sl
                ):
                    to_close.append(
                        (
                            pos.id,
                            pos.sl,
                            "SL",
                        )
                    )

                elif (
                    pos.tp
                    and ask
                    <= pos.tp
                ):
                    to_close.append(
                        (
                            pos.id,
                            pos.tp,
                            "TP",
                        )
                    )

        for (
            pos_id,
            price,
            reason,
        ) in to_close:
            self.close_position(
                pos_id,
                price,
                reason,
            )

        # Recalculate floating equity
        # only from positions still open.
        remaining_floating = 0.0

        for pos in (
            self.positions.values()
        ):
            if pos.symbol != symbol:
                continue

            current_price = (
                bid
                if pos.action
                == "BUY"
                else ask
            )

            remaining_floating += (
                self._paper_pnl(
                    pos,
                    current_price,
                )
            )

        self.virtual_equity = (
            self.virtual_balance
            + remaining_floating
        )

    def close_position(
        self,
        pos_id: int,
        close_price: float,
        reason: str,
    ) -> Optional[
        TradePosition
    ]:
        pos = self.positions.pop(
            int(pos_id),
            None,
        )

        if pos is None:
            return None

        pos.pnl = (
            self._paper_pnl(
                pos,
                float(close_price),
            )
        )

        pos.close_price = float(
            close_price
        )

        pos.close_time = datetime.now(
            timezone.utc
        )

        pos.close_reason = str(
            reason
        )

        pos.status = "CLOSED"

        self.virtual_balance += (
            pos.pnl
        )

        self.virtual_equity = (
            self.virtual_balance
        )

        self.closed_positions.append(
            pos
        )

        self.logger.info(
            (
                "Closed paper position "
                "#%s (%s) @ %.5f | "
                "PnL %.2f"
            ),
            pos.id,
            reason,
            close_price,
            pos.pnl,
        )

        return pos

    def _paper_pnl(
        self,
        pos: TradePosition,
        close_price: float,
    ) -> float:
        try:
            order_type = (
                self._order_type_for_direction(
                    pos.action
                )
            )

            pnl = (
                mt5.order_calc_profit(
                    order_type,
                    pos.symbol,
                    pos.volume,
                    pos.entry_price,
                    close_price,
                )
            )

            if pnl is not None:
                return float(
                    pnl
                )

        except Exception:
            pass

        info = mt5.symbol_info(
            pos.symbol
        )

        if info is None:
            return 0.0

        tick_value = (
            self._finite_float(
                getattr(
                    info,
                    "trade_tick_value",
                    0.0,
                )
            )
        )

        tick_size = (
            self._finite_float(
                getattr(
                    info,
                    "trade_tick_size",
                    0.0,
                )
            )
        )

        if (
            tick_value <= 0.0
            or tick_size <= 0.0
        ):
            return 0.0

        distance = (
            close_price
            - pos.entry_price
            if pos.action == "BUY"
            else (
                pos.entry_price
                - close_price
            )
        )

        return (
            distance
            / tick_size
            * tick_value
            * pos.volume
        )

    def _resolve_atr(
        self,
        df_m1: Optional[
            pd.DataFrame
        ],
        atr: Optional[
            float
        ],
        point: float,
    ) -> float:
        value = (
            self._finite_float(
                atr
            )
        )

        if (
            value <= 0.0
            and df_m1 is not None
            and not df_m1.empty
            and "atr"
            in df_m1.columns
        ):
            value = (
                self._finite_float(
                    df_m1[
                        "atr"
                    ].iloc[-1]
                )
            )

        if value > 0.0:
            return value

        return 15.0 * point

    @staticmethod
    def _sl_improves(
        pos: TradePosition,
        target: float,
    ) -> bool:
        if target <= 0.0:
            return False

        if pos.action == "BUY":
            return (
                pos.sl == 0.0
                or target
                > pos.sl
            )

        return (
            pos.sl == 0.0
            or target
            < pos.sl
        )

    def _clamp_sl_to_market(
        self,
        pos: TradePosition,
        target: float,
        bid: float,
        ask: float,
        info: Any,
    ) -> Optional[
        float
    ]:
        point = (
            self._finite_float(
                getattr(
                    info,
                    "point",
                    0.0,
                )
            )
        )

        digits = int(
            getattr(
                info,
                "digits",
                5,
            )
        )

        stops_level = (
            self._finite_float(
                getattr(
                    info,
                    "trade_stops_level",
                    0.0,
                )
            )
        )

        minimum = max(
            point,
            stops_level
            * point,
        )

        if pos.action == "BUY":
            target = min(
                target,
                bid - minimum,
            )

        else:
            target = max(
                target,
                ask + minimum,
            )

        if target <= 0.0:
            return None

        return round(
            target,
            digits,
        )


# =============================================================================
# LIVE TRADE MANAGER
# =============================================================================


class LiveTradeManager(
    BaseTradeManager
):
    def __init__(
        self,
        config,
    ):
        super().__init__(
            config
        )

        self.magic_number = (
            123456
        )

    # =========================================================================
    # LIVE ACCOUNT INFORMATION
    # =========================================================================

    def get_win_streak(
        self,
    ) -> int:
        try:
            from datetime import timedelta

            start = (
                datetime.now(
                    timezone.utc
                )
                - timedelta(
                    days=7
                )
            )

            end = datetime.now(
                timezone.utc
            )

            deals = (
                mt5.history_deals_get(
                    start,
                    end,
                )
            )

            if deals:
                exits = [
                    deal
                    for deal in deals
                    if (
                        getattr(
                            deal,
                            "magic",
                            None,
                        )
                        == self.magic_number
                        and getattr(
                            deal,
                            "entry",
                            None,
                        )
                        in (
                            mt5.DEAL_ENTRY_OUT,
                            mt5.DEAL_ENTRY_INOUT,
                        )
                    )
                ]

                exits.sort(
                    key=lambda deal: getattr(
                        deal,
                        "time_msc",
                        getattr(
                            deal,
                            "time",
                            0,
                        ),
                    )
                )

                streak = 0

                for deal in reversed(
                    exits
                ):
                    realized = (
                        self._finite_float(
                            getattr(
                                deal,
                                "profit",
                                0.0,
                            )
                        )
                        + self._finite_float(
                            getattr(
                                deal,
                                "commission",
                                0.0,
                            )
                        )
                        + self._finite_float(
                            getattr(
                                deal,
                                "swap",
                                0.0,
                            )
                        )
                    )

                    if realized > 0:
                        streak += 1

                    else:
                        break

                return streak

        except Exception as exc:
            self.logger.debug(
                (
                    "Win-streak history "
                    "unavailable: %s"
                ),
                exc,
            )

        return (
            super().get_win_streak()
        )

    def get_capital(
        self,
    ) -> float:
        account = mt5.account_info()

        if account is not None:
            equity = (
                self._finite_float(
                    getattr(
                        account,
                        "equity",
                        0.0,
                    )
                )
            )

            if equity > 0.0:
                return equity

        return (
            super().get_capital()
        )

    def get_balance(
        self,
    ) -> float:
        account = mt5.account_info()

        if account is not None:
            balance = (
                self._finite_float(
                    getattr(
                        account,
                        "balance",
                        0.0,
                    )
                )
            )

            if balance > 0.0:
                return balance

        return (
            super().get_balance()
        )

    # =========================================================================
    # NEW LIVE POSITION
    # =========================================================================

    def open_position(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        sl_price: float,
        tp1_price: Optional[
            float
        ] = None,
        tp2_price: Optional[
            float
        ] = None,
        tp_price: Optional[
            float
        ] = None,
        risk_percent: Optional[
            float
        ] = None,
        brain_score: float = 0.0,
        decision_snapshot: Optional[
            TradeDecisionSnapshot
        ] = None,
        execution_id: Optional[
            str
        ] = None,
        validated_request: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Optional[
        TradePosition
    ]:
        """
        Open EXACTLY ONE live broker position.

        Preferred production path:

            validation = ExecutionValidator.validate(...)

            manager.open_position(
                ...,
                validated_request=validation.validated_request,
            )

        This method NEVER:

        - splits a validated position,
        - re-fetches and substitutes another entry price,
        - re-clamps validated SL/TP,
        - changes validated volume.
        """

        action = str(
            action
        ).upper()

        if (
            action
            not in {
                "BUY",
                "SELL",
            }
        ):
            return None

        if not self._check_daily_trade_limit():
            return None

        info = mt5.symbol_info(
            symbol
        )

        if info is None:
            self.logger.error(
                (
                    "No symbol info "
                    "for live entry %s"
                ),
                symbol,
            )

            return None

        final_tp = tp_price

        if final_tp is None:
            final_tp = (
                tp2_price
                if tp2_price
                is not None
                else tp1_price
            )

        if final_tp is None:
            final_tp = 0.0

        # ---------------------------------------------------------------------
        # EXACT VALIDATED REQUEST
        # ---------------------------------------------------------------------

        if validated_request is not None:
            request = dict(
                validated_request
            )

        else:
            # -----------------------------------------------------------------
            # TEMPORARY COMPATIBILITY PATH
            #
            # Your existing engine.py does not yet pass validated_request.
            #
            # This reconstructs the request, but the gateway's one-time token
            # fingerprint will STILL reject it if ANY risk-sensitive field
            # differs from what ExecutionValidator approved.
            #
            # After replacing engine.py, this path should rarely/never be used.
            # -----------------------------------------------------------------

            volume = (
                self.calculate_lot_size(
                    symbol=symbol,
                    sl_price=sl_price,
                    entry_price=entry_price,
                    risk_percent=risk_percent,
                    brain_score=brain_score,
                )
            )

            if volume <= 0.0:
                return None

            request = {
                "action": (
                    mt5.TRADE_ACTION_DEAL
                ),
                "symbol": symbol,
                "volume": volume,
                "type": (
                    self._order_type_for_direction(
                        action
                    )
                ),
                "price": float(
                    entry_price
                ),
                "sl": float(
                    sl_price
                ),
                "tp": float(
                    final_tp
                ),
                "magic": (
                    self.magic_number
                ),
            }

        request_action = int(
            request.get(
                "action",
                -1,
            )
        )

        request_type = int(
            request.get(
                "type",
                -1,
            )
        )

        expected_type = (
            self._order_type_for_direction(
                action
            )
        )

        request_magic = int(
            request.get(
                "magic",
                self.magic_number,
            )
        )

        if (
            request_action
            != mt5.TRADE_ACTION_DEAL
            or str(
                request.get(
                    "symbol",
                    "",
                )
            )
            != symbol
            or request_type
            != expected_type
            or request_magic
            != self.magic_number
        ):
            self.logger.error(
                (
                    "Validated request does "
                    "not match requested "
                    "live trade."
                )
            )

            return None

        # ---------------------------------------------------------------------
        # Risk-sensitive fields are frozen here.
        # ---------------------------------------------------------------------

        immutable_price = (
            self._finite_float(
                request.get(
                    "price"
                )
            )
        )

        immutable_sl = (
            self._finite_float(
                request.get(
                    "sl"
                )
            )
        )

        immutable_tp = (
            self._finite_float(
                request.get(
                    "tp"
                )
            )
        )

        immutable_volume = (
            self._finite_float(
                request.get(
                    "volume"
                )
            )
        )

        if (
            immutable_price <= 0.0
            or immutable_sl <= 0.0
            or immutable_volume <= 0.0
        ):
            self.logger.error(
                (
                    "Validated live request "
                    "has invalid immutable "
                    "geometry."
                )
            )

            return None

        # ---------------------------------------------------------------------
        # Only TRANSPORT fields may be added/changed.
        #
        # execution_service canonical fingerprint deliberately excludes these.
        # ---------------------------------------------------------------------

        request["deviation"] = int(
            request.get(
                "deviation",
                20,
            )
        )

        request["comment"] = str(
            request.get(
                "comment",
                (
                    "PulseViper "
                    "validated entry"
                ),
            )
        )[:31]

        request["type_time"] = int(
            request.get(
                "type_time",
                mt5.ORDER_TIME_GTC,
            )
        )

        result = None

        fill_modes = (
            self._filling_modes(
                info
            )
        )

        # ---------------------------------------------------------------------
        # Gateway claims validation token ONCE.
        #
        # Retry only changes type_filling.
        # ---------------------------------------------------------------------

        with (
            mt5.execution_transaction()
            as execution_api
        ):
            for fill_mode in (
                fill_modes
            ):
                request[
                    "type_filling"
                ] = fill_mode

                result = (
                    execution_api.order_send(
                        request
                    )
                )

                if (
                    self._is_execution_success(
                        result
                    )
                ):
                    break

                # Gateway permits safe retry only
                # for INVALID_FILL.
                if (
                    getattr(
                        result,
                        "retcode",
                        None,
                    )
                    != mt5.TRADE_RETCODE_INVALID_FILL
                ):
                    break

        if not (
            self._is_execution_success(
                result
            )
        ):
            self.logger.error(
                (
                    "Validated live entry "
                    "rejected: code=%s "
                    "comment=%s"
                ),
                getattr(
                    result,
                    "retcode",
                    None,
                ),
                getattr(
                    result,
                    "comment",
                    "NO_RESULT",
                ),
            )

            return None

        # ---------------------------------------------------------------------
        # Resolve actual broker POSITION ticket.
        # ---------------------------------------------------------------------

        ticket = (
            self._resolve_position_ticket(
                result,
                request,
            )
        )

        if ticket <= 0:
            self.logger.error(
                (
                    "Order executed but live "
                    "position ticket could "
                    "not be resolved."
                )
            )

            return None

        actual_entry = (
            self._finite_float(
                getattr(
                    result,
                    "price",
                    0.0,
                ),
                immutable_price,
            )
        )

        actual_volume = (
            self._finite_float(
                getattr(
                    result,
                    "volume",
                    0.0,
                ),
                immutable_volume,
            )
        )

        if actual_volume <= 0.0:
            actual_volume = (
                immutable_volume
            )

        pos = TradePosition(
            ticket_id=ticket,
            symbol=symbol,
            action=action,
            entry_price=(
                actual_entry
            ),
            volume=actual_volume,
            sl=immutable_sl,
            tp=immutable_tp,
            timestamp=datetime.now(
                timezone.utc
            ),
            magic=self.magic_number,
        )

        pos.tp1 = (
            float(tp1_price)
            if tp1_price
            is not None
            else immutable_tp
        )

        pos.tp2 = (
            float(tp2_price)
            if tp2_price
            is not None
            else immutable_tp
        )

        pos.entry_spread_points = (
            self._entry_spread_points(
                symbol
            )
        )

        pos.risk_percent = (
            self.estimate_risk_percent(
                symbol=symbol,
                action=action,
                volume=actual_volume,
                entry_price=actual_entry,
                sl_price=immutable_sl,
                capital=(
                    self.get_capital()
                ),
            )
        )

        self._attach_decision_metadata(
            pos,
            decision_snapshot,
            execution_id,
        )

        self.positions[
            pos.id
        ] = pos

        self.daily_trade_count += 1

        self.logger.info(
            (
                "Live position opened "
                "#%s %s %s @ %.5f | "
                "vol=%.4f SL=%.5f "
                "TP=%.5f risk=%.4f%%"
            ),
            pos.id,
            action,
            symbol,
            actual_entry,
            actual_volume,
            immutable_sl,
            immutable_tp,
            pos.risk_percent,
        )

        return pos

    # =========================================================================
    # LIVE POSITION SYNCHRONIZATION
    # =========================================================================

    def update_positions(
        self,
        symbol: str,
        bid: float,
        ask: float,
        current_regime: str = (
            "RANGING"
        ),
        df_m1: Optional[
            pd.DataFrame
        ] = None,
        atr: Optional[
            float
        ] = None,
        news_locked: bool = False,
        df_h1: Optional[
            pd.DataFrame
        ] = None,
    ) -> None:
        # ---------------------------------------------------------------------
        # No emergency hedge is created here.
        #
        # Hedge creation is a NEW position and must therefore have its own
        # validated entry pipeline. Until that exists, it remains disabled.
        # ---------------------------------------------------------------------

        del news_locked
        del df_h1

        mt5_positions = (
            mt5.positions_get(
                symbol=symbol
            )
        )

        if mt5_positions is None:
            mt5_positions = ()

        broker_positions = tuple(
            pos
            for pos in mt5_positions
            if getattr(
                pos,
                "magic",
                None,
            )
            in (
                self.magic_number,
                0,
            )
        )

        active_tickets = {
            int(pos.ticket)
            for pos in broker_positions
        }

        # ---------------------------------------------------------------------
        # Find positions that disappeared from broker.
        # ---------------------------------------------------------------------

        for (
            ticket,
            pos,
        ) in list(
            self.positions.items()
        ):
            if (
                pos.symbol
                == symbol
                and ticket
                not in active_tickets
            ):
                self._finalize_external_close(
                    pos
                )

        info = mt5.symbol_info(
            symbol
        )

        if info is None:
            return

        point = (
            self._finite_float(
                getattr(
                    info,
                    "point",
                    0.0,
                )
            )
        )

        if point <= 0.0:
            return

        atr_value = (
            self._resolve_atr(
                df_m1,
                atr,
                point,
            )
        )

        self.regime_state_machine.update(
            current_regime
        )

        exit_params = (
            self.regime_state_machine
            .get_exit_params()
        )

        # ---------------------------------------------------------------------
        # Explicitly ignore legacy hedge toggle.
        # ---------------------------------------------------------------------

        if (
            bool(
                settings_manager.get(
                    "emergency_hedging_enabled",
                    False,
                )
            )
            and not (
                self._warned_live_hedge_disabled
            )
        ):
            self.logger.warning(
                (
                    "emergency_hedging_enabled "
                    "is ignored: opening an "
                    "unvalidated hedge is "
                    "disabled."
                )
            )

            self._warned_live_hedge_disabled = (
                True
            )

        # ---------------------------------------------------------------------
        # Recover positions after restart/manual entry.
        # ---------------------------------------------------------------------

        for broker_pos in (
            broker_positions
        ):
            ticket = int(
                broker_pos.ticket
            )

            if ticket not in (
                self.positions
            ):
                self.positions[
                    ticket
                ] = (
                    self._position_from_mt5(
                        broker_pos
                    )
                )

        break_even_enabled = bool(
            settings_manager.get(
                "break_even_enabled",
                True,
            )
        )

        trailing_enabled = bool(
            settings_manager.get(
                "trailing_stop_enabled",
                True,
            )
        )

        # ---------------------------------------------------------------------
        # Manage open positions.
        # ---------------------------------------------------------------------

        for broker_pos in (
            broker_positions
        ):
            ticket = int(
                broker_pos.ticket
            )

            pos = self.positions.get(
                ticket
            )

            if pos is None:
                continue

            self._sync_position_fields(
                pos,
                broker_pos,
            )

            if pos.is_hedge:
                continue

            current_price = (
                bid
                if pos.action
                == "BUY"
                else ask
            )

            pnl_points = (
                (
                    current_price
                    - pos.entry_price
                )
                / point
                if pos.action
                == "BUY"
                else (
                    pos.entry_price
                    - current_price
                )
                / point
            )

            pos.max_profit_points = max(
                pos.max_profit_points,
                pnl_points,
            )

            initial_risk = (
                pos.initial_sl_dist
            )

            if initial_risk <= 0.0:
                continue

            floating_distance = (
                bid
                - pos.entry_price
                if pos.action
                == "BUY"
                else (
                    pos.entry_price
                    - ask
                )
            )

            # =================================================================
            # BREAK EVEN
            #
            # Only after at least 1R or configured pip threshold.
            # =================================================================

            if (
                break_even_enabled
                and not pos.moved_to_be
            ):
                be_pips = (
                    self._finite_float(
                        settings_manager.get(
                            "break_even_pips",
                            8.0,
                        ),
                        8.0,
                    )
                )

                trigger = max(
                    (
                        initial_risk
                        * exit_params[
                            "breakeven_r"
                        ]
                    ),
                    be_pips * point,
                )

                if (
                    floating_distance
                    >= trigger
                ):
                    live_spread = max(
                        0.0,
                        ask - bid,
                    )

                    buffer = max(
                        live_spread,
                        point,
                    )

                    target_sl = (
                        pos.entry_price
                        + buffer
                        if pos.action
                        == "BUY"
                        else (
                            pos.entry_price
                            - buffer
                        )
                    )

                    target_sl = (
                        self._normalize_protective_sl(
                            pos,
                            target_sl,
                            bid,
                            ask,
                            info,
                        )
                    )

                    if (
                        target_sl
                        is not None
                        and self._sl_improves(
                            pos,
                            target_sl,
                        )
                    ):
                        if (
                            self._modify_protection(
                                pos,
                                target_sl,
                                pos.tp,
                            )
                        ):
                            pos.moved_to_be = (
                                True
                            )

            # =================================================================
            # TRAILING STOP
            #
            # Only starts after trade earns >= 1R.
            # Always monotonic/risk-reducing.
            # =================================================================

            if (
                trailing_enabled
                and floating_distance
                >= initial_risk
            ):
                trail_pips = (
                    self._finite_float(
                        settings_manager.get(
                            "trailing_stop_pips",
                            10.0,
                        ),
                        10.0,
                    )
                )

                trail_distance = max(
                    (
                        atr_value
                        * max(
                            1.0,
                            exit_params[
                                "trail_r"
                            ]
                            * 2.0,
                        )
                    ),
                    trail_pips
                    * point,
                )

                raw_target = (
                    bid
                    - trail_distance
                    if pos.action
                    == "BUY"
                    else (
                        ask
                        + trail_distance
                    )
                )

                target_sl = (
                    self._normalize_protective_sl(
                        pos,
                        raw_target,
                        bid,
                        ask,
                        info,
                    )
                )

                if (
                    target_sl
                    is not None
                    and self._sl_improves(
                        pos,
                        target_sl,
                    )
                ):
                    self._modify_protection(
                        pos,
                        target_sl,
                        pos.tp,
                    )

    # =========================================================================
    # MANAGEMENT TRANSACTION
    # =========================================================================

    def _send_management_order(
        self,
        request: dict,
    ):
        """
        Existing-position risk reduction only.

        This path is intentionally separate from validation-token entry
        execution.
        """
        with (
            mt5.management_transaction()
            as management_api
        ):
            return (
                management_api
                .order_send(
                    request
                )
            )

    # =========================================================================
    # MODIFY SL / TP
    # =========================================================================

    def _modify_protection(
        self,
        pos: TradePosition,
        new_sl: float,
        tp: float,
    ) -> bool:
        request = {
            "action": (
                mt5.TRADE_ACTION_SLTP
            ),
            "position": pos.id,
            "symbol": pos.symbol,
            "sl": float(
                new_sl
            ),
            "tp": float(
                tp or 0.0
            ),
        }

        result = (
            self._send_management_order(
                request
            )
        )

        if (
            self._is_management_success(
                result
            )
        ):
            pos.sl = float(
                new_sl
            )

            pos.tp = float(
                tp or 0.0
            )

            self.logger.info(
                (
                    "Position #%s "
                    "protective SL moved "
                    "to %.5f"
                ),
                pos.id,
                pos.sl,
            )

            return True

        self.logger.warning(
            (
                "SL/TP modification "
                "rejected for #%s: "
                "code=%s comment=%s"
            ),
            pos.id,
            getattr(
                result,
                "retcode",
                None,
            ),
            getattr(
                result,
                "comment",
                "NO_RESULT",
            ),
        )

        return False

    # =========================================================================
    # PARTIAL CLOSE
    # =========================================================================

    def partial_close_position(
        self,
        pos: TradePosition,
        volume_to_close: float,
    ) -> bool:
        info = mt5.symbol_info(
            pos.symbol
        )

        tick = (
            mt5.symbol_info_tick(
                pos.symbol
            )
        )

        if (
            info is None
            or tick is None
        ):
            return False

        step = (
            self._finite_float(
                getattr(
                    info,
                    "volume_step",
                    0.01,
                ),
                0.01,
            )
        )

        minimum = (
            self._finite_float(
                getattr(
                    info,
                    "volume_min",
                    0.01,
                ),
                0.01,
            )
        )

        maximum_close = max(
            0.0,
            pos.volume,
        )

        volume = (
            self._normalize_volume_down(
                float(
                    volume_to_close
                ),
                minimum,
                maximum_close,
                step,
            )
        )

        if (
            volume <= 0.0
            or volume
            > pos.volume
            + 1e-9
        ):
            return False

        order_type = (
            mt5.ORDER_TYPE_SELL
            if pos.action == "BUY"
            else mt5.ORDER_TYPE_BUY
        )

        price = (
            self._finite_float(
                tick.bid
                if pos.action
                == "BUY"
                else tick.ask
            )
        )

        if price <= 0.0:
            return False

        request = {
            "action": (
                mt5.TRADE_ACTION_DEAL
            ),
            "symbol": pos.symbol,
            "volume": volume,
            "type": order_type,
            "position": pos.id,
            "price": price,
            "deviation": 20,
            "magic": (
                self.magic_number
            ),
            "comment": (
                "PulseViper "
                "partial close"
            ),
            "type_time": (
                mt5.ORDER_TIME_GTC
            ),
        }

        result = None

        with (
            mt5.management_transaction()
            as management_api
        ):
            for fill_mode in (
                self._filling_modes(
                    info
                )
            ):
                request[
                    "type_filling"
                ] = fill_mode

                result = (
                    management_api
                    .order_send(
                        request
                    )
                )

                if (
                    self._is_management_success(
                        result
                    )
                ):
                    break

                if (
                    getattr(
                        result,
                        "retcode",
                        None,
                    )
                    != mt5.TRADE_RETCODE_INVALID_FILL
                ):
                    break

        if (
            self._is_management_success(
                result
            )
        ):
            # Broker state remains authoritative.
            # update_positions() will synchronize exact remaining volume.
            pos.volume = max(
                0.0,
                pos.volume - volume,
            )

            self.logger.info(
                (
                    "Partially closed "
                    "#%s by %.4f lots"
                ),
                pos.id,
                volume,
            )

            return True

        self.logger.warning(
            (
                "Partial close rejected "
                "for #%s: %s"
            ),
            pos.id,
            getattr(
                result,
                "comment",
                "NO_RESULT",
            ),
        )

        return False

    # =========================================================================
    # COMPLETE CLOSE
    # =========================================================================

    def close_position(
        self,
        pos_id: int,
        close_price: float,
        reason: str,
    ) -> Optional[
        TradePosition
    ]:
        pos = self.positions.get(
            int(pos_id)
        )

        if pos is None:
            return None

        # ---------------------------------------------------------------------
        # Recover/close a LEGACY hedge pair if one already exists.
        #
        # This code does NOT create new hedges.
        # ---------------------------------------------------------------------

        if (
            pos.hedge_ticket
            and pos.hedge_ticket
            in self.positions
        ):
            hedge = self.positions[
                pos.hedge_ticket
            ]

            close_by_request = {
                "action": (
                    mt5.TRADE_ACTION_CLOSE_BY
                ),
                "position": pos.id,
                "position_by": (
                    hedge.id
                ),
                "symbol": pos.symbol,
                "magic": (
                    self.magic_number
                ),
            }

            result = (
                self._send_management_order(
                    close_by_request
                )
            )

            if (
                self._is_management_success(
                    result
                )
            ):
                now = datetime.now(
                    timezone.utc
                )

                self.positions.pop(
                    pos.id,
                    None,
                )

                self.positions.pop(
                    hedge.id,
                    None,
                )

                self._mark_closed_from_history(
                    pos,
                    reason,
                    fallback_price=(
                        close_price
                    ),
                    fallback_time=now,
                )

                self._mark_closed_from_history(
                    hedge,
                    (
                        f"CLOSE_BY_"
                        f"{pos.id}"
                    ),
                    fallback_price=(
                        close_price
                    ),
                    fallback_time=now,
                )

                self.closed_positions.extend(
                    [
                        pos,
                        hedge,
                    ]
                )

                return pos

        # ---------------------------------------------------------------------
        # Standard risk-reducing close.
        # ---------------------------------------------------------------------

        info = mt5.symbol_info(
            pos.symbol
        )

        tick = (
            mt5.symbol_info_tick(
                pos.symbol
            )
        )

        if (
            info is None
            or tick is None
        ):
            return None

        order_type = (
            mt5.ORDER_TYPE_SELL
            if pos.action == "BUY"
            else mt5.ORDER_TYPE_BUY
        )

        market_price = (
            self._finite_float(
                tick.bid
                if pos.action
                == "BUY"
                else tick.ask
            )
        )

        if market_price <= 0.0:
            return None

        request = {
            "action": (
                mt5.TRADE_ACTION_DEAL
            ),
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.id,
            "price": market_price,
            "deviation": 20,
            "magic": (
                self.magic_number
            ),
            "comment": (
                "PulseViper close"
            ),
            "type_time": (
                mt5.ORDER_TIME_GTC
            ),
        }

        result = None

        with (
            mt5.management_transaction()
            as management_api
        ):
            for fill_mode in (
                self._filling_modes(
                    info
                )
            ):
                request[
                    "type_filling"
                ] = fill_mode

                result = (
                    management_api
                    .order_send(
                        request
                    )
                )

                if (
                    self._is_management_success(
                        result
                    )
                ):
                    break

                if (
                    getattr(
                        result,
                        "retcode",
                        None,
                    )
                    != mt5.TRADE_RETCODE_INVALID_FILL
                ):
                    break

        if not (
            self._is_management_success(
                result
            )
        ):
            self.logger.error(
                (
                    "Close rejected for "
                    "#%s: code=%s "
                    "comment=%s"
                ),
                pos.id,
                getattr(
                    result,
                    "retcode",
                    None,
                ),
                getattr(
                    result,
                    "comment",
                    "NO_RESULT",
                ),
            )

            return None

        self.positions.pop(
            pos.id,
            None,
        )

        fallback_price = (
            self._finite_float(
                getattr(
                    result,
                    "price",
                    0.0,
                ),
                market_price,
            )
        )

        self._mark_closed_from_history(
            pos,
            reason,
            fallback_price=(
                fallback_price
            ),
            fallback_time=(
                datetime.now(
                    timezone.utc
                )
            ),
        )

        self.closed_positions.append(
            pos
        )

        if (
            pos.is_hedge
            and pos.parent_position_id
            in self.positions
        ):
            self.positions[
                pos.parent_position_id
            ].hedge_ticket = None

        self.logger.info(
            (
                "Live position #%s "
                "closed (%s), "
                "PnL %.2f"
            ),
            pos.id,
            reason,
            pos.pnl,
        )

        return pos

    # =========================================================================
    # BROKER POSITION RECOVERY
    # =========================================================================

    def _position_from_mt5(
        self,
        broker_pos: Any,
    ) -> TradePosition:
        action = (
            "BUY"
            if broker_pos.type
            == mt5.POSITION_TYPE_BUY
            else "SELL"
        )

        timestamp = (
            datetime.fromtimestamp(
                float(
                    broker_pos.time
                ),
                tz=timezone.utc,
            )
        )

        pos = TradePosition(
            ticket_id=int(
                broker_pos.ticket
            ),
            symbol=str(
                broker_pos.symbol
            ),
            action=action,
            entry_price=float(
                broker_pos.price_open
            ),
            volume=float(
                broker_pos.volume
            ),
            sl=float(
                getattr(
                    broker_pos,
                    "sl",
                    0.0,
                )
                or 0.0
            ),
            tp=float(
                getattr(
                    broker_pos,
                    "tp",
                    0.0,
                )
                or 0.0
            ),
            timestamp=timestamp,
            magic=int(
                getattr(
                    broker_pos,
                    "magic",
                    0,
                )
                or 0
            ),
        )

        comment = str(
            getattr(
                broker_pos,
                "comment",
                "",
            )
            or ""
        )

        # Legacy hedge recovery only.
        if (
            "Hedge for #"
            in comment
        ):
            pos.is_hedge = True

            try:
                pos.parent_position_id = int(
                    comment.rsplit(
                        "#",
                        1,
                    )[-1]
                )

            except ValueError:
                pass

        pos.pnl = (
            self._finite_float(
                getattr(
                    broker_pos,
                    "profit",
                    0.0,
                )
            )
        )

        pos.risk_percent = (
            self.estimate_risk_percent(
                symbol=pos.symbol,
                action=pos.action,
                volume=pos.volume,
                entry_price=(
                    pos.entry_price
                ),
                sl_price=(
                    pos.initial_sl
                ),
                capital=(
                    self.get_capital()
                ),
            )
        )

        if (
            (
                pos.action
                == "BUY"
                and pos.sl
                >= pos.entry_price
                and pos.sl > 0.0
            )
            or (
                pos.action
                == "SELL"
                and 0.0
                < pos.sl
                <= pos.entry_price
            )
        ):
            pos.moved_to_be = (
                True
            )

        return pos

    def _sync_position_fields(
        self,
        pos: TradePosition,
        broker_pos: Any,
    ) -> None:
        pos.volume = (
            self._finite_float(
                getattr(
                    broker_pos,
                    "volume",
                    pos.volume,
                ),
                pos.volume,
            )
        )

        pos.pnl = (
            self._finite_float(
                getattr(
                    broker_pos,
                    "profit",
                    pos.pnl,
                ),
                pos.pnl,
            )
        )

        pos.sl = (
            self._finite_float(
                getattr(
                    broker_pos,
                    "sl",
                    pos.sl,
                ),
                pos.sl,
            )
        )

        pos.tp = (
            self._finite_float(
                getattr(
                    broker_pos,
                    "tp",
                    pos.tp,
                ),
                pos.tp,
            )
        )

        # ---------------------------------------------------------------------
        # For manually attached positions:
        # initialize ORIGINAL risk only once.
        # ---------------------------------------------------------------------

        if (
            pos.initial_sl_dist <= 0.0
            and pos.initial_sl <= 0.0
            and pos.sl > 0.0
        ):
            pos.initial_sl = (
                pos.sl
            )

            pos.initial_sl_dist = abs(
                pos.entry_price
                - pos.sl
            )

            pos.initial_risk_distance = (
                pos.initial_sl_dist
            )

        if (
            (
                pos.action
                == "BUY"
                and pos.sl
                >= pos.entry_price
                and pos.sl > 0.0
            )
            or (
                pos.action
                == "SELL"
                and 0.0
                < pos.sl
                <= pos.entry_price
            )
        ):
            pos.moved_to_be = (
                True
            )

    # =========================================================================
    # EXTERNAL BROKER CLOSE
    # =========================================================================

    def _finalize_external_close(
        self,
        pos: TradePosition,
    ) -> None:
        self.positions.pop(
            pos.id,
            None,
        )

        self._mark_closed_from_history(
            pos,
            "MT5_CLOSE",
            fallback_price=(
                pos.close_price
                or pos.entry_price
            ),
            fallback_time=(
                datetime.now(
                    timezone.utc
                )
            ),
        )

        self.closed_positions.append(
            pos
        )

        self.logger.info(
            (
                "Position #%s finalized "
                "from MT5 history (%s) "
                "@ %.5f | PnL %.2f"
            ),
            pos.id,
            pos.close_reason,
            pos.close_price,
            pos.pnl,
        )

    def _mark_closed_from_history(
        self,
        pos: TradePosition,
        reason: str,
        fallback_price: float,
        fallback_time: datetime,
    ) -> None:
        pos.status = "CLOSED"

        pos.close_reason = (
            reason
        )

        pos.close_price = float(
            fallback_price
        )

        pos.close_time = (
            fallback_time
            .astimezone(
                timezone.utc
            )
        )

        try:
            deals = (
                mt5.history_deals_get(
                    position=pos.id
                )
            )

        except Exception:
            deals = None

        if not deals:
            return

        exit_deals = [
            deal
            for deal in deals
            if getattr(
                deal,
                "entry",
                None,
            )
            in (
                mt5.DEAL_ENTRY_OUT,
                mt5.DEAL_ENTRY_INOUT,
            )
        ]

        if not exit_deals:
            return

        exit_deals.sort(
            key=lambda deal: getattr(
                deal,
                "time_msc",
                getattr(
                    deal,
                    "time",
                    0,
                ),
            )
        )

        last = exit_deals[-1]

        pos.close_price = (
            self._finite_float(
                getattr(
                    last,
                    "price",
                    pos.close_price,
                ),
                pos.close_price,
            )
        )

        last_time = (
            self._finite_float(
                getattr(
                    last,
                    "time",
                    0.0,
                )
            )
        )

        if last_time > 0.0:
            pos.close_time = (
                datetime.fromtimestamp(
                    last_time,
                    tz=timezone.utc,
                )
            )

        # ---------------------------------------------------------------------
        # Realized P&L includes exit-side commission and swap.
        # ---------------------------------------------------------------------

        pos.pnl = sum(
            (
                self._finite_float(
                    getattr(
                        deal,
                        "profit",
                        0.0,
                    )
                )
                + self._finite_float(
                    getattr(
                        deal,
                        "commission",
                        0.0,
                    )
                )
                + self._finite_float(
                    getattr(
                        deal,
                        "swap",
                        0.0,
                    )
                )
            )
            for deal
            in exit_deals
        )

        reason_code = getattr(
            last,
            "reason",
            None,
        )

        if (
            reason_code
            == mt5.DEAL_REASON_SL
        ):
            pos.close_reason = "SL"

        elif (
            reason_code
            == mt5.DEAL_REASON_TP
        ):
            pos.close_reason = "TP"

    # =========================================================================
    # POSITION TICKET RESOLUTION
    # =========================================================================

    def _resolve_position_ticket(
        self,
        result: Any,
        request: dict,
    ) -> int:
        candidate = int(
            getattr(
                result,
                "order",
                0,
            )
            or 0
        )

        if candidate > 0:
            try:
                direct = (
                    mt5.positions_get(
                        ticket=candidate
                    )
                )

                if direct:
                    return int(
                        direct[0].ticket
                    )

            except Exception:
                pass

        symbol = str(
            request.get(
                "symbol",
                "",
            )
        )

        expected_type = int(
            request.get(
                "type",
                -1,
            )
        )

        expected_magic = int(
            request.get(
                "magic",
                self.magic_number,
            )
        )

        positions = (
            mt5.positions_get(
                symbol=symbol
            )
            or ()
        )

        matching = [
            pos
            for pos in positions
            if (
                int(
                    getattr(
                        pos,
                        "magic",
                        -1,
                    )
                )
                == expected_magic
                and (
                    (
                        expected_type
                        == mt5.ORDER_TYPE_BUY
                        and pos.type
                        == mt5.POSITION_TYPE_BUY
                    )
                    or (
                        expected_type
                        == mt5.ORDER_TYPE_SELL
                        and pos.type
                        == mt5.POSITION_TYPE_SELL
                    )
                )
            )
        ]

        if not matching:
            return candidate

        matching.sort(
            key=lambda pos: getattr(
                pos,
                "time_msc",
                getattr(
                    pos,
                    "time",
                    0,
                ),
            ),
            reverse=True,
        )

        return int(
            matching[0].ticket
        )

    # =========================================================================
    # FILLING MODES
    # =========================================================================

    @staticmethod
    def _filling_modes(
        info: Any,
    ) -> List[int]:
        modes: List[
            int
        ] = []

        mask = int(
            getattr(
                info,
                "filling_mode",
                0,
            )
            or 0
        )

        if mask & 1:
            modes.append(
                mt5.ORDER_FILLING_FOK
            )

        if mask & 2:
            modes.append(
                mt5.ORDER_FILLING_IOC
            )

        for mode in (
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_RETURN,
        ):
            if mode not in modes:
                modes.append(
                    mode
                )

        # execution_transaction()
        # allows max 3 attempts.
        return modes[:3]

    # =========================================================================
    # RESULT HELPERS
    # =========================================================================

    @staticmethod
    def _is_execution_success(
        result: Any,
    ) -> bool:
        if result is None:
            return False

        return (
            getattr(
                result,
                "retcode",
                None,
            )
            in {
                mt5.TRADE_RETCODE_DONE,
                mt5.TRADE_RETCODE_DONE_PARTIAL,
                mt5.TRADE_RETCODE_PLACED,
            }
        )

    @staticmethod
    def _is_management_success(
        result: Any,
    ) -> bool:
        if result is None:
            return False

        return (
            getattr(
                result,
                "retcode",
                None,
            )
            in {
                mt5.TRADE_RETCODE_DONE,
                mt5.TRADE_RETCODE_DONE_PARTIAL,
                mt5.TRADE_RETCODE_PLACED,
            }
        )

    # =========================================================================
    # ATR HELPER
    # =========================================================================

    def _resolve_atr(
        self,
        df_m1: Optional[
            pd.DataFrame
        ],
        atr: Optional[
            float
        ],
        point: float,
    ) -> float:
        value = (
            self._finite_float(
                atr
            )
        )

        if (
            value <= 0.0
            and df_m1 is not None
            and not df_m1.empty
            and "atr"
            in df_m1.columns
        ):
            value = (
                self._finite_float(
                    df_m1[
                        "atr"
                    ].iloc[-1]
                )
            )

        if value > 0.0:
            return value

        return (
            15.0
            * point
        )

    # =========================================================================
    # MONOTONIC SL
    # =========================================================================

    @staticmethod
    def _sl_improves(
        pos: TradePosition,
        target: float,
    ) -> bool:
        if target <= 0.0:
            return False

        if pos.action == "BUY":
            return (
                pos.sl == 0.0
                or target
                > pos.sl
            )

        return (
            pos.sl == 0.0
            or target
            < pos.sl
        )

    # =========================================================================
    # BROKER-COMPATIBLE PROTECTIVE SL
    # =========================================================================

    def _normalize_protective_sl(
        self,
        pos: TradePosition,
        target: float,
        bid: float,
        ask: float,
        info: Any,
    ) -> Optional[
        float
    ]:
        point = (
            self._finite_float(
                getattr(
                    info,
                    "point",
                    0.0,
                )
            )
        )

        if point <= 0.0:
            return None

        digits = int(
            getattr(
                info,
                "digits",
                5,
            )
        )

        stops_level = (
            self._finite_float(
                getattr(
                    info,
                    "trade_stops_level",
                    0.0,
                )
            )
        )

        freeze_level = (
            self._finite_float(
                getattr(
                    info,
                    "trade_freeze_level",
                    0.0,
                )
            )
        )

        minimum = max(
            point,
            stops_level
            * point,
            freeze_level
            * point,
        )

        if pos.action == "BUY":
            target = min(
                float(target),
                bid - minimum,
            )

            if target >= bid:
                return None

        else:
            target = max(
                float(target),
                ask + minimum,
            )

            if target <= ask:
                return None

        target = round(
            target,
            digits,
        )

        if target <= 0.0:
            return None

        return target