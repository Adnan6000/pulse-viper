from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np


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
    """
    Frozen-set challenger-vs-champion promotion validator.

    This class ONLY determines eligibility.

    It does NOT:
        - replace model files
        - change settings
        - promote a challenger
        - mutate the model registry

    Promotion requires:

        1. enough frozen validation candidates
        2. valid probabilities
        3. no unacceptable Brier regression
        4. no unacceptable log-loss regression
        5. no unacceptable drawdown regression
        6. actual realized net-R outcomes
        7. statistically positive economic improvement
        8. at least some calibration improvement
    """

    def __init__(
        self,
        minimum_validation_candidates: int = 100,
        maximum_brier_regression: float = 0.005,
        maximum_log_loss_regression: float = 0.01,
        maximum_drawdown_regression: float = 0.05,
        decision_threshold: float = 0.50,
        bootstrap_iterations: int = 2000,
        confidence_alpha: float = 0.05,
        random_seed: int = 1337,
    ):
        self.logger = logging.getLogger(
            "PulseViper.PromotionValidator"
        )

        self.minimum_validation_candidates = max(
            20,
            int(
                minimum_validation_candidates
            ),
        )

        self.maximum_brier_regression = max(
            0.0,
            float(
                maximum_brier_regression
            ),
        )

        self.maximum_log_loss_regression = max(
            0.0,
            float(
                maximum_log_loss_regression
            ),
        )

        self.maximum_drawdown_regression = max(
            0.0,
            float(
                maximum_drawdown_regression
            ),
        )

        self.decision_threshold = max(
            0.01,
            min(
                0.99,
                float(
                    decision_threshold
                ),
            ),
        )

        self.bootstrap_iterations = max(
            500,
            min(
                20000,
                int(
                    bootstrap_iterations
                ),
            ),
        )

        self.confidence_alpha = max(
            0.001,
            min(
                0.20,
                float(
                    confidence_alpha
                ),
            ),
        )

        self.random_seed = int(
            random_seed
        )

    # =========================================================================
    # VALUE VALIDATION
    # =========================================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:

        try:
            value = float(
                value
            )

            if math.isfinite(
                value
            ):
                return value

        except (
            TypeError,
            ValueError,
        ):
            pass

        return None

    @classmethod
    def _probabilities(
        cls,
        values: Sequence[Any],
    ) -> Optional[
        np.ndarray
    ]:

        parsed = []

        for value in values:

            number = (
                cls._safe_float(
                    value
                )
            )

            if (
                number is None
                or not (
                    0.0
                    <= number
                    <= 1.0
                )
            ):
                return None

            parsed.append(
                number
            )

        return np.asarray(
            parsed,
            dtype=float,
        )

    @classmethod
    def _labels(
        cls,
        values: Sequence[Any],
    ) -> Optional[
        np.ndarray
    ]:

        parsed = []

        for value in values:

            number = (
                cls._safe_float(
                    value
                )
            )

            if number not in (
                0.0,
                1.0,
            ):
                return None

            parsed.append(
                int(
                    number
                )
            )

        return np.asarray(
            parsed,
            dtype=np.int8,
        )

    @classmethod
    def _realized_r(
        cls,
        values: Sequence[Any],
    ) -> Optional[
        np.ndarray
    ]:

        parsed = []

        for value in values:

            number = (
                cls._safe_float(
                    value
                )
            )

            if number is None:
                return None

            parsed.append(
                number
            )

        return np.asarray(
            parsed,
            dtype=float,
        )

    # =========================================================================
    # PROPER SCORING RULES
    # =========================================================================

    @staticmethod
    def _brier(
        probabilities: np.ndarray,
        labels: np.ndarray,
    ) -> float:

        return float(
            np.mean(
                (
                    probabilities
                    - labels
                )
                ** 2
            )
        )

    @staticmethod
    def _log_loss(
        probabilities: np.ndarray,
        labels: np.ndarray,
    ) -> float:

        probabilities = (
            np.clip(
                probabilities,
                1e-12,
                1.0
                - 1e-12,
            )
        )

        return float(
            -np.mean(
                labels
                * np.log(
                    probabilities
                )
                + (
                    1
                    - labels
                )
                * np.log(
                    1.0
                    - probabilities
                )
            )
        )

    # =========================================================================
    # ECONOMIC BOOTSTRAP
    # =========================================================================

    def _economic_bootstrap(
        self,
        challenger: np.ndarray,
        champion: np.ndarray,
        realized_r: np.ndarray,
    ) -> Tuple[
        float,
        float,
        float,
    ]:
        """
        Compare challenger and champion using ACTUAL realized net R.

        Policy:

            probability >= decision_threshold
                -> candidate is taken
                -> actual realized R applies

            probability < decision_threshold
                -> candidate is skipped
                -> 0R

        Both models are evaluated on the exact same frozen candidates.
        """

        challenger_policy = (
            np.where(
                challenger
                >= self.decision_threshold,
                realized_r,
                0.0,
            )
        )

        champion_policy = (
            np.where(
                champion
                >= self.decision_threshold,
                realized_r,
                0.0,
            )
        )

        challenger_ev = float(
            np.mean(
                challenger_policy
            )
        )

        champion_ev = float(
            np.mean(
                champion_policy
            )
        )

        paired_delta = (
            challenger_policy
            - champion_policy
        )

        if (
            len(
                paired_delta
            )
            == 0
            or np.allclose(
                paired_delta,
                0.0,
                rtol=0.0,
                atol=1e-15,
            )
        ):
            return (
                0.0,
                challenger_ev,
                champion_ev,
            )

        rng = (
            np.random.default_rng(
                self.random_seed
            )
        )

        bootstrap_means = (
            np.empty(
                self.bootstrap_iterations,
                dtype=float,
            )
        )

        for iteration in range(
            self.bootstrap_iterations
        ):

            indices = (
                rng.integers(
                    0,
                    len(
                        paired_delta
                    ),
                    size=len(
                        paired_delta
                    ),
                )
            )

            bootstrap_means[
                iteration
            ] = float(
                np.mean(
                    paired_delta[
                        indices
                    ]
                )
            )

        lower_bound = float(
            np.percentile(
                bootstrap_means,
                (
                    self.confidence_alpha
                    * 100.0
                ),
            )
        )

        return (
            lower_bound,
            challenger_ev,
            champion_ev,
        )

    # =========================================================================
    # RESULT
    # =========================================================================

    @staticmethod
    def _result(
        eligible: bool,
        reason: str,
        brier_challenger: float,
        brier_champion: float,
        log_loss_challenger: float,
        log_loss_champion: float,
        improvement_lower_bound: float = 0.0,
    ) -> PromotionValidationResult:

        return (
            PromotionValidationResult(
                eligible=bool(
                    eligible
                ),

                reason=str(
                    reason
                ),

                brier_score_challenger=float(
                    brier_challenger
                ),

                brier_score_champion=float(
                    brier_champion
                ),

                log_loss_challenger=float(
                    log_loss_challenger
                ),

                log_loss_champion=float(
                    log_loss_champion
                ),

                improvement_lower_bound=float(
                    improvement_lower_bound
                ),
            )
        )

    # =========================================================================
    # PUBLIC VALIDATION
    # =========================================================================

    def validate_bundle(
        self,
        challenger_preds: List[float],
        champion_preds: List[float],
        labels: List[int],
        challenger_drawdown: float = 0.0,
        champion_drawdown: float = 0.0,
        realized_outcomes_r: Optional[
            List[float]
        ] = None,
    ) -> PromotionValidationResult:
        """
        Validate challenger against current champion.

        Compatibility:
            Original first five arguments are unchanged.

        New promotion requirement:
            `realized_outcomes_r` must contain actual net-R outcomes from
            the SAME frozen validation candidates.

        If real R is not supplied, calibration metrics are still calculated,
        but promotion is rejected.
        """

        try:

            n = len(
                labels
            )

            # -----------------------------------------------------------------
            # LENGTHS
            # -----------------------------------------------------------------

            if (
                len(
                    challenger_preds
                )
                != n
                or len(
                    champion_preds
                )
                != n
            ):

                return self._result(
                    False,
                    "VALIDATION_LENGTH_MISMATCH",
                    1.0,
                    1.0,
                    math.inf,
                    math.inf,
                )

            challenger = (
                self._probabilities(
                    challenger_preds
                )
            )

            champion = (
                self._probabilities(
                    champion_preds
                )
            )

            y_true = (
                self._labels(
                    labels
                )
            )

            if (
                challenger is None
                or champion is None
                or y_true is None
            ):

                return self._result(
                    False,
                    "INVALID_VALIDATION_VALUES",
                    1.0,
                    1.0,
                    math.inf,
                    math.inf,
                )

            if n == 0:

                return self._result(
                    False,
                    "EMPTY_VALIDATION_SET",
                    1.0,
                    1.0,
                    math.inf,
                    math.inf,
                )

            # -----------------------------------------------------------------
            # REAL CALIBRATION METRICS
            # -----------------------------------------------------------------

            brier_challenger = (
                self._brier(
                    challenger,
                    y_true,
                )
            )

            brier_champion = (
                self._brier(
                    champion,
                    y_true,
                )
            )

            log_loss_challenger = (
                self._log_loss(
                    challenger,
                    y_true,
                )
            )

            log_loss_champion = (
                self._log_loss(
                    champion,
                    y_true,
                )
            )

            # -----------------------------------------------------------------
            # SAMPLE SIZE
            # -----------------------------------------------------------------

            if (
                n
                < self.minimum_validation_candidates
            ):

                return self._result(
                    False,
                    "INSUFFICIENT_VALIDATION_SAMPLES",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            # -----------------------------------------------------------------
            # BRIER REGRESSION
            # -----------------------------------------------------------------

            if (
                brier_challenger
                > (
                    brier_champion
                    + self.maximum_brier_regression
                )
            ):

                return self._result(
                    False,
                    "BRIER_SCORE_REGRESSION_EXCEEDED",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            # -----------------------------------------------------------------
            # LOG LOSS REGRESSION
            # -----------------------------------------------------------------

            if (
                log_loss_challenger
                > (
                    log_loss_champion
                    + self.maximum_log_loss_regression
                )
            ):

                return self._result(
                    False,
                    "LOG_LOSS_REGRESSION_EXCEEDED",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            # -----------------------------------------------------------------
            # DRAWDOWN
            # -----------------------------------------------------------------

            challenger_dd = (
                self._safe_float(
                    challenger_drawdown
                )
            )

            champion_dd = (
                self._safe_float(
                    champion_drawdown
                )
            )

            if (
                challenger_dd is None
                or champion_dd is None
                or challenger_dd < 0.0
                or champion_dd < 0.0
            ):

                return self._result(
                    False,
                    "INVALID_DRAWDOWN_METRICS",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            if (
                challenger_dd
                > (
                    champion_dd
                    + self.maximum_drawdown_regression
                )
            ):

                return self._result(
                    False,
                    "DRAWDOWN_REGRESSION_EXCEEDED",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            # -----------------------------------------------------------------
            # ACTUAL R IS REQUIRED
            # -----------------------------------------------------------------

            if realized_outcomes_r is None:

                return self._result(
                    False,
                    "REALIZED_R_REQUIRED_FOR_PROMOTION",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            if (
                len(
                    realized_outcomes_r
                )
                != n
            ):

                return self._result(
                    False,
                    "REALIZED_R_LENGTH_MISMATCH",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            realized_r = (
                self._realized_r(
                    realized_outcomes_r
                )
            )

            if realized_r is None:

                return self._result(
                    False,
                    "INVALID_REALIZED_R_VALUES",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                )

            # -----------------------------------------------------------------
            # ECONOMIC SIGNIFICANCE
            # -----------------------------------------------------------------

            (
                improvement_lower_bound,
                challenger_ev,
                champion_ev,
            ) = (
                self._economic_bootstrap(
                    challenger,
                    champion,
                    realized_r,
                )
            )

            if (
                improvement_lower_bound
                <= 0.0
            ):

                self.logger.warning(
                    (
                        "Promotion rejected: "
                        "economic lower bound "
                        "%.6fR/candidate "
                        "(challenger EV %.6f, "
                        "champion EV %.6f)."
                    ),
                    improvement_lower_bound,
                    challenger_ev,
                    champion_ev,
                )

                return self._result(
                    False,
                    (
                        "ECONOMIC_IMPROVEMENT_"
                        "NOT_SIGNIFICANT"
                    ),
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                    improvement_lower_bound,
                )

            # -----------------------------------------------------------------
            # REQUIRE REAL CALIBRATION IMPROVEMENT TOO
            # -----------------------------------------------------------------

            calibration_improved = (
                brier_challenger
                < brier_champion
                or log_loss_challenger
                < log_loss_champion
            )

            if not calibration_improved:

                return self._result(
                    False,
                    "NO_CALIBRATION_IMPROVEMENT",
                    brier_challenger,
                    brier_champion,
                    log_loss_challenger,
                    log_loss_champion,
                    improvement_lower_bound,
                )

            self.logger.info(
                (
                    "Promotion eligibility validated "
                    "on frozen data | "
                    "n=%d | "
                    "Brier %.6f -> %.6f | "
                    "LogLoss %.6f -> %.6f | "
                    "economic lower bound "
                    "%.6fR/candidate"
                ),
                n,
                brier_champion,
                brier_challenger,
                log_loss_champion,
                log_loss_challenger,
                improvement_lower_bound,
            )

            return self._result(
                True,
                "VALIDATED_ON_FROZEN_DATA",
                brier_challenger,
                brier_champion,
                log_loss_challenger,
                log_loss_champion,
                improvement_lower_bound,
            )

        except Exception as exc:

            self.logger.exception(
                (
                    "Promotion validation "
                    "failed closed: %s"
                ),
                exc,
            )

            return self._result(
                False,
                "PROMOTION_VALIDATION_EXCEPTION",
                1.0,
                1.0,
                math.inf,
                math.inf,
            )