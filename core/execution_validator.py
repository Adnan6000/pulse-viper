# core/execution_validator.py

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.execution_service import canonical_request_hash
from core.execution_token import (
    ExecutionValidationToken,
    validation_token_store,
)
from utils.mt5_gateway import mt5_gateway as mt5
from utils.settings_manager import settings_manager


@dataclass(frozen=True)
class ExecutionValidationResult:
    allowed: bool
    reason: str
    validated_at_utc: datetime
    validation_id: str
    decision_id: str

    actual_entry_price: float
    effective_rr: float
    spread_points: float
    quote_age_ms: float

    token: Optional[ExecutionValidationToken] = None

    # Exact trade geometry that was validated.
    validated_request: Optional[Dict[str, Any]] = None

    # Actual broker-estimated capital risk of this final request.
    estimated_risk_percent: float = 0.0


class ExecutionValidator:
    """
    Final deterministic validation before a NEW broker position is submitted.

    It does not decide whether a strategy is good.
    It verifies whether the already-decided trade is safe and internally valid.
    """

    def __init__(self):
        self.logger = logging.getLogger(
            "PulseViper.ExecutionValidator"
        )

    # ------------------------------------------------------------------

    def validate(
        self,
        symbol: str,
        action: str,
        sl: float,
        tp: float,
        volume: float,
        analysis: Dict[str, Any],
        trade_manager,
        decision_id: str,
        candidate_id: str = "UNKNOWN",
    ) -> ExecutionValidationResult:
        validated_at_utc = datetime.now(
            timezone.utc
        )

        validation_id = (
            f"PV-VAL-{uuid.uuid4().hex[:12]}"
        )

        def reject(
            reason: str,
            entry_price: float = 0.0,
            effective_rr: float = 0.0,
            spread_points: float = 0.0,
            quote_age_ms: float = 0.0,
            estimated_risk_percent: float = 0.0,
        ) -> ExecutionValidationResult:
            return ExecutionValidationResult(
                allowed=False,
                reason=reason,
                validated_at_utc=validated_at_utc,
                validation_id=validation_id,
                decision_id=decision_id,
                actual_entry_price=entry_price,
                effective_rr=effective_rr,
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
                token=None,
                validated_request=None,
                estimated_risk_percent=(
                    estimated_risk_percent
                ),
            )

        try:
            # ----------------------------------------------------------
            # Basic inputs
            # ----------------------------------------------------------

            action = str(action).upper().strip()
            symbol = str(symbol).strip()

            if action not in {"BUY", "SELL"}:
                return reject(
                    f"INVALID_ACTION_{action}"
                )

            if not symbol:
                return reject(
                    "SYMBOL_MISSING"
                )

            sl = self._finite_float(sl)
            tp = self._finite_float(tp)
            volume = self._finite_float(volume)

            if volume <= 0.0:
                return reject(
                    "INVALID_VOLUME"
                )

            # ----------------------------------------------------------
            # Fresh broker data
            # ----------------------------------------------------------

            tick = mt5.symbol_info_tick(symbol)

            if tick is None:
                return reject(
                    "NO_TICK"
                )

            symbol_info = mt5.symbol_info(symbol)

            if symbol_info is None:
                return reject(
                    "NO_SYMBOL_INFO"
                )

            point = self._finite_float(
                getattr(
                    symbol_info,
                    "point",
                    0.0,
                )
            )

            if point <= 0.0:
                return reject(
                    "INVALID_POINT_SIZE"
                )

            bid = self._finite_float(
                getattr(
                    tick,
                    "bid",
                    0.0,
                )
            )

            ask = self._finite_float(
                getattr(
                    tick,
                    "ask",
                    0.0,
                )
            )

            if (
                bid <= 0.0
                or ask <= 0.0
                or ask < bid
            ):
                return reject(
                    "INVALID_BID_ASK"
                )

            quote_age_ms = self._quote_age_ms(
                tick
            )

            max_quote_age_ms = self._finite_float(
                settings_manager.get(
                    "max_validation_token_age_ms",
                    5000.0,
                ),
                5000.0,
            )

            max_quote_age_ms = max(
                100.0,
                max_quote_age_ms,
            )

            if quote_age_ms > max_quote_age_ms:
                return reject(
                    (
                        f"STALE_QUOTE_{quote_age_ms:.0f}MS_"
                        f"MAX_{max_quote_age_ms:.0f}MS"
                    ),
                    quote_age_ms=quote_age_ms,
                )

            # BUY executes ASK. SELL executes BID.
            entry_price = (
                ask
                if action == "BUY"
                else bid
            )

            # ----------------------------------------------------------
            # Spread
            # ----------------------------------------------------------

            spread_points = (
                ask - bid
            ) / point

            max_spread_points = self._finite_float(
                settings_manager.get(
                    "max_spread_points",
                    350.0,
                ),
                350.0,
            )

            if (
                spread_points
                > max_spread_points
            ):
                return reject(
                    (
                        f"SPREAD_TOO_HIGH_"
                        f"{spread_points:.1f}_"
                        f"MAX_{max_spread_points:.1f}"
                    ),
                    entry_price,
                    spread_points=spread_points,
                    quote_age_ms=quote_age_ms,
                )

            # ----------------------------------------------------------
            # SL / TP direction
            # ----------------------------------------------------------

            if action == "BUY":
                if sl != 0.0 and sl >= entry_price:
                    return reject(
                        "BUY_SL_MUST_BE_BELOW_ENTRY",
                        entry_price,
                        spread_points=spread_points,
                        quote_age_ms=quote_age_ms,
                    )

                if tp != 0.0 and tp <= entry_price:
                    return reject(
                        "BUY_TP_MUST_BE_ABOVE_ENTRY",
                        entry_price,
                        spread_points=spread_points,
                        quote_age_ms=quote_age_ms,
                    )

            else:
                if sl != 0.0 and sl <= entry_price:
                    return reject(
                        "SELL_SL_MUST_BE_ABOVE_ENTRY",
                        entry_price,
                        spread_points=spread_points,
                        quote_age_ms=quote_age_ms,
                    )

                if tp != 0.0 and tp >= entry_price:
                    return reject(
                        "SELL_TP_MUST_BE_BELOW_ENTRY",
                        entry_price,
                        spread_points=spread_points,
                        quote_age_ms=quote_age_ms,
                    )

            # New entries must have a real protective stop.
            if sl == 0.0:
                return reject(
                    "STOP_LOSS_REQUIRED",
                    entry_price,
                    spread_points=spread_points,
                    quote_age_ms=quote_age_ms,
                )

            sl_distance = abs(
                entry_price - sl
            )

            if sl_distance <= 0.0:
                return reject(
                    "ZERO_RISK_DISTANCE",
                    entry_price,
                    spread_points=spread_points,
                    quote_age_ms=quote_age_ms,
                )

            # ----------------------------------------------------------
            # Broker stop distance
            # ----------------------------------------------------------

            stops_level = self._finite_float(
                getattr(
                    symbol_info,
                    "trade_stops_level",
                    0.0,
                )
            )

            minimum_stop_distance = (
                stops_level * point
            )

            if (
                minimum_stop_distance > 0.0
                and sl_distance
                + (point * 0.01)
                < minimum_stop_distance
            ):
                return reject(
                    (
                        "SL_BELOW_BROKER_STOPS_LEVEL_"
                        f"{sl_distance / point:.1f}_"
                        f"MIN_{stops_level:.1f}"
                    ),
                    entry_price,
                    spread_points=spread_points,
                    quote_age_ms=quote_age_ms,
                )

            # ----------------------------------------------------------
            # Reward/risk
            # ----------------------------------------------------------

            effective_rr = 0.0

            if tp != 0.0:
                tp_distance = abs(
                    tp - entry_price
                )

                effective_rr = (
                    tp_distance
                    / sl_distance
                )

                minimum_rr = self._finite_float(
                    settings_manager.get(
                        "min_rr_ratio",
                        1.5,
                    ),
                    1.5,
                )

                if effective_rr < minimum_rr:
                    return reject(
                        (
                            "RR_BELOW_MINIMUM_"
                            f"{effective_rr:.2f}_"
                            f"REQUIRED_{minimum_rr:.2f}"
                        ),
                        entry_price,
                        effective_rr,
                        spread_points,
                        quote_age_ms,
                    )

                if (
                    minimum_stop_distance > 0.0
                    and tp_distance
                    + (point * 0.01)
                    < minimum_stop_distance
                ):
                    return reject(
                        "TP_BELOW_BROKER_STOPS_LEVEL",
                        entry_price,
                        effective_rr,
                        spread_points,
                        quote_age_ms,
                    )

            # ----------------------------------------------------------
            # Volume constraints
            # ----------------------------------------------------------

            volume_min = self._finite_float(
                getattr(
                    symbol_info,
                    "volume_min",
                    0.0,
                )
            )

            volume_max = self._finite_float(
                getattr(
                    symbol_info,
                    "volume_max",
                    0.0,
                )
            )

            volume_step = self._finite_float(
                getattr(
                    symbol_info,
                    "volume_step",
                    0.0,
                )
            )

            if (
                volume_min > 0.0
                and volume + 1e-12 < volume_min
            ):
                return reject(
                    (
                        f"VOLUME_BELOW_MINIMUM_"
                        f"{volume}_MIN_{volume_min}"
                    ),
                    entry_price,
                    effective_rr,
                    spread_points,
                    quote_age_ms,
                )

            if (
                volume_max > 0.0
                and volume - 1e-12 > volume_max
            ):
                return reject(
                    (
                        f"VOLUME_ABOVE_MAXIMUM_"
                        f"{volume}_MAX_{volume_max}"
                    ),
                    entry_price,
                    effective_rr,
                    spread_points,
                    quote_age_ms,
                )

            if (
                volume_step > 0.0
                and volume_min >= 0.0
            ):
                steps = (
                    volume - volume_min
                ) / volume_step

                if abs(
                    steps - round(steps)
                ) > 1e-5:
                    return reject(
                        (
                            "VOLUME_NOT_ALIGNED_TO_STEP_"
                            f"{volume_step}"
                        ),
                        entry_price,
                        effective_rr,
                        spread_points,
                        quote_age_ms,
                    )

            # ----------------------------------------------------------
            # Duplicate broker/local exposure
            # ----------------------------------------------------------

            positions = getattr(
                trade_manager,
                "positions",
                {},
            )

            if not isinstance(
                positions,
                dict,
            ):
                positions = {}

            if not settings_manager.get(
                "hedging_mode",
                False,
            ):
                for position in positions.values():
                    if (
                        getattr(
                            position,
                            "symbol",
                            None,
                        )
                        == symbol
                        and str(
                            getattr(
                                position,
                                "action",
                                "",
                            )
                        ).upper()
                        == action
                    ):
                        return reject(
                            "DUPLICATE_POSITION",
                            entry_price,
                            effective_rr,
                            spread_points,
                            quote_age_ms,
                        )

            # ----------------------------------------------------------
            # News / setup status
            # ----------------------------------------------------------

            if bool(
                analysis.get(
                    "news_locked",
                    False,
                )
            ):
                return reject(
                    "NEWS_LOCK_ACTIVE",
                    entry_price,
                    effective_rr,
                    spread_points,
                    quote_age_ms,
                )

            if not bool(
                analysis.get(
                    "revalidation_status",
                    True,
                )
            ):
                return reject(
                    "SETUP_REVALIDATION_FAILED",
                    entry_price,
                    effective_rr,
                    spread_points,
                    quote_age_ms,
                )

            # ----------------------------------------------------------
            # Planned price drift
            # ----------------------------------------------------------

            target_setup = analysis.get(
                "target_setup",
                {},
            )

            if not isinstance(
                target_setup,
                dict,
            ):
                target_setup = {}

            planned_entry = self._finite_float(
                target_setup.get(
                    "entry",
                    entry_price,
                ),
                entry_price,
            )

            max_price_drift_points = (
                self._finite_float(
                    settings_manager.get(
                        "max_price_drift_points",
                        50.0,
                    ),
                    50.0,
                )
            )

            planned_drift_points = (
                abs(
                    entry_price
                    - planned_entry
                )
                / point
            )

            if (
                planned_drift_points
                > max_price_drift_points
            ):
                return reject(
                    (
                        "PRICE_DRIFT_EXCEEDED_"
                        f"{planned_drift_points:.1f}_"
                        f"MAX_{max_price_drift_points:.1f}"
                    ),
                    entry_price,
                    effective_rr,
                    spread_points,
                    quote_age_ms,
                )

            # ----------------------------------------------------------
            # Calculate actual request risk using broker calculator
            # ----------------------------------------------------------

            order_type = (
                mt5.ORDER_TYPE_BUY
                if action == "BUY"
                else mt5.ORDER_TYPE_SELL
            )

            estimated_risk_percent = (
                self._calculate_actual_risk_percent(
                    symbol=symbol,
                    order_type=order_type,
                    volume=volume,
                    entry_price=entry_price,
                    stop_price=sl,
                )
            )

            max_portfolio_heat = (
                self._finite_float(
                    settings_manager.get(
                        "max_portfolio_heat",
                        5.0,
                    ),
                    5.0,
                )
            )

            current_heat = 0.0

            for position in positions.values():
                position_risk = self._finite_float(
                    getattr(
                        position,
                        "risk_percent",
                        0.0,
                    )
                )

                if position_risk > 0.0:
                    current_heat += position_risk

            if (
                estimated_risk_percent > 0.0
                and (
                    current_heat
                    + estimated_risk_percent
                )
                > max_portfolio_heat + 1e-9
            ):
                return reject(
                    (
                        "PORTFOLIO_HEAT_EXCEEDED_"
                        f"CURRENT_{current_heat:.3f}%_"
                        f"NEW_{estimated_risk_percent:.3f}%_"
                        f"MAX_{max_portfolio_heat:.3f}%"
                    ),
                    entry_price,
                    effective_rr,
                    spread_points,
                    quote_age_ms,
                    estimated_risk_percent,
                )

            # ----------------------------------------------------------
            # Construct exact validated request geometry
            # ----------------------------------------------------------

            magic = int(
                getattr(
                    trade_manager,
                    "magic_number",
                    99999,
                )
            )

            validated_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(volume),
                "type": order_type,
                "price": float(entry_price),
                "sl": float(sl),
                "tp": float(tp),
                "magic": magic,
            }

            fingerprint = canonical_request_hash(
                validated_request
            )

            # ----------------------------------------------------------
            # One-time token
            # ----------------------------------------------------------

            token_id = (
                f"PV-TOK-{uuid.uuid4().hex}"
            )

            expiry_seconds = self._finite_float(
                settings_manager.get(
                    "token_expiry_seconds",
                    30.0,
                ),
                30.0,
            )

            expiry_seconds = max(
                1.0,
                min(
                    expiry_seconds,
                    60.0,
                ),
            )

            token = ExecutionValidationToken(
                token_id=token_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                symbol=symbol,
                action=action,
                request_fingerprint=fingerprint,
                issued_at_utc=validated_at_utc,
                expires_at_utc=(
                    validated_at_utc
                    + timedelta(
                        seconds=expiry_seconds
                    )
                ),
                validation_id=validation_id,
            )

            validation_token_store.store(
                token
            )

            return ExecutionValidationResult(
                allowed=True,
                reason="VALIDATED",
                validated_at_utc=validated_at_utc,
                validation_id=validation_id,
                decision_id=decision_id,
                actual_entry_price=entry_price,
                effective_rr=effective_rr,
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
                token=token,
                validated_request=validated_request,
                estimated_risk_percent=(
                    estimated_risk_percent
                ),
            )

        except Exception as exc:
            self.logger.exception(
                "Execution validation failed"
            )

            return reject(
                "VALIDATOR_EXCEPTION_"
                f"{type(exc).__name__}"
            )

    # ------------------------------------------------------------------
    # Broker-estimated risk
    # ------------------------------------------------------------------

    def _calculate_actual_risk_percent(
        self,
        symbol: str,
        order_type: int,
        volume: float,
        entry_price: float,
        stop_price: float,
    ) -> float:
        if (
            volume <= 0.0
            or entry_price <= 0.0
            or stop_price <= 0.0
        ):
            return 0.0

        try:
            potential_pnl = mt5.order_calc_profit(
                order_type,
                symbol,
                volume,
                entry_price,
                stop_price,
            )

            if potential_pnl is None:
                return 0.0

            potential_loss = abs(
                float(potential_pnl)
            )

            account = mt5.account_info()

            if account is None:
                return 0.0

            equity = self._finite_float(
                getattr(
                    account,
                    "equity",
                    0.0,
                )
            )

            if equity <= 0.0:
                equity = self._finite_float(
                    getattr(
                        account,
                        "balance",
                        0.0,
                    )
                )

            if equity <= 0.0:
                return 0.0

            return (
                potential_loss
                / equity
            ) * 100.0

        except Exception:
            self.logger.exception(
                "Failed calculating broker-estimated trade risk"
            )

            return 0.0

    # ------------------------------------------------------------------

    @staticmethod
    def _finite_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            number = float(value)

            if not math.isfinite(number):
                return default

            return number

        except (
            TypeError,
            ValueError,
        ):
            return default

    # ------------------------------------------------------------------

    @staticmethod
    def _quote_age_ms(
        tick: Any,
    ) -> float:
        import time

        now_ms = time.time() * 1000.0

        time_msc = getattr(
            tick,
            "time_msc",
            None,
        )

        try:
            timestamp = ExecutionValidator._finite_float(time_msc, 0.0)

            if (
                math.isfinite(timestamp)
                and timestamp > 0.0
            ):
                return max(
                    0.0,
                    now_ms - timestamp,
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

        time_sec = getattr(
            tick,
            "time",
            None,
        )

        try:
            timestamp = ExecutionValidator._finite_float(time_sec, 0.0)

            if (
                math.isfinite(timestamp)
                and timestamp > 0.0
            ):
                return max(
                    0.0,
                    now_ms
                    - timestamp * 1000.0,
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

        return float("inf")