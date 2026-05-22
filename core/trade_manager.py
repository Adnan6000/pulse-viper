# core/trade_manager.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class TradePosition:
    def __init__(self, ticket_id: int, symbol: str, action: str, entry_price: float, 
                 volume: float, sl: float, tp: float, timestamp: datetime, magic: int = 123456):
        self.id = ticket_id
        self.symbol = symbol
        self.action = action  # "BUY" or "SELL"
        self.entry_price = entry_price
        self.volume = volume
        self.sl = sl
        self.tp = tp
        self.entry_time = timestamp
        self.magic = magic
        self.status = "OPEN"
        self.pnl = 0.0
        self.close_price = 0.0
        self.close_time = None
        self.close_reason = ""
        self.max_profit_points = 0.0
        self.initial_sl_dist = abs(entry_price - sl) if sl != 0 else 0.0
        
        # Sibling splitting features
        self.tp1 = tp
        self.tp2 = tp
        self.sibling_id = None
        self.is_tp1_target = False
        self.is_tp2_target = False

class BaseTradeManager:
    def __init__(self, config):
        self.config = config
        self.positions: Dict[int, TradePosition] = {}
        self.closed_positions: List[TradePosition] = []
        self.logger = logging.getLogger("PulseViper.TradeManager")
        self.daily_trade_count = 0
        self.last_trade_date = None

    def get_win_streak(self) -> int:
        """Count consecutive wins in closed positions"""
        streak = 0
        for pos in reversed(self.closed_positions):
            if pos.pnl > 0:
                streak += 1
            else:
                break
        return streak

    def get_capital(self) -> float:
        """Get capital for lot size calculations"""
        return getattr(self.config, 'INITIAL_BALANCE', 10000.0)

    def get_balance(self) -> float:
        """Get balance for lot size calculations"""
        return getattr(self.config, 'INITIAL_BALANCE', 10000.0)

    def _check_daily_trade_limit(self) -> bool:
        """Enforce the configurable daily trade limit from settings"""
        from utils.settings_manager import settings_manager
        if settings_manager.get("hedging_mode", False):
            return True
            
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.daily_trade_count = 0
            self.last_trade_date = today
        
        max_daily = settings_manager.get("max_daily_trades", 3)  # default: 3 trades per day
        if self.daily_trade_count >= max_daily:
            self.logger.warning(f"Daily trade limit ({max_daily} trades/day) reached. Entry blocked.")
            return False
        return True

    def calculate_lot_size(self, symbol: str, sl_price: float, entry_price: float, balance: Optional[float] = None) -> float:
        """
        Dynamically calculate standard contract size based on risk percent of balance/equity.
        Formula: Lot Size = (Capital * Risk%) / (SL points * Tick Value)
        """
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"Failed to get symbol info for {symbol}")
                return 0.01

            from utils.settings_manager import settings_manager
            risk_percent = settings_manager.get("risk_percent", getattr(self.config, 'RISK_PERCENT', 1.0))
            
            # Apply win streak multiplier if streak >= 3
            streak = self.get_win_streak()
            if streak >= 3:
                risk_percent *= 1.25
                self.logger.info(f"🔥 Win streak is {streak}! Risk scaled by 1.25x to {risk_percent:.2f}%")

            compounding = settings_manager.get("compounding_mode", False)
            if balance is not None:
                capital = balance
            elif compounding:
                capital = self.get_capital()  # Use equity when compounding is enabled
            else:
                capital = self.get_balance()  # Use balance when compounding is disabled
                
            risk_amount = capital * (risk_percent / 100.0)
            
            # Retrieve the broker profile for the active symbol and enforce a minimum risk amount
            try:
                from utils.symbol_manager import symbol_manager
                profile = symbol_manager.get_broker_profile(symbol)
                is_cent = profile.get("is_cent_account", False)
                min_risk = 300.0 if is_cent else 3.0
                if risk_amount < min_risk:
                    self.logger.info(f"Capital risk of {risk_amount:.2f} is below the minimum allowed risk of {min_risk:.2f}. Forcing risk to {min_risk:.2f}.")
                    risk_amount = min_risk
            except Exception as e:
                self.logger.error(f"Error checking broker profile for minimum risk: {e}")
            
            # SL distance in price
            price_distance = abs(entry_price - sl_price)
            if price_distance == 0:
                return symbol_info.volume_min if symbol_info else 0.01

            # Calculate sl in points
            sl_points = price_distance / symbol_info.point
            
            # Value of 1 point for 1 standard lot
            point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
            
            if sl_points * point_value == 0:
                return symbol_info.volume_min if symbol_info else 0.01
                
            raw_lots = risk_amount / (sl_points * point_value)
            
            # Round to step
            vol_step = symbol_info.volume_step if (symbol_info and hasattr(symbol_info, 'volume_step')) else 0.01
            vol_min = symbol_info.volume_min if (symbol_info and hasattr(symbol_info, 'volume_min')) else 0.01
            vol_max = symbol_info.volume_max if (symbol_info and hasattr(symbol_info, 'volume_max')) else 100.0
            
            lots = round(raw_lots / vol_step) * vol_step
            min_allowed = max(0.01, vol_min)
            lots = max(min_allowed, min(vol_max, lots))
            
            return round(lots, 2)
        except Exception as e:
            self.logger.error(f"Error calculating lot size: {e}")
            return 0.01



