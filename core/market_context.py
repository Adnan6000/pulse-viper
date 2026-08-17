# core/market_context.py
import hashlib
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Mapping, Any, Tuple
from core.bar_normalizer import TimeframeDataSnapshot

@dataclass(frozen=True)
class MarketContext:
    context_version: int

    boot_id: str
    cycle_id: str
    symbol: str
    decision_time_utc: datetime

    instrument_profile_id: str
    mode_profile_id: str

    timeframe_snapshots: Mapping[str, TimeframeDataSnapshot]

    regime_probabilities: Mapping[str, float]
    regime_label: str
    regime_age_bars: int

    trend_state: Mapping[str, Any]
    structure_graph_version: str
    active_structure_events: tuple
    liquidity_state: Mapping[str, Any]

    session_context: Mapping[str, Any]
    news_context: Mapping[str, Any]
    spread_context: Mapping[str, Any]

    data_quality: Mapping[str, Any]
    context_hash: str

def generate_context_hash(symbol: str, cycle_id: str, decision_time: datetime, snapshot_hashes: Mapping[str, str]) -> str:
    """Creates a unique hash representing the exact state of this market context cycle."""
    raw_str = f"{symbol}_{cycle_id}_{decision_time.isoformat()}"
    sorted_snapshots = sorted(snapshot_hashes.items())
    for tf, h in sorted_snapshots:
        raw_str += f"_{tf}:{h}"
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()
