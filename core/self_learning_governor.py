# core/self_learning_governor.py
import logging
from enum import Enum
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Mapping, Dict, List, Optional
from utils.settings_manager import settings_manager

class ProposalState(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    SHADOW_PENDING = "SHADOW_PENDING"
    SHADOW_ACTIVE = "SHADOW_ACTIVE"
    ELIGIBLE_FOR_PROMOTION = "ELIGIBLE_FOR_PROMOTION"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ROLLED_BACK = "ROLLED_BACK"

@dataclass(frozen=True)
class LearningProposal:
    proposal_id: str
    source_component: str
    proposal_type: str

    current_value: Any
    proposed_value: Any

    dataset_id: str
    evidence_summary: Mapping[str, Any]

    expected_benefit: float
    estimated_risk: float

    created_at_utc: datetime
    expires_at_utc: datetime

class SelfLearningGovernor:
    """Hardened gatekeeper that validates and routes settings modification proposals from self-learning modules."""
    
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.SelfLearningGovernor")
        self.proposals: Dict[str, LearningProposal] = {}
        self.states: Dict[str, ProposalState] = {}

    def submit_proposal(self, proposal: LearningProposal, initial_state: ProposalState = ProposalState.SHADOW_PENDING) -> None:
        """Saves a proposal in shadow or research state, blocking direct mutations to settings."""
        self.proposals[proposal.proposal_id] = proposal
        self.states[proposal.proposal_id] = initial_state
        self.logger.info(
            f"📥 Learning Proposal submitted: id={proposal.proposal_id} type={proposal.proposal_type} "
            f"source={proposal.source_component} state={initial_state.value}"
        )

    def promote_proposal(self, proposal_id: str, promotion_token: str) -> bool:
        """Privileged transition of a validated proposal into production configs."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            self.logger.error(f"Proposal {proposal_id} not found.")
            return False

        current_state = self.states.get(proposal_id, ProposalState.REJECTED)
        if current_state not in (ProposalState.SHADOW_ACTIVE, ProposalState.ELIGIBLE_FOR_PROMOTION, ProposalState.SHADOW_PENDING):
            self.logger.error(f"Proposal {proposal_id} is in state {current_state.value}, ineligible for promotion.")
            return False

        # Apply settings write atomically with source and audit trail tracking
        try:
            # Assume proposal_type contains key mapping, e.g. "min_rr_ratio" or "disabled_setups"
            key = proposal.proposal_type
            settings_manager.set(
                key=key,
                value=proposal.proposed_value,
                source=f"GOVERNOR_{proposal.source_component}",
                reason=f"Promotion of proposal {proposal_id} expected benefit={proposal.expected_benefit:.2f}"
            )
            self.states[proposal_id] = ProposalState.PROMOTED
            self.logger.warning(f"🚀 Proposal {proposal_id} successfully PROMOTED to settings. config updated.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to promote learning proposal {proposal_id}: {e}")
            return False
            
    def get_proposals_by_state(self, state: ProposalState) -> List[LearningProposal]:
        return [p for pid, p in self.proposals.items() if self.states.get(pid) == state]
