# utils/mt5_gateway.py

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import MetaTrader5 as _raw_mt5


logger = logging.getLogger("PulseViper.MT5Gateway")

raw_mt5: Any = _raw_mt5


# ----------------------------------------------------------------------
# Global broker synchronization
# ----------------------------------------------------------------------

_gateway_lock = threading.RLock()

_emergency_halt_event: Optional[threading.Event] = None


def set_emergency_halt_event(
    event: Optional[threading.Event],
) -> None:
    global _emergency_halt_event
    _emergency_halt_event = event


# ----------------------------------------------------------------------
# Rejection result
# ----------------------------------------------------------------------

class _RejectedMT5Result:
    def __init__(
        self,
        comment: str,
        retcode: int = 10014,
    ):
        self.retcode = retcode
        self.comment = comment
        self.order = 0
        self.deal = 0
        self.volume = 0.0
        self.price = 0.0
        self.request_id = 0


# ----------------------------------------------------------------------
# Read-only MT5 gateway
# ----------------------------------------------------------------------

class MT5ReadGateway:
    """
    Synchronized read-only facade over MetaTrader5.

    NEW position creation is possible ONLY through:
        execution_transaction()

    Existing-position risk reduction is possible ONLY through:
        management_transaction()

    Direct mt5.order_send() access remains blocked.
    """

    # ------------------------------------------------------------------
    # Timeframes
    # ------------------------------------------------------------------

    TIMEFRAME_M1 = raw_mt5.TIMEFRAME_M1
    TIMEFRAME_M5 = raw_mt5.TIMEFRAME_M5
    TIMEFRAME_M15 = raw_mt5.TIMEFRAME_M15
    TIMEFRAME_M30 = raw_mt5.TIMEFRAME_M30
    TIMEFRAME_H1 = raw_mt5.TIMEFRAME_H1
    TIMEFRAME_H4 = raw_mt5.TIMEFRAME_H4
    TIMEFRAME_D1 = raw_mt5.TIMEFRAME_D1

    # ------------------------------------------------------------------
    # Order types
    # ------------------------------------------------------------------

    ORDER_TYPE_BUY = raw_mt5.ORDER_TYPE_BUY
    ORDER_TYPE_SELL = raw_mt5.ORDER_TYPE_SELL

    # ------------------------------------------------------------------
    # Trade actions
    # ------------------------------------------------------------------

    TRADE_ACTION_DEAL = raw_mt5.TRADE_ACTION_DEAL
    TRADE_ACTION_SLTP = raw_mt5.TRADE_ACTION_SLTP
    TRADE_ACTION_CLOSE_BY = raw_mt5.TRADE_ACTION_CLOSE_BY

    # ------------------------------------------------------------------
    # Deal entry
    # ------------------------------------------------------------------

    DEAL_ENTRY_IN = raw_mt5.DEAL_ENTRY_IN
    DEAL_ENTRY_OUT = raw_mt5.DEAL_ENTRY_OUT
    DEAL_ENTRY_INOUT = raw_mt5.DEAL_ENTRY_INOUT

    # ------------------------------------------------------------------
    # Position types
    # ------------------------------------------------------------------

    POSITION_TYPE_BUY = raw_mt5.POSITION_TYPE_BUY
    POSITION_TYPE_SELL = raw_mt5.POSITION_TYPE_SELL

    # ------------------------------------------------------------------
    # Time / fill
    # ------------------------------------------------------------------

    ORDER_TIME_GTC = raw_mt5.ORDER_TIME_GTC

    ORDER_FILLING_FOK = raw_mt5.ORDER_FILLING_FOK
    ORDER_FILLING_IOC = raw_mt5.ORDER_FILLING_IOC
    ORDER_FILLING_RETURN = raw_mt5.ORDER_FILLING_RETURN

    # ------------------------------------------------------------------
    # Retcodes
    # ------------------------------------------------------------------

    TRADE_RETCODE_DONE = raw_mt5.TRADE_RETCODE_DONE

    TRADE_RETCODE_DONE_PARTIAL = getattr(
        raw_mt5,
        "TRADE_RETCODE_DONE_PARTIAL",
        10010,
    )

    TRADE_RETCODE_PLACED = getattr(
        raw_mt5,
        "TRADE_RETCODE_PLACED",
        10008,
    )

    TRADE_RETCODE_INVALID_FILL = getattr(
        raw_mt5,
        "TRADE_RETCODE_INVALID_FILL",
        10030,
    )

    # ------------------------------------------------------------------
    # Deal reason
    # ------------------------------------------------------------------

    DEAL_REASON_SL = raw_mt5.DEAL_REASON_SL
    DEAL_REASON_TP = raw_mt5.DEAL_REASON_TP

    DEAL_TYPE_BUY = raw_mt5.DEAL_TYPE_BUY
    DEAL_TYPE_SELL = raw_mt5.DEAL_TYPE_SELL

    # ------------------------------------------------------------------
    # Standard synchronized read operations
    # ------------------------------------------------------------------

    def initialize(self, *args, **kwargs) -> bool:
        with _gateway_lock:
            return raw_mt5.initialize(*args, **kwargs)

    def shutdown(self) -> None:
        with _gateway_lock:
            raw_mt5.shutdown()

    def symbol_select(
        self,
        symbol: str,
        select: bool,
    ) -> bool:
        with _gateway_lock:
            return raw_mt5.symbol_select(
                symbol,
                select,
            )

    def account_info(self) -> Any:
        with _gateway_lock:
            return raw_mt5.account_info()

    def terminal_info(self) -> Any:
        with _gateway_lock:
            return raw_mt5.terminal_info()

    def symbol_info(
        self,
        symbol: str,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.symbol_info(symbol)

    def symbol_info_tick(
        self,
        symbol: str,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.symbol_info_tick(symbol)

    def positions_get(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.positions_get(
                *args,
                **kwargs,
            )

    def orders_get(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.orders_get(
                *args,
                **kwargs,
            )

    def history_deals_get(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.history_deals_get(
                *args,
                **kwargs,
            )

    def history_orders_get(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.history_orders_get(
                *args,
                **kwargs,
            )

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_rates_from_pos(
                symbol,
                timeframe,
                start_pos,
                count,
            )

    def copy_rates_from(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_rates_from(
                *args,
                **kwargs,
            )

    def copy_ticks_from(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_ticks_from(
                *args,
                **kwargs,
            )

    def copy_ticks_range(
        self,
        *args,
        **kwargs,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_ticks_range(
                *args,
                **kwargs,
            )

    def order_calc_margin(
        self,
        action: int,
        symbol: str,
        volume: float,
        price: float,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.order_calc_margin(
                action,
                symbol,
                volume,
                price,
            )

    def order_calc_profit(
        self,
        action: int,
        symbol: str,
        volume: float,
        price_open: float,
        price_close: float,
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.order_calc_profit(
                action,
                symbol,
                volume,
                price_open,
                price_close,
            )

    def symbols_get(
        self,
        group: str = "*",
    ) -> Any:
        with _gateway_lock:
            return raw_mt5.symbols_get(group)

    def version(self) -> Any:
        with _gateway_lock:
            return raw_mt5.version()

    # ------------------------------------------------------------------
    # Restricted attribute access
    # ------------------------------------------------------------------

    def __getattr__(
        self,
        name: str,
    ) -> Any:
        if name in {
            "order_send",
            "raw_mt5",
            "MetaTrader5",
        }:
            raise AttributeError(
                "MT5Gateway: execution capability "
                f"{name!r} is restricted."
            )

        value = getattr(
            raw_mt5,
            name,
            None,
        )

        if value is None:
            raise AttributeError(
                f"MetaTrader5 attribute {name!r} not found"
            )

        if callable(value):
            raise AttributeError(
                f"MT5 function {name!r} has no "
                "synchronized gateway wrapper"
            )

        return value

    # ------------------------------------------------------------------
    # NEW POSITION EXECUTION
    # ------------------------------------------------------------------

    def execution_transaction(self):
        """
        Privileged transaction for creating a NEW position.

        Rules:
        - Requires a valid one-time validation token.
        - Claims the token exactly once.
        - Request fingerprint cannot change inside the transaction.
        - Maximum 3 submission attempts.
        - Retry is allowed ONLY after MT5 reports INVALID_FILL.
        - Successful/placed requests cannot be submitted twice.
        """

        gateway = self

        class _ExecutionContext:
            def __init__(self):
                self._claimed_token = None
                self._fingerprint = None
                self._attempts = 0
                self._completed = False
                self._last_retcode = None
                self._entered = False

            def __enter__(self):
                _gateway_lock.acquire()
                self._entered = True
                return self

            def __exit__(
                self,
                exc_type,
                exc,
                tb,
            ):
                if self._entered:
                    self._entered = False
                    _gateway_lock.release()

                return False

            def order_send(
                self,
                request: dict,
            ):
                if not self._entered:
                    return _RejectedMT5Result(
                        "EXECUTION_CONTEXT_NOT_ENTERED"
                    )

                if (
                    _emergency_halt_event is not None
                    and _emergency_halt_event.is_set()
                ):
                    return _RejectedMT5Result(
                        "REJECTED_EMERGENCY_HALT"
                    )

                if not isinstance(request, dict):
                    return _RejectedMT5Result(
                        "INVALID_EXECUTION_REQUEST"
                    )

                from core.execution_service import (
                    MT5ExecutionService,
                    canonical_request_hash,
                )
                from core.execution_token import (
                    validation_token_store,
                )

                fingerprint = canonical_request_hash(
                    request
                )

                # ------------------------------------------------------
                # First submission claims the token.
                # ------------------------------------------------------

                if self._claimed_token is None:
                    token = (
                        validation_token_store
                        .consume_by_fingerprint(
                            fingerprint
                        )
                    )

                    if token is None:
                        # Production path is fail closed.
                        #
                        # allow_untokenized_orders is intentionally NOT
                        # honored here. A hidden bypass defeats the entire
                        # validation boundary.
                        return _RejectedMT5Result(
                            "TOKEN_UNKNOWN_EXPIRED_OR_ALREADY_USED"
                        )

                    self._claimed_token = token
                    self._fingerprint = fingerprint

                # ------------------------------------------------------
                # Request mutation detection
                # ------------------------------------------------------

                elif fingerprint != self._fingerprint:
                    return _RejectedMT5Result(
                        "EXECUTION_REQUEST_MUTATED_AFTER_VALIDATION"
                    )

                if self._completed:
                    return _RejectedMT5Result(
                        "EXECUTION_TRANSACTION_ALREADY_COMPLETED"
                    )

                # ------------------------------------------------------
                # Retry protection
                # ------------------------------------------------------

                if self._attempts >= 3:
                    return _RejectedMT5Result(
                        "EXECUTION_RETRY_LIMIT_EXCEEDED"
                    )

                if self._attempts > 0:
                    if (
                        self._last_retcode
                        != gateway.TRADE_RETCODE_INVALID_FILL
                    ):
                        return _RejectedMT5Result(
                            "EXECUTION_RETRY_NOT_SAFE"
                        )

                self._attempts += 1

                service = MT5ExecutionService(
                    _emergency_halt_event
                )

                result = service.submit_claimed_order(
                    self._claimed_token,
                    request,
                )

                self._last_retcode = getattr(
                    result,
                    "retcode",
                    None,
                )

                terminal_success_codes = {
                    gateway.TRADE_RETCODE_DONE,
                    gateway.TRADE_RETCODE_DONE_PARTIAL,
                    gateway.TRADE_RETCODE_PLACED,
                }

                if self._last_retcode in terminal_success_codes:
                    self._completed = True

                return result

        return _ExecutionContext()

    # ------------------------------------------------------------------
    # EXISTING POSITION MANAGEMENT
    # ------------------------------------------------------------------

    def management_transaction(self):
        """
        Privileged transaction for RISK-REDUCING management of positions that
        already exist at the broker.

        Allowed:
        - SL/TP modification for an existing position
        - partial/complete close of an existing position
        - CLOSE_BY between opposite positions

        Blocked:
        - opening any new DEAL without an existing position ticket
        - emergency hedge creation
        - worsening an existing protective SL

        Existing-position exits remain available during emergency halt.
        """

        gateway = self

        class _ManagementContext:
            def __init__(self):
                self._entered = False

            def __enter__(self):
                _gateway_lock.acquire()
                self._entered = True
                return self

            def __exit__(
                self,
                exc_type,
                exc,
                tb,
            ):
                if self._entered:
                    self._entered = False
                    _gateway_lock.release()

                return False

            def order_send(
                self,
                request: dict,
            ):
                if not self._entered:
                    return _RejectedMT5Result(
                        "MANAGEMENT_CONTEXT_NOT_ENTERED"
                    )

                if not isinstance(request, dict):
                    return _RejectedMT5Result(
                        "INVALID_MANAGEMENT_REQUEST"
                    )

                validation_error = (
                    self._validate_management_request(
                        request
                    )
                )

                if validation_error is not None:
                    return _RejectedMT5Result(
                        validation_error
                    )

                try:
                    return raw_mt5.order_send(request)

                except Exception as exc:
                    logger.exception(
                        "MT5 management order failed"
                    )

                    return _RejectedMT5Result(
                        "MANAGEMENT_ORDER_EXCEPTION_"
                        f"{type(exc).__name__}"
                    )

            # ----------------------------------------------------------

            def _validate_management_request(
                self,
                request: dict,
            ) -> Optional[str]:
                action = request.get("action")

                if action == gateway.TRADE_ACTION_SLTP:
                    return self._validate_sltp(request)

                if action == gateway.TRADE_ACTION_DEAL:
                    return self._validate_close_deal(
                        request
                    )

                if action == gateway.TRADE_ACTION_CLOSE_BY:
                    return self._validate_close_by(
                        request
                    )

                return (
                    "MANAGEMENT_ACTION_NOT_ALLOWED_"
                    f"{action}"
                )

            # ----------------------------------------------------------
            # SLTP
            # ----------------------------------------------------------

            def _validate_sltp(
                self,
                request: dict,
            ) -> Optional[str]:
                ticket = request.get("position")

                if not ticket:
                    return (
                        "MANAGEMENT_SLTP_POSITION_MISSING"
                    )

                positions = raw_mt5.positions_get(
                    ticket=int(ticket)
                )

                if not positions:
                    return (
                        "MANAGEMENT_POSITION_NOT_FOUND"
                    )

                position = positions[0]

                request_symbol = str(
                    request.get(
                        "symbol",
                        position.symbol,
                    )
                )

                if request_symbol != position.symbol:
                    return (
                        "MANAGEMENT_SYMBOL_MISMATCH"
                    )

                new_sl = self._safe_float(
                    request.get("sl", position.sl)
                )

                current_sl = self._safe_float(
                    getattr(position, "sl", 0.0)
                )

                position_type = getattr(
                    position,
                    "type",
                    None,
                )

                # If there is already an SL, never allow it to be moved
                # farther into risk.
                if (
                    current_sl > 0.0
                    and new_sl > 0.0
                ):
                    if (
                        position_type
                        == gateway.POSITION_TYPE_BUY
                        and new_sl < current_sl
                    ):
                        return (
                            "MANAGEMENT_BUY_SL_WORSENS_RISK"
                        )

                    if (
                        position_type
                        == gateway.POSITION_TYPE_SELL
                        and new_sl > current_sl
                    ):
                        return (
                            "MANAGEMENT_SELL_SL_WORSENS_RISK"
                        )

                # Prevent removal of an existing protective SL.
                if current_sl > 0.0 and new_sl <= 0.0:
                    return (
                        "MANAGEMENT_CANNOT_REMOVE_EXISTING_SL"
                    )

                return None

            # ----------------------------------------------------------
            # Partial / full closing DEAL
            # ----------------------------------------------------------

            def _validate_close_deal(
                self,
                request: dict,
            ) -> Optional[str]:
                ticket = request.get("position")

                if not ticket:
                    # DEAL without a position reference would create new risk.
                    return (
                        "MANAGEMENT_NEW_POSITION_DEAL_BLOCKED"
                    )

                positions = raw_mt5.positions_get(
                    ticket=int(ticket)
                )

                if not positions:
                    return (
                        "MANAGEMENT_POSITION_NOT_FOUND"
                    )

                position = positions[0]

                request_symbol = str(
                    request.get(
                        "symbol",
                        position.symbol,
                    )
                )

                if request_symbol != position.symbol:
                    return (
                        "MANAGEMENT_SYMBOL_MISMATCH"
                    )

                close_type = request.get("type")

                if (
                    position.type
                    == gateway.POSITION_TYPE_BUY
                ):
                    required_type = gateway.ORDER_TYPE_SELL

                elif (
                    position.type
                    == gateway.POSITION_TYPE_SELL
                ):
                    required_type = gateway.ORDER_TYPE_BUY

                else:
                    return (
                        "MANAGEMENT_UNKNOWN_POSITION_TYPE"
                    )

                if close_type != required_type:
                    return (
                        "MANAGEMENT_DEAL_DOES_NOT_REDUCE_POSITION"
                    )

                requested_volume = self._safe_float(
                    request.get("volume")
                )

                position_volume = self._safe_float(
                    getattr(position, "volume", 0.0)
                )

                if requested_volume <= 0.0:
                    return (
                        "MANAGEMENT_INVALID_CLOSE_VOLUME"
                    )

                if (
                    requested_volume
                    > position_volume + 1e-8
                ):
                    return (
                        "MANAGEMENT_CLOSE_VOLUME_EXCEEDS_POSITION"
                    )

                return None

            # ----------------------------------------------------------
            # CLOSE_BY
            # ----------------------------------------------------------

            def _validate_close_by(
                self,
                request: dict,
            ) -> Optional[str]:
                ticket_a = request.get("position")
                ticket_b = request.get("position_by")

                if not ticket_a or not ticket_b:
                    return (
                        "MANAGEMENT_CLOSE_BY_TICKETS_MISSING"
                    )

                pos_a_list = raw_mt5.positions_get(
                    ticket=int(ticket_a)
                )

                pos_b_list = raw_mt5.positions_get(
                    ticket=int(ticket_b)
                )

                if not pos_a_list or not pos_b_list:
                    return (
                        "MANAGEMENT_CLOSE_BY_POSITION_NOT_FOUND"
                    )

                pos_a = pos_a_list[0]
                pos_b = pos_b_list[0]

                if pos_a.symbol != pos_b.symbol:
                    return (
                        "MANAGEMENT_CLOSE_BY_SYMBOL_MISMATCH"
                    )

                if pos_a.type == pos_b.type:
                    return (
                        "MANAGEMENT_CLOSE_BY_REQUIRES_OPPOSITE_POSITIONS"
                    )

                return None

            @staticmethod
            def _safe_float(
                value: Any,
            ) -> float:
                try:
                    return float(value)
                except (
                    TypeError,
                    ValueError,
                ):
                    return 0.0

        return _ManagementContext()


# ----------------------------------------------------------------------
# Global singleton
# ----------------------------------------------------------------------

mt5_read_gateway = MT5ReadGateway()

# Backwards compatibility.
mt5_gateway = mt5_read_gateway