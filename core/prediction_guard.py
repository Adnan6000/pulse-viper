# core/prediction_guard.py
import logging
from typing import Optional
from core.candidate_prediction import CandidatePrediction
from core.market_context import MarketContext

class PredictionGuard:
    """Evaluates prediction metadata to decide if the model should abstain from trading."""
    
    def __init__(self, ood_limit: float = 0.8, uncertainty_limit: float = 0.15):
        self.logger = logging.getLogger("PulseViper.PredictionGuard")
        self.ood_limit = ood_limit
        self.uncertainty_limit = uncertainty_limit

    def should_abstain(self, prediction: CandidatePrediction, context: MarketContext) -> Optional[str]:
        """
        Determines if the model should abstain.
        Returns a string reason if yes, or None if the prediction is accepted.
        """
        # 1. Model Availability
        if not prediction.model_version:
            return "MODEL_UNAVAILABLE"

        # 2. Data Quality check
        if context.data_quality.get("critical_failure", False):
            return "LOW_DATA_QUALITY"

        # 3. Out of Distribution Check
        if prediction.out_of_distribution_score > self.ood_limit:
            self.logger.warning(
                f"Prediction blocked: out-of-distribution score {prediction.out_of_distribution_score:.2f} > {self.ood_limit}"
            )
            return "OUT_OF_DISTRIBUTION"

        # 4. Epistemic Uncertainty (Ensemble Disagreement) Check
        if prediction.epistemic_uncertainty > self.uncertainty_limit:
            self.logger.warning(
                f"Prediction blocked: high model disagreement uncertainty {prediction.epistemic_uncertainty:.3f} > {self.uncertainty_limit}"
            )
            return "MODEL_DISAGREEMENT"

        return None
