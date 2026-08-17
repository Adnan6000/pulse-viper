# utils/mt5_gateway.py
import threading
import MetaTrader5 as _raw_mt5
from typing import Optional, Any

raw_mt5: Any = _raw_mt5

# Reentrant lock for all broker interactions
_gateway_lock = threading.RLock()

# Shared reference to the emergency halt event
_emergency_halt_event: Optional[threading.Event] = None

def set_emergency_halt_event(event: threading.Event):
    global _emergency_halt_event
    _emergency_halt_event = event

class MT5ReadGateway:
    """Read-only gateway exposing only safe query methods and constants from MetaTrader 5."""
    
    # Expose required MT5 Constants
    TIMEFRAME_M1 = raw_mt5.TIMEFRAME_M1
    TIMEFRAME_M5 = raw_mt5.TIMEFRAME_M5
    TIMEFRAME_M15 = raw_mt5.TIMEFRAME_M15
    TIMEFRAME_M30 = raw_mt5.TIMEFRAME_M30
    TIMEFRAME_H1 = raw_mt5.TIMEFRAME_H1
    TIMEFRAME_H4 = raw_mt5.TIMEFRAME_H4
    TIMEFRAME_D1 = raw_mt5.TIMEFRAME_D1
    
    ORDER_TYPE_BUY = raw_mt5.ORDER_TYPE_BUY
    ORDER_TYPE_SELL = raw_mt5.ORDER_TYPE_SELL
    
    TRADE_ACTION_DEAL = raw_mt5.TRADE_ACTION_DEAL
    
    DEAL_ENTRY_IN = raw_mt5.DEAL_ENTRY_IN
    DEAL_ENTRY_OUT = raw_mt5.DEAL_ENTRY_OUT
    DEAL_ENTRY_INOUT = raw_mt5.DEAL_ENTRY_INOUT
    
    POSITION_TYPE_BUY = raw_mt5.POSITION_TYPE_BUY
    POSITION_TYPE_SELL = raw_mt5.POSITION_TYPE_SELL
    
    ORDER_TIME_GTC = raw_mt5.ORDER_TIME_GTC
    
    ORDER_FILLING_FOK = raw_mt5.ORDER_FILLING_FOK
    ORDER_FILLING_IOC = raw_mt5.ORDER_FILLING_IOC
    ORDER_FILLING_RETURN = raw_mt5.ORDER_FILLING_RETURN
    
    TRADE_RETCODE_DONE = raw_mt5.TRADE_RETCODE_DONE
    
    DEAL_REASON_SL = raw_mt5.DEAL_REASON_SL
    DEAL_REASON_TP = raw_mt5.DEAL_REASON_TP

    DEAL_TYPE_BUY = raw_mt5.DEAL_TYPE_BUY
    DEAL_TYPE_SELL = raw_mt5.DEAL_TYPE_SELL

    def initialize(self, *args, **kwargs) -> bool:
        with _gateway_lock:
            return raw_mt5.initialize(*args, **kwargs)

    def shutdown(self) -> None:
        with _gateway_lock:
            raw_mt5.shutdown()

    def symbol_select(self, symbol: str, select: bool) -> bool:
        with _gateway_lock:
            return raw_mt5.symbol_select(symbol, select)

    def account_info(self) -> Any:
        with _gateway_lock:
            return raw_mt5.account_info()

    def terminal_info(self) -> Any:
        with _gateway_lock:
            return raw_mt5.terminal_info()

    def symbol_info(self, symbol: str) -> Any:
        with _gateway_lock:
            return raw_mt5.symbol_info(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        with _gateway_lock:
            return raw_mt5.symbol_info_tick(symbol)

    def positions_get(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.positions_get(*args, **kwargs)

    def orders_get(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.orders_get(*args, **kwargs)

    def history_deals_get(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.history_deals_get(*args, **kwargs)

    def history_orders_get(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.history_orders_get(*args, **kwargs)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def copy_rates_from(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_rates_from(*args, **kwargs)

    def copy_ticks_from(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_ticks_from(*args, **kwargs)

    def copy_ticks_range(self, *args, **kwargs) -> Any:
        with _gateway_lock:
            return raw_mt5.copy_ticks_range(*args, **kwargs)

    def order_calc_margin(self, action: int, symbol: str, volume: float, price: float) -> Any:
        with _gateway_lock:
            return raw_mt5.order_calc_margin(action, symbol, volume, price)

    def order_calc_profit(self, action: int, symbol: str, volume: float, price_open: float, price_close: float) -> Any:
        with _gateway_lock:
            return raw_mt5.order_calc_profit(action, symbol, volume, price_open, price_close)

    def symbols_get(self, group: str = "*") -> Any:
        with _gateway_lock:
            return raw_mt5.symbols_get(group)

    def version(self) -> Any:
        with _gateway_lock:
            return raw_mt5.version()

    def __getattr__(self, name: str) -> Any:
        # Enforce that no order sending methods or raw modules are reachable
        if name in ("order_send", "raw_mt5", "MetaTrader5"):
            raise AttributeError(f"MT5Gateway: execution capability '{name}' is restricted.")
        
        value = getattr(raw_mt5, name, None)
        if value is None:
            raise AttributeError(f"MetaTrader5 attribute '{name}' not found")
        if callable(value):
            raise AttributeError(f"MT5 function {name!r} has no synchronized gateway wrapper")
        return value

    def execution_transaction(self):
        class _ExecCtx:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, exc_type, exc, tb):
                return False
            def order_send(self_inner, request: dict):
                if _emergency_halt_event is not None and _emergency_halt_event.is_set():
                    class Rejected:
                        def __init__(self):
                            self.retcode = 10014
                            self.comment = "REJECTED_EMERGENCY_HALT"
                            self.order = 0
                            self.volume = 0.0
                            self.price = 0.0
                    return Rejected()
                from core.execution_service import MT5ExecutionService, canonical_request_hash
                from core.execution_token import validation_token_store
                from utils.settings_manager import settings_manager
                fp = canonical_request_hash(request)
                token = validation_token_store.consume_by_fingerprint(fp)
                if token is None:
                    if settings_manager.get("allow_untokenized_orders", False):
                        with _gateway_lock:
                            return raw_mt5.order_send(request)
                    else:
                        class Rejected:
                            def __init__(self):
                                self.retcode = 10014
                                self.comment = "TOKEN_UNKNOWN_OR_ALREADY_USED"
                                self.order = 0
                                self.volume = 0.0
                                self.price = 0.0
                        return Rejected()
                svc = MT5ExecutionService(_emergency_halt_event)  # type: ignore
                return svc.submit_order(token, request)
        return _ExecCtx()

# Global singleton instances for read access
mt5_read_gateway = MT5ReadGateway()
mt5_gateway = mt5_read_gateway  # For backwards compatibility with other files
