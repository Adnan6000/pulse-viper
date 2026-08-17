# core/trade_manager.py
from utils.mt5_gateway import mt5_gateway as mt5
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from dataclasses import dataclass
from copy import deepcopy
from types import MappingProxyType
from typing import Mapping, Any, Optional

def deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({
            key: deep_freeze(val)
            for key, val in deepcopy(value).items()
        })
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
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
    model_source: str # "NN_CHAMPION", "NAIVE_BAYES", "NO_VALID_MODEL"
    
    regime: str
    regime_confidence: float
    session: str
    
    entry_features: Mapping[str, Any]
    strategy_metadata: Mapping[str, Any]


class RegimeStateMachine:
    """Requires N consecutive confirmations before switching regimes, and blends
    exit parameters across a short transition window instead of snapping."""

    REGIME_PARAMS = {
        "trending":    {"trail_r": 0.65, "breakeven_r": 0.85},
        "compression": {"trail_r": 0.30, "breakeven_r": 0.50},
        "chaotic":     {"trail_r": 0.25, "breakeven_r": 0.40},
        "ranging":     {"trail_r": 0.50, "breakeven_r": 0.70},  # default
        "range":       {"trail_r": 0.50, "breakeven_r": 0.70},  # alias
    }

    def __init__(self, confirm_ticks: int = 3, blend_ticks: int = 5):
        self.confirm_ticks = confirm_ticks
        self.blend_ticks = blend_ticks
        self.current_regime = "ranging"
        self.candidate_regime = None
        self.candidate_count = 0
        self.transition_progress = 0  # 0 = fully old regime, blend_ticks = fully new

    def update(self, classifier_output: str):
        val = classifier_output.lower()
        if val == "range":
            val = "ranging"
        if val not in self.REGIME_PARAMS:
            val = "ranging"

        if val == self.current_regime:
            self.candidate_regime = None
            self.candidate_count = 0
            if self.transition_progress > 0:
                self.transition_progress = 0
            return

        if val == self.candidate_regime:
            self.candidate_count += 1
        else:
            self.candidate_regime = val
            self.candidate_count = 1

        if self.candidate_count >= self.confirm_ticks and self.transition_progress == 0:
            self.transition_progress = 1  # begin blending toward the new regime

        if self.transition_progress > 0:
            self.transition_progress += 1
            if self.transition_progress >= self.blend_ticks:
                self.current_regime = self.candidate_regime if self.candidate_regime is not None else "ranging"
                self.candidate_regime = None
                self.candidate_count = 0
                self.transition_progress = 0

    def get_exit_params(self) -> dict:
        base = self.REGIME_PARAMS[self.current_regime]
        if self.transition_progress == 0 or self.candidate_regime is None:
            return base
        target = self.REGIME_PARAMS[self.candidate_regime]
        t = self.transition_progress / self.blend_ticks
        return {
            "trail_r": base["trail_r"] + (target["trail_r"] - base["trail_r"]) * t,
            "breakeven_r": base["breakeven_r"] + (target["breakeven_r"] - base["breakeven_r"]) * t,
        }

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
        self.decision_snapshot = None
        self.decision_id = None
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
        self.moved_to_be = False
        self.has_booked_50pct = False
        self.volatility_regime = "RANGING"
        self.strategy_name = "UNKNOWN"
        self.entry_pattern = "UNKNOWN"
        self.risk_percent = 0.0
        
        # Hedging parameters
        self.hedge_ticket = None
        self.is_hedge = False
        self.parent_position_id = None
        self.saved_sl = 0.0
        self.saved_tp = 0.0
        self.execution_id: Optional[str] = None
        self.cycle_id: str = 'UNKNOWN'