class PaperTradeManager(BaseTradeManager):
    def __init__(self, config):
        super().__init__(config)
        self.virtual_balance = getattr(config, 'INITIAL_BALANCE', 10000.0)
        self.virtual_equity = self.virtual_balance
        self.simulated_ticket = 100000

    def get_capital(self) -> float:
        return self.virtual_equity

    def get_balance(self) -> float:
        return self.virtual_balance

    def open_position(self, symbol: str, action: str, entry_price: float, 
                      sl_price: float, tp1_price: Optional[float] = None, 
                      tp2_price: Optional[float] = None, tp_price: Optional[float] = None) -> Optional[TradePosition]:
        """Simulate opening a trade"""
        if tp1_price is None:
            tp1_price = tp_price
        if tp1_price is None:
            tp1_price = entry_price
        if tp2_price is None:
            tp2_price = tp1_price
            
        if not self._check_daily_trade_limit():
            return None
            
        symbol_info = mt5.symbol_info(symbol)
        volume_step = symbol_info.volume_step if symbol_info else 0.01
        volume_min = symbol_info.volume_min if symbol_info else 0.01
        
        lot_size = self.calculate_lot_size(symbol, sl_price, entry_price)
        
        # Check if we can split
        if lot_size >= 2 * volume_step:
            vol1 = round((lot_size / 2.0) / volume_step) * volume_step
            vol1 = round(vol1, 2)
            vol2 = round(lot_size - vol1, 2)
            if vol1 < volume_min or vol2 < volume_min:
                vol1 = lot_size
                vol2 = 0.0
        else:
            vol1 = lot_size
            vol2 = 0.0
            
        self.simulated_ticket += 1
        pos1 = TradePosition(
            ticket_id=self.simulated_ticket,
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            volume=vol1,
            sl=sl_price,
            tp=tp1_price,
            timestamp=datetime.now(),
            magic=999999
        )
        pos1.tp1 = tp1_price
        pos1.tp2 = tp2_price
        pos1.is_tp1_target = True if vol2 > 0 else False
        pos1.is_tp2_target = True if vol2 == 0 else False
        
        self.positions[pos1.id] = pos1
        self.daily_trade_count += 1
        self.logger.info(f"Opened simulated {action} Position 1 (Ticket #{pos1.id}) on {symbol} @ {entry_price:.2f} | Vol: {vol1:.2f} (SL: {sl_price:.2f}, TP1: {tp1_price:.2f})")
        
        if vol2 > 0:
            self.simulated_ticket += 1
            pos2 = TradePosition(
                ticket_id=self.simulated_ticket,
                symbol=symbol,
                action=action,
                entry_price=entry_price,
                volume=vol2,
                sl=sl_price,
                tp=tp2_price,
                timestamp=datetime.now(),
                magic=999999
            )
            pos2.tp1 = tp1_price
            pos2.tp2 = tp2_price
            pos2.is_tp2_target = True
            pos2.sibling_id = pos1.id
            pos1.sibling_id = pos2.id
            
            self.positions[pos2.id] = pos2
            self.logger.info(f"Opened simulated {action} Position 2 (Ticket #{pos2.id}) on {symbol} @ {entry_price:.2f} | Vol: {vol2:.2f} (SL: {sl_price:.2f}, TP2: {tp2_price:.2f})")
            
        return pos1

    def update_positions(self, symbol: str, bid: float, ask: float):
        """Update open simulated positions against current bid/ask and check SL/TP"""
        to_close = []
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return
            
        point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
        
        total_pnl = 0.0
        from utils.settings_manager import settings_manager
        break_even_enabled = settings_manager.get("break_even_enabled", True)
        trailing_stop_enabled = settings_manager.get("trailing_stop_enabled", True)

        for pos_id, pos in list(self.positions.items()):
            if pos.symbol != symbol:
                continue
                
            # Current price for closing/updating pnl
            current_price = bid if pos.action == "BUY" else ask
            
            # Point diff
            if pos.action == "BUY":
                pnl_points = (current_price - pos.entry_price) / symbol_info.point
            else:
                pnl_points = (pos.entry_price - current_price) / symbol_info.point
                
            pos.pnl = pnl_points * point_value * pos.volume
            total_pnl += pos.pnl
            
            # Track max profit in points for break-even/trailing logic
            pos.max_profit_points = max(pos.max_profit_points, pnl_points)

            # Time-based break-even movement (after 30 seconds if in profit)
            elapsed_seconds = (datetime.now() - pos.timestamp).total_seconds() if pos.timestamp else 0
            if break_even_enabled and elapsed_seconds >= 30.0 and pos.sl != pos.entry_price:
                is_favorable = (current_price > pos.entry_price) if pos.action == "BUY" else (current_price < pos.entry_price)
                if is_favorable:
                    pos.sl = pos.entry_price
                    self.logger.info(f"Simulated position #{pos.id} moved to Break-Even (30 seconds elapsed and in profit)")
            
            # Sibling closed BE movement
            if pos.sibling_id and pos.sibling_id not in self.positions:
                if pos.sl != pos.entry_price:
                    pos.sl = pos.entry_price
                    self.logger.info(f"Simulated position #{pos.id} moved to Break-Even (sibling #{pos.sibling_id} closed)")
            
            # Single position BE movement on TP1 hit
            elif not pos.sibling_id and pos.tp1 and pos.sl != pos.entry_price:
                reached_tp1 = (current_price >= pos.tp1) if pos.action == "BUY" else (current_price <= pos.tp1)
                if reached_tp1:
                    pos.sl = pos.entry_price
                    self.logger.info(f"Simulated single position #{pos.id} moved to Break-Even (reached TP1)")
            
            # Apply Trailing Stop or Break-Even logic
            elif trailing_stop_enabled and pos.initial_sl_dist > 0:
                if pos.action == "BUY":
                    new_sl = round(current_price - pos.initial_sl_dist, symbol_info.digits)
                    if new_sl > pos.sl:
                        pos.sl = new_sl
                        self.logger.info(f"Simulated position #{pos.id} trailed SL to {new_sl:.2f}")
                else:
                    new_sl = round(current_price + pos.initial_sl_dist, symbol_info.digits)
                    if pos.sl == 0 or new_sl < pos.sl:
                        pos.sl = new_sl
                        self.logger.info(f"Simulated position #{pos.id} trailed SL to {new_sl:.2f}")
            elif break_even_enabled and pos.sl != 0 and pos.sl != pos.entry_price:
                sl_distance_pts = pos.initial_sl_dist / symbol_info.point
                if pos.max_profit_points >= sl_distance_pts:
                    pos.sl = pos.entry_price
                    self.logger.info(f"Simulated position #{pos.id} moved to Break-Even (SL set to entry)")
                
            # Check SL/TP hit
            if pos.action == "BUY":
                if low_hit := (current_price <= pos.sl):
                    to_close.append((pos.id, pos.sl, "SL"))
                elif high_hit := (current_price >= pos.tp):
                    to_close.append((pos.id, pos.tp, "TP"))
            else:
                if high_hit := (current_price >= pos.sl):
                    to_close.append((pos.id, pos.sl, "SL"))
                elif low_hit := (current_price <= pos.tp):
                    to_close.append((pos.id, pos.tp, "TP"))

        # Close hit positions
        for pos_id, close_price, reason in to_close:
            self.close_position(pos_id, close_price, reason)
            
        self.virtual_equity = self.virtual_balance + total_pnl

    def close_position(self, pos_id: int, close_price: float, reason: str) -> Optional[TradePosition]:
        """Close simulated position"""
        pos = self.positions.pop(pos_id, None)
        if pos:
            symbol_info = mt5.symbol_info(pos.symbol)
            point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
            
            if pos.action == "BUY":
                pnl_points = (close_price - pos.entry_price) / symbol_info.point
            else:
                pnl_points = (pos.entry_price - close_price) / symbol_info.point
                
            pos.pnl = pnl_points * point_value * pos.volume
            pos.close_price = close_price
            pos.close_time = datetime.now()
            pos.close_reason = reason
            pos.status = "CLOSED"
            
            self.virtual_balance += pos.pnl
            self.virtual_equity = self.virtual_balance
            
            self.closed_positions.append(pos)
            self.logger.info(f"Closed simulated position #{pos.id} ({reason}) @ {close_price:.2f} | PnL: ${pos.pnl:.2f}")
            return pos
        return None


