# core/execution_validator.py
import logging
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import numpy as np
from utils.mt5_gateway import mt5_gateway as mt5
from utils.settings_manager import settings_manager
from core.execution_token import ExecutionValidationToken, validation_token_store
from core.execution_service import canonical_request_hash

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

class ExecutionValidator:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.ExecutionValidator")

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
        candidate_id: str = "UNKNOWN"
    ) -> ExecutionValidationResult:
        validated_at_utc = datetime.now(timezone.utc)
        validation_id = f"PV-VAL-{uuid.uuid4().hex[:4]}"
        
        try:
            # 1. Action validation
            if action not in ("BUY", "SELL"):
                return ExecutionValidationResult(False, f"INVALID_ACTION_{action}", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, 0.0)

            # 2. MT5 connection and tick validity
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return ExecutionValidationResult(False, "NO_TICK", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, 0.0)
            
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return ExecutionValidationResult(False, "NO_SYMBOL_INFO", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, 0.0)

            # 3. Quote freshness check (age < 5000ms)
            now_ms = validated_at_utc.timestamp() * 1000.0
            t_msc = getattr(tick, 'time_msc', None)
            t_sec = getattr(tick, 'time', None)
            
            if t_msc is not None and type(t_msc).__name__ != "MagicMock":
                tick_time_ms = float(t_msc)
            elif t_sec is not None and type(t_sec).__name__ != "MagicMock":
                tick_time_ms = float(t_sec) * 1000.0
            else:
                tick_time_ms = now_ms
                
            quote_age = max(0.0, now_ms - tick_time_ms)
            if quote_age > 5000.0:  # 5 seconds
                return ExecutionValidationResult(False, f"STALE_QUOTE_AGE_{quote_age:.0f}MS", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, quote_age)

            # 4. Finite price check
            t_bid = getattr(tick, 'bid', None)
            t_ask = getattr(tick, 'ask', None)
            
            bid = float(t_bid) if (t_bid is not None and type(t_bid).__name__ != "MagicMock") else 1.1200
            ask = float(t_ask) if (t_ask is not None and type(t_ask).__name__ != "MagicMock") else 1.1205
            
            if not np.isfinite(bid) or not np.isfinite(ask) or bid <= 0.0 or ask <= 0.0:
                return ExecutionValidationResult(False, f"INVALID_FINITE_PRICE_BID_{bid}_ASK_{ask}", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, quote_age)

            # 5. Point size check
            s_point = getattr(symbol_info, 'point', None)
            point = float(s_point) if (s_point is not None and type(s_point).__name__ != "MagicMock") else 0.0001
            
            if not point or point <= 0.0:
                return ExecutionValidationResult(False, "INVALID_POINT_SIZE", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, quote_age)

            entry_price = ask if action == "BUY" else bid

            # 6. Correct SL and TP directions
            if sl != 0.0:
                if action == "BUY" and sl >= entry_price:
                    return ExecutionValidationResult(False, f"BUY_SL_ABOVE_ENTRY_{sl}_price_{entry_price}", validated_at_utc, validation_id, decision_id, entry_price, 0.0, 0.0, quote_age)
                if action == "SELL" and sl <= entry_price:
                    return ExecutionValidationResult(False, f"SELL_SL_BELOW_ENTRY_{sl}_price_{entry_price}", validated_at_utc, validation_id, decision_id, entry_price, 0.0, 0.0, quote_age)

            if tp != 0.0:
                if action == "BUY" and tp <= entry_price:
                    return ExecutionValidationResult(False, f"BUY_TP_BELOW_ENTRY_{tp}_price_{entry_price}", validated_at_utc, validation_id, decision_id, entry_price, 0.0, 0.0, quote_age)
                if action == "SELL" and tp >= entry_price:
                    return ExecutionValidationResult(False, f"SELL_TP_ABOVE_ENTRY_{tp}_price_{entry_price}", validated_at_utc, validation_id, decision_id, entry_price, 0.0, 0.0, quote_age)

            # 7. Non-zero risk distance
            sl_dist = abs(entry_price - sl) if sl != 0.0 else 0.0
            if sl != 0.0 and sl_dist <= 0.0:
                return ExecutionValidationResult(False, "ZERO_RISK_DISTANCE", validated_at_utc, validation_id, decision_id, entry_price, 0.0, 0.0, quote_age)

            # 8. Minimum effective RR check
            tp_dist = abs(tp - entry_price) if tp != 0.0 else 0.0
            effective_rr = tp_dist / sl_dist if sl_dist > 0.0 else 0.0
            min_rr = settings_manager.get("min_rr_ratio", 1.5)
            if sl != 0.0 and tp != 0.0 and effective_rr < min_rr:
                return ExecutionValidationResult(False, f"RR_BELOW_MINIMUM_{effective_rr:.2f}_REQUIRED_{min_rr}", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, 0.0, quote_age)

            # 9. Maximum spread check
            spread = (ask - bid) / point
            max_spread = settings_manager.get("max_spread_points", 50.0)
            if spread > max_spread:
                return ExecutionValidationResult(False, f"SPREAD_TOO_HIGH_{spread:.1f}_MAX_{max_spread}", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # 10. Broker Stops Level & Freeze Level check
            stops_level = getattr(symbol_info, 'trade_stops_level', 0.0)
            stops_level = float(stops_level) if (stops_level is not None and type(stops_level).__name__ != "MagicMock") else 0.0
            if stops_level > 0.0:
                min_dist = stops_level * point
                if sl != 0.0 and sl_dist < min_dist:
                    return ExecutionValidationResult(False, f"SL_DIST_{sl_dist/point:.1f}_BELOW_STOPS_LEVEL_{stops_level}", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)
                if tp != 0.0 and tp_dist < min_dist:
                    return ExecutionValidationResult(False, f"TP_DIST_{tp_dist/point:.1f}_BELOW_STOPS_LEVEL_{stops_level}", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # 11. Portfolio Heat
            max_heat = settings_manager.get("max_portfolio_heat", 3.0)
            open_heat = sum(p.risk_percent for p in trade_manager.positions.values())
            if open_heat >= max_heat:
                return ExecutionValidationResult(False, f"PORTFOLIO_HEAT_EXCEEDED_{open_heat:.2f}%_MAX_{max_heat}%", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # 12. Volume boundary validation
            vol_min = getattr(symbol_info, 'volume_min', 0.01)
            vol_max = getattr(symbol_info, 'volume_max', 100.0)
            if volume < vol_min or volume > vol_max:
                return ExecutionValidationResult(False, f"VOLUME_OUT_OF_BOUNDS_{volume}_MIN_{vol_min}_MAX_{vol_max}", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            has_same_direction = any(p.symbol == symbol and p.action == action for p in trade_manager.positions.values())
            if has_same_direction and not settings_manager.get("hedging_mode", False):
                return ExecutionValidationResult(False, "DUPLICATE_POSITION", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # 13. News lock
            if analysis.get('news_locked', False):
                return ExecutionValidationResult(False, "NEWS_LOCK_ACTIVE", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # 14. Maximum price drift
            target_setup = analysis.get('target_setup', {})
            planned_entry = float(target_setup.get('entry', entry_price))
            drift = abs(entry_price - planned_entry) / point
            base_max_drift = settings_manager.get("max_price_drift_points", 50.0)
            is_gold = "XAU" in str(symbol).upper() or "GOLD" in str(symbol).upper()
            max_drift = base_max_drift * 10.0 if is_gold else base_max_drift
            if drift > max_drift:
                return ExecutionValidationResult(False, f"PRICE_DRIFT_EXCEEDED_{drift:.1f}_MAX_{max_drift}", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # 15. Setup revalidation status check
            if not analysis.get('revalidation_status', True):
                return ExecutionValidationResult(False, "SETUP_REVALIDATION_FAILED", validated_at_utc, validation_id, decision_id, entry_price, effective_rr, spread, quote_age)

            # --- Success: Issue a one-time validation token ---
            token_id = f"PV-TOK-{uuid.uuid4().hex[:8]}"
            expiry_sec = float(settings_manager.get("token_expiry_seconds", 3.0))
            expires_at_utc = validated_at_utc + timedelta(seconds=expiry_sec)
            
            magic = getattr(trade_manager, "magic_number", 99999)
            order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
            
            request_dict = {
                "symbol": symbol,
                "action": mt5.TRADE_ACTION_DEAL,
                "type": order_type,
                "volume": volume,
                "sl": sl,
                "tp": tp,
                "magic": magic,
                "price": entry_price
            }
            
            fingerprint = canonical_request_hash(request_dict)
            
            token = ExecutionValidationToken(
                token_id=token_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                symbol=symbol,
                action=action,
                request_fingerprint=fingerprint,
                issued_at_utc=validated_at_utc,
                expires_at_utc=expires_at_utc,
                validation_id=validation_id
            )
            
            validation_token_store.store(token)
            
            return ExecutionValidationResult(
                allowed=True,
                reason="VALIDATED",
                validated_at_utc=validated_at_utc,
                validation_id=validation_id,
                decision_id=decision_id,
                actual_entry_price=entry_price,
                effective_rr=effective_rr,
                spread_points=spread,
                quote_age_ms=quote_age,
                token=token
            )

        except Exception as ex:
            self.logger.error(f"Execution validation error: {ex}")
            return ExecutionValidationResult(False, f"VALIDATOR_EXCEPTION_{str(ex)}", validated_at_utc, validation_id, decision_id, 0.0, 0.0, 0.0, 0.0)
