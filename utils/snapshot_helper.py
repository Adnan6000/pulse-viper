# utils/snapshot_helper.py
import secrets
import numpy as np
from datetime import datetime, timezone
from typing import Mapping, Any, Tuple
from dataclasses import dataclass
from copy import deepcopy
from types import MappingProxyType

def deep_freeze(value: Any) -> Any:
    """Recursively freeze dictionaries, lists, sets into MappingProxyType, tuple, and frozenset."""
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

def deep_thaw(value: Any) -> Any:
    """Recursively thaw immutable representations and convert dates/NumPy types to standard JSON-compatible formats."""
    import dataclasses
    if dataclasses.is_dataclass(value):
        return {
            field.name: deep_thaw(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): deep_thaw(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [
            deep_thaw(item)
            for item in value
        ]
    if isinstance(value, frozenset):
        return sorted(
            deep_thaw(item)
            for item in value
        )
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (list, set)):
        return [deep_thaw(item) for item in value]
    return value

@dataclass(frozen=True)
class DashboardStateSnapshot:
    snapshot_version: int
    boot_id: str
    cycle_number: int
    cycle_id: str
    generated_at_utc: datetime
    generated_monotonic: float
    connected: bool
    symbols: Tuple[str, ...]

    account: Mapping[str, Any]
    positions: Tuple[Mapping[str, Any], ...]
    market: Mapping[str, Any]
    model_status: Mapping[str, Any]
    prediction: Mapping[str, Any]
    risk_status: Mapping[str, Any]
    diagnostics: Mapping[str, Any]
    routing: Mapping[str, Any]
    active_sessions: Tuple[str, ...]
    tf_alignment: Mapping[str, Any]
    starvation_stats: Mapping[str, Any]
    session_context: Mapping[str, Any]
    strategy_suggestion: Mapping[str, Any]
    strategy_rankings: Tuple[Mapping[str, Any], ...]
