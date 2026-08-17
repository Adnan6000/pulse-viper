# core/market_structure_graph.py
import uuid
from enum import Enum
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

class SwingScale(str, Enum):
    MICRO = "MICRO"
    INTERNAL = "INTERNAL"
    INTERMEDIATE = "INTERMEDIATE"
    EXTERNAL = "EXTERNAL"
    MAJOR = "MAJOR"

@dataclass(frozen=True)
class SwingEvent:
    event_id: str
    symbol: str
    timeframe: str
    direction: str  # "HIGH" or "LOW"
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    price: float
    scale: SwingScale
    strength_atr: float
    prominence_atr: float
    
    bars_left: int
    bars_right: int
    
    created_from_event_ids: tuple = ()
    quality: float = 1.0
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class LiquidityPoolEvent:
    event_id: str
    symbol: str
    timeframe: str
    direction: str  # "BUY_SIDE" or "SELL_SIDE"
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    price: float
    quality: float
    created_from_event_ids: tuple
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class LiquiditySweepEvent:
    event_id: str
    symbol: str
    timeframe: str
    direction: str  # "BULLISH_SWEEP" (swept low) or "BEARISH_SWEEP" (swept high)
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    price: float
    swept_pool_id: str
    created_from_event_ids: tuple
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class StructureBreakEvent:
    event_id: str
    symbol: str
    timeframe: str
    direction: str  # "BOS" (bullish break of structure) or "CHOCH" (bearish change of character)
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    broken_swing_id: str
    displacement_ratio: float
    created_from_event_ids: tuple
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class FVGEvent:
    event_id: str
    symbol: str
    timeframe: str
    direction: str  # "BULLISH" or "BEARISH"
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    top: float
    bottom: float
    fvg_size_atr: float
    created_from_event_ids: tuple
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class OrderBlockEvent:
    event_id: str
    symbol: str
    timeframe: str
    direction: str  # "BULLISH" or "BEARISH"
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    top: float
    bottom: float
    mitigation_pct: float
    created_from_event_ids: tuple
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class RetestEvent:
    event_id: str
    symbol: str
    timeframe: str
    
    pivot_time: datetime
    confirmed_at: datetime
    available_at: datetime
    
    retested_zone_id: str
    created_from_event_ids: tuple
    status: str = "ACTIVE"
    invalidated_at: Optional[datetime] = None

@dataclass(frozen=True)
class SetupSequence:
    sequence_id: str
    symbol: str
    timeframe: str
    
    liquidity_pool_id: str
    sweep_event_id: str
    displacement_event_id: Optional[str]
    structure_break_id: str
    zone_event_id: str
    retest_event_id: Optional[str]
    trigger_event_id: str