class LiveTradeManager(BaseTradeManager):
    def __init__(self, config):
        super().__init__(config)
        self.magic_number = 123456

    def get_win_streak(self) -> int:
        """Count consecutive wins from MT5 history deals plus local cache"""
        try:
            from datetime import datetime, timedelta
            start_date = datetime.now() - timedelta(days=7)
            end_date = datetime.now()
            
            # Request history deals
            deals = mt5.history_deals_get(start_date, end_date)
            if deals:
                # Filter by magic number and entry = DEAL_ENTRY_OUT (which is a close)
                # Sort by time
                our_deals = [d for d in deals if d.magic == self.magic_number and d.entry == mt5.DEAL_ENTRY_OUT]
                our_deals.sort(key=lambda x: x.time)
                
                # Check win streak
                streak = 0
                for deal in reversed(our_deals):
                    if deal.profit > 0:
                        streak += 1
                    else:
                        break
                return streak
        except Exception as e:
            self.logger.error(f"Error fetching win streak from MT5 history: {e}")
            
        return super().get_win_streak()

    def get_capital(self) -> float:
        account = mt5.account_info()
        if account:
            return account.equity
        return getattr(self.config, 'INITIAL_BALANCE', 10000.0)

    def get_balance(self) -> float:
        account = mt5.account_info()
        if account:
            return account.balance
        return getattr(self.config, 'INITIAL_BALANCE', 10000.0)

    def open_position(self, symbol: str, action: str, entry_price: float, 
                      sl_price: float, tp1_price: Optional[float] = None, 
                      tp2_price: Optional[float] = None, tp_price: Optional[float] = None) -> Optional[TradePosition]:
        """Open split positions on MT5"""
        if tp1_price is None:
            tp1_price = tp_price
        if tp1_price is None:
            tp1_price = entry_price
        if tp2_price is None:
            tp2_price = tp1_price
            
        if not self._check_daily_trade_limit():
            return None
            
        # Get account balance
        account = mt5.account_info()
        if account is None:
            self.logger.error("Failed to get MT5 account info")
            return None
            
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.logger.error(f"Failed to get symbol info for {symbol}")
            return None
            
        volume_step = symbol_info.volume_step
        volume_min = symbol_info.volume_min
        
        lot_size = self.calculate_lot_size(symbol, sl_price, entry_price)
        
        if lot_size >= 2 * volume_step:
            vol1 = round((lot_size / 2.0) / volume_step) * volume_step
            vol1 = round(vol1, 2)
            vol2 = round(lot_size - vol1, 2)
            if vol1 < volume_min or vol2 < volume_min:
                vol1 = lot_size
                vol2 = 0.0
        else:
            vol1 = lot_size
            vol2 = 0.0
            
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if action == "BUY" else tick.bid
        
        # Determine filling mode priority based on symbol info bitmask
        filling_modes = []
        mode_mask = getattr(symbol_info, 'filling_mode', 0)
        if mode_mask & 1:  # SYMBOL_FILLING_FOK
            filling_modes.append(mt5.ORDER_FILLING_FOK)
        if mode_mask & 2:  # SYMBOL_FILLING_IOC
            filling_modes.append(mt5.ORDER_FILLING_IOC)
        
        # Fallback modes in case bitmask doesn't resolve or order fails
        for m in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
            if m not in filling_modes:
                filling_modes.append(m)
        
        request1 = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol1,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp1_price,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "PulseViper EA TP1",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        result1 = None
        for fill_mode in filling_modes:
            request1["type_filling"] = fill_mode
            self.logger.info(f"Sending real {action} order 1 to MT5 for {symbol} | size: {vol1} | filling: {fill_mode}")
            result1 = mt5.order_send(request1)
            if result1 is not None and result1.retcode == mt5.TRADE_RETCODE_DONE:
                break
            else:
                err_code = result1.retcode if result1 else "None"
                err_comment = result1.comment if result1 else "None"
                self.logger.warning(f"Order 1 failed with filling {fill_mode}: code={err_code}, comment={err_comment}. Retrying next mode...")
        
        if result1 is None or result1.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"Failed to place real order 1: {result1.comment if result1 else 'None'}")
            return None
            
        # Record successful trade
        pos1 = TradePosition(
            ticket_id=result1.order,
            symbol=symbol,
            action=action,
            entry_price=result1.price,
            volume=result1.volume,
            sl=sl_price,
            tp=tp1_price,
            timestamp=datetime.now(),
            magic=self.magic_number
        )
        pos1.tp1 = tp1_price
        pos1.tp2 = tp2_price
        pos1.is_tp1_target = True if vol2 > 0 else False
        pos1.is_tp2_target = True if vol2 == 0 else False
        
        self.positions[pos1.id] = pos1
        self.daily_trade_count += 1
        self.logger.info(f"✅ Real trade 1 placed successfully. Ticket: {pos1.id} @ {pos1.entry_price:.2f}")
        
        if vol2 > 0:
            tick = mt5.symbol_info_tick(symbol)
            price = tick.ask if action == "BUY" else tick.bid
            
            request2 = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": vol2,
                "type": order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp2_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "PulseViper EA TP2",
                "type_time": mt5.ORDER_TIME_GTC,
            }
            
            result2 = None
            for fill_mode in filling_modes:
                request2["type_filling"] = fill_mode
                self.logger.info(f"Sending real {action} order 2 to MT5 for {symbol} | size: {vol2} | filling: {fill_mode}")
                result2 = mt5.order_send(request2)
                if result2 is not None and result2.retcode == mt5.TRADE_RETCODE_DONE:
                    break
                else:
                    err_code = result2.retcode if result2 else "None"
                    err_comment = result2.comment if result2 else "None"
                    self.logger.warning(f"Order 2 failed with filling {fill_mode}: code={err_code}, comment={err_comment}. Retrying next mode...")
            
            if result2 is not None and result2.retcode == mt5.TRADE_RETCODE_DONE:
                pos2 = TradePosition(
                    ticket_id=result2.order,
                    symbol=symbol,
                    action=action,
                    entry_price=result2.price,
                    volume=result2.volume,
                    sl=sl_price,
                    tp=tp2_price,
                    timestamp=datetime.now(),
                    magic=self.magic_number
                )
                pos2.tp1 = tp1_price
                pos2.tp2 = tp2_price
                pos2.is_tp2_target = True
                pos2.sibling_id = pos1.id
                pos1.sibling_id = pos2.id
                
                self.positions[pos2.id] = pos2
                self.logger.info(f"✅ Real trade 2 placed successfully. Ticket: {pos2.id} @ {pos2.entry_price:.2f}")
            else:
                self.logger.error(f"Failed to place real order 2: {result2.comment if result2 else 'None'}")
                pos1.is_tp1_target = False
                pos1.is_tp2_target = True
                
        return pos1

    def update_positions(self, symbol: str, bid: float, ask: float):
        """Update status of open MT5 trades, apply trailing stops and break-even"""
        # Query open positions on MT5
        mt5_positions = mt5.positions_get(symbol=symbol)
        if mt5_positions is None:
            return
            
        # Synch local list with MT5
        active_tickets = [p.ticket for p in mt5_positions]
        
        # Identify closed positions
        for pos_id, pos in list(self.positions.items()):
            if pos.symbol == symbol and pos_id not in active_tickets:
                # Position was closed by MT5 (SL/TP hit or manually)
                # Fetch history deal to get actual close price
                close_price = bid
                reason = "Unknown"
                
                # Fetch recent history
                history = mt5.history_deals_get(position=pos_id)
                if history:
                    # Find closing deal
                    closing_deal = [d for d in history if d.entry == mt5.DEAL_ENTRY_OUT]
                    if closing_deal:
                        close_price = closing_deal[0].price
                        # Check reason
                        reason_code = closing_deal[0].reason
                        if reason_code == mt5.DEAL_REASON_SL:
                            reason = "SL"
                        elif reason_code == mt5.DEAL_REASON_TP:
                            reason = "TP"
                        else:
                            reason = "MT5 Close"
                            
                self.positions.pop(pos_id)
                pos.status = "CLOSED"
                pos.close_price = close_price
                pos.close_time = datetime.now()
                pos.close_reason = reason
                self.closed_positions.append(pos)
                self.logger.info(f"Position ticket #{pos_id} closed externally by MT5 ({reason}) @ {close_price:.2f}")

        # Update open positions and manage SL modifications
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return
            
        point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
        
        from utils.settings_manager import settings_manager
        break_even_enabled = settings_manager.get("break_even_enabled", True)
        trailing_stop_enabled = settings_manager.get("trailing_stop_enabled", True)

        # Pass 1: Re-attach any missing tracking
        for mt5_pos in mt5_positions:
            if mt5_pos.magic != self.magic_number:
                continue
                
            ticket = mt5_pos.ticket
            
            # Find in our tracking
            if ticket not in self.positions:
                # Re-attach missing tracking
                action_str = "BUY" if mt5_pos.type == mt5.POSITION_TYPE_BUY else "SELL"
                self.positions[ticket] = TradePosition(
                    ticket_id=ticket,
                    symbol=symbol,
                    action=action_str,
                    entry_price=mt5_pos.price_open,
                    volume=mt5_pos.volume,
                    sl=mt5_pos.sl,
                    tp=mt5_pos.tp,
                    timestamp=datetime.fromtimestamp(mt5_pos.time),
                    magic=mt5_pos.magic
                )

        # Pass 2: Recover sibling links for unlinked positions
        unlinked = [pos for pos in self.positions.values() if pos.symbol == symbol and pos.sibling_id is None]
        if len(unlinked) >= 2:
            for i in range(len(unlinked)):
                pos1 = unlinked[i]
                if pos1.sibling_id is not None:
                    continue
                for j in range(i + 1, len(unlinked)):
                    pos2 = unlinked[j]
                    if pos2.sibling_id is not None:
                        continue
                    
                    # Match criteria: same symbol, action, volume, magic, entry price, and time (within 15s)
                    same_type = (pos1.action == pos2.action) and (pos1.magic == pos2.magic)
                    same_entry = abs(pos1.entry_price - pos2.entry_price) < 0.0001
                    same_time = abs((pos1.entry_time - pos2.entry_time).total_seconds()) < 15.0
                    
                    if same_type and same_entry and same_time:
                        pos1.sibling_id = pos2.id
                        pos2.sibling_id = pos1.id
                        
                        tp1_is_pos1 = (pos1.tp < pos2.tp) if pos1.action == "BUY" else (pos1.tp > pos2.tp)
                            
                        if tp1_is_pos1:
                            pos1.is_tp1_target = True
                            pos1.is_tp2_target = False
                            pos2.is_tp1_target = False
                            pos2.is_tp2_target = True
                            pos1.tp1 = pos1.tp
                            pos1.tp2 = pos2.tp
                            pos2.tp1 = pos1.tp
                            pos2.tp2 = pos2.tp
                        else:
                            pos1.is_tp1_target = False
                            pos1.is_tp2_target = True
                            pos2.is_tp1_target = True
                            pos2.is_tp2_target = False
                            pos1.tp1 = pos2.tp
                            pos1.tp2 = pos1.tp
                            pos2.tp1 = pos2.tp
                            pos2.tp2 = pos1.tp
                            
                        self.logger.info(f"🔗 Recovered sibling link between Position #{pos1.id} (TP: {pos1.tp}) and Position #{pos2.id} (TP: {pos2.tp})")
                        break

        # Pass 3: Update positions and manage SL modifications
        for mt5_pos in mt5_positions:
            if mt5_pos.magic != self.magic_number:
                continue
                
            ticket = mt5_pos.ticket
            pos = self.positions[ticket]
            pos.pnl = mt5_pos.profit
            pos.sl = mt5_pos.sl
            pos.tp = mt5_pos.tp
            
            # Apply dynamic risk adjustments (Break-Even and Trailing Stop)
            current_price = bid if pos.action == "BUY" else ask
            pnl_points = (current_price - pos.entry_price) / symbol_info.point if pos.action == "BUY" else (pos.entry_price - current_price) / symbol_info.point
            
            pos.max_profit_points = max(pos.max_profit_points, pnl_points)

            # Time-based break-even movement (after 30 seconds if in profit)
            elapsed_seconds = (datetime.now() - pos.timestamp).total_seconds() if pos.timestamp else 0
            if break_even_enabled and elapsed_seconds >= 30.0 and pos.sl != pos.entry_price:
                is_favorable = (current_price > pos.entry_price) if pos.action == "BUY" else (current_price < pos.entry_price)
                if is_favorable:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "sl": pos.entry_price,
                        "tp": pos.tp
                    }
                    res = mt5.order_send(request)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        pos.sl = pos.entry_price
                        self.logger.info(f"✅ Position #{ticket} moved to Break-Even on MT5 (30 seconds elapsed and in profit)")
                    else:
                        self.logger.error(f"Failed to move position #{ticket} to Break-Even: {res.comment if res else 'None'}")
                    continue
            
            # Sibling check for BE movement
            if pos.sibling_id and pos.sibling_id not in self.positions:
                if pos.sl != pos.entry_price:
                    # Filter to avoid "Invalid stops" when price is on the wrong side
                    is_favorable = (current_price > pos.entry_price) if pos.action == "BUY" else (current_price < pos.entry_price)
                    if is_favorable:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": pos.entry_price,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = pos.entry_price
                            self.logger.info(f"✅ Live Position #{ticket} moved to Break-Even (sibling #{pos.sibling_id} closed)")
                        else:
                            self.logger.error(f"Failed to move Live Position #{ticket} to Break-Even: {res.comment if res else 'None'}")
            
            # Single position BE movement on TP1 hit
            elif not pos.sibling_id and pos.tp1 and pos.sl != pos.entry_price:
                reached_tp1 = (current_price >= pos.tp1) if pos.action == "BUY" else (current_price <= pos.tp1)
                if reached_tp1:
                    is_favorable = (current_price > pos.entry_price) if pos.action == "BUY" else (current_price < pos.entry_price)
                    if is_favorable:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": pos.entry_price,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = pos.entry_price
                            self.logger.info(f"✅ Single Live Position #{ticket} moved to Break-Even after hitting TP1")
                        else:
                            self.logger.error(f"Failed to move Single Live Position #{ticket} to Break-Even: {res.comment if res else 'None'}")
                        
            # Trailing Stop
            elif trailing_stop_enabled and pos.initial_sl_dist > 0:
                if pos.action == "BUY":
                    new_sl = round(current_price - pos.initial_sl_dist, symbol_info.digits)
                    if new_sl > pos.sl:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = new_sl
                            self.logger.info(f"✅ Position #{ticket} trailed SL to {new_sl:.2f} on MT5")
                        else:
                            self.logger.error(f"Failed to trail position #{ticket} SL: {res.comment if res else 'None'}")
                else:
                    new_sl = round(current_price + pos.initial_sl_dist, symbol_info.digits)
                    if pos.sl == 0 or new_sl < pos.sl:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = new_sl
                            self.logger.info(f"✅ Position #{ticket} trailed SL to {new_sl:.2f} on MT5")
                        else:
                            self.logger.error(f"Failed to trail position #{ticket} SL: {res.comment if res else 'None'}")
            elif break_even_enabled and pos.sl != 0 and pos.sl != pos.entry_price:
                sl_distance_pts = pos.initial_sl_dist / symbol_info.point
                if pos.max_profit_points >= sl_distance_pts:
                    is_favorable = (current_price > pos.entry_price) if pos.action == "BUY" else (current_price < pos.entry_price)
                    if is_favorable:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": pos.entry_price,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = pos.entry_price
                            self.logger.info(f"✅ Position #{ticket} moved to Break-Even on MT5")
                        else:
                            self.logger.error(f"Failed to move position #{ticket} to Break-Even: {res.comment if res else 'None'}")

    def close_position(self, pos_id: int, close_price: float, reason: str) -> Optional[TradePosition]:
        """Close position manually"""
        pos = self.positions.get(pos_id, None)
        if pos:
            order_type = mt5.ORDER_TYPE_SELL if pos.action == "BUY" else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).bid if pos.action == "BUY" else mt5.symbol_info_tick(pos.symbol).ask
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "position": pos_id,
                "price": price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "PulseViper close position",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                self.positions.pop(pos_id)
                pos.status = "CLOSED"
                pos.close_price = res.price
                pos.close_time = datetime.now()
                pos.close_reason = reason
                
                # Calculate fallback profit manually
                symbol_info = mt5.symbol_info(pos.symbol)
                pnl = 0.0
                if symbol_info:
                    point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
                    if pos.action == "BUY":
                        pnl_points = (res.price - pos.entry_price) / symbol_info.point
                    else:
                        pnl_points = (pos.entry_price - res.price) / symbol_info.point
                    pnl = pnl_points * point_value * pos.volume
                
                # Fetch exact profit from deal history
                if hasattr(res, 'deal') and res.deal:
                    history = mt5.history_deals_get(ticket=res.deal)
                    if history:
                        pnl = history[0].profit
                        
                pos.pnl = pnl
                self.closed_positions.append(pos)
                self.logger.info(f"Position #{pos_id} closed manually: PnL: ${pos.pnl:.2f}")
                return pos
            else:
                self.logger.error(f"Failed to close position #{pos_id}: {res.comment if res else 'None'}")
        return None
