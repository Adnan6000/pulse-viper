# core/promotion_validator.py
import logging
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

@dataclass(frozen=True)
class PromotionValidationResult:
    eligible: bool
    reason: str
    brier_score_challenger: float
    brier_score_champion: float
    log_loss_challenger: float
    log_loss_champion: float
    improvement_lower_bound: float

class PromotionValidator:
    """Compares champion and challenger model performance on frozen validation data with bootstrap checks."""
    
    def __init__(self, minimum_validation_candidates: int = 100, maximum_brier_regression: float = 0.005):
        self.logger = logging.getLogger("PulseViper.PromotionValidator")
        self.minimum_validation_candidates = minimum_validation_candidates
        self.maximum_brier_regression = maximum_brier_regression

    def validate_bundle(
        self,
        challenger_preds: List[float],
        champion_preds: List[float],
        labels: List[int],
        challenger_drawdown: float = 0.0,
        champion_drawdown: float = 0.0
    ) -> PromotionValidationResult:
        n = len(labels)
        if n < self.minimum_validation_candidates:
            return PromotionValidationResult(
                eligible=False,
                reason="INSUFFICIENT_VALIDATION_SAMPLES",
                brier_score_challenger=1.0,
                brier_score_champion=1.0,
                log_loss_challenger=9.9,
                log_loss_champion=9.9,
                improvement_lower_bound=0.0
            )

        # 1. Brier Score
        brier_challenger = np.mean((np.array(challenger_preds) - np.array(labels)) ** 2)
        brier_champion = np.mean((np.array(champion_preds) - np.array(labels)) ** 2)

        # Max Brier regression limit
        if brier_challenger > brier_champion + self.maximum_brier_regression:
            return PromotionValidationResult(
                eligible=False,
                reason="BRIER_SCORE_REGRESSION_EXCEEDED",
                brier_score_challenger=float(brier_challenger),
                brier_score_champion=float(brier_champion),
                log_loss_challenger=0.0,
                log_loss_champion=0.0,
                improvement_lower_bound=0.0
            )

        # 2. Drawdown check
        if challenger_drawdown > champion_drawdown + 0.05:
            return PromotionValidationResult(
                eligible=False,
                reason="DRAWDOWN_REGRESSION_EXCEEDED",
                brier_score_challenger=float(brier_challenger),
                brier_score_champion=float(brier_champion),
                log_loss_challenger=0.0,
                log_loss_champion=0.0,
                improvement_lower_bound=0.0
            )

        # 3. Bootstrap expected value difference (2.5th percentile lower bound)
        bootstrap_iters = 1000
        delta_evs = []
        
        y_true = np.array(labels)
        p_chal = np.array(challenger_preds)
        p_champ = np.array(champion_preds)
        
        # Simple net outcome estimate (2.0R on win, -1.0R on loss)
        outcomes = np.where(y_true == 1, 2.0, -1.0)
        
        for _ in range(bootstrap_iters):
            indices = np.random.choice(n, size=n, replace=True)
            # Challenger EV in sample
            ev_chal = np.mean(p_chal[indices] * outcomes[indices] - (1.0 - p_chal[indices]) * 1.0)
            # Champion EV in sample
            ev_champ = np.mean(p_champ[indices] * outcomes[indices] - (1.0 - p_champ[indices]) * 1.0)
            
            delta_evs.append(ev_chal - ev_champ)
            
        lower_bound = float(np.percentile(delta_evs, 2.5))
        
        if lower_bound <= 0.0:
            self.logger.warning(f"Promotion rejected. EV improvement is not statistically significant: lower bound={lower_bound:.4f}")
            return PromotionValidationResult(
                eligible=False,
                reason="EXPECTED_VALUE_IMPROVEMENT_NOT_SIGNIFICANT",
                brier_score_challenger=float(brier_challenger),
                brier_score_champion=float(brier_champion),
                log_loss_challenger=0.0,
                log_loss_champion=0.0,
                improvement_lower_bound=lower_bound
            )

        self.logger.warning("🎉 Promotion approved! Challenger model has statistically significant improvement.")
        return PromotionValidationResult(
            eligible=True,
            reason="VALIDATED",
            brier_score_challenger=float(brier_challenger),
            brier_score_champion=float(brier_champion),
            log_loss_challenger=0.0,
            log_loss_champion=0.0,
            improvement_lower_bound=lower_bound
        )
