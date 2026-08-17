# core/candidate_setup.py
from enum import Enum
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Mapping, Set, Dict

class CandidateState(str, Enum):
    DETECTED = "DETECTED"
    CONTEXT_VALIDATED = "CONTEXT_VALIDATED"
    GEOMETRY_VALIDATED = "GEOMETRY_VALIDATED"
    FEATURED = "FEATURED"
    PREDICTED = "PREDICTED"
    ABSTAINED = "ABSTAINED"
    ELIGIBLE = "ELIGIBLE"
    RISK_APPROVED = "RISK_APPROVED"
    EXECUTION_VALIDATED = "EXECUTION_VALIDATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"
    LABELED = "LABELED"
    TRAINING_ELIGIBLE = "TRAINING_ELIGIBLE"

ALLOWED_TRANSITIONS: Dict[CandidateState, Set[CandidateState]] = {
    CandidateState.DETECTED: {
        CandidateState.CONTEXT_VALIDATED,
        CandidateState.REJECTED,
    },
    CandidateState.CONTEXT_VALIDATED: {
        CandidateState.GEOMETRY_VALIDATED,
        CandidateState.REJECTED,
    },
    CandidateState.GEOMETRY_VALIDATED: {
        CandidateState.FEATURED,
        CandidateState.REJECTED,
    },
    CandidateState.FEATURED: {
        CandidateState.PREDICTED,
        CandidateState.ABSTAINED,
        CandidateState.REJECTED,
    },
    CandidateState.PREDICTED: {
        CandidateState.ELIGIBLE,
        CandidateState.ABSTAINED,
        CandidateState.REJECTED,
    },
    CandidateState.ELIGIBLE: {
        CandidateState.RISK_APPROVED,
        CandidateState.REJECTED,
    },
    CandidateState.RISK_APPROVED: {
        CandidateState.EXECUTION_VALIDATED,
        CandidateState.REJECTED,
    },
    CandidateState.EXECUTION_VALIDATED: {
        CandidateState.SUBMITTED,
        CandidateState.REJECTED,
    },
    CandidateState.SUBMITTED: {
        CandidateState.FILLED,
        CandidateState.REJECTED,
    },
    CandidateState.FILLED: {
        CandidateState.CLOSED,
        CandidateState.REJECTED,
    },
    CandidateState.CLOSED: {
        CandidateState.LABELED,
        CandidateState.REJECTED,
    },
    CandidateState.LABELED: {
        CandidateState.TRAINING_ELIGIBLE,
    },
    CandidateState.ABSTAINED: {
        CandidateState.REJECTED
    },
    CandidateState.REJECTED: set(),
    CandidateState.TRAINING_ELIGIBLE: set()
}

@dataclass(frozen=True)
class CandidateSetup:
    candidate_id: str
    decision_id: str
    cycle_id: str

    strategy_name: str
    action: str
    symbol: str
    mode: str
    execution_timeframe: str

    detected_at_utc: datetime
    valid_until_utc: datetime

    planned_entry: float
    stop_price: float
    target_price: float

    risk_distance: float
    reward_distance: float
    planned_rr: float

    setup_sequence_id: str
    entry_anchor_event_id: str
    stop_anchor_event_id: str
    target_anchor_event_id: str

    metadata: Mapping[str, Any]

    def validate_geometry(self, graph) -> bool:
        """
        Enforces Layer 1 (Location), Layer 3 (Entry Quality), Stop buffers, 
        and Path Cleanliness validations.
        """
        if not self.stop_anchor_event_id or not self.target_anchor_event_id:
            return False
        
        # 1. Structural existence verification
        swings_and_sweeps = {s.event_id: s for s in graph.swings}
        sweeps_dict = {s.event_id: s for s in graph.sweeps}
        pools_dict = {p.event_id: p for p in graph.pools}
        
        if self.stop_anchor_event_id not in swings_and_sweeps and self.stop_anchor_event_id not in sweeps_dict:
            return False
        if self.target_anchor_event_id not in pools_dict:
            return False
            
        # Get prices of anchors
        stop_anchor = swings_and_sweeps.get(self.stop_anchor_event_id) or sweeps_dict.get(self.stop_anchor_event_id)
        if stop_anchor is None:
            return False
        stop_anchor_price = stop_anchor.price
        target_anchor_price = pools_dict[self.target_anchor_event_id].price

        # 2. Location Layer: Discount (BUY) / Premium (SELL) check
        midpoint = (target_anchor_price + stop_anchor_price) / 2.0
        if self.action.upper() == "BUY":
            if self.planned_entry > midpoint:
                return False  # Block: Chasing outside discount area
            # Verify stop price is below anchor (structural invalidation)
            if self.stop_price > stop_anchor_price:
                return False
        elif self.action.upper() == "SELL":
            if self.planned_entry < midpoint:
                return False  # Block: Chasing outside premium area
            # Verify stop price is above anchor
            if self.stop_price < stop_anchor_price:
                return False

        # 3. Path Cleanliness check: Reject if an active opposing order block blocks the path
        if self.action.upper() == "BUY":
            for ob in graph.obs:
                if ob.direction == "BEARISH" and ob.status == "ACTIVE":
                    # Opposing OB is in the path
                    if self.planned_entry < ob.bottom < self.target_price:
                        return False
        elif self.action.upper() == "SELL":
            for ob in graph.obs:
                if ob.direction == "BULLISH" and ob.status == "ACTIVE":
                    if self.target_price < ob.top < self.planned_entry:
                        return False

        return True

class CandidateLifecycle:
    """Manages the state transitions for a CandidateSetup to prevent premature executions."""
    def __init__(self, candidate: CandidateSetup, initial_state: CandidateState = CandidateState.DETECTED):
        self.candidate = candidate
        self.state = initial_state

    def transition_to(self, new_state: CandidateState) -> None:
        """Validates and applies a state transition."""
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Invalid CandidateState transition from {self.state.value} to {new_state.value}")
        self.state = new_state