class BaseTradeManager:
    def __init__(self, config):
        self.config = config
        self.positions: Dict[int, TradePosition] = {}
        self.closed_positions: List[TradePosition] = []
        self.logger = logging.getLogger("PulseViper.TradeManager")
        self.last_trade_date = datetime.now().date()
        self.daily_trade_count = self._load_today_trade_count()
        self.regime_state_machine = RegimeStateMachine()

    def _load_today_trade_count(self) -> int:
        """Read today's executed count from the audit DB so restarts don't reset the limit."""
        try:
            import sqlite3, os
            db_path = "data/pulse_viper.db"
            if not os.path.exists(db_path):
                return 0
            today = datetime.now().date().isoformat()
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM audit_evaluations WHERE executed=1 AND DATE(datetime)=?",
                (today,)
            )
            count = c.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0

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
        
        max_daily = settings_manager.get("max_daily_trades", 3)
        if max_daily >= 999 or settings_manager.get("hedging_mode", False):
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

    def calculate_lot_size(self, symbol: str, sl_price: float, entry_price: float, balance: Optional[float] = None, risk_percent: Optional[float] = None, brain_score: float = 0.0) -> float:
        """
        Dynamically calculate standard contract size based on risk percent of balance/equity.
        Formula: Lot Size = (Capital * Risk%) / (SL points * Tick Value)
        """
        try:
            from utils.settings_manager import settings_manager
            
            # Check if manual lot size is enabled
            use_manual_lot = settings_manager.get("use_manual_lot", False)
            if use_manual_lot:
                manual_lot = settings_manager.get("manual_lot_size", 0.01)
                self.logger.info(f"📏 Using manual lot size: {manual_lot:.2f} lots")
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info:
                    vol_min = symbol_info.volume_min if hasattr(symbol_info, 'volume_min') else 0.01
                    vol_max = symbol_info.volume_max if hasattr(symbol_info, 'volume_max') else 100.0
                    return max(vol_min, min(vol_max, manual_lot))
                return 0.01
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.error(f"Failed to get symbol info for {symbol}")
                return 0.01

            if risk_percent is None:
                risk_percent = settings_manager.get("risk_percent", getattr(self.config, 'RISK_PERCENT', 1.0))
            
            # Apply BrainScore scaling multiplier
            threshold = settings_manager.get("brain_threshold", 55.0)
            if brain_score < threshold:
                brain_mult = 0.0
            elif brain_score < 70.0:
                brain_mult = 0.50
            elif brain_score < 80.0:
                brain_mult = 0.75
            else:
                brain_mult = 1.00

            # Scale risk_percent by brain_mult
            risk_percent *= brain_mult
            self.logger.info(f"🧠 BrainScore risk modifier applied: score={brain_score:.1f} mult={brain_mult:.2f}x. Base scaled risk = {risk_percent:.2f}%")

            compounding = settings_manager.get("compounding_mode", False)
            if balance is not None:
                capital = balance
            elif compounding:
                capital = self.get_capital()  # Use equity when compounding is enabled
            else:
                capital = self.get_balance()  # Use balance when compounding is disabled

            # 💰 Micro-Account Dynamic Risk Manager ($3 - $20 Balance Mode)
            if capital <= 20.00:
                self.logger.info(f"💰 Micro-Account Mode Active (Balance: ${capital:.2f}): Forcing 0.01 micro lot size")
                return 0.01

            # Disable win streak and balance growth compounding multipliers (hardened mode)
            # Sizing is constrained strictly to base risk settings and Heat Cap limits.
            base_risk_val = settings_manager.get("risk_percent", getattr(self.config, 'RISK_PERCENT', 1.0))
            clamped_risk = min(risk_percent, base_risk_val, 3.0)
            
            # Keep aggregate risk under the portfolio heat cap (configurable via settings, defaults to 3.0%)
            max_heat = settings_manager.get("max_portfolio_heat", 3.0)
            open_heat = sum(p.risk_percent for p in self.positions.values())
            remaining_heat = max(0.0, max_heat - open_heat)
            
            if remaining_heat <= 0.01:
                self.logger.warning(f"❌ Portfolio Heat Cap ({max_heat:.2f}%) reached (Current open heat: {open_heat:.2f}%). Entry blocked.")
                return 0.0
                
            if clamped_risk > remaining_heat:
                self.logger.info(f"🛡️ Portfolio Heat Guard: Clamping trade risk from {clamped_risk:.2f}% to remaining heat {remaining_heat:.2f}% (current open heat: {open_heat:.2f}%)")
                clamped_risk = remaining_heat
                
            if clamped_risk <= 0.01:
                self.logger.warning(f"❌ Calculated trade risk ({clamped_risk:.2f}%) is too low to execute. Entry blocked.")
                return 0.0
                
            risk_percent = clamped_risk
                
            risk_amount = capital * (risk_percent / 100.0)
            
            # Retrieve the broker profile for the active symbol and enforce a minimum risk amount
            try:
                from utils.symbol_manager import symbol_manager
                profile = symbol_manager.get_broker_profile(symbol)
                is_cent = profile.get("is_cent_account", False)
                min_risk = 0.1 if is_cent else 0.01
                
                # Low capital safety check: cap min_risk at 10% of total capital
                if min_risk > capital * 0.10:
                    min_risk = capital * 0.10
                    self.logger.info(f"Low capital ({capital:.2f}) detected. Capping min risk to {min_risk:.2f}.")
                    
                if risk_amount < min_risk:
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
            lots = round(lots, 2)
            
            # Capital margin safety check
            try:
                # Calculate margin required for this position size
                margin_req = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, lots, entry_price)
                if margin_req is not None:
                    if margin_req > capital * 0.95:
                        self.logger.warning(f"❌ Blocked trade: Required margin ({margin_req:.2f}) exceeds 95% of capital ({capital:.2f})")
                        return 0.0
            except Exception as margin_err:
                self.logger.error(f"Error checking margin requirements: {margin_err}")
                
            return lots
        except Exception as e:
            self.logger.error(f"Error calculating lot size: {e}")
            return 0.01

    def is_velocity_stable(self, symbol: str) -> bool:
        """
        Enforce rollover spread lockout and session active hours checks.
        """
        from datetime import datetime, timezone, time
        current_time_utc = datetime.now(timezone.utc).time()
        
        # Rollover lockout
        if "BTC" not in symbol.upper():
            if time(21, 55) <= current_time_utc <= time(22, 15):
                return False
                
        # Session active hours
        if "XAU" in symbol.upper() or "GOLD" in symbol.upper():
            if not (time(7, 0) <= current_time_utc <= time(18, 0)):
                return False
        elif any(fx in symbol.upper() for fx in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"]):
            if time(19, 0) <= current_time_utc <= time(6, 0):
                return False
                
        return True

    def find_touched_h1_ob(self, price: float, df_h1: Optional[pd.DataFrame], atr: float) -> Tuple[bool, Optional[float], Optional[float]]:
        """
        Checks if the current price touches/resides inside any unmitigated H1 OB
        or historical key S/R level. Returns (is_touching, ob_top, ob_bottom).
        """
        if df_h1 is None or len(df_h1) < 52:
            return False, None, None
            
        envelope = 0.15 * atr
        h1_closed_history = df_h1.iloc[-51:-1]
        
        # 1. Check order blocks
        ob_tops = h1_closed_history['ob_top'].dropna().values if 'ob_top' in h1_closed_history.columns else np.array([])
        ob_bottoms = h1_closed_history['ob_bottom'].dropna().values if 'ob_bottom' in h1_closed_history.columns else np.array([])
        for top, bottom in zip(ob_tops, ob_bottoms):
            if bottom - envelope <= price <= top + envelope:
                return True, float(top), float(bottom)
                
        # 2. Check S/R fallbacks
        supports = h1_closed_history['support'].dropna().values if 'support' in h1_closed_history.columns else np.array([])
        for sup in supports:
            if abs(price - sup) <= envelope:
                return True, float(sup), float(sup)
                
        resistances = h1_closed_history['resistance'].dropna().values if 'resistance' in h1_closed_history.columns else np.array([])
        for res in resistances:
            if abs(price - res) <= envelope:
                return True, float(res), float(res)
                
        return False, None, None



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
                      tp2_price: Optional[float] = None, tp_price: Optional[float] = None,
                      risk_percent: Optional[float] = None, brain_score: float = 0.0,
                      decision_snapshot: Optional[TradeDecisionSnapshot] = None,
                      execution_id: Optional[str] = None) -> Optional[TradePosition]:
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
        
        lot_size = self.calculate_lot_size(symbol, sl_price, entry_price, risk_percent=risk_percent, brain_score=brain_score)
        if lot_size <= 0.0:
            self.logger.warning(f"🚫 Virtual trade blocked: Calculated lot size is 0.0 (possibly due to capital constraints)")
            return None

        from utils.settings_manager import settings_manager
        actual_risk_pct = risk_percent if risk_percent is not None else settings_manager.get("risk_percent", 1.0)
            
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
            timestamp=datetime.now(timezone.utc),
            magic=999999
        )
        pos1.tp1 = tp1_price
        pos1.tp2 = tp2_price
        pos1.is_tp1_target = True if vol2 > 0 else False
        pos1.is_tp2_target = True if vol2 == 0 else False
        pos1.risk_percent = actual_risk_pct * (vol1 / lot_size) if lot_size > 0 else 0.0
        
        pos1.execution_id = execution_id
        if decision_snapshot is not None:
            pos1.decision_snapshot = decision_snapshot
            pos1.decision_id = decision_snapshot.decision_id
            pos1.volatility_regime = decision_snapshot.regime
            pos1.strategy_name = decision_snapshot.strategy_name
            pos1.cycle_id = getattr(decision_snapshot, 'cycle_id', 'UNKNOWN')
        
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
                timestamp=datetime.now(timezone.utc),
                magic=999999
            )
            pos2.tp1 = tp1_price
            pos2.tp2 = tp2_price
            pos2.is_tp2_target = True
            pos2.sibling_id = pos1.id
            pos1.sibling_id = pos2.id
            pos2.risk_percent = actual_risk_pct * (vol2 / lot_size) if lot_size > 0 else 0.0
            
            pos2.execution_id = execution_id
            if decision_snapshot is not None:
                pos2.decision_snapshot = decision_snapshot
                pos2.decision_id = decision_snapshot.decision_id
                pos2.volatility_regime = decision_snapshot.regime
                pos2.strategy_name = decision_snapshot.strategy_name
                pos2.cycle_id = getattr(decision_snapshot, 'cycle_id', 'UNKNOWN')
            
            self.positions[pos2.id] = pos2
            self.logger.info(f"Opened simulated {action} Position 2 (Ticket #{pos2.id}) on {symbol} @ {entry_price:.2f} | Vol: {vol2:.2f} (SL: {sl_price:.2f}, TP2: {tp2_price:.2f})")
            
        return pos1

    def update_positions(self, symbol: str, bid: float, ask: float, current_regime: str = "RANGING", 
                         df_m1: Optional[pd.DataFrame] = None, atr: Optional[float] = None, 
                         news_locked: bool = False, df_h1: Optional[pd.DataFrame] = None):
        """Update open simulated positions against current bid/ask and check SL/TP"""
        to_close = []
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return
            
        point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
        stops_level = (symbol_info.trade_stops_level if hasattr(symbol_info, 'trade_stops_level') else 0) * symbol_info.point
        if stops_level <= 0:
            stops_level = 2 * symbol_info.point
            
        atr_val = atr
        if atr_val is None and df_m1 is not None and 'atr' in df_m1.columns:
            atr_val = float(df_m1['atr'].iloc[-1])
        if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
            atr_val = 15.0 * symbol_info.point
            
        total_pnl = 0.0
        from utils.settings_manager import settings_manager
        break_even_enabled = settings_manager.get("break_even_enabled", True)
        trailing_stop_enabled = settings_manager.get("trailing_stop_enabled", True)
        emergency_hedging = settings_manager.get("emergency_hedging_enabled", True)

        # Update regime state machine and blend parameters once per tick
        self.regime_state_machine.update(current_regime)
        exit_params = self.regime_state_machine.get_exit_params()
        be_threshold_mult = exit_params["breakeven_r"]
        trail_distance_mult = exit_params["trail_r"]
        reg = self.regime_state_machine.current_regime.upper()

        # Clean up orphaned hedges
        for pos_id, pos in list(self.positions.items()):
            if pos.symbol == symbol and pos.is_hedge and pos.parent_position_id not in self.positions:
                current_price = bid if pos.action == "BUY" else ask
                to_close.append((pos_id, current_price, "ORPHANED_HEDGE_CLEANUP"))

        for pos_id, pos in list(self.positions.items()):
            if pos.symbol != symbol:
                continue
                
            current_price = bid if pos.action == "BUY" else ask
            
            # Point diff
            if pos.action == "BUY":
                pnl_points = (current_price - pos.entry_price) / symbol_info.point
            else:
                pnl_points = (pos.entry_price - current_price) / symbol_info.point
                
            pos.pnl = pnl_points * point_value * pos.volume
            total_pnl += pos.pnl
            
            if pos.is_hedge:
                continue
                
            pos.max_profit_points = max(pos.max_profit_points, pnl_points)

            # --- EMERGENCY HEDGE MANAGEMENT ---
            if pos.hedge_ticket is not None:
                # Check unwind conditions
                chaos_subsided = (current_regime != "CHAOTIC") and (not news_locked)
                velocity_stable = self.is_velocity_stable(symbol)
                touched, ob_top, ob_bottom = self.find_touched_h1_ob(current_price, df_h1, atr_val)
                
                if chaos_subsided and velocity_stable and touched:
                    self.logger.info(f"🔓 Simulated Position #{pos.id} unwinding hedge #{pos.hedge_ticket}")
                    self.close_position(pos.hedge_ticket, current_price, "HEDGE UNWIND")
                    
                    # Structural Unwind Recalculation
                    saved_sl_val = pos.saved_sl if pos.saved_sl is not None else 0.0
                    ob_top_val = ob_top if ob_top is not None else current_price
                    ob_bot_val = ob_bottom if ob_bottom is not None else current_price
                    if pos.action == "BUY":
                        price_breached = (bid <= saved_sl_val + 0.1 * atr_val)
                        if price_breached:
                            new_sl = ob_bot_val - 0.1 * atr_val
                            self.logger.warning(f"⚠️ Price breached saved SL during hedge. Recalculated new structural SL: {new_sl:.5f}")
                        else:
                            new_sl = saved_sl_val
                    else:  # SELL
                        price_breached = (ask >= saved_sl_val - 0.1 * atr_val) if saved_sl_val > 0 else False
                        if price_breached:
                            new_sl = ob_top_val + 0.1 * atr_val
                            self.logger.warning(f"⚠️ Price breached saved SL during hedge. Recalculated new structural SL: {new_sl:.5f}")
                        else:
                            new_sl = saved_sl_val
                            
                    pos.sl = new_sl
                    pos.tp = pos.saved_tp
                    pos.hedge_ticket = None
                continue

            # --- EMERGENCY HEDGING TRIGGER ---
            if emergency_hedging and pos.hedge_ticket is None:
                is_underwater = False
                if pos.action == "BUY" and bid < pos.entry_price - 1.5 * atr_val:
                    is_underwater = True
                elif pos.action == "SELL" and ask > pos.entry_price + 1.5 * atr_val:
                    is_underwater = True
                    
                is_chaos = (current_regime == "CHAOTIC" or news_locked)
                if is_chaos and is_underwater:
                    # Open simulated counter hedge
                    self.simulated_ticket += 1
                    hedge_action = "SELL" if pos.action == "BUY" else "BUY"
                    hedge_pos = TradePosition(
                        ticket_id=self.simulated_ticket,
                        symbol=symbol,
                        action=hedge_action,
                        entry_price=current_price,
                        volume=pos.volume,
                        sl=0.0,
                        tp=0.0,
                        timestamp=datetime.now(timezone.utc),
                        magic=pos.magic
                    )
                    hedge_pos.is_hedge = True
                    hedge_pos.parent_position_id = pos.id
                    
                    pos.saved_sl = pos.sl
                    pos.saved_tp = pos.tp
                    pos.sl = 0.0
                    pos.tp = 0.0
                    pos.hedge_ticket = hedge_pos.id
                    
                    self.positions[hedge_pos.id] = hedge_pos
                    self.logger.warning(f"🔒 Emergency Hedge triggered for simulated position #{pos.id}. Opened opposing hedge position #{hedge_pos.id}")
                    continue

            # --- DYNAMIC BREAKEVEN (1:1 RR) ---
            moved_to_be = False
            be_pips = float(settings_manager.get("break_even_pips", 16.0))
            be_trigger_dist = max(1.5 * initial_risk, be_pips * symbol_info.point)
                
            if break_even_enabled and not pos.moved_to_be:
                live_spread = max(ask - bid, symbol_info.spread * symbol_info.point)
                profit_buffer = 2.5 * symbol_info.point  # $0.25 profit buffer above entry
                
                if pos.action == "BUY":
                    floating_dist = bid - pos.entry_price
                    be_target_sl = pos.entry_price + live_spread + profit_buffer
                    is_past_milestone = (initial_risk > 0 and floating_dist >= be_trigger_dist)
                    is_sl_unprotected = pos.sl < pos.entry_price
                else:
                    floating_dist = pos.entry_price - ask
                    be_target_sl = pos.entry_price - live_spread - profit_buffer
                    is_past_milestone = (initial_risk > 0 and floating_dist >= be_trigger_dist)
                    is_sl_unprotected = pos.sl > pos.entry_price or pos.sl == 0.0
                    
                be_target_sl = round(be_target_sl, symbol_info.digits)
                
                # 1. Check distance milestone (1.5R / 16 pips min)
                if is_past_milestone and is_sl_unprotected:
                    pos.sl = be_target_sl
                    moved_to_be = True
                    pos.moved_to_be = True
                    self.logger.info(f"Simulated position #{pos.id} moved to Break-Even + Buffer ({be_target_sl:.2f}) at 1.5R")
                    
                # 2. Sibling closed BE
                if not moved_to_be and pos.sibling_id and pos.sibling_id not in self.positions:
                    pos.sl = be_target_sl
                    moved_to_be = True
                    pos.moved_to_be = True
                    self.logger.info(f"Simulated position #{pos.id} moved to Break-Even + Buffer ({be_target_sl:.2f}) due to sibling close")
                    
                # 3. TP1 hit BE
                if not moved_to_be and not pos.sibling_id and pos.tp1:
                    reached_tp1 = (current_price >= pos.tp1) if pos.action == "BUY" else (current_price <= pos.tp1)
                    if reached_tp1:
                        pos.sl = be_target_sl
                        moved_to_be = True
                        pos.moved_to_be = True
                        self.logger.info(f"Simulated single position #{pos.id} moved to Break-Even + Buffer ({be_target_sl:.2f}) (reached TP1)")

            # --- PRO TRADER VOLATILITY & STRUCTURE TRAILING STOP ---
            if trailing_stop_enabled:
                target_sl = None
                trail_pips = float(settings_manager.get("trailing_stop_pips", 18.0))
                min_trail_dist = max(1.8 * atr_val, trail_pips * symbol_info.point)
                
                # Check for recent M15/M5 Market Structure Shift or Liquidity Sweep in df_m1/df_h1
                mss_swing_sl = None
                if df_m1 is not None and 'mss_signal' in df_m1.columns and len(df_m1) >= 5:
                    recent_mss = df_m1.iloc[-5:]
                    if pos.action == "BUY":
                        mss_bars = recent_mss[recent_mss['mss_signal'] > 0]
                        if len(mss_bars) > 0:
                            mss_swing_sl = float(mss_bars['low'].min())
                    else:
                        mss_bars = recent_mss[recent_mss['mss_signal'] < 0]
                        if len(mss_bars) > 0:
                            mss_swing_sl = float(mss_bars['high'].max())

                if mss_swing_sl is not None and mss_swing_sl > 0:
                    target_sl = mss_swing_sl
                elif current_regime == "TRENDING":
                    # ATR Volatility Choke
                    if pos.action == "BUY":
                        target_sl = bid - min_trail_dist
                    else:
                        target_sl = ask + min_trail_dist
                else:
                    # SMC Candle-Wick Trail
                    if df_m1 is not None and len(df_m1) >= 4:
                        if pos.action == "BUY":
                            target_sl = bid - min_trail_dist
                        else:
                            target_sl = ask + min_trail_dist
                            
                if target_sl is not None:
                    # Clamping with stops_level
                    if pos.action == "BUY":
                        max_allowed = bid - stops_level
                        if target_sl > max_allowed:
                            target_sl = max_allowed
                        # Monotonicity Guard
                        if target_sl > pos.sl:
                            pos.sl = round(target_sl, symbol_info.digits)
                            self.logger.info(f"Simulated position #{pos.id} trailed SL to {pos.sl:.2f} (structure-based)")
                    else:
                        min_allowed = ask + stops_level
                        if target_sl < min_allowed:
                            target_sl = min_allowed
                        # Monotonicity Guard
                        if pos.sl == 0.0 or target_sl < pos.sl:
                            pos.sl = round(target_sl, symbol_info.digits)
                            self.logger.info(f"Simulated position #{pos.id} trailed SL to {pos.sl:.2f} (structure-based)")

            # Check standard SL/TP hit
            if pos.sl != 0.0 or pos.tp != 0.0:
                if pos.action == "BUY":
                    if pos.sl != 0.0 and current_price <= pos.sl:
                        to_close.append((pos.id, pos.sl, "SL"))
                    elif pos.tp != 0.0 and current_price >= pos.tp:
                        to_close.append((pos.id, pos.tp, "TP"))
                else:
                    if pos.sl != 0.0 and current_price >= pos.sl:
                        to_close.append((pos.id, pos.sl, "SL"))
                    elif pos.tp != 0.0 and current_price <= pos.tp:
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
            pos.close_time = datetime.now(timezone.utc)
            pos.close_reason = reason
            pos.status = "CLOSED"
            
            self.virtual_balance += pos.pnl
            self.virtual_equity = self.virtual_balance
            
            self.closed_positions.append(pos)
            self.logger.info(f"Closed simulated position #{pos.id} ({reason}) @ {close_price:.2f} | PnL: ${pos.pnl:.2f}")
            
            # Recursive cleanup of sibling and hedges
            if pos.hedge_ticket and pos.hedge_ticket in self.positions:
                self.logger.info(f"Closing hedge position #{pos.hedge_ticket} along with parent #{pos.id}")
                self.close_position(pos.hedge_ticket, close_price, f"HEDGE_CLOSE_WITH_PARENT ({reason})")
            if pos.is_hedge and pos.parent_position_id in self.positions:
                parent = self.positions[pos.parent_position_id]
                parent.hedge_ticket = None
                
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
                      tp2_price: Optional[float] = None, tp_price: Optional[float] = None,
                      risk_percent: Optional[float] = None, brain_score: float = 0.0,
                      decision_snapshot: Optional[TradeDecisionSnapshot] = None,
                      execution_id: Optional[str] = None) -> Optional[TradePosition]:
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
        
        lot_size = self.calculate_lot_size(symbol, sl_price, entry_price, risk_percent=risk_percent, brain_score=brain_score)
        if lot_size <= 0.0:
            self.logger.warning(f"🚫 Live trade blocked: Calculated lot size is 0.0 (possibly due to capital constraints)")
            return None

        from utils.settings_manager import settings_manager
        actual_risk_pct = risk_percent if risk_percent is not None else settings_manager.get("risk_percent", 1.0)
            
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
        
        # Enforce Exness minimum stops level clamping before sending order
        from utils.settings_manager import validate_and_clamp_stops
        sl_price, tp1_price = validate_and_clamp_stops(symbol, action, price, sl_price, tp1_price)
        if tp2_price:
            _, tp2_price = validate_and_clamp_stops(symbol, action, price, sl_price, tp2_price)

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
        with mt5.execution_transaction() as execution_api:
            for fill_mode in filling_modes:
                request1["type_filling"] = fill_mode
                self.logger.info(f"Sending real {action} order 1 to MT5 for {symbol} | size: {vol1} | filling: {fill_mode}")
                result1 = execution_api.order_send(request1)
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
            timestamp=datetime.now(timezone.utc),
            magic=self.magic_number
        )
        pos1.tp1 = tp1_price
        pos1.tp2 = tp2_price
        pos1.is_tp1_target = True if vol2 > 0 else False
        pos1.is_tp2_target = True if vol2 == 0 else False
        pos1.risk_percent = actual_risk_pct * (vol1 / lot_size) if lot_size > 0 else 0.0
        
        pos1.execution_id = execution_id
        if decision_snapshot is not None:
            pos1.decision_snapshot = decision_snapshot
            pos1.decision_id = decision_snapshot.decision_id
            pos1.volatility_regime = decision_snapshot.regime
            pos1.strategy_name = decision_snapshot.strategy_name
            pos1.cycle_id = getattr(decision_snapshot, 'cycle_id', 'UNKNOWN')
            
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
            with mt5.execution_transaction() as execution_api:
                for fill_mode in filling_modes:
                    request2["type_filling"] = fill_mode
                    self.logger.info(f"Sending real {action} order 2 to MT5 for {symbol} | size: {vol2} | filling: {fill_mode}")
                    result2 = execution_api.order_send(request2)
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
                    timestamp=datetime.now(timezone.utc),
                    magic=self.magic_number
                )
                pos2.tp1 = tp1_price
                pos2.tp2 = tp2_price
                pos2.is_tp2_target = True
                pos2.sibling_id = pos1.id
                pos1.sibling_id = pos2.id
                pos2.risk_percent = actual_risk_pct * (vol2 / lot_size) if lot_size > 0 else 0.0
                
                pos2.execution_id = execution_id
                if decision_snapshot is not None:
                    pos2.decision_snapshot = decision_snapshot
                    pos2.decision_id = decision_snapshot.decision_id
                    pos2.volatility_regime = decision_snapshot.regime
                    pos2.strategy_name = decision_snapshot.strategy_name
                    pos2.cycle_id = getattr(decision_snapshot, 'cycle_id', 'UNKNOWN')
                    
                self.positions[pos2.id] = pos2
                self.logger.info(f"✅ Real trade 2 placed successfully. Ticket: {pos2.id} @ {pos2.entry_price:.2f}")
            else:
                self.logger.error(f"Failed to place real order 2: {result2.comment if result2 else 'None'}")
                pos1.is_tp1_target = False
                pos1.is_tp2_target = True
                
        return pos1

    def update_positions(self, symbol: str, bid: float, ask: float, current_regime: str = "RANGING", 
                         df_m1: Optional[pd.DataFrame] = None, atr: Optional[float] = None, 
                         news_locked: bool = False, df_h1: Optional[pd.DataFrame] = None):
        """Update status of open MT5 trades, apply trailing stops and break-even"""
        # Query open positions on MT5 with smart symbol suffix matching
        mt5_positions = mt5.positions_get(symbol=symbol)
        if mt5_positions is None or len(mt5_positions) == 0:
            all_pos = mt5.positions_get()
            if all_pos:
                sym_upper = symbol.upper()
                mt5_positions = tuple(p for p in all_pos if p.symbol.upper().startswith(sym_upper) or sym_upper.startswith(p.symbol.upper()))
            else:
                mt5_positions = ()
            
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
                    closing_deal = [d for d in history if d.entry == mt5.DEAL_ENTRY_OUT]
                    if closing_deal:
                        close_price = closing_deal[0].price
                        pos.pnl = closing_deal[0].profit + closing_deal[0].commission + closing_deal[0].swap
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
                pos.close_time = datetime.now(timezone.utc)
                pos.close_reason = reason
                self.closed_positions.append(pos)
                self.logger.info(f"Position ticket #{pos_id} closed externally by MT5 ({reason}) @ {close_price:.2f}")

        # Update open positions and manage SL modifications
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return
            
        point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
        stops_level = (symbol_info.trade_stops_level if hasattr(symbol_info, 'trade_stops_level') else 0) * symbol_info.point
        if stops_level <= 0:
            stops_level = 2 * symbol_info.point
            
        atr_val = atr
        if atr_val is None and df_m1 is not None and 'atr' in df_m1.columns:
            atr_val = float(df_m1['atr'].iloc[-1])
        if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
            atr_val = 15.0 * symbol_info.point
            
        from utils.settings_manager import settings_manager
        break_even_enabled = settings_manager.get("break_even_enabled", True)
        trailing_stop_enabled = settings_manager.get("trailing_stop_enabled", True)
        emergency_hedging = settings_manager.get("emergency_hedging_enabled", True)

        # Pass 1: Re-attach any missing tracking
        for mt5_pos in mt5_positions:
            if mt5_pos.magic not in (self.magic_number, 0):
                continue
                
            ticket = mt5_pos.ticket
            
            # Find in our tracking
            if ticket not in self.positions:
                action_str = "BUY" if mt5_pos.type == mt5.POSITION_TYPE_BUY else "SELL"
                pos = TradePosition(
                    ticket_id=ticket,
                    symbol=symbol,
                    action=action_str,
                    entry_price=mt5_pos.price_open,
                    volume=mt5_pos.volume,
                    sl=mt5_pos.sl,
                    tp=mt5_pos.tp,
                    timestamp=datetime.fromtimestamp(mt5_pos.time, tz=timezone.utc),
                    magic=mt5_pos.magic
                )
                if "Hedge for #" in getattr(mt5_pos, 'comment', ''):
                    pos.is_hedge = True
                    try:
                        parent_id = int(mt5_pos.comment.split("#")[-1])
                        pos.parent_position_id = parent_id
                        if parent_id in self.positions:
                            self.positions[parent_id].hedge_ticket = ticket
                    except:
                        pass
                pos.risk_percent = settings_manager.get("risk_percent", 1.0)
                if mt5_pos.magic == 0:
                    self.logger.info(f"📓 LiveTradeManager: Detected manual trade #{ticket} (magic=0) on {symbol}, attaching tracking & risk management.")
                is_at_or_better = (pos.sl >= pos.entry_price) if pos.action == "BUY" else (pos.sl <= pos.entry_price and pos.sl != 0)
                if is_at_or_better:
                    pos.moved_to_be = True
                self.positions[ticket] = pos

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

        # Update regime state machine and blend parameters once per tick
        self.regime_state_machine.update(current_regime)
        exit_params = self.regime_state_machine.get_exit_params()
        be_threshold_mult = exit_params["breakeven_r"]
        trail_distance_mult = exit_params["trail_r"]
        reg = self.regime_state_machine.current_regime.upper()

        # Clean up orphaned live hedges
        for pos_id, pos in list(self.positions.items()):
            if pos.symbol == symbol and pos.is_hedge and pos.parent_position_id not in self.positions:
                current_price = bid if pos.action == "BUY" else ask
                self.logger.warning(f"⚠️ Live orphaned hedge position #{pos_id} detected. Closing Counter Order.")
                self.close_position(pos_id, current_price, "ORPHANED_HEDGE_CLEANUP")

        # Pass 3: Update positions and manage SL modifications
        for mt5_pos in mt5_positions:
            if mt5_pos.magic not in (self.magic_number, 0):
                continue
            ticket = mt5_pos.ticket
            pos = self.positions[ticket]
            pos.volume = mt5_pos.volume
            pos.pnl = mt5_pos.profit
            pos.sl = mt5_pos.sl
            pos.tp = mt5_pos.tp
            
            if pos.initial_sl_dist == 0.0 and mt5_pos.sl != 0:
                pos.initial_sl_dist = abs(pos.entry_price - mt5_pos.sl)
                self.logger.info(f"🛡️ LiveTradeManager: Detected SL added to manual trade #{ticket}, set initial risk distance to {pos.initial_sl_dist:.5f}")
            
            is_at_or_better = (pos.sl >= pos.entry_price) if pos.action == "BUY" else (pos.sl <= pos.entry_price and pos.sl != 0)
            if is_at_or_better:
                pos.moved_to_be = True
            
            current_price = bid if pos.action == "BUY" else ask
            pnl_points = (current_price - pos.entry_price) / symbol_info.point if pos.action == "BUY" else (pos.entry_price - current_price) / symbol_info.point
            
            if pos.is_hedge:
                continue
                
            pos.max_profit_points = max(pos.max_profit_points, pnl_points)
            volume_step = getattr(symbol_info, 'volume_step', 0.01)
            volume_min = getattr(symbol_info, 'volume_min', 0.01)

            # --- EMERGENCY HEDGE MANAGEMENT ---
            if pos.hedge_ticket is not None:
                chaos_subsided = (current_regime != "CHAOTIC") and (not news_locked)
                velocity_stable = self.is_velocity_stable(symbol)
                touched, ob_top, ob_bottom = self.find_touched_h1_ob(current_price, df_h1, atr_val)
                
                if chaos_subsided and velocity_stable and touched:
                    self.logger.info(f"🔓 Live Position #{pos.id} unwinding hedge #{pos.hedge_ticket}")
                    self.close_position(pos.hedge_ticket, current_price, "HEDGE UNWIND")
                    
                    # Structural Unwind Recalculation
                    if pos.action == "BUY":
                        price_breached = (bid <= pos.saved_sl + 0.1 * atr_val)
                        if price_breached:
                            new_sl = (ob_bottom or 0.0) - 0.1 * atr_val
                            self.logger.warning(f"⚠️ Price breached saved SL during hedge. Recalculated new structural SL: {new_sl:.5f}")
                        else:
                            new_sl = pos.saved_sl
                    else:
                        price_breached = (ask >= pos.saved_sl - 0.1 * atr_val) if pos.saved_sl > 0 else False
                        if price_breached:
                            new_sl = (ob_top or 0.0) + 0.1 * atr_val
                            self.logger.warning(f"⚠️ Price breached saved SL during hedge. Recalculated new structural SL: {new_sl:.5f}")
                        else:
                            new_sl = pos.saved_sl
                            
                    # Restore parent SL/TP
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": pos.saved_tp
                    }
                    res = mt5.order_send(request)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        pos.sl = new_sl
                        pos.tp = pos.saved_tp
                        pos.hedge_ticket = None
                        self.logger.info(f"✅ Restored parent position #{ticket} SL to {new_sl:.5f} and TP to {pos.saved_tp:.5f}")
                    else:
                        self.logger.error(f"Failed to restore parent position #{ticket} stops: {res.comment if res else 'None'}")
                continue

            # --- EMERGENCY HEDGING TRIGGER ---
            if emergency_hedging and pos.hedge_ticket is None:
                is_underwater = False
                if pos.action == "BUY" and bid < pos.entry_price - 1.5 * atr_val:
                    is_underwater = True
                elif pos.action == "SELL" and ask > pos.entry_price + 1.5 * atr_val:
                    is_underwater = True
                    
                is_chaos = (current_regime == "CHAOTIC" or news_locked)
                if is_chaos and is_underwater:
                    hedge_action = "SELL" if pos.action == "BUY" else "BUY"
                    order_type = mt5.ORDER_TYPE_SELL if hedge_action == "SELL" else mt5.ORDER_TYPE_BUY
                    tick = mt5.symbol_info_tick(symbol)
                    price = tick.ask if hedge_action == "BUY" else tick.bid
                    
                    filling_modes = []
                    mode_mask = getattr(symbol_info, 'filling_mode', 0)
                    if mode_mask & 1:
                        filling_modes.append(mt5.ORDER_FILLING_FOK)
                    if mode_mask & 2:
                        filling_modes.append(mt5.ORDER_FILLING_IOC)
                    for m in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
                        if m not in filling_modes:
                            filling_modes.append(m)
                            
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": pos.volume,
                        "type": order_type,
                        "price": price,
                        "sl": 0.0,
                        "tp": 0.0,
                        "deviation": 20,
                        "magic": self.magic_number,
                        "comment": f"PulseViper Hedge for #{pos.id}",
                        "type_time": mt5.ORDER_TIME_GTC,
                    }
                    
                    hedge_ticket_id = None
                    for fill_mode in filling_modes:
                        request["type_filling"] = fill_mode
                        self.logger.warning(f"🔒 Firing emergency hedge order for position #{pos.id} | filling: {fill_mode}")
                        result = mt5.order_send(request)
                        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                            hedge_ticket_id = result.order
                            break
                            
                    if hedge_ticket_id:
                        pos.saved_sl = pos.sl
                        pos.saved_tp = pos.tp
                        
                        sltp_req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.id,
                            "sl": 0.0,
                            "tp": 0.0
                        }
                        sltp_res = mt5.order_send(sltp_req)
                        if sltp_res and sltp_res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = 0.0
                            pos.tp = 0.0
                            
                        pos.hedge_ticket = hedge_ticket_id
                        
                        hedge_pos = TradePosition(
                            ticket_id=hedge_ticket_id,
                            symbol=symbol,
                            action=hedge_action,
                            entry_price=result.price if result and hasattr(result, 'price') else current_price,
                            volume=result.volume if result and hasattr(result, 'volume') else pos.volume,
                            sl=0.0,
                            tp=0.0,
                            timestamp=datetime.now(timezone.utc),
                            magic=self.magic_number
                        )
                        hedge_pos.is_hedge = True
                        hedge_pos.parent_position_id = pos.id
                        self.positions[hedge_ticket_id] = hedge_pos
                        
                        self.logger.warning(f"🔒 Emergency Hedge placed successfully. Ticket #{hedge_ticket_id} hedging parent #{pos.id}")
                    else:
                        self.logger.error(f"Failed to place emergency hedge for position #{pos.id}")
                    continue

            # --- BREAK-EVEN CHECK (LIVE) ---
            moved_to_be = False
            initial_risk = pos.initial_sl_dist
            if initial_risk <= 0.0 and pos.sl != 0.0:
                initial_risk = abs(pos.entry_price - pos.sl)
                
            be_pips = float(settings_manager.get("break_even_pips", 16.0))
            be_trigger_dist = max(1.5 * initial_risk, be_pips * symbol_info.point)

            if break_even_enabled and not pos.moved_to_be:
                live_spread = max(ask - bid, symbol_info.spread * symbol_info.point)
                profit_buffer = 2.5 * symbol_info.point  # $0.25 profit buffer above entry
                
                if pos.action == "BUY":
                    floating_dist = bid - pos.entry_price
                    be_target_sl = pos.entry_price + live_spread + profit_buffer
                    is_past_milestone = (initial_risk > 0 and floating_dist >= be_trigger_dist)
                    is_sl_unprotected = pos.sl < pos.entry_price
                else:
                    floating_dist = pos.entry_price - ask
                    be_target_sl = pos.entry_price - live_spread - profit_buffer
                    is_past_milestone = (initial_risk > 0 and floating_dist >= be_trigger_dist)
                    is_sl_unprotected = pos.sl > pos.entry_price or pos.sl == 0.0
                    
                be_target_sl = round(be_target_sl, symbol_info.digits)
                is_favorable = (current_price > be_target_sl) if pos.action == "BUY" else (current_price < be_target_sl)
                
                if is_favorable:
                    # 1. Distance-based BE (1.5R / 16 pips min)
                    if is_past_milestone and is_sl_unprotected:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": be_target_sl,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = be_target_sl
                            moved_to_be = True
                            pos.moved_to_be = True
                            self.logger.info(f"✅ Position #{ticket} moved to Break-Even + Buffer ({be_target_sl:.2f}) on MT5 at 1.5R")
                        else:
                            self.logger.error(f"Failed to move position #{ticket} to Break-Even: {res.comment if res else 'None'}")
                    
                    # 2. Sibling closed BE
                    if not moved_to_be and pos.sibling_id and pos.sibling_id not in self.positions:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": be_target_sl,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = be_target_sl
                            moved_to_be = True
                            pos.moved_to_be = True
                            self.logger.info(f"✅ Live Position #{ticket} moved to Break-Even + Buffer due to sibling close")
                        else:
                            self.logger.error(f"Failed to move Live Position #{ticket} to Break-Even: {res.comment if res else 'None'}")
                    
                    # 3. TP1 reached BE
                    if not moved_to_be and not pos.sibling_id and pos.tp1:
                        reached_tp1 = (current_price >= pos.tp1) if pos.action == "BUY" else (current_price <= pos.tp1)
                        if reached_tp1:
                            request = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": ticket,
                                "sl": be_target_sl,
                                "tp": pos.tp
                            }
                            res = mt5.order_send(request)
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                pos.sl = be_target_sl
                                moved_to_be = True
                                pos.moved_to_be = True
                                self.logger.info(f"✅ Single Live Position #{ticket} moved to Break-Even + Buffer after hitting TP1")
                            else:
                                self.logger.error(f"Failed to move Single Live Position #{ticket} to Break-Even: {res.comment if res else 'None'}")

            # --- PARTIAL PROFIT BOOKING & SHUTDOWN PROTECTION (at 1.0R profit) ---
            if pos.initial_sl_dist > 0 and pos.max_profit_points >= (pos.initial_sl_dist / symbol_info.point):
                if pos.volume >= 2 * volume_step and not pos.has_booked_50pct:
                    pos.has_booked_50pct = True
                    half_vol = round((pos.volume / 2.0) / volume_step) * volume_step
                    half_vol = round(half_vol, 2)
                    if half_vol >= volume_min:
                        self.logger.info(f"Target 1.0R reached for position #{ticket}. Booking 50% profit by closing {half_vol:.2f} lots.")
                        self.partial_close_position(pos, half_vol)
                        
                elif pos.volume < 2 * volume_step and not pos.has_booked_50pct:
                    lock_profit_price = round(pos.entry_price + 0.3 * pos.initial_sl_dist if pos.action == "BUY" else pos.entry_price - 0.3 * pos.initial_sl_dist, symbol_info.digits)
                    is_lock_sl_better = (pos.sl > lock_profit_price) if pos.action == "BUY" else (pos.sl < lock_profit_price and pos.sl != 0)
                    if not is_lock_sl_better:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": lock_profit_price,
                            "tp": pos.tp
                        }
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            pos.sl = lock_profit_price
                            pos.has_booked_50pct = True
                            self.logger.info(f"✅ Single position #{ticket} reached 1.0R. Trailed SL to lock 30% profit ({lock_profit_price:.2f})")
                        else:
                            self.logger.error(f"Failed to lock profit on single position #{ticket}: {res.comment if res else 'None'}")

            # --- VOLATILITY-ADAPTIVE TRAILING STOP ---
            if trailing_stop_enabled:
                target_sl = None
                trail_pips = float(settings_manager.get("trailing_stop_pips", 18.0))
                min_trail_dist = max(1.8 * atr_val, trail_pips * symbol_info.point)
                
                if current_regime == "TRENDING":
                    # ATR Volatility Choke
                    if pos.action == "BUY":
                        target_sl = bid - min_trail_dist
                    else:
                        target_sl = ask + min_trail_dist
                else:
                    # SMC Candle-Wick Trail
                    if df_m1 is not None and len(df_m1) >= 4:
                        if pos.action == "BUY":
                            target_sl = bid - min_trail_dist
                        else:
                            target_sl = ask + min_trail_dist
                            
                if target_sl is not None:
                    # Clamping with stops_level
                    if pos.action == "BUY":
                        max_allowed = bid - stops_level
                        if target_sl > max_allowed:
                            target_sl = max_allowed
                        # Monotonicity Guard
                        if target_sl > pos.sl:
                            request = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": ticket,
                                "sl": round(target_sl, symbol_info.digits),
                                "tp": pos.tp
                            }
                            res = mt5.order_send(request)
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                pos.sl = round(target_sl, symbol_info.digits)
                                self.logger.info(f"✅ Live Position #{ticket} trailed SL to {pos.sl:.2f} (monotonic)")
                            else:
                                self.logger.error(f"Failed to trail Live Position #{ticket} SL: {res.comment if res else 'None'}")
                    else:
                        min_allowed = ask + stops_level
                        if target_sl < min_allowed:
                            target_sl = min_allowed
                        # Monotonicity Guard
                        if pos.sl == 0.0 or target_sl < pos.sl:
                            request = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": ticket,
                                "sl": round(target_sl, symbol_info.digits),
                                "tp": pos.tp
                            }
                            res = mt5.order_send(request)
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                pos.sl = round(target_sl, symbol_info.digits)
                                self.logger.info(f"✅ Live Position #{ticket} trailed SL to {pos.sl:.2f} (monotonic)")
                            else:
                                self.logger.error(f"Failed to trail Live Position #{ticket} SL: {res.comment if res else 'None'}")

    def partial_close_position(self, pos: TradePosition, volume_to_close: float) -> bool:
        """Partially close an open MT5 position by sending a counter order for the specified volume"""
        try:
            symbol_info = mt5.symbol_info(pos.symbol)
            if symbol_info is None:
                self.logger.error(f"Failed to get symbol info for partial close: {pos.symbol}")
                return False
                
            # Align volume to step
            volume_step = symbol_info.volume_step
            volume_to_close = round(volume_to_close / volume_step) * volume_step
            volume_to_close = round(volume_to_close, 2)
            
            if volume_to_close < symbol_info.volume_min:
                self.logger.warning(f"Partial close volume {volume_to_close} is below minimum allowed {symbol_info.volume_min}")
                return False
                
            order_type = mt5.ORDER_TYPE_SELL if pos.action == "BUY" else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).bid if pos.action == "BUY" else mt5.symbol_info_tick(pos.symbol).ask
            
            # Determine filling mode
            filling_modes = []
            mode_mask = getattr(symbol_info, 'filling_mode', 0)
            if mode_mask & 1:
                filling_modes.append(mt5.ORDER_FILLING_FOK)
            if mode_mask & 2:
                filling_modes.append(mt5.ORDER_FILLING_IOC)
            for m in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
                if m not in filling_modes:
                    filling_modes.append(m)
                    
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": volume_to_close,
                "type": order_type,
                "position": pos.id,
                "price": price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "PulseViper trailing 50% partial close",
                "type_time": mt5.ORDER_TIME_GTC,
            }
            
            for fill_mode in filling_modes:
                request["type_filling"] = fill_mode
                self.logger.info(f"Sending partial close for position #{pos.id} | Vol: {volume_to_close} | filling: {fill_mode}")
                res = mt5.order_send(request)
                if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                    self.logger.info(f"✅ Partially closed position #{pos.id} for {volume_to_close} lots on MT5")
                    pos.volume = round(pos.volume - volume_to_close, 2)
                    return True
                else:
                    err_code = res.retcode if res else "None"
                    err_comment = res.comment if res else "None"
                    self.logger.warning(f"Partial close failed with mode {fill_mode}: code={err_code}, comment={err_comment}")
                    
        except Exception as e:
            self.logger.error(f"Error executing partial close on position #{pos.id}: {e}")
            
        return False

    def close_position(self, pos_id: int, close_price: float, reason: str) -> Optional[TradePosition]:
        """Close position manually, optimized with Close By if hedged"""
        pos = self.positions.get(pos_id, None)
        if pos:
            # Check if this position has an active hedge
            if pos.hedge_ticket and pos.hedge_ticket in self.positions:
                self.logger.warning(f"🔄 Utilizing CLOSE BY to unwind hedged parent #{pos_id} and counter #{pos.hedge_ticket}")
                request = {
                    "action": mt5.TRADE_ACTION_CLOSE_BY,
                    "position": pos_id,
                    "position_by": pos.hedge_ticket,
                    "symbol": pos.symbol,
                    "magic": self.magic_number
                }
                res = mt5.order_send(request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    hedge_pos = self.positions.pop(pos.hedge_ticket)
                    self.positions.pop(pos_id)
                    
                    pos.status = "CLOSED"
                    pos.close_price = res.price if hasattr(res, 'price') else close_price
                    pos.close_time = datetime.now(timezone.utc)
                    pos.close_reason = reason
                    pos.pnl = res.profit if hasattr(res, 'profit') else 0.0
                    
                    hedge_pos.status = "CLOSED"
                    hedge_pos.close_price = res.price if hasattr(res, 'price') else close_price
                    hedge_pos.close_time = datetime.now(timezone.utc)
                    hedge_pos.close_reason = f"CLOSE BY #{pos_id}"
                    
                    # Fetch deal histories for exact profits
                    if hasattr(res, 'deal') and res.deal:
                        history = mt5.history_deals_get(ticket=res.deal)
                        if history:
                            pos.pnl = history[0].profit
                            
                    self.closed_positions.append(pos)
                    self.closed_positions.append(hedge_pos)
                    return pos
                else:
                    self.logger.error(f"Failed CLOSE BY execution: {res.comment if res else 'None'}. Falling back to standard close.")
            
            # Standard Close (Non-hedged or fallback)
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
                pos.close_time = datetime.now(timezone.utc)
                pos.close_reason = reason
                
                symbol_info = mt5.symbol_info(pos.symbol)
                pnl = 0.0
                if symbol_info:
                    point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
                    if pos.action == "BUY":
                        pnl_points = (res.price - pos.entry_price) / symbol_info.point
                    else:
                        pnl_points = (pos.entry_price - res.price) / symbol_info.point
                    pnl = pnl_points * point_value * pos.volume
                
                if hasattr(res, 'deal') and res.deal:
                    history = mt5.history_deals_get(ticket=res.deal)
                    if history:
                        pnl = history[0].profit
                        
                pos.pnl = pnl
                self.closed_positions.append(pos)
                self.logger.info(f"Position #{pos_id} closed manually: PnL: ${pos.pnl:.2f}")
                
                # Recursive cleanup of sibling and hedges
                if pos.hedge_ticket and pos.hedge_ticket in self.positions:
                    self.logger.info(f"Closing hedge position #{pos.hedge_ticket} along with parent #{pos_id}")
                    self.close_position(pos.hedge_ticket, close_price, f"HEDGE_CLOSE_WITH_PARENT ({reason})")
                if pos.is_hedge and pos.parent_position_id in self.positions:
                    parent = self.positions[pos.parent_position_id]
                    parent.hedge_ticket = None
                    
                return pos
            else:
                self.logger.error(f"Failed to close position #{pos_id}: {res.comment if res else 'None'}")
        return None
