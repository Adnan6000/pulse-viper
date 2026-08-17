# core/mode_profile.py
from dataclasses import dataclass
from typing import Tuple, Dict

@dataclass(frozen=True)
class ModeProfile:
    mode_id: str  # "scalping", "intraday", "swing"
    context_timeframe: str
    structure_timeframe: str
    trigger_timeframe: str
    
    warmup_bars: int
    max_holding_bars: int
    outcome_horizon_bars: int
    
    minimum_rr: float
    max_spread_to_risk_ratio: float
    permitted_swing_scales: Tuple[str, ...]
    news_buffer_minutes: int
    candidate_expiry_minutes: int

MODE_REGISTRY: Dict[str, ModeProfile] = {
    "scalping": ModeProfile(
        mode_id="scalping",
        context_timeframe="M5",
        structure_timeframe="M5",
        trigger_timeframe="M1",
        warmup_bars=120,
        max_holding_bars=40,
        outcome_horizon_bars=60,
        minimum_rr=1.5,
        max_spread_to_risk_ratio=0.15,
        permitted_swing_scales=("MICRO", "INTERNAL", "INTERMEDIATE"),
        news_buffer_minutes=15,
        candidate_expiry_minutes=5
    ),
    "intraday": ModeProfile(
        mode_id="intraday",
        context_timeframe="H1",
        structure_timeframe="M15",
        trigger_timeframe="M5",
        warmup_bars=150,
        max_holding_bars=100,
        outcome_horizon_bars=120,
        minimum_rr=2.0,
        max_spread_to_risk_ratio=0.10,
        permitted_swing_scales=("INTERNAL", "INTERMEDIATE", "EXTERNAL"),
        news_buffer_minutes=30,
        candidate_expiry_minutes=15
    ),
    "swing": ModeProfile(
        mode_id="swing",
        context_timeframe="D1",
        structure_timeframe="H1",
        trigger_timeframe="M15",
        warmup_bars=200,
        max_holding_bars=200,
        outcome_horizon_bars=300,
        minimum_rr=2.5,
        max_spread_to_risk_ratio=0.05,
        permitted_swing_scales=("INTERMEDIATE", "EXTERNAL", "MAJOR"),
        news_buffer_minutes=60,
        candidate_expiry_minutes=60
    )
}

def get_mode_profile(mode_id: str) -> ModeProfile:
    """Gets the profile parameters for scalping, intraday, or swing trading."""
    return MODE_REGISTRY.get(mode_id.lower(), MODE_REGISTRY["intraday"])
