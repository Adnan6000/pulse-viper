# core/execution_service.py

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import MetaTrader5 as raw_mt5

from core.execution_token import (
    ExecutionValidationToken,
    validation_token_store,
)
from utils.settings_manager import settings_manager


logger = logging.getLogger("PulseViper.ExecutionService")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def canonical_request_payload(request: dict) -> dict:
    """
    Build the immutable/risk-sensitive portion of an MT5 request.

    Deliberately excludes fields such as:
        - type_filling
        - deviation
        - comment
        - type_time

    because a broker may require a different filling mode while the actual
    validated trade geometry MUST remain unchanged.

    Any change to:
        symbol / action / type / volume / price / SL / TP / magic

    produces a different fingerprint and therefore cannot reuse the token.
    """
    return {
        "symbol": str(request.get("symbol", "")).strip(),
        "action": _safe_int(request.get("action")),
        "type": _safe_int(request.get("type")),
        "volume": round(_safe_float(request.get("volume")), 8),
        "price": round(_safe_float(request.get("price")), 8),
        "sl": round(_safe_float(request.get("sl")), 8),
        "tp": round(_safe_float(request.get("tp")), 8),
        "magic": _safe_int(request.get("magic")),
    }


def canonical_request_hash(request: dict) -> str:
    """
    Return SHA-256 fingerprint of the immutable execution request.
    """
    canonical = canonical_request_payload(request)

    dumped = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


@dataclass
class RejectedResult:
    """
    Lightweight object compatible with the MT5 order_send result attributes
    used by the rest of the project.
    """

    comment: str
    retcode: int = 10014
    order: int = 0
    deal: int = 0
    volume: float = 0.0
    price: float = 0.0
    request_id: int = 0


@dataclass(frozen=True)
class SubmissionRevalidation:
    allowed: bool
    reason: str

    current_entry_price: float = 0.0
    spread_points: float = 0.0
    quote_age_ms: float = 0.0
    price_drift_points: float = 0.0


