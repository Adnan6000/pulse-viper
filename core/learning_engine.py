from __future__ import annotations

import copy
import logging
import threading

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ShadowTrainingResult:
    status: str
    trained_timeframes: tuple[str, ...]
    validation_status: str
    created_at_utc: str
    error: Optional[str] = None


class AsynchronousMultiTimeframeTrainer:
    """
    Shadow-only asynchronous trainer.

    It MAY:
        - deep-copy current model
        - train the copied challenger
        - keep challenger in memory

    It may NOT:
        - replace pipeline.nn_model
        - replace the champion model
        - set pipeline.nn_ready
        - save challenger as live model
        - call legacy _validate_and_promote()
    """

    def __init__(
        self,
        neural_net_model,
        learning_pipeline,
    ):
        self.model = neural_net_model
        self.pipeline = learning_pipeline

        self.logger = getattr(
            learning_pipeline,
            "logger",
            logging.getLogger(
                "PulseViper.AsyncTrainer"
            ),
        )

        self.worker_lock = (
            threading.Lock()
        )

        self._result_lock = (
            threading.RLock()
        )

        self._last_shadow_candidate = (
            None
        )

        self._last_result = (
            ShadowTrainingResult(
                status=(
                    "NOT_STARTED"
                ),
                trained_timeframes=(),
                validation_status=(
                    "NOT_RUN"
                ),
                created_at_utc=(
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            )
        )

    # =========================================================================
    # TRIGGER
    # =========================================================================

    def trigger_background_timeframe_training(
        self,
        historical_market_matrix,
    ) -> bool:
        """
        Start one shadow training worker.

        Returns False if another worker is already active.
        """

        if not self.worker_lock.acquire(
            blocking=False
        ):
            return False

        worker = threading.Thread(
            target=(
                self._async_training_worker_routine
            ),
            args=(
                historical_market_matrix,
            ),
            daemon=True,
            name=(
                "PulseViper-ShadowTrainer"
            ),
        )

        try:
            worker.start()

            return True

        except Exception:
            self.worker_lock.release()

            raise

    # =========================================================================
    # TRAINING WORKER
    # =========================================================================

    def _async_training_worker_routine(
        self,
        historical_market_matrix,
    ) -> None:

        trained_timeframes = []

        try:
            if not isinstance(
                historical_market_matrix,
                Mapping,
            ):
                self._set_result(
                    ShadowTrainingResult(
                        status=(
                            "REJECTED"
                        ),
                        trained_timeframes=(),
                        validation_status=(
                            "NOT_RUN"
                        ),
                        created_at_utc=(
                            self._now_text()
                        ),
                        error=(
                            "INVALID_HISTORICAL_MARKET_MATRIX"
                        ),
                    )
                )

                return

            # -----------------------------------------------------------------
            # COPY CHAMPION
            # -----------------------------------------------------------------

            try:
                candidate_model = (
                    copy.deepcopy(
                        self.model
                    )
                )

            except Exception as exc:
                self._set_result(
                    ShadowTrainingResult(
                        status=(
                            "REJECTED"
                        ),
                        trained_timeframes=(),
                        validation_status=(
                            "NOT_RUN"
                        ),
                        created_at_utc=(
                            self._now_text()
                        ),
                        error=(
                            "MODEL_DEEPCOPY_FAILED:"
                            f"{type(exc).__name__}"
                        ),
                    )
                )

                return

            # -----------------------------------------------------------------
            # TRAIN CHALLENGER ONLY
            # -----------------------------------------------------------------

            for timeframe in (
                "M1",
                "M5",
                "H1",
                "H4",
                "D1",
            ):
                timeframe_data = (
                    historical_market_matrix.get(
                        timeframe
                    )
                )

                if timeframe_data is None:
                    continue

                self.pipeline.train_timeframe_layer(
                    candidate_model,
                    timeframe_data,
                )

                trained_timeframes.append(
                    timeframe
                )

            if not trained_timeframes:
                self._set_result(
                    ShadowTrainingResult(
                        status=(
                            "REJECTED"
                        ),
                        trained_timeframes=(),
                        validation_status=(
                            "NOT_RUN"
                        ),
                        created_at_utc=(
                            self._now_text()
                        ),
                        error=(
                            "NO_TRAINING_DATA"
                        ),
                    )
                )

                return

            # -----------------------------------------------------------------
            # IMPORTANT:
            #
            # DO NOT CALL:
            #
            #     pipeline._validate_and_promote(...)
            #
            # The old function combines validation and live mutation.
            #
            # The candidate remains shadow-only.
            # -----------------------------------------------------------------

            with self._result_lock:
                self._last_shadow_candidate = (
                    candidate_model
                )

                self._last_result = (
                    ShadowTrainingResult(
                        status=(
                            "SHADOW_CANDIDATE_READY"
                        ),
                        trained_timeframes=tuple(
                            trained_timeframes
                        ),
                        validation_status=(
                            "PENDING_CAUSAL_FROZEN_VALIDATION"
                        ),
                        created_at_utc=(
                            self._now_text()
                        ),
                    )
                )

            self.logger.info(
                (
                    "Shadow challenger trained on %s. "
                    "Live champion unchanged; "
                    "causal frozen validation required."
                ),
                ",".join(
                    trained_timeframes
                ),
            )

        except Exception as exc:
            self.logger.exception(
                (
                    "Shadow training failed: %s"
                ),
                exc,
            )

            self._set_result(
                ShadowTrainingResult(
                    status=(
                        "REJECTED"
                    ),
                    trained_timeframes=tuple(
                        trained_timeframes
                    ),
                    validation_status=(
                        "NOT_RUN"
                    ),
                    created_at_utc=(
                        self._now_text()
                    ),
                    error=(
                        "SHADOW_TRAINING_EXCEPTION:"
                        f"{type(exc).__name__}"
                    ),
                )
            )

        finally:
            self.worker_lock.release()

    # =========================================================================
    # SHADOW CANDIDATE API
    # =========================================================================

    def get_last_shadow_candidate(
        self,
    ):
        """
        Return current challenger.

        This does NOT mean the candidate is approved.
        """

        with self._result_lock:
            return (
                self._last_shadow_candidate
            )

    def consume_shadow_candidate(
        self,
    ):
        """
        Return and remove current shadow candidate.

        Helps prevent accidentally processing the same candidate twice.
        """

        with self._result_lock:
            candidate = (
                self._last_shadow_candidate
            )

            self._last_shadow_candidate = (
                None
            )

            return candidate

    def get_last_result(
        self,
    ) -> Dict[str, Any]:

        with self._result_lock:
            result = (
                self._last_result
            )

            return {
                "status": (
                    result.status
                ),

                "trained_timeframes": list(
                    result.trained_timeframes
                ),

                "validation_status": (
                    result.validation_status
                ),

                "created_at_utc": (
                    result.created_at_utc
                ),

                "error": (
                    result.error
                ),
            }

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _now_text() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    def _set_result(
        self,
        result: ShadowTrainingResult,
    ) -> None:

        with self._result_lock:
            self._last_result = (
                result
            )