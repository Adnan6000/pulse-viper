# core/chart_annotation_snapshot.py
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class ChartAnnotationSnapshot:
    cycle_id: str
    decision_id: str
    candidate_id: str

    symbol: str
    timeframe: str
    as_of_utc: datetime

    candles: Tuple[dict, ...]
    swings: Tuple[dict, ...]
    liquidity_events: Tuple[dict, ...]
    structure_events: Tuple[dict, ...]
    order_blocks: Tuple[dict, ...]
    fvgs: Tuple[dict, ...]

    entry_candle_time: Optional[datetime]
    entry_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]

    stop_anchor_event_id: Optional[str]
    target_anchor_event_id: Optional[str]
    setup_sequence_id: Optional[str]
