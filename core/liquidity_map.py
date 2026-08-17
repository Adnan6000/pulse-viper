# core/liquidity_map.py
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging

class LiquidityMap:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.LiquidityMap")
        self.pools: Dict[str, Dict] = {}  # format: {pool_id: {price, type, touches, description, status}}
        self._swept_this_cycle: List[Dict] = []

    def update_pools(self, df_d1: pd.DataFrame, df_h1: pd.DataFrame, asian_range: Optional[Tuple[float, float]] = None):
        """
        Re-scan market structure and populate resting institutional liquidity pools.
        Keeps track of touch counts; once a pool is touched more than 3 times, it is considered mitigated and cleared.
        """
        try:
            current_pools = dict(self.pools)
            self.pools.clear()
            
            # 1. Previous Day High & Low (PDH/PDL)
            if df_d1 is not None and len(df_d1) >= 2:
                pdh = float(df_d1['high'].iloc[-2])
                pdl = float(df_d1['low'].iloc[-2])
                
                # Carry forward touches if level is unchanged
                self.pools["PDH"] = {
                    "price": pdh,
                    "type": "BUY_STOP",
                    "touches": current_pools.get("PDH", {}).get("touches", 0) if abs(current_pools.get("PDH", {}).get("price", 0) - pdh) < 0.1 else 0,
                    "description": "Previous Day High"
                }
                self.pools["PDL"] = {
                    "price": pdl,
                    "type": "SELL_STOP",
                    "touches": current_pools.get("PDL", {}).get("touches", 0) if abs(current_pools.get("PDL", {}).get("price", 0) - pdl) < 0.1 else 0,
                    "description": "Previous Day Low"
                }

            # 2. Asian Session Extremes
            if asian_range is not None:
                ah, al = asian_range
                self.pools["ASIA_HIGH"] = {
                    "price": ah,
                    "type": "BUY_STOP",
                    "touches": current_pools.get("ASIA_HIGH", {}).get("touches", 0) if abs(current_pools.get("ASIA_HIGH", {}).get("price", 0) - ah) < 0.1 else 0,
                    "description": "Asian Session High"
                }
                self.pools["ASIA_LOW"] = {
                    "price": al,
                    "type": "SELL_STOP",
                    "touches": current_pools.get("ASIA_LOW", {}).get("touches", 0) if abs(current_pools.get("ASIA_LOW", {}).get("price", 0) - al) < 0.1 else 0,
                    "description": "Asian Session Low"
                }

            # 3. Equal Highs & Equal Lows (EQH/EQL) on H1
            # We scan the last 40 H1 candles for matching high/low zones (within 0.15 * ATR threshold)
            if df_h1 is not None and len(df_h1) >= 20:
                highs = df_h1['high'].tail(40).values
                lows = df_h1['low'].tail(40).values
                atr = float(df_h1['atr'].iloc[-1]) if 'atr' in df_h1.columns else 1.5
                threshold = 0.15 * atr
                
                eqh_found = False
                eql_found = False
                
                # Scan for Equal Highs (Double/Triple Tops)
                for idx in range(len(highs)):
                    if eqh_found:
                        break
                    for j in range(idx + 2, len(highs)):
                        if abs(highs[idx] - highs[j]) <= threshold:
                            eqh_price = float(max(highs[idx], highs[j]))
                            self.pools["EQH"] = {
                                "price": eqh_price,
                                "type": "BUY_STOP",
                                "touches": current_pools.get("EQH", {}).get("touches", 0),
                                "description": "Equal Highs (H1 Structure)"
                            }
                            eqh_found = True
                            break

                # Scan for Equal Lows (Double/Triple Bottoms)
                for idx in range(len(lows)):
                    if eql_found:
                        break
                    for j in range(idx + 2, len(lows)):
                        if abs(lows[idx] - lows[j]) <= threshold:
                            eql_price = float(min(lows[idx], lows[j]))
                            self.pools["EQL"] = {
                                "price": eql_price,
                                "type": "SELL_STOP",
                                "touches": current_pools.get("EQL", {}).get("touches", 0),
                                "description": "Equal Lows (H1 Structure)"
                            }
                            eql_found = True
                            break
                            
            # Filter out mitigated pools (touches >= 3)
            self.pools = {k: v for k, v in self.pools.items() if v["touches"] < 3}
            
        except Exception as e:
            self.logger.error(f"Error updating liquidity pools: {e}")

    def check_sweeps(self, current_price: float, atr: float) -> List[Dict]:
        """
        Check if the current tick has swept any active liquidity pools.
        Returns a list of swept pools detected in this cycle.
        """
        sweeps = []
        try:
            still_active = {}
            for pool_id, pool in self.pools.items():
                p_price = pool["price"]
                p_type = pool["type"]
                
                is_swept = False
                # Sweep Buy Stop: Price goes above high pool and closes back inside or retreats
                if p_type == "BUY_STOP":
                    # Sweep threshold: price is within 0.3 * ATR above the high pool
                    if p_price <= current_price <= p_price + (0.3 * atr):
                        is_swept = True
                # Sweep Sell Stop: Price goes below low pool and closes back inside
                elif p_type == "SELL_STOP":
                    if p_price - (0.3 * atr) <= current_price <= p_price:
                        is_swept = True
                        
                if is_swept:
                    pool["touches"] += 1
                    sweeps.append({
                        "pool_id": pool_id,
                        "price": p_price,
                        "type": p_type,
                        "touches": pool["touches"],
                        "description": pool["description"]
                    })
                    
                # Retain pool if it has not exceeded touch limits
                if pool["touches"] < 3:
                    still_active[pool_id] = pool
                    
            self.pools = still_active
            self._swept_this_cycle = sweeps
        except Exception as e:
            self.logger.error(f"Error checking liquidity sweeps: {e}")
            
        return sweeps

    def get_resting_pools(self) -> List[Dict]:
        """Get list of active pools for dashboard display"""
        return [{"pool_id": k, **v} for k, v in self.pools.items()]

    def calculate_order_flow_imbalance(self, symbol: str, lookback_seconds: int = 300) -> float:
        """
        Constructs an Order Flow Imbalance (OFI) proxy using MT5's copy_ticks_from.
        Calculates the delta between aggressive buyers (ticks at Ask) and aggressive sellers (ticks at Bid).
        Returns an imbalance ratio between -1.0 (heavy selling) and 1.0 (heavy buying).
        """
        from utils.mt5_gateway import mt5_gateway as mt5
        from datetime import datetime, timedelta
        
        try:
            # Query recent ticks from 5 minutes lookback
            date_from = datetime.now() - timedelta(seconds=lookback_seconds)
            ticks = mt5.copy_ticks_from(symbol, date_from, 1000, mt5.COPY_TICKS_ALL)
            
            if ticks is None or len(ticks) == 0:
                return 0.0
                
            buy_volume = 0.0
            sell_volume = 0.0
            
            # Loop through ticks and accumulate buying/selling pressure
            for tick in ticks:
                flags = int(tick['flags'])
                vol = float(tick['volume'] or 1.0)
                
                # MT5 flags: TICK_FLAG_BUY = 32, TICK_FLAG_SELL = 64
                if flags & 32:
                    buy_volume += vol
                elif flags & 64:
                    sell_volume += vol
                else:
                    # Fallback to proximity
                    last = float(tick['last'])
                    bid = float(tick['bid'])
                    ask = float(tick['ask'])
                    if last > 0:
                        if last >= ask:
                            buy_volume += vol
                        elif last <= bid:
                            sell_volume += vol
                    else:
                        # Fallback to quote change flags
                        if flags & 4:    # TICK_FLAG_ASK (ask changed/increased)
                            buy_volume += vol
                        elif flags & 2:  # TICK_FLAG_BID (bid changed/decreased)
                            sell_volume += vol
                            
            total_volume = buy_volume + sell_volume
            if total_volume < 1e-9:
                return 0.0
                
            imbalance = (buy_volume - sell_volume) / total_volume
            return float(np.clip(imbalance, -1.0, 1.0))
            
        except Exception as e:
            self.logger.error(f"Error calculating Order Flow Imbalance: {e}")
            return 0.0