class MT5ExecutionService:
    """
    Privileged boundary for opening NEW MT5 positions.

    Security rules
    --------------
    1. New entries require a one-time ExecutionValidationToken.
    2. The immutable request fingerprint must match the validated request.
    3. The market is revalidated immediately before submission.
    4. Emergency halt blocks NEW risk.
    5. Existing-position management is intentionally NOT handled here.
       That is handled by mt5_gateway.management_transaction().
    """

    def __init__(
        self,
        emergency_halt_event: Optional[threading.Event],
        token_store=None,
    ):
        self._emergency_halt_event = emergency_halt_event
        self._token_store = (
            token_store
            if token_store is not None
            else validation_token_store
        )

        self._execution_lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def submit_order(
        self,
        token: ExecutionValidationToken,
        request: dict,
    ):
        """
        Submit a request when THIS service owns token consumption.

        Do not use this method after the gateway has already claimed the token.
        Gateway execution_transaction() must use submit_claimed_order().
        """
        with self._execution_lock:
            if self._is_emergency_halted():
                return RejectedResult("REJECTED_EMERGENCY_HALT")

            if token is None:
                return RejectedResult("VALIDATION_TOKEN_MISSING")

            stored_token = self._token_store.consume(token.token_id)

            if stored_token is None:
                return RejectedResult(
                    "TOKEN_UNKNOWN_EXPIRED_OR_ALREADY_USED"
                )

            return self._submit_claimed(stored_token, request)

    def submit_claimed_order(
        self,
        token: ExecutionValidationToken,
        request: dict,
    ):
        """
        Submit a request for a token that has ALREADY been atomically claimed
        by MT5Gateway.execution_transaction().

        IMPORTANT:
        This method does NOT consume the token again.
        """
        with self._execution_lock:
            return self._submit_claimed(token, request)

    # ------------------------------------------------------------------
    # Internal secure submission
    # ------------------------------------------------------------------

    def _submit_claimed(
        self,
        token: ExecutionValidationToken,
        request: dict,
    ):
        if self._is_emergency_halted():
            return RejectedResult("REJECTED_EMERGENCY_HALT")

        if token is None:
            return RejectedResult("VALIDATION_TOKEN_MISSING")

        now = datetime.now(timezone.utc)

        if now > token.expires_at_utc:
            return RejectedResult("TOKEN_EXPIRED")

        if not request:
            return RejectedResult("EMPTY_EXECUTION_REQUEST")

        request_symbol = str(request.get("symbol", "")).strip()

        if not request_symbol:
            return RejectedResult("REQUEST_SYMBOL_MISSING")

        if request_symbol != token.symbol:
            return RejectedResult(
                "REQUEST_SYMBOL_DOES_NOT_MATCH_TOKEN"
            )

        fingerprint = canonical_request_hash(request)

        if fingerprint != token.request_fingerprint:
            logger.error(
                "Execution fingerprint mismatch token=%s expected=%s actual=%s",
                token.token_id,
                token.request_fingerprint,
                fingerprint,
            )

            return RejectedResult("REQUEST_FINGERPRINT_MISMATCH")

        revalidation = self._final_submission_revalidation(
            token,
            request,
        )

        if not revalidation.allowed:
            return RejectedResult(revalidation.reason)

        # Check the emergency switch immediately before the privileged call.
        if self._is_emergency_halted():
            return RejectedResult("REJECTED_EMERGENCY_HALT")

        try:
            return raw_mt5.order_send(request)  # type: ignore[attr-defined]

        except Exception as exc:
            logger.exception(
                "Raw MT5 order_send failed for %s",
                request_symbol,
            )

            return RejectedResult(
                f"MT5_ORDER_SEND_EXCEPTION_{type(exc).__name__}"
            )

    # ------------------------------------------------------------------
    # Final market revalidation
    # ------------------------------------------------------------------

    def _final_submission_revalidation(
        self,
        token: ExecutionValidationToken,
        request: dict,
    ) -> SubmissionRevalidation:
        symbol = str(request.get("symbol", "")).strip()

        if not symbol:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_SYMBOL_MISSING",
            )

        symbol_info = raw_mt5.symbol_info(symbol)  # type: ignore[attr-defined]

        if symbol_info is None:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_SYMBOL_INFO_UNAVAILABLE",
            )

        tick = raw_mt5.symbol_info_tick(symbol)  # type: ignore[attr-defined]

        if tick is None:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_TICK_UNAVAILABLE",
            )

        point = _safe_float(
            getattr(symbol_info, "point", 0.0)
        )

        if point <= 0.0:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_INVALID_POINT_SIZE",
            )

        bid = _safe_float(getattr(tick, "bid", 0.0))
        ask = _safe_float(getattr(tick, "ask", 0.0))

        if bid <= 0.0 or ask <= 0.0 or ask < bid:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_INVALID_BID_ASK",
            )

        # --------------------------------------------------------------
        # Quote freshness
        # --------------------------------------------------------------

        quote_age_ms = self._quote_age_ms(tick)

        max_quote_age_ms = _safe_float(
            settings_manager.get(
                "max_validation_token_age_ms",
                5000.0,
            ),
            5000.0,
        )

        max_quote_age_ms = max(100.0, max_quote_age_ms)

        if quote_age_ms > max_quote_age_ms:
            return SubmissionRevalidation(
                False,
                (
                    "REVALIDATION_TICK_STALE_"
                    f"{quote_age_ms:.0f}MS_MAX_{max_quote_age_ms:.0f}MS"
                ),
                quote_age_ms=quote_age_ms,
            )

        # --------------------------------------------------------------
        # Spread
        # --------------------------------------------------------------

        spread_points = (ask - bid) / point

        max_spread_points = _safe_float(
            settings_manager.get(
                "max_spread_points",
                350.0,
            ),
            350.0,
        )

        if spread_points > max_spread_points:
            return SubmissionRevalidation(
                False,
                (
                    "REVALIDATION_SPREAD_TOO_HIGH_"
                    f"{spread_points:.1f}_MAX_{max_spread_points:.1f}"
                ),
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
            )

        # --------------------------------------------------------------
        # Request type / market-side price
        # --------------------------------------------------------------

        order_type = _safe_int(request.get("type"), -1)

        if order_type == raw_mt5.ORDER_TYPE_BUY:
            current_entry = ask
            action_name = "BUY"

        elif order_type == raw_mt5.ORDER_TYPE_SELL:
            current_entry = bid
            action_name = "SELL"

        else:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_UNSUPPORTED_ORDER_TYPE",
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
            )

        if token.action and token.action.upper() != action_name:
            return SubmissionRevalidation(
                False,
                "TOKEN_ACTION_DOES_NOT_MATCH_REQUEST",
                current_entry_price=current_entry,
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
            )

        # --------------------------------------------------------------
        # Price drift
        # --------------------------------------------------------------

        validated_price = _safe_float(
            request.get("price"),
            0.0,
        )

        if validated_price <= 0.0:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_INVALID_REQUEST_PRICE",
                current_entry_price=current_entry,
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
            )

        price_drift_points = (
            abs(current_entry - validated_price) / point
        )

        max_price_drift_points = _safe_float(
            settings_manager.get(
                "max_price_drift_points",
                50.0,
            ),
            50.0,
        )

        if price_drift_points > max_price_drift_points:
            return SubmissionRevalidation(
                False,
                (
                    "REVALIDATION_PRICE_DRIFT_"
                    f"{price_drift_points:.1f}_MAX_"
                    f"{max_price_drift_points:.1f}"
                ),
                current_entry_price=current_entry,
                spread_points=spread_points,
                quote_age_ms=quote_age_ms,
                price_drift_points=price_drift_points,
            )

        # --------------------------------------------------------------
        # Volume
        # --------------------------------------------------------------

        volume = _safe_float(request.get("volume"))

        vol_min = _safe_float(
            getattr(symbol_info, "volume_min", 0.0)
        )

        vol_max = _safe_float(
            getattr(symbol_info, "volume_max", 0.0)
        )

        vol_step = _safe_float(
            getattr(symbol_info, "volume_step", 0.0)
        )

        if volume <= 0.0:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_INVALID_VOLUME",
                current_entry,
                spread_points,
                quote_age_ms,
                price_drift_points,
            )

        if vol_min > 0.0 and volume + 1e-12 < vol_min:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_VOLUME_BELOW_MINIMUM",
                current_entry,
                spread_points,
                quote_age_ms,
                price_drift_points,
            )

        if vol_max > 0.0 and volume - 1e-12 > vol_max:
            return SubmissionRevalidation(
                False,
                "REVALIDATION_VOLUME_ABOVE_MAXIMUM",
                current_entry,
                spread_points,
                quote_age_ms,
                price_drift_points,
            )

        if vol_step > 0.0 and vol_min >= 0.0:
            steps = (volume - vol_min) / vol_step
            nearest_steps = round(steps)

            if abs(steps - nearest_steps) > 1e-5:
                return SubmissionRevalidation(
                    False,
                    "REVALIDATION_VOLUME_STEP_INVALID",
                    current_entry,
                    spread_points,
                    quote_age_ms,
                    price_drift_points,
                )

        # --------------------------------------------------------------
        # SL / TP geometry against CURRENT executable price
        # --------------------------------------------------------------

        sl = _safe_float(request.get("sl"))
        tp = _safe_float(request.get("tp"))

        if action_name == "BUY":
            if sl != 0.0 and sl >= current_entry:
                return SubmissionRevalidation(
                    False,
                    "REVALIDATION_BUY_SL_INVALID",
                    current_entry,
                    spread_points,
                    quote_age_ms,
                    price_drift_points,
                )

            if tp != 0.0 and tp <= current_entry:
                return SubmissionRevalidation(
                    False,
                    "REVALIDATION_BUY_TP_INVALID",
                    current_entry,
                    spread_points,
                    quote_age_ms,
                    price_drift_points,
                )

        else:
            if sl != 0.0 and sl <= current_entry:
                return SubmissionRevalidation(
                    False,
                    "REVALIDATION_SELL_SL_INVALID",
                    current_entry,
                    spread_points,
                    quote_age_ms,
                    price_drift_points,
                )

            if tp != 0.0 and tp >= current_entry:
                return SubmissionRevalidation(
                    False,
                    "REVALIDATION_SELL_TP_INVALID",
                    current_entry,
                    spread_points,
                    quote_age_ms,
                    price_drift_points,
                )

        # --------------------------------------------------------------
        # Broker minimum stop distance
        # --------------------------------------------------------------

        stops_level = _safe_float(
            getattr(symbol_info, "trade_stops_level", 0.0)
        )

        min_stop_distance = max(
            0.0,
            stops_level * point,
        )

        if min_stop_distance > 0.0:
            if sl != 0.0:
                sl_distance = abs(current_entry - sl)

                if sl_distance + (point * 0.01) < min_stop_distance:
                    return SubmissionRevalidation(
                        False,
                        "REVALIDATION_SL_BELOW_STOPS_LEVEL",
                        current_entry,
                        spread_points,
                        quote_age_ms,
                        price_drift_points,
                    )

            if tp != 0.0:
                tp_distance = abs(current_entry - tp)

                if tp_distance + (point * 0.01) < min_stop_distance:
                    return SubmissionRevalidation(
                        False,
                        "REVALIDATION_TP_BELOW_STOPS_LEVEL",
                        current_entry,
                        spread_points,
                        quote_age_ms,
                        price_drift_points,
                    )

        return SubmissionRevalidation(
            True,
            "REVALIDATED",
            current_entry_price=current_entry,
            spread_points=spread_points,
            quote_age_ms=quote_age_ms,
            price_drift_points=price_drift_points,
        )

    # ------------------------------------------------------------------

    def _quote_age_ms(self, tick: Any) -> float:
        now_ms = time.time() * 1000.0

        time_msc = getattr(tick, "time_msc", None)

        try:
            value = float(time_msc)

            if math.isfinite(value) and value > 0:
                return max(0.0, now_ms - value)

        except (TypeError, ValueError):
            pass

        time_sec = getattr(tick, "time", None)

        try:
            value = float(time_sec)

            if math.isfinite(value) and value > 0:
                return max(
                    0.0,
                    now_ms - (value * 1000.0),
                )

        except (TypeError, ValueError):
            pass

        return float("inf")

    def _is_emergency_halted(self) -> bool:
        return bool(
            self._emergency_halt_event is not None
            and self._emergency_halt_event.is_set()
        )