from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import secrets
import threading
import time

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple


REGISTRY_FILE = "configs/model_registry.json"
REGISTRY_VERSION = 2


@dataclass(frozen=True)
class ModelBundle:
    model_version: str
    feature_schema_hash: str
    model_weights_path: str
    calibrator_params: Dict[str, Any]
    policy_version: int
    timestamp: float
    dataset_id: str

    # Filled/verified by registry.
    weights_sha256: str = ""


@dataclass(frozen=True)
class _PromotionAuthorization:
    bundle_fingerprint: str
    token_hash: str
    weights_sha256: str
    dataset_id: str

    issued_at_utc: datetime
    expires_at_utc: datetime


class ModelRegistry:
    """
    Fail-closed production model registry.

    A challenger can become active only when:

        1. model metadata is real
        2. model file exists under models/
        3. model file SHA-256 is frozen
        4. walk-forward validation passed
        5. PromotionValidator approved challenger
        6. validation dataset matches bundle dataset
        7. short-lived single-use promotion token is presented

    Registry never invents a default champion.
    """

    def __init__(
        self,
        registry_file: str = REGISTRY_FILE,
        allowed_model_root: str = "models",
        history_limit: int = 10,
        authorization_ttl_seconds: int = 300,
    ):
        self.logger = logging.getLogger(
            "PulseViper.ModelRegistry"
        )

        self.registry_file = registry_file

        self.project_root = os.path.realpath(
            os.getcwd()
        )

        self.allowed_model_root = os.path.realpath(
            os.path.join(
                self.project_root,
                allowed_model_root,
            )
        )

        self.history_limit = max(
            1,
            min(
                100,
                int(history_limit),
            ),
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

        self.active_bundle: Optional[
            ModelBundle
        ] = None

        self.history: List[
            ModelBundle
        ] = []

        self._authorizations: Dict[
            str,
            _PromotionAuthorization
        ] = {}

        self._lock = threading.RLock()

        self._last_mtime = 0.0

        self.load_registry(
            force=True
        )

    # =========================================================================
    # BASIC HELPERS
    # =========================================================================

    @staticmethod
    def _now() -> datetime:
        return datetime.now(
            timezone.utc
        )

    @staticmethod
    def _finite(
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

    @staticmethod
    def _validation_eligible(
        result: Any,
    ) -> bool:

        if isinstance(
            result,
            Mapping,
        ):
            return bool(
                result.get(
                    "eligible",
                    False,
                )
            )

        return bool(
            getattr(
                result,
                "eligible",
                False,
            )
        )

    @staticmethod
    def _validation_reason(
        result: Any,
    ) -> str:

        if isinstance(
            result,
            Mapping,
        ):
            return str(
                result.get(
                    "reason",
                    "",
                )
            )

        return str(
            getattr(
                result,
                "reason",
                "",
            )
        )

    # =========================================================================
    # BUNDLE PARSING
    # =========================================================================

    def _bundle_from_mapping(
        self,
        data: Mapping[
            str,
            Any,
        ],
    ) -> Optional[
        ModelBundle
    ]:

        try:
            calibrator = data.get(
                "calibrator_params",
                {},
            )

            if not isinstance(
                calibrator,
                Mapping,
            ):
                return None

            return ModelBundle(
                model_version=str(
                    data.get(
                        "model_version",
                        "",
                    )
                ),

                feature_schema_hash=str(
                    data.get(
                        "feature_schema_hash",
                        "",
                    )
                ),

                model_weights_path=str(
                    data.get(
                        "model_weights_path",
                        "",
                    )
                ),

                calibrator_params=dict(
                    calibrator
                ),

                policy_version=int(
                    data.get(
                        "policy_version",
                        0,
                    )
                ),

                timestamp=float(
                    data.get(
                        "timestamp",
                        0.0,
                    )
                ),

                dataset_id=str(
                    data.get(
                        "dataset_id",
                        "",
                    )
                ),

                weights_sha256=str(
                    data.get(
                        "weights_sha256",
                        "",
                    )
                    or ""
                ),
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    # =========================================================================
    # METADATA VALIDATION
    # =========================================================================

    def _metadata_valid(
        self,
        bundle: ModelBundle,
        require_production_metadata: bool,
    ) -> Tuple[
        bool,
        str,
    ]:

        if not isinstance(
            bundle,
            ModelBundle,
        ):
            return (
                False,
                "INVALID_BUNDLE_TYPE",
            )

        version = str(
            bundle.model_version
            or ""
        ).strip()

        schema_hash = str(
            bundle.feature_schema_hash
            or ""
        ).strip()

        weights_path = str(
            bundle.model_weights_path
            or ""
        ).strip()

        dataset_id = str(
            bundle.dataset_id
            or ""
        ).strip()

        if not version:
            return (
                False,
                "EMPTY_MODEL_VERSION",
            )

        if not schema_hash:
            return (
                False,
                "EMPTY_FEATURE_SCHEMA_HASH",
            )

        if not weights_path:
            return (
                False,
                "EMPTY_MODEL_WEIGHTS_PATH",
            )

        if not dataset_id:
            return (
                False,
                "EMPTY_DATASET_ID",
            )

        if (
            not isinstance(
                bundle.policy_version,
                int,
            )
            or bundle.policy_version
            < 1
        ):
            return (
                False,
                "INVALID_POLICY_VERSION",
            )

        timestamp = self._finite(
            bundle.timestamp
        )

        if timestamp is None:
            return (
                False,
                "INVALID_MODEL_TIMESTAMP",
            )

        try:
            json.dumps(
                bundle.calibrator_params,
                sort_keys=True,
                allow_nan=False,
            )

        except (
            TypeError,
            ValueError,
        ):
            return (
                False,
                "INVALID_CALIBRATOR_PARAMS",
            )

        if require_production_metadata:

            if schema_hash.upper() in {
                "DEFAULT_HASH",
                "UNKNOWN",
                "NONE",
            }:
                return (
                    False,
                    "PLACEHOLDER_FEATURE_SCHEMA_HASH",
                )

            if dataset_id.upper() in {
                "INITIAL_BOOTSTRAP",
                "UNKNOWN",
                "NONE",
            }:
                return (
                    False,
                    "PLACEHOLDER_DATASET_ID",
                )

            if timestamp <= 0.0:
                return (
                    False,
                    "NON_POSITIVE_MODEL_TIMESTAMP",
                )

        return (
            True,
            "VALID",
        )

    # =========================================================================
    # MODEL FILE VALIDATION
    # =========================================================================

    def _resolve_weights_path(
        self,
        model_weights_path: str,
    ) -> Optional[str]:

        raw = str(
            model_weights_path
            or ""
        ).strip()

        if not raw:
            return None

        if os.path.isabs(
            raw
        ):
            resolved = os.path.realpath(
                raw
            )

        else:
            resolved = os.path.realpath(
                os.path.join(
                    self.project_root,
                    raw,
                )
            )

        # Model files must live under ./models
        try:
            common = os.path.commonpath(
                [
                    resolved,
                    self.allowed_model_root,
                ]
            )

        except ValueError:
            return None

        if common != self.allowed_model_root:
            return None

        if not os.path.isfile(
            resolved
        ):
            return None

        try:
            if os.path.getsize(
                resolved
            ) <= 0:
                return None

        except OSError:
            return None

        return resolved

    @staticmethod
    def _hash_file(
        path: str,
    ) -> Optional[str]:

        digest = hashlib.sha256()

        try:
            with open(
                path,
                "rb",
            ) as handle:

                while True:
                    chunk = handle.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    digest.update(
                        chunk
                    )

            return digest.hexdigest()

        except OSError:
            return None

    def _normalized_activatable_bundle(
        self,
        bundle: ModelBundle,
    ) -> Tuple[
        Optional[ModelBundle],
        str,
    ]:

        valid, reason = (
            self._metadata_valid(
                bundle,
                require_production_metadata=True,
            )
        )

        if not valid:
            return (
                None,
                reason,
            )

        resolved = (
            self._resolve_weights_path(
                bundle.model_weights_path
            )
        )

        if resolved is None:
            return (
                None,
                (
                    "MODEL_WEIGHTS_MISSING_"
                    "OR_OUTSIDE_ALLOWED_ROOT"
                ),
            )

        actual_hash = (
            self._hash_file(
                resolved
            )
        )

        if not actual_hash:
            return (
                None,
                "MODEL_WEIGHTS_HASH_FAILED",
            )

        declared_hash = str(
            bundle.weights_sha256
            or ""
        ).strip().lower()

        if (
            declared_hash
            and declared_hash
            != actual_hash
        ):
            return (
                None,
                "MODEL_WEIGHTS_HASH_MISMATCH",
            )

        normalized = replace(
            bundle,

            model_version=str(
                bundle.model_version
            ).strip(),

            feature_schema_hash=str(
                bundle.feature_schema_hash
            ).strip(),

            model_weights_path=(
                os.path.relpath(
                    resolved,
                    self.project_root,
                )
                .replace(
                    "\\",
                    "/",
                )
            ),

            calibrator_params=dict(
                bundle.calibrator_params
            ),

            dataset_id=str(
                bundle.dataset_id
            ).strip(),

            weights_sha256=(
                actual_hash
            ),
        )

        return (
            normalized,
            "VALID",
        )

    # =========================================================================
    # IMMUTABLE BUNDLE FINGERPRINT
    # =========================================================================

    @staticmethod
    def _bundle_fingerprint(
        bundle: ModelBundle,
    ) -> str:

        payload = {
            "model_version": (
                bundle.model_version
            ),

            "feature_schema_hash": (
                bundle.feature_schema_hash
            ),

            "model_weights_path": (
                bundle.model_weights_path
            ),

            "calibrator_params": (
                bundle.calibrator_params
            ),

            "policy_version": (
                bundle.policy_version
            ),

            "timestamp": (
                bundle.timestamp
            ),

            "dataset_id": (
                bundle.dataset_id
            ),

            "weights_sha256": (
                bundle.weights_sha256
            ),
        }

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

        return hashlib.sha256(
            canonical.encode(
                "utf-8"
            )
        ).hexdigest()

    # =========================================================================
    # LOAD REGISTRY
    # =========================================================================

    def load_registry(
        self,
        force: bool = False,
    ) -> None:

        with self._lock:

            if not os.path.exists(
                self.registry_file
            ):
                self.active_bundle = (
                    None
                )

                self.history = []

                self._last_mtime = (
                    0.0
                )

                self.logger.warning(
                    (
                        "Model registry missing; "
                        "no active champion is assumed."
                    )
                )

                return

            try:
                mtime = os.path.getmtime(
                    self.registry_file
                )

                if (
                    not force
                    and self._last_mtime
                    and mtime
                    == self._last_mtime
                ):
                    return

                with open(
                    self.registry_file,
                    "r",
                    encoding="utf-8",
                ) as handle:

                    data = json.load(
                        handle
                    )

                if not isinstance(
                    data,
                    Mapping,
                ):
                    raise ValueError(
                        (
                            "registry root "
                            "must be an object"
                        )
                    )

                # -------------------------------------------------------------
                # HISTORY
                # -------------------------------------------------------------

                loaded_history: List[
                    ModelBundle
                ] = []

                raw_history = data.get(
                    "history",
                    [],
                )

                if isinstance(
                    raw_history,
                    list,
                ):

                    for item in raw_history:

                        if not isinstance(
                            item,
                            Mapping,
                        ):
                            continue

                        parsed = (
                            self._bundle_from_mapping(
                                item
                            )
                        )

                        if parsed is None:
                            continue

                        valid, _ = (
                            self._metadata_valid(
                                parsed,
                                require_production_metadata=False,
                            )
                        )

                        if valid:
                            loaded_history.append(
                                parsed
                            )

                # -------------------------------------------------------------
                # ACTIVE
                # -------------------------------------------------------------

                active = None

                raw_active = data.get(
                    "active"
                )

                if isinstance(
                    raw_active,
                    Mapping,
                ):

                    parsed = (
                        self._bundle_from_mapping(
                            raw_active
                        )
                    )

                    if parsed is not None:

                        (
                            normalized,
                            reason,
                        ) = (
                            self._normalized_activatable_bundle(
                                parsed
                            )
                        )

                        if normalized is not None:
                            active = (
                                normalized
                            )

                        else:
                            self.logger.error(
                                (
                                    "Configured active "
                                    "model rejected: %s"
                                ),
                                reason,
                            )

                self.active_bundle = (
                    active
                )

                self.history = (
                    loaded_history[
                        -self.history_limit:
                    ]
                )

                self._last_mtime = (
                    mtime
                )

            except Exception as exc:

                self.active_bundle = (
                    None
                )

                self.history = []

                self.logger.exception(
                    (
                        "Failed to load model "
                        "registry; no active "
                        "champion: %s"
                    ),
                    exc,
                )

    # =========================================================================
    # READ API
    # =========================================================================

    def get_active_bundle(
        self,
    ) -> Optional[
        ModelBundle
    ]:

        self.load_registry()

        with self._lock:

            if self.active_bundle is None:
                return None

            (
                normalized,
                reason,
            ) = (
                self._normalized_activatable_bundle(
                    self.active_bundle
                )
            )

            if normalized is None:

                self.logger.error(
                    (
                        "Active model became "
                        "invalid: %s"
                    ),
                    reason,
                )

                self.active_bundle = (
                    None
                )

                return None

            self.active_bundle = (
                normalized
            )

            return normalized

    def get_history(
        self,
    ) -> List[
        ModelBundle
    ]:

        self.load_registry()

        with self._lock:
            return list(
                self.history
            )

    def get_status(
        self,
    ) -> Dict[str, Any]:

        active = (
            self.get_active_bundle()
        )

        with self._lock:

            return {
                "registry_version": (
                    REGISTRY_VERSION
                ),

                "active": (
                    asdict(
                        active
                    )
                    if active
                    else None
                ),

                "history_count": len(
                    self.history
                ),

                "promotion_authorizations": len(
                    self._authorizations
                ),

                "allowed_model_root": (
                    os.path.relpath(
                        self.allowed_model_root,
                        self.project_root,
                    )
                    .replace(
                        "\\",
                        "/",
                    )
                ),
            }

    # =========================================================================
    # AUTHORIZE PROMOTION
    # =========================================================================

    def authorize_bundle_promotion(
        self,
        bundle: ModelBundle,
        promotion_validation: Any,
        walk_forward_result: Mapping[
            str,
            Any,
        ],
        validation_dataset_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> Optional[str]:
        """
        Create short-lived single-use authorization.

        This does NOT activate the challenger.
        """

        with self._lock:

            (
                normalized,
                reason,
            ) = (
                self._normalized_activatable_bundle(
                    bundle
                )
            )

            if normalized is None:

                self.logger.error(
                    (
                        "Bundle authorization "
                        "rejected: %s"
                    ),
                    reason,
                )

                return None

            # -------------------------------------------------------------
            # Dataset must be exactly the frozen validation dataset.
            # -------------------------------------------------------------

            if (
                str(
                    validation_dataset_id
                    or ""
                ).strip()
                != normalized.dataset_id
            ):

                self.logger.error(
                    (
                        "Bundle authorization "
                        "rejected: validation "
                        "dataset mismatch."
                    )
                )

                return None

            # -------------------------------------------------------------
            # Walk-forward must validate stability only.
            # -------------------------------------------------------------

            if not bool(
                walk_forward_result.get(
                    "validation_passed",
                    False,
                )
            ):

                self.logger.info(
                    (
                        "Bundle authorization "
                        "rejected: walk-forward "
                        "did not pass."
                    )
                )

                return None

            if bool(
                walk_forward_result.get(
                    "passed_promotion",
                    False,
                )
            ):

                self.logger.error(
                    (
                        "Bundle authorization "
                        "rejected: walk-forward "
                        "cannot claim promotion."
                    )
                )

                return None

            # -------------------------------------------------------------
            # Challenger-vs-champion validator.
            # -------------------------------------------------------------

            if not self._validation_eligible(
                promotion_validation
            ):

                self.logger.info(
                    (
                        "Bundle authorization "
                        "rejected by PromotionValidator: %s"
                    ),
                    self._validation_reason(
                        promotion_validation
                    ),
                )

                return None

            # -------------------------------------------------------------
            # Immutable versioning.
            # -------------------------------------------------------------

            if (
                self.active_bundle
                is not None
                and self.active_bundle.model_version
                == normalized.model_version
            ):

                self.logger.error(
                    (
                        "Bundle authorization "
                        "rejected: model version "
                        "already active."
                    )
                )

                return None

            if any(
                item.model_version
                == normalized.model_version
                for item
                in self.history
            ):

                self.logger.error(
                    (
                        "Bundle authorization "
                        "rejected: model version "
                        "already in history."
                    )
                )

                return None

            fingerprint = (
                self._bundle_fingerprint(
                    normalized
                )
            )

            raw_token = (
                secrets.token_urlsafe(
                    32
                )
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

            issued = (
                self._now()
            )

            self._authorizations[
                fingerprint
            ] = (
                _PromotionAuthorization(
                    bundle_fingerprint=(
                        fingerprint
                    ),

                    token_hash=(
                        token_hash
                    ),

                    weights_sha256=(
                        normalized.weights_sha256
                    ),

                    dataset_id=(
                        normalized.dataset_id
                    ),

                    issued_at_utc=(
                        issued
                    ),

                    expires_at_utc=(
                        issued
                        + timedelta(
                            seconds=ttl
                        )
                    ),
                )
            )

            self.logger.info(
                (
                    "Model bundle authorized "
                    "for one-time promotion | "
                    "version=%s dataset=%s hash=%s"
                ),
                normalized.model_version,
                normalized.dataset_id,
                normalized.weights_sha256[
                    :12
                ],
            )

            return raw_token

    # =========================================================================
    # PROMOTE
    # =========================================================================

    def promote_bundle(
        self,
        bundle: ModelBundle,
        promotion_token: Optional[
            str
        ] = None,
    ) -> bool:
        """
        Activate a validated model.

        Backward compatibility:
            promote_bundle(bundle)

        still exists, but now fails closed because token is mandatory.
        """

        with self._lock:

            (
                normalized,
                reason,
            ) = (
                self._normalized_activatable_bundle(
                    bundle
                )
            )

            if normalized is None:

                self.logger.error(
                    (
                        "Model promotion "
                        "rejected: %s"
                    ),
                    reason,
                )

                return False

            fingerprint = (
                self._bundle_fingerprint(
                    normalized
                )
            )

            authorization = (
                self._authorizations.get(
                    fingerprint
                )
            )

            if authorization is None:

                self.logger.error(
                    (
                        "Model promotion rejected: "
                        "no validation authorization."
                    )
                )

                return False

            if (
                self._now()
                >= authorization.expires_at_utc
            ):

                self._authorizations.pop(
                    fingerprint,
                    None,
                )

                self.logger.warning(
                    (
                        "Model promotion rejected: "
                        "authorization expired."
                    )
                )

                return False

            if not promotion_token:

                self.logger.error(
                    (
                        "Model promotion rejected: "
                        "token required."
                    )
                )

                return False

            supplied_hash = hashlib.sha256(
                str(
                    promotion_token
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
                        "Model promotion rejected: "
                        "invalid token."
                    )
                )

                return False

            # -------------------------------------------------------------
            # File cannot change between validation and promotion.
            # -------------------------------------------------------------

            if (
                normalized.weights_sha256
                != authorization.weights_sha256
            ):

                self.logger.error(
                    (
                        "Model promotion rejected: "
                        "weights changed after validation."
                    )
                )

                return False

            if (
                normalized.dataset_id
                != authorization.dataset_id
            ):

                self.logger.error(
                    (
                        "Model promotion rejected: "
                        "dataset changed after validation."
                    )
                )

                return False

            # -------------------------------------------------------------
            # Immutable version IDs.
            # -------------------------------------------------------------

            if (
                self.active_bundle
                is not None
                and self.active_bundle.model_version
                == normalized.model_version
            ):

                self.logger.error(
                    (
                        "Model promotion rejected: "
                        "version already active."
                    )
                )

                return False

            if any(
                item.model_version
                == normalized.model_version
                for item
                in self.history
            ):

                self.logger.error(
                    (
                        "Model promotion rejected: "
                        "version already exists "
                        "in history."
                    )
                )

                return False

            previous_active = (
                self.active_bundle
            )

            previous_history = list(
                self.history
            )

            new_history = list(
                self.history
            )

            # -------------------------------------------------------------
            # Preserve previous champion only if it is still valid.
            # -------------------------------------------------------------

            if previous_active is not None:

                (
                    old_normalized,
                    old_reason,
                ) = (
                    self._normalized_activatable_bundle(
                        previous_active
                    )
                )

                if old_normalized is not None:

                    new_history.append(
                        old_normalized
                    )

                else:

                    self.logger.warning(
                        (
                            "Previous active model "
                            "excluded from rollback "
                            "history: %s"
                        ),
                        old_reason,
                    )

            self.active_bundle = (
                normalized
            )

            self.history = (
                new_history[
                    -self.history_limit:
                ]
            )

            # -------------------------------------------------------------
            # Atomic persistence.
            # -------------------------------------------------------------

            try:
                self._save_registry_locked()

            except Exception as exc:

                self.active_bundle = (
                    previous_active
                )

                self.history = (
                    previous_history
                )

                self.logger.exception(
                    (
                        "Model promotion "
                        "persistence failed: %s"
                    ),
                    exc,
                )

                return False

            # Token becomes unusable only after persistence succeeds.
            self._authorizations.pop(
                fingerprint,
                None,
            )

            self.logger.warning(
                (
                    "Validated model PROMOTED | "
                    "version=%s dataset=%s hash=%s"
                ),
                normalized.model_version,
                normalized.dataset_id,
                normalized.weights_sha256[
                    :12
                ],
            )

            return True

    # =========================================================================
    # ROLLBACK
    # =========================================================================

    def rollback(
        self,
    ) -> bool:
        """
        Rollback is a safety operation.

        It does not require promotion authorization.
        Invalid/missing historical models are skipped.
        """

        with self._lock:

            if not self.history:

                self.logger.error(
                    (
                        "Rollback failed: "
                        "no model history available."
                    )
                )

                return False

            previous_active = (
                self.active_bundle
            )

            previous_history = list(
                self.history
            )

            remaining = list(
                self.history
            )

            candidate = None

            while remaining:

                raw_candidate = (
                    remaining.pop()
                )

                (
                    normalized,
                    reason,
                ) = (
                    self._normalized_activatable_bundle(
                        raw_candidate
                    )
                )

                if normalized is not None:

                    candidate = (
                        normalized
                    )

                    break

                self.logger.error(
                    (
                        "Skipping invalid "
                        "rollback model "
                        "version=%s reason=%s"
                    ),
                    raw_candidate.model_version,
                    reason,
                )

            if candidate is None:

                self.logger.error(
                    (
                        "Rollback failed: no "
                        "valid historical model."
                    )
                )

                return False

            self.active_bundle = (
                candidate
            )

            self.history = (
                remaining
            )

            try:
                self._save_registry_locked()

            except Exception as exc:

                self.active_bundle = (
                    previous_active
                )

                self.history = (
                    previous_history
                )

                self.logger.exception(
                    (
                        "Rollback persistence "
                        "failed: %s"
                    ),
                    exc,
                )

                return False

            self.logger.warning(
                (
                    "Model rollback complete | "
                    "active=%s hash=%s"
                ),
                candidate.model_version,
                candidate.weights_sha256[
                    :12
                ],
            )

            return True

    # =========================================================================
    # SAVE
    # =========================================================================

    def _save_registry_locked(
        self,
    ) -> None:
        """
        Atomically persist registry.

        Caller must hold self._lock.
        """

        directory = os.path.dirname(
            self.registry_file
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True,
            )

        temp_file = (
            self.registry_file
            + ".tmp"
        )

        data = {
            "registry_version": (
                REGISTRY_VERSION
            ),

            "active": (
                asdict(
                    self.active_bundle
                )
                if self.active_bundle
                else None
            ),

            "history": [
                asdict(
                    bundle
                )
                for bundle
                in self.history
            ],

            "updated_at_utc": (
                self._now()
                .isoformat()
            ),
        }

        try:

            with open(
                temp_file,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    data,
                    handle,
                    indent=2,
                    allow_nan=False,
                )

                handle.flush()

                try:
                    os.fsync(
                        handle.fileno()
                    )

                except OSError:
                    pass

            os.replace(
                temp_file,
                self.registry_file,
            )

            try:
                self._last_mtime = (
                    os.path.getmtime(
                        self.registry_file
                    )
                )

            except OSError:
                self._last_mtime = (
                    time.time()
                )

        except Exception:

            try:
                if os.path.exists(
                    temp_file
                ):
                    os.remove(
                        temp_file
                    )

            except OSError:
                pass

            raise


# Global coordination instance.
model_registry = ModelRegistry()