# core/emergency_exit_controller.py
import os
import json
import time
import logging
import threading
from enum import Enum
from typing import List, Dict, Any
import MetaTrader5 as raw_mt5

class EmergencyScope(str, Enum):
    ENGINE_ONLY = "ENGINE_ONLY"
    ACCOUNT_WIDE = "ACCOUNT_WIDE"

HALT_STATE_FILE = "config/emergency_halt.json"

class EmergencyExitController:
    """Manages emergency position/order closure and ensures broker-level reconciliation."""
    def __init__(self, emergency_halt_event: threading.Event):
        self.logger = logging.getLogger("PulseViper.EmergencyExitController")
        self._emergency_halt_event = emergency_halt_event
        self._lock = threading.Lock()
        
        # Ensure config dir exists
        os.makedirs("config", exist_ok=True)
        
        # Restore state on startup
        if os.path.exists(HALT_STATE_FILE):
            try:
                with open(HALT_STATE_FILE, "r") as f:
                    data = json.load(f)
                    if data.get("halt_active", False):
                        self._emergency_halt_event.set()
                        self.logger.warning("🚨 Restored active emergency halt status from persistent storage.")
            except Exception as e:
                self.logger.error(f"Failed to restore emergency halt state: {e}")

    def is_halted(self) -> bool:
        return self._emergency_halt_event.is_set()

    def persist_halt(self, active: bool) -> None:
        """Persist the emergency halt status to prevent resume on reboot."""
        with self._lock:
            try:
                with open(HALT_STATE_FILE, "w") as f:
                    json.dump({"halt_active": active, "timestamp": time.time()}, f)
            except Exception as e:
                self.logger.error(f"Failed to persist emergency halt state: {e}")

    def release_halt(self) -> None:
        """Privileged command to clear the emergency halt."""
        self._emergency_halt_event.clear()
        self.persist_halt(False)
        self.logger.warning("🔓 Emergency halt successfully released.")

    def emergency_close(self, scope: EmergencyScope, magic_number: int, reconciliation_timeout: float = 15.0, reconciliation_interval: float = 0.5) -> Dict[str, Any]:
        """
        Executes emergency position closure and pending order cancellation.
        Ensures broker reconciliation is confirmed before returning.
        """
        # 1. Trigger the halt event immediately
        self._emergency_halt_event.set()
        self.persist_halt(True)
        
        self.logger.warning(f"🚨 EMERGENCY PANIC CLOSE TRIGGERED: scope={scope}, magic={magic_number}")
        
        # 2. Cancel pending orders
        target_orders = self._find_target_orders(scope, magic_number)
        self._cancel_pending_orders(target_orders)
        
        # 3. Close open positions
        target_positions = self._find_target_positions(scope, magic_number)
        self._close_positions(target_positions, magic_number)
        
        # 4. Broker reconciliation loop
        deadline = time.monotonic() + reconciliation_timeout
        reconciled = False
        remaining_orders = []
        remaining_positions = []
        
        while time.monotonic() < deadline:
            remaining_orders = self._find_target_orders(scope, magic_number)
            remaining_positions = self._find_target_positions(scope, magic_number)
            
            if not remaining_orders and not remaining_positions:
                reconciled = True
                break
                
            # Retry any remaining closes/cancels
            self._cancel_pending_orders(remaining_orders)
            self._close_positions(remaining_positions, magic_number)
            
            time.sleep(reconciliation_interval)
            
        if reconciled:
            self.logger.info("🚨 Emergency exit successfully RECONCILED. All target positions/orders are closed.")
            return {
                "completed": True,
                "status": "RECONCILED",
                "halt_active": True,
                "closed_count": len(target_positions)
            }
        else:
            self.logger.error(f"🚨 Emergency exit PARTIAL FAILURE. Unclosed: positions={len(remaining_positions)}, orders={len(remaining_orders)}")
            return {
                "completed": False,
                "status": "PARTIAL_FAILURE",
                "halt_active": True,
                "remaining_positions": [getattr(p, 'ticket', p) for p in remaining_positions],
                "remaining_orders": [getattr(o, 'ticket', o) for o in remaining_orders]
            }

    def _find_target_orders(self, scope: EmergencyScope, magic_number: int) -> List[Any]:
        orders = raw_mt5.orders_get()  # type: ignore[attr-defined]
        if not orders:
            return []
        if scope == EmergencyScope.ENGINE_ONLY:
            return [o for o in orders if getattr(o, 'magic', 0) == magic_number]
        return list(orders)

    def _find_target_positions(self, scope: EmergencyScope, magic_number: int) -> List[Any]:
        positions = raw_mt5.positions_get()  # type: ignore[attr-defined]
        if not positions:
            return []
        if scope == EmergencyScope.ENGINE_ONLY:
            return [p for p in positions if getattr(p, 'magic', 0) == magic_number]
        return list(positions)

    def _cancel_pending_orders(self, orders: List[Any]) -> None:
        for order in orders:
            ticket = getattr(order, 'ticket', None)
            if ticket is None:
                continue
            request = {
                "action": raw_mt5.TRADE_ACTION_REMOVE,
                "order": ticket
            }
            res = raw_mt5.order_send(request)  # type: ignore[attr-defined]
            if res and res.retcode == raw_mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"Successfully cancelled pending order #{ticket}")
            else:
                self.logger.error(f"Failed to cancel pending order #{ticket}: {getattr(res, 'comment', 'None')}")

    def _close_positions(self, positions: List[Any], magic_number: int) -> None:
        for pos in positions:
            ticket = getattr(pos, 'ticket', None)
            symbol = getattr(pos, 'symbol', None)
            pos_type = getattr(pos, 'type', None)
            volume = getattr(pos, 'volume', None)
            
            if ticket is None or symbol is None or pos_type is None or volume is None:
                continue
                
            tick = raw_mt5.symbol_info_tick(symbol)  # type: ignore[attr-defined]
            if not tick:
                self.logger.error(f"Could not get tick for {symbol} to close position #{ticket}")
                continue
                
            order_type = raw_mt5.ORDER_TYPE_SELL if pos_type == raw_mt5.POSITION_TYPE_BUY else raw_mt5.ORDER_TYPE_BUY
            price = tick.bid if pos_type == raw_mt5.POSITION_TYPE_BUY else tick.ask
            
            request = {
                "action": raw_mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": magic_number,
            }
            res = raw_mt5.order_send(request)  # type: ignore[attr-defined]
            if res and res.retcode == raw_mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"Successfully closed position #{ticket}")
            else:
                self.logger.error(f"Failed to close position #{ticket}: {getattr(res, 'comment', 'None')}")
