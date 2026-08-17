from __future__ import annotations

import hashlib
import logging
import secrets
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

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


@dataclass(frozen=True)
class _PromotionAuthorization:
    proposal_id: str
    token_hash: str
    dataset_id: str
    issued_at_utc: datetime
    expires_at_utc: datetime


class SelfLearningGovernor:
    """
    Gatekeeper for self-learning SETTINGS proposals.

    Learning components may:
        - research
        - generate proposals
        - run shadow evaluation

    Learning components may NOT:
        - directly change production settings
        - change safety settings
        - change execution controls
        - activate auto trading
        - promote without frozen validation
    """

    DEFAULT_LEARNABLE_KEYS = frozenset(
        {
            "min_rr_ratio",
            "min_ai_confidence",
            "max_entry_distance_atr_coef",
            "disabled_setups",
            "break_even_pips",
            "trailing_stop_pips",
        }
    )

    def __init__(
        self,
        learnable_keys: Optional[set[str]] = None,
        authorization_ttl_seconds: int = 300,
    ):
        self.logger = logging.getLogger(
            "PulseViper.SelfLearningGovernor"
        )

        self.proposals: Dict[
            str,
            LearningProposal,
        ] = {}

        self.states: Dict[
            str,
            ProposalState,
        ] = {}

        self._authorizations: Dict[
            str,
            _PromotionAuthorization,
        ] = {}

        self._lock = threading.RLock()

        self.learnable_keys = frozenset(
            learnable_keys
            if learnable_keys is not None
            else self.DEFAULT_LEARNABLE_KEYS
        )

        self.authorization_ttl_seconds = max(
            30,
            min(
                3600,
                int(
                    authorization_ttl_seconds
                ),
            ),
        )

    # =========================================================================
    # TIME
    # =========================================================================

    @staticmethod
    def _utc(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(
            timezone.utc
        )

    # =========================================================================
    # VALIDATION HELPERS
    # =========================================================================

    def _proposal_is_expired(
        self,
        proposal: LearningProposal,
    ) -> bool:
        return (
            self._now()
            >= self._utc(
                proposal.expires_at_utc
            )
        )

    def _expire_if_needed(
        self,
        proposal_id: str,
    ) -> bool:
        proposal = self.proposals.get(
            proposal_id
        )

        if proposal is None:
            return False

        if not self._proposal_is_expired(
            proposal
        ):
            return False

        self.states[
            proposal_id
        ] = ProposalState.EXPIRED

        self._authorizations.pop(
            proposal_id,
            None,
        )

        return True

    def _proposal_key_allowed(
        self,
        proposal: LearningProposal,
    ) -> bool:
        return (
            str(
                proposal.proposal_type
            )
            in self.learnable_keys
        )

    @staticmethod
    def _validation_eligible(
        validation_result: Any,
    ) -> bool:
        if isinstance(
            validation_result,
            Mapping,
        ):
            return bool(
                validation_result.get(
                    "eligible",
                    False,
                )
            )

        return bool(
            getattr(
                validation_result,
                "eligible",
                False,
            )
        )

    @staticmethod
    def _validation_reason(
        validation_result: Any,
    ) -> str:
        if isinstance(
            validation_result,
            Mapping,
        ):
            return str(
                validation_result.get(
                    "reason",
                    "",
                )
            )

        return str(
            getattr(
                validation_result,
                "reason",
                "",
            )
        )

    # =========================================================================
    # PROPOSALS
    # =========================================================================

    def submit_proposal(
        self,
        proposal: LearningProposal,
        initial_state: ProposalState = ProposalState.SHADOW_PENDING,
    ) -> None:
        """
        Register proposal without changing production configuration.
        """

        with self._lock:
            proposal_id = str(
                proposal.proposal_id
                or ""
            ).strip()

            if not proposal_id:
                self.logger.error(
                    "Rejected learning proposal without proposal_id."
                )
                return

            if proposal_id in self.proposals:
                self.logger.error(
                    "Rejected duplicate learning proposal id=%s",
                    proposal_id,
                )
                return

            if initial_state not in (
                ProposalState.RESEARCH_ONLY,
                ProposalState.SHADOW_PENDING,
            ):
                self.logger.error(
                    (
                        "Proposal %s requested illegal initial state %s."
                    ),
                    proposal_id,
                    initial_state.value,
                )

                self.proposals[
                    proposal_id
                ] = proposal

                self.states[
                    proposal_id
                ] = ProposalState.REJECTED

                return

            created = self._utc(
                proposal.created_at_utc
            )

            expires = self._utc(
                proposal.expires_at_utc
            )

            if (
                expires <= created
                or expires <= self._now()
            ):
                self.proposals[
                    proposal_id
                ] = proposal

                self.states[
                    proposal_id
                ] = ProposalState.EXPIRED

                self.logger.warning(
                    "Rejected expired learning proposal id=%s",
                    proposal_id,
                )

                return

            if not str(
                proposal.dataset_id
                or ""
            ).strip():
                self.proposals[
                    proposal_id
                ] = proposal

                self.states[
                    proposal_id
                ] = ProposalState.REJECTED

                self.logger.error(
                    "Proposal %s has no frozen dataset_id.",
                    proposal_id,
                )

                return

            if not self._proposal_key_allowed(
                proposal
            ):
                self.proposals[
                    proposal_id
                ] = proposal

                self.states[
                    proposal_id
                ] = ProposalState.REJECTED

                self.logger.error(
                    (
                        "Self-learning proposal %s attempted "
                        "non-learnable setting '%s'."
                    ),
                    proposal_id,
                    proposal.proposal_type,
                )

                return

            self.proposals[
                proposal_id
            ] = proposal

            self.states[
                proposal_id
            ] = initial_state

            self.logger.info(
                (
                    "Learning proposal submitted | "
                    "id=%s type=%s source=%s state=%s dataset=%s"
                ),
                proposal_id,
                proposal.proposal_type,
                proposal.source_component,
                initial_state.value,
                proposal.dataset_id,
            )

    def activate_shadow(
        self,
        proposal_id: str,
    ) -> bool:
        """
        Move SHADOW_PENDING proposal into active shadow evaluation.
        """

        with self._lock:
            if self._expire_if_needed(
                proposal_id
            ):
                return False

            if proposal_id not in self.proposals:
                return False

            state = self.states.get(
                proposal_id
            )

            if state != ProposalState.SHADOW_PENDING:
                return False

            self.states[
                proposal_id
            ] = ProposalState.SHADOW_ACTIVE

            return True

    # =========================================================================
    # PROMOTION AUTHORIZATION
    # =========================================================================

    def authorize_promotion(
        self,
        proposal_id: str,
        promotion_validation: Any,
        walk_forward_result: Mapping[str, Any],
        validation_dataset_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> Optional[str]:
        """
        Issue a short-lived, single-use promotion token.

        Requirements:
            proposal is SHADOW_ACTIVE
            walk-forward passed
            PromotionValidator says eligible
            validation dataset matches proposal dataset exactly
        """

        with self._lock:
            if self._expire_if_needed(
                proposal_id
            ):
                return None

            proposal = self.proposals.get(
                proposal_id
            )

            if proposal is None:
                self.logger.error(
                    "Promotion authorization failed: proposal %s not found.",
                    proposal_id,
                )
                return None

            if self.states.get(
                proposal_id
            ) != ProposalState.SHADOW_ACTIVE:
                self.logger.error(
                    (
                        "Promotion authorization failed: proposal %s "
                        "must be SHADOW_ACTIVE."
                    ),
                    proposal_id,
                )
                return None

            if (
                str(
                    validation_dataset_id
                    or ""
                )
                != str(
                    proposal.dataset_id
                )
            ):
                self.logger.error(
                    (
                        "Promotion authorization failed: "
                        "dataset mismatch proposal=%s validation=%s."
                    ),
                    proposal.dataset_id,
                    validation_dataset_id,
                )
                return None

            if not bool(
                walk_forward_result.get(
                    "validation_passed",
                    False,
                )
            ):
                self.logger.info(
                    (
                        "Promotion authorization rejected for %s: "
                        "walk-forward did not pass."
                    ),
                    proposal_id,
                )
                return None

            # Walk-forward only validates stability.
            # It must NEVER claim it performed promotion.
            if bool(
                walk_forward_result.get(
                    "passed_promotion",
                    False,
                )
            ):
                self.logger.error(
                    (
                        "Promotion authorization rejected for %s: "
                        "walk-forward incorrectly claims promotion."
                    ),
                    proposal_id,
                )
                return None

            if not self._validation_eligible(
                promotion_validation
            ):
                self.logger.info(
                    (
                        "Promotion authorization rejected for %s: %s"
                    ),
                    proposal_id,
                    self._validation_reason(
                        promotion_validation
                    ),
                )
                return None

            raw_token = secrets.token_urlsafe(
                32
            )

            token_hash = hashlib.sha256(
                raw_token.encode(
                    "utf-8"
                )
            ).hexdigest()

            ttl = (
                self.authorization_ttl_seconds
                if ttl_seconds is None
                else max(
                    30,
                    min(
                        3600,
                        int(
                            ttl_seconds
                        ),
                    ),
                )
            )

            issued = self._now()

            self._authorizations[
                proposal_id
            ] = _PromotionAuthorization(
                proposal_id=proposal_id,
                token_hash=token_hash,
                dataset_id=(
                    proposal.dataset_id
                ),
                issued_at_utc=issued,
                expires_at_utc=(
                    issued
                    + timedelta(
                        seconds=ttl
                    )
                ),
            )

            self.states[
                proposal_id
            ] = (
                ProposalState.ELIGIBLE_FOR_PROMOTION
            )

            self.logger.info(
                (
                    "Proposal %s became ELIGIBLE_FOR_PROMOTION "
                    "after frozen validation."
                ),
                proposal_id,
            )

            return raw_token

    # =========================================================================
    # APPLY PROMOTION
    # =========================================================================

    def promote_proposal(
        self,
        proposal_id: str,
        promotion_token: str,
    ) -> bool:
        """
        Apply an authorized learning proposal.

        Arbitrary strings no longer work as promotion tokens.
        """

        with self._lock:
            if self._expire_if_needed(
                proposal_id
            ):
                self.logger.warning(
                    "Promotion rejected: proposal %s expired.",
                    proposal_id,
                )
                return False

            proposal = self.proposals.get(
                proposal_id
            )

            if proposal is None:
                self.logger.error(
                    "Proposal %s not found.",
                    proposal_id,
                )
                return False

            if self.states.get(
                proposal_id
            ) != ProposalState.ELIGIBLE_FOR_PROMOTION:
                self.logger.error(
                    (
                        "Proposal %s is not ELIGIBLE_FOR_PROMOTION."
                    ),
                    proposal_id,
                )
                return False

            authorization = (
                self._authorizations.get(
                    proposal_id
                )
            )

            if authorization is None:
                self.logger.error(
                    (
                        "Promotion rejected for %s: "
                        "no internal authorization exists."
                    ),
                    proposal_id,
                )
                return False

            now = self._now()

            if now >= authorization.expires_at_utc:
                self._authorizations.pop(
                    proposal_id,
                    None,
                )

                self.states[
                    proposal_id
                ] = ProposalState.REJECTED

                self.logger.warning(
                    (
                        "Promotion authorization expired "
                        "for proposal %s."
                    ),
                    proposal_id,
                )

                return False

            supplied_hash = hashlib.sha256(
                str(
                    promotion_token
                    or ""
                ).encode(
                    "utf-8"
                )
            ).hexdigest()

            if not secrets.compare_digest(
                supplied_hash,
                authorization.token_hash,
            ):
                self.logger.error(
                    (
                        "Promotion rejected for %s: invalid token."
                    ),
                    proposal_id,
                )
                return False

            if (
                authorization.dataset_id
                != proposal.dataset_id
            ):
                self.logger.error(
                    (
                        "Promotion rejected for %s: "
                        "authorization dataset mismatch."
                    ),
                    proposal_id,
                )
                return False

            if not self._proposal_key_allowed(
                proposal
            ):
                self.logger.error(
                    (
                        "Promotion rejected for %s: "
                        "setting '%s' is not self-learnable."
                    ),
                    proposal_id,
                    proposal.proposal_type,
                )
                return False

            key = str(
                proposal.proposal_type
            )

            current_live_value = (
                settings_manager.get(
                    key
                )
            )

            # Prevent a stale learning proposal from overwriting
            # a newer manual/system change.
            if (
                current_live_value
                != proposal.current_value
            ):
                self._authorizations.pop(
                    proposal_id,
                    None,
                )

                self.states[
                    proposal_id
                ] = ProposalState.REJECTED

                self.logger.warning(
                    (
                        "Promotion rejected for %s: "
                        "live value changed since proposal creation."
                    ),
                    proposal_id,
                )

                return False

            # Single-use token: consume before mutation.
            self._authorizations.pop(
                proposal_id,
                None,
            )

            try:
                settings_manager.set(
                    key=key,
                    value=(
                        proposal.proposed_value
                    ),
                    source=(
                        f"GOVERNOR_"
                        f"{proposal.source_component}"
                    ),
                    reason=(
                        "Validated promotion "
                        f"proposal={proposal_id} "
                        f"dataset={proposal.dataset_id} "
                        f"expected_benefit="
                        f"{proposal.expected_benefit:.6f}"
                    ),
                )

            except Exception as exc:
                self.states[
                    proposal_id
                ] = ProposalState.REJECTED

                self.logger.exception(
                    (
                        "Failed to apply validated "
                        "proposal %s: %s"
                    ),
                    proposal_id,
                    exc,
                )

                return False

            self.states[
                proposal_id
            ] = ProposalState.PROMOTED

            self.logger.warning(
                (
                    "Validated learning proposal PROMOTED | "
                    "id=%s key=%s dataset=%s"
                ),
                proposal_id,
                key,
                proposal.dataset_id,
            )

            return True

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def reject_proposal(
        self,
        proposal_id: str,
        reason: str = "REJECTED",
    ) -> bool:

        with self._lock:
            if proposal_id not in self.proposals:
                return False

            state = self.states.get(
                proposal_id
            )

            if state in (
                ProposalState.PROMOTED,
                ProposalState.ROLLED_BACK,
            ):
                return False

            self._authorizations.pop(
                proposal_id,
                None,
            )

            self.states[
                proposal_id
            ] = ProposalState.REJECTED

            self.logger.info(
                "Proposal %s rejected: %s",
                proposal_id,
                reason,
            )

            return True

    def mark_rolled_back(
        self,
        proposal_id: str,
    ) -> bool:
        """
        Record rollback state.

        Actual old-value restoration belongs to settings/audit recovery.
        """

        with self._lock:
            if self.states.get(
                proposal_id
            ) != ProposalState.PROMOTED:
                return False

            self.states[
                proposal_id
            ] = ProposalState.ROLLED_BACK

            return True

    # =========================================================================
    # READ API
    # =========================================================================

    def get_proposal_state(
        self,
        proposal_id: str,
    ) -> Optional[
        ProposalState
    ]:

        with self._lock:
            self._expire_if_needed(
                proposal_id
            )

            return self.states.get(
                proposal_id
            )

    def get_proposals_by_state(
        self,
        state: ProposalState,
    ) -> List[
        LearningProposal
    ]:

        with self._lock:
            for proposal_id in list(
                self.proposals
            ):
                self._expire_if_needed(
                    proposal_id
                )

            return [
                proposal
                for proposal_id, proposal
                in self.proposals.items()
                if self.states.get(
                    proposal_id
                )
                == state
            ]