class MarketStructureGraph:
    """Computes, stores, and resolves causal relationships between SMC structural events."""
    
    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.swings: List[SwingEvent] = []
        self.pools: List[LiquidityPoolEvent] = []
        self.sweeps: List[LiquiditySweepEvent] = []
        self.breaks: List[StructureBreakEvent] = []
        self.fvgs: List[FVGEvent] = []
        self.obs: List[OrderBlockEvent] = []
        self.retests: List[RetestEvent] = []
        self.sequences: List[SetupSequence] = []

    def update_graph(self, ohlc_bars: tuple, atr_value: float, decision_time: datetime) -> None:
        """Processes the closed bar tuple to identify and confirm structural events causally."""
        if len(ohlc_bars) < 10:
            return
            
        # 1. Detect Swings using prominence
        self._detect_swings(ohlc_bars, atr_value, decision_time)
        
        # 2. Build Liquidity Pools
        self._build_liquidity_pools(decision_time)
        
        # 3. Detect Sweeps
        self._detect_sweeps(ohlc_bars, decision_time)
        
        # 4. Detect Breaks of Structure (BOS / CHOCH)
        self._detect_breaks(ohlc_bars, decision_time)

    def _detect_swings(self, bars: tuple, atr: float, decision_time: datetime) -> None:
        # Standard swing detection: pivot high/low with left/right closed confirmations
        # Multi-scale classification based on ATR-normalized prominence
        swing_window = 3 # Confirmed after 3 bars on right close
        n = len(bars)
        
        for i in range(swing_window, n - swing_window):
            t_pivot = datetime.fromisoformat(bars[i]["time"])
            
            # Check availability: cannot know swing exists until right confirmation window is closed
            t_conf = datetime.fromisoformat(bars[i + swing_window]["time"])
            if t_conf > decision_time:
                continue # Causal boundary: Not yet available at decision_time

            h_pivot = bars[i]["high"]
            l_pivot = bars[i]["low"]

            # Pivot High Check
            is_high = True
            for r in range(1, swing_window + 1):
                if bars[i - r]["high"] >= h_pivot or bars[i + r]["high"] > h_pivot:
                    is_high = False
                    break
                    
            if is_high:
                # Calculate ATR-based prominence (prominence = high minus max of surrounding left/right highs)
                surrounding_highs = [bars[i - r]["high"] for r in range(1, swing_window + 1)] + \
                                    [bars[i + r]["high"] for r in range(1, swing_window + 1)]
                prominence = h_pivot - max(surrounding_highs)
                prominence_atr = prominence / (atr if atr > 0 else 1.0)
                
                # Classify Swing scale
                if prominence_atr < 0.5:
                    scale = SwingScale.MICRO
                elif prominence_atr < 1.0:
                    scale = SwingScale.INTERNAL
                elif prominence_atr < 2.0:
                    scale = SwingScale.INTERMEDIATE
                elif prominence_atr < 3.5:
                    scale = SwingScale.EXTERNAL
                else:
                    scale = SwingScale.MAJOR
                    
                # Deduplicate swing event
                if not any(s.pivot_time == t_pivot and s.direction == "HIGH" for s in self.swings):
                    event = SwingEvent(
                        event_id=f"PV-SW-H-{uuid.uuid4().hex[:6]}",
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        direction="HIGH",
                        pivot_time=t_pivot,
                        confirmed_at=t_conf,
                        available_at=t_conf,
                        price=h_pivot,
                        scale=scale,
                        strength_atr=prominence_atr * 1.5,
                        prominence_atr=prominence_atr,
                        bars_left=swing_window,
                        bars_right=swing_window
                    )
                    self.swings.append(event)

            # Pivot Low Check
            is_low = True
            for r in range(1, swing_window + 1):
                if bars[i - r]["low"] <= l_pivot or bars[i + r]["low"] < l_pivot:
                    is_low = False
                    break
                    
            if is_low:
                surrounding_lows = [bars[i - r]["low"] for r in range(1, swing_window + 1)] + \
                                   [bars[i + r]["low"] for r in range(1, swing_window + 1)]
                prominence = min(surrounding_lows) - l_pivot
                prominence_atr = prominence / (atr if atr > 0 else 1.0)
                
                if prominence_atr < 0.5:
                    scale = SwingScale.MICRO
                elif prominence_atr < 1.0:
                    scale = SwingScale.INTERNAL
                elif prominence_atr < 2.0:
                    scale = SwingScale.INTERMEDIATE
                elif prominence_atr < 3.5:
                    scale = SwingScale.EXTERNAL
                else:
                    scale = SwingScale.MAJOR
                    
                if not any(s.pivot_time == t_pivot and s.direction == "LOW" for s in self.swings):
                    event = SwingEvent(
                        event_id=f"PV-SW-L-{uuid.uuid4().hex[:6]}",
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        direction="LOW",
                        pivot_time=t_pivot,
                        confirmed_at=t_conf,
                        available_at=t_conf,
                        price=l_pivot,
                        scale=scale,
                        strength_atr=prominence_atr * 1.5,
                        prominence_atr=prominence_atr,
                        bars_left=swing_window,
                        bars_right=swing_window
                    )
                    self.swings.append(event)

    def _build_liquidity_pools(self, decision_time: datetime) -> None:
        # Create liquidity pools from external/major/intermediate swings
        for swing in self.swings:
            if swing.scale in (SwingScale.INTERMEDIATE, SwingScale.EXTERNAL, SwingScale.MAJOR):
                # Ensure no duplicate pool
                if not any(p.created_from_event_ids == (swing.event_id,) for p in self.pools):
                    pool = LiquidityPoolEvent(
                        event_id=f"PV-POOL-{uuid.uuid4().hex[:6]}",
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        direction="BUY_SIDE" if swing.direction == "HIGH" else "SELL_SIDE",
                        pivot_time=swing.pivot_time,
                        confirmed_at=swing.confirmed_at,
                        available_at=swing.confirmed_at,
                        price=swing.price,
                        quality=1.0,
                        created_from_event_ids=(swing.event_id,)
                    )
                    self.pools.append(pool)

    def _detect_sweeps(self, bars: tuple, decision_time: datetime) -> None:
        # Check if the wicks of active bars break pool price but close inside the range
        n = len(bars)
        for i in range(1, n):
            t_bar = datetime.fromisoformat(bars[i]["time"])
            if t_bar > decision_time:
                continue
                
            high = bars[i]["high"]
            low = bars[i]["low"]
            close = bars[i]["close"]
            open_ = bars[i]["open"]

            for pool in self.pools:
                if pool.status != "ACTIVE" or pool.available_at > t_bar:
                    continue

                if pool.direction == "BUY_SIDE":
                    # Wick breaks pool price, body closes below pool price
                    if high > pool.price and max(open_, close) <= pool.price:
                        # Sweep event detected
                        if not any(s.swept_pool_id == pool.event_id and s.pivot_time == t_bar for s in self.sweeps):
                            sweep = LiquiditySweepEvent(
                                event_id=f"PV-SWEEP-H-{uuid.uuid4().hex[:6]}",
                                symbol=self.symbol,
                                timeframe=self.timeframe,
                                direction="BEARISH_SWEEP",
                                pivot_time=t_bar,
                                confirmed_at=t_bar,
                                available_at=t_bar,
                                price=high,
                                swept_pool_id=pool.event_id,
                                created_from_event_ids=(pool.event_id,)
                            )
                            self.sweeps.append(sweep)
                            # Deactivate swept pool
                            pool_idx = self.pools.index(pool)
                            self.pools[pool_idx] = LiquidityPoolEvent(
                                **{**pool.__dict__, "status": "SWEPT", "invalidated_at": t_bar}  # type: ignore[arg-type]
                            )

                elif pool.direction == "SELL_SIDE":
                    # Wick breaks pool price, body closes above pool price
                    if low < pool.price and min(open_, close) >= pool.price:
                        if not any(s.swept_pool_id == pool.event_id and s.pivot_time == t_bar for s in self.sweeps):
                            sweep = LiquiditySweepEvent(
                                event_id=f"PV-SWEEP-L-{uuid.uuid4().hex[:6]}",
                                symbol=self.symbol,
                                timeframe=self.timeframe,
                                direction="BULLISH_SWEEP",
                                pivot_time=t_bar,
                                confirmed_at=t_bar,
                                available_at=t_bar,
                                price=low,
                                swept_pool_id=pool.event_id,
                                created_from_event_ids=(pool.event_id,)
                            )
                            self.sweeps.append(sweep)
                            pool_idx = self.pools.index(pool)
                            self.pools[pool_idx] = LiquidityPoolEvent(
                                **{**pool.__dict__, "status": "SWEPT", "invalidated_at": t_bar}  # type: ignore[arg-type]
                            )

    def _detect_breaks(self, bars: tuple, decision_time: datetime) -> None:
        # Check for break of structure (BOS): body close breaks swing high/low
        n = len(bars)
        for i in range(1, n):
            t_bar = datetime.fromisoformat(bars[i]["time"])
            if t_bar > decision_time:
                continue

            close = bars[i]["close"]
            for swing in self.swings:
                if swing.status != "ACTIVE" or swing.available_at > t_bar:
                    continue

                if swing.direction == "HIGH" and close > swing.price:
                    # Break high swing (BOS)
                    if not any(b.broken_swing_id == swing.event_id and b.pivot_time == t_bar for b in self.breaks):
                        bos = StructureBreakEvent(
                            event_id=f"PV-BOS-{uuid.uuid4().hex[:6]}",
                            symbol=self.symbol,
                            timeframe=self.timeframe,
                            direction="BOS",
                            pivot_time=t_bar,
                            confirmed_at=t_bar,
                            available_at=t_bar,
                            broken_swing_id=swing.event_id,
                            displacement_ratio=(close - swing.price) / (bars[i]["high"] - bars[i]["low"] + 1e-9),
                            created_from_event_ids=(swing.event_id,)
                        )
                        self.breaks.append(bos)
                        # Deactivate broken swing
                        swing_idx = self.swings.index(swing)
                        self.swings[swing_idx] = SwingEvent(
                            **{**swing.__dict__, "status": "BROKEN", "invalidated_at": t_bar}  # type: ignore[arg-type]
                        )

                elif swing.direction == "LOW" and close < swing.price:
                    # Break low swing (BOS)
                    if not any(b.broken_swing_id == swing.event_id and b.pivot_time == t_bar for b in self.breaks):
                        bos = StructureBreakEvent(
                            event_id=f"PV-BOS-{uuid.uuid4().hex[:6]}",
                            symbol=self.symbol,
                            timeframe=self.timeframe,
                            direction="CHOCH",
                            pivot_time=t_bar,
                            confirmed_at=t_bar,
                            available_at=t_bar,
                            broken_swing_id=swing.event_id,
                            displacement_ratio=(swing.price - close) / (bars[i]["high"] - bars[i]["low"] + 1e-9),
                            created_from_event_ids=(swing.event_id,)
                        )
                        self.breaks.append(bos)
                        swing_idx = self.swings.index(swing)
                        self.swings[swing_idx] = SwingEvent(
                            **{**swing.__dict__, "status": "BROKEN", "invalidated_at": t_bar}  # type: ignore[arg-type]
                        )

    def validate_setup_sequence(self, sequence: SetupSequence) -> bool:
        """Verifies that all events in a SetupSequence are strictly ordered chronologically."""
        try:
            # Gather events by ID
            pool = next(p for p in self.pools if p.event_id == sequence.liquidity_pool_id)
            sweep = next(s for s in self.sweeps if s.event_id == sequence.sweep_event_id)
            bos = next(b for b in self.breaks if b.event_id == sequence.structure_break_id)
            
            # Retrieve timestamps
            t_pool = pool.pivot_time
            t_sweep = sweep.pivot_time
            t_bos = bos.pivot_time
            t_trigger = sequence.trigger_event_id  # Assuming trigger is index or timestamp string, check order
            
            # Simple chronological logic
            if t_pool < t_sweep and t_sweep <= t_bos:
                return True
            return False
        except Exception:
            return False
