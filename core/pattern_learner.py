from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim

from core.experience_memory import ExperienceMemory
from core.feature_extractor import FeatureExtractor


class PulseViperNeuralNet(nn.Module):
    """Production-compatible probability network."""

    def __init__(self, input_dim: int = 30, hidden_dim: int = 32):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),

            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),

            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),

            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 1:
            x = x.unsqueeze(0)
            return self.network(x).squeeze(0)

        return self.network(x)


class KMeansClustering:
    """
    Small deterministic K-Means.

    Used only for descriptive regime/cluster IDs.
    It is NOT a production probability model.
    """

    def __init__(self, k: int = 4):
        self.k = max(1, int(k))

        self.centroids: np.ndarray = np.empty(
            (0, 0),
            dtype=float,
        )

    def fit(
        self,
        X: np.ndarray,
        max_iters: int = 20,
    ) -> None:

        X = np.asarray(
            X,
            dtype=float,
        )

        if X.ndim != 2 or len(X) == 0:
            self.centroids = np.empty(
                (0, 0),
                dtype=float,
            )
            return

        finite_mask = np.isfinite(
            X
        ).all(axis=1)

        X = X[
            finite_mask
        ]

        if len(X) == 0:
            self.centroids = np.empty(
                (0, 0),
                dtype=float,
            )
            return

        if len(X) < self.k:
            pad = np.repeat(
                X[-1:, :],
                self.k - len(X),
                axis=0,
            )

            self.centroids = np.concatenate(
                [
                    X.copy(),
                    pad,
                ],
                axis=0,
            )

            return

        # Deterministic initialization.
        # No random promotion/training behavior.
        seed_indices = np.linspace(
            0,
            len(X) - 1,
            self.k,
            dtype=int,
        )

        centroids = X[
            seed_indices
        ].copy()

        for _ in range(
            max(
                1,
                int(
                    max_iters
                ),
            )
        ):
            distances = np.linalg.norm(
                (
                    X[
                        :,
                        None,
                        :,
                    ]
                    - centroids[
                        None,
                        :,
                        :,
                    ]
                ),
                axis=2,
            )

            labels = np.argmin(
                distances,
                axis=1,
            )

            updated = (
                centroids.copy()
            )

            for cluster_idx in range(
                self.k
            ):
                members = X[
                    labels
                    == cluster_idx
                ]

                if len(members):
                    updated[
                        cluster_idx
                    ] = np.mean(
                        members,
                        axis=0,
                    )

            if np.allclose(
                updated,
                centroids,
                atol=1e-12,
                rtol=0.0,
            ):
                centroids = (
                    updated
                )
                break

            centroids = (
                updated
            )

        self.centroids = (
            centroids
        )

    def predict(
        self,
        point: np.ndarray,
    ) -> int:

        point = np.asarray(
            point,
            dtype=float,
        )

        if (
            self.centroids.size == 0
            or point.ndim != 1
            or self.centroids.ndim != 2
            or self.centroids.shape[
                1
            ]
            != point.shape[
                0
            ]
            or not np.isfinite(
                point
            ).all()
        ):
            return 0

        distances = np.linalg.norm(
            (
                self.centroids
                - point
            ),
            axis=1,
        )

        return int(
            np.argmin(
                distances
            )
        )


class NaiveBayesClassifier:
    """
    Legacy research classifier.

    It remains available so old code importing the class does not break.

    IMPORTANT:
        PatternLearner never uses this classifier as a production
        confidence source anymore.

    Production confidence must come from an active ModelRegistry champion.
    """

    def __init__(self):
        self.class_priors = {
            0: 0.5,
            1: 0.5,
        }

        self.discrete_conds: Dict[
            int,
            Dict[
                str,
                Dict[
                    str,
                    float,
                ],
            ],
        ] = {}

        self.continuous_conds: Dict[
            int,
            Dict[
                str,
                Tuple[
                    float,
                    float,
                ],
            ],
        ] = {}

    def fit(
        self,
        X_discrete: List[
            Dict[str, str]
        ],
        X_continuous: List[
            Dict[str, float]
        ],
        y: List[int],
    ) -> None:

        n = len(
            y
        )

        if (
            n < 20
            or len(
                X_discrete
            )
            != n
            or len(
                X_continuous
            )
            != n
        ):
            return

        classes = (
            0,
            1,
        )

        positives = int(
            sum(
                int(
                    value
                )
                for value
                in y
            )
        )

        self.class_priors[
            1
        ] = (
            positives
            / n
        )

        self.class_priors[
            0
        ] = (
            1.0
            - self.class_priors[
                1
            ]
        )

        # -------------------------------------------------------------
        # DISCRETE FEATURES
        # -------------------------------------------------------------

        self.discrete_conds = {
            c: {}
            for c
            in classes
        }

        discrete_keys = (
            list(
                X_discrete[
                    0
                ].keys()
            )
            if X_discrete
            else []
        )

        for key in discrete_keys:

            vocabulary = sorted(
                {
                    str(
                        row.get(
                            key,
                            "",
                        )
                    )
                    for row
                    in X_discrete
                }
            )

            vocab_size = max(
                1,
                len(
                    vocabulary
                ),
            )

            for c in classes:

                indices = [
                    i
                    for i, label
                    in enumerate(
                        y
                    )
                    if int(
                        label
                    )
                    == c
                ]

                denominator = (
                    len(
                        indices
                    )
                    + vocab_size
                )

                counts: Dict[
                    str,
                    int,
                ] = defaultdict(
                    int
                )

                for i in indices:
                    counts[
                        str(
                            X_discrete[
                                i
                            ].get(
                                key,
                                "",
                            )
                        )
                    ] += 1

                self.discrete_conds[
                    c
                ][
                    key
                ] = {
                    value: (
                        (
                            counts[
                                value
                            ]
                            + 1.0
                        )
                        / max(
                            1.0,
                            denominator,
                        )
                    )
                    for value
                    in vocabulary
                }

        # -------------------------------------------------------------
        # CONTINUOUS FEATURES
        # -------------------------------------------------------------

        self.continuous_conds = {
            c: {}
            for c
            in classes
        }

        continuous_keys = (
            list(
                X_continuous[
                    0
                ].keys()
            )
            if X_continuous
            else []
        )

        for key in continuous_keys:

            for c in classes:

                values = []

                for i, label in enumerate(
                    y
                ):
                    if int(
                        label
                    ) != c:
                        continue

                    try:
                        value = float(
                            X_continuous[
                                i
                            ].get(
                                key,
                                0.0,
                            )
                        )

                        if math.isfinite(
                            value
                        ):
                            values.append(
                                value
                            )

                    except Exception:
                        continue

                if len(
                    values
                ) >= 2:

                    mean = float(
                        np.mean(
                            values
                        )
                    )

                    std = max(
                        float(
                            np.std(
                                values
                            )
                        ),
                        1e-5,
                    )

                elif values:

                    mean = float(
                        values[
                            0
                        ]
                    )

                    std = 1.0

                else:
                    mean = 0.0
                    std = 1.0

                self.continuous_conds[
                    c
                ][
                    key
                ] = (
                    mean,
                    std,
                )

    def predict_probability(
        self,
        x_discrete: Dict[
            str,
            str,
        ],
        x_continuous: Dict[
            str,
            float,
        ],
    ) -> float:

        posteriors: Dict[
            int,
            float,
        ] = {}

        for c in (
            0,
            1,
        ):
            score = math.log(
                max(
                    self.class_priors.get(
                        c,
                        0.5,
                    ),
                    1e-12,
                )
            )

            for key, value in x_discrete.items():

                table = (
                    self.discrete_conds
                    .get(
                        c,
                        {},
                    )
                    .get(
                        key,
                        {},
                    )
                )

                score += math.log(
                    max(
                        table.get(
                            str(
                                value
                            ),
                            1e-3,
                        ),
                        1e-12,
                    )
                )

            for key, raw_value in x_continuous.items():

                params = (
                    self.continuous_conds
                    .get(
                        c,
                        {},
                    )
                    .get(
                        key
                    )
                )

                if params is None:
                    continue

                value = float(
                    raw_value
                )

                mean, std = (
                    params
                )

                exponent = -(
                    (
                        value
                        - mean
                    )
                    ** 2
                ) / (
                    2.0
                    * std
                    * std
                )

                pdf = math.exp(
                    exponent
                ) / (
                    math.sqrt(
                        2.0
                        * math.pi
                    )
                    * std
                )

                score += math.log(
                    max(
                        pdf,
                        1e-12,
                    )
                )

            posteriors[
                c
            ] = score

        max_score = max(
            posteriors.values()
        )

        p0 = math.exp(
            posteriors[
                0
            ]
            - max_score
        )

        p1 = math.exp(
            posteriors[
                1
            ]
            - max_score
        )

        return float(
            p1
            / max(
                p0 + p1,
                1e-12,
            )
        )


class ChartPatternDetector:
    """
    Causal chart-pattern detector.

    Only candles already present in supplied frames are inspected.

    No pattern is confirmed using candles after the decision candle.
    """

    @staticmethod
    def _empty(
        name: str,
    ) -> Dict[
        str,
        Any,
    ]:

        return {
            "detected": False,
            "confidence": 0.0,
            "level": None,
            "name": name,
        }

    @staticmethod
    def detect(
        df_m1: pd.DataFrame,
        df_m5: Optional[
            pd.DataFrame
        ] = None,
        df_h1: Optional[
            pd.DataFrame
        ] = None,
        window: int = 5,
    ) -> Dict[
        str,
        Dict[
            str,
            Any,
        ],
    ]:

        names = (
            "ORDER_BLOCK_BULL",
            "ORDER_BLOCK_BEAR",
            "FVG_BULL",
            "FVG_BEAR",
            "LIQUIDITY_SWEEP_LOW",
            "LIQUIDITY_SWEEP_HIGH",
            "MSS_BULLISH",
            "MSS_BEARISH",
            "DISPLACEMENT_BULL",
            "DISPLACEMENT_BEAR",
        )

        results = {
            name: (
                ChartPatternDetector
                ._empty(
                    name
                )
            )
            for name
            in names
        }

        try:
            if (
                df_m1 is None
                or len(
                    df_m1
                ) < 5
            ):
                return results

            m1 = df_m1

            highs = (
                m1[
                    "high"
                ]
                .astype(
                    float
                )
                .to_numpy()
            )

            lows = (
                m1[
                    "low"
                ]
                .astype(
                    float
                )
                .to_numpy()
            )

            opens = (
                m1[
                    "open"
                ]
                .astype(
                    float
                )
                .to_numpy()
            )

            closes = (
                m1[
                    "close"
                ]
                .astype(
                    float
                )
                .to_numpy()
            )

            # ---------------------------------------------------------
            # FVG
            # ---------------------------------------------------------

            if len(
                m1
            ) >= 3:

                if highs[
                    -3
                ] < lows[
                    -1
                ]:

                    level = float(
                        (
                            highs[
                                -3
                            ]
                            + lows[
                                -1
                            ]
                        )
                        / 2.0
                    )

                    results[
                        "FVG_BULL"
                    ] = {
                        "detected": True,
                        "confidence": 0.75,
                        "level": level,
                        "name": "FVG_BULL",
                    }

                if lows[
                    -3
                ] > highs[
                    -1
                ]:

                    level = float(
                        (
                            lows[
                                -3
                            ]
                            + highs[
                                -1
                            ]
                        )
                        / 2.0
                    )

                    results[
                        "FVG_BEAR"
                    ] = {
                        "detected": True,
                        "confidence": 0.75,
                        "level": level,
                        "name": "FVG_BEAR",
                    }

            # ---------------------------------------------------------
            # SWEEP / MSS
            # ---------------------------------------------------------

            lookback = max(
                3,
                min(
                    int(
                        window
                    )
                    + 5,
                    len(
                        m1
                    )
                    - 1,
                ),
            )

            if lookback >= 3:

                prior_high = float(
                    np.max(
                        highs[
                            -lookback:
                            -1
                        ]
                    )
                )

                prior_low = float(
                    np.min(
                        lows[
                            -lookback:
                            -1
                        ]
                    )
                )

                if (
                    lows[
                        -1
                    ]
                    < prior_low
                    and closes[
                        -1
                    ]
                    > prior_low
                ):

                    results[
                        "LIQUIDITY_SWEEP_LOW"
                    ] = {
                        "detected": True,
                        "confidence": 0.8,
                        "level": prior_low,
                        "name": (
                            "LIQUIDITY_SWEEP_LOW"
                        ),
                    }

                if (
                    highs[
                        -1
                    ]
                    > prior_high
                    and closes[
                        -1
                    ]
                    < prior_high
                ):

                    results[
                        "LIQUIDITY_SWEEP_HIGH"
                    ] = {
                        "detected": True,
                        "confidence": 0.8,
                        "level": prior_high,
                        "name": (
                            "LIQUIDITY_SWEEP_HIGH"
                        ),
                    }

                if closes[
                    -1
                ] > prior_high:

                    results[
                        "MSS_BULLISH"
                    ] = {
                        "detected": True,
                        "confidence": 0.7,
                        "level": prior_high,
                        "name": "MSS_BULLISH",
                    }

                if closes[
                    -1
                ] < prior_low:

                    results[
                        "MSS_BEARISH"
                    ] = {
                        "detected": True,
                        "confidence": 0.7,
                        "level": prior_low,
                        "name": "MSS_BEARISH",
                    }

            # ---------------------------------------------------------
            # DISPLACEMENT
            # ---------------------------------------------------------

            ranges = (
                highs
                - lows
            )

            if len(
                ranges
            ) >= 10:

                baseline = float(
                    np.median(
                        ranges[
                            -10:
                            -1
                        ]
                    )
                )

                last_range = float(
                    ranges[
                        -1
                    ]
                )

                if (
                    baseline > 0.0
                    and last_range
                    >= 1.5
                    * baseline
                ):

                    if closes[
                        -1
                    ] > opens[
                        -1
                    ]:

                        results[
                            "DISPLACEMENT_BULL"
                        ] = {
                            "detected": True,
                            "confidence": 0.7,
                            "level": float(
                                closes[
                                    -1
                                ]
                            ),
                            "name": (
                                "DISPLACEMENT_BULL"
                            ),
                        }

                    elif closes[
                        -1
                    ] < opens[
                        -1
                    ]:

                        results[
                            "DISPLACEMENT_BEAR"
                        ] = {
                            "detected": True,
                            "confidence": 0.7,
                            "level": float(
                                closes[
                                    -1
                                ]
                            ),
                            "name": (
                                "DISPLACEMENT_BEAR"
                            ),
                        }

            # ---------------------------------------------------------
            # ORDER-BLOCK CONTEXT
            # ---------------------------------------------------------

            ob_df = (
                df_h1
                if (
                    df_h1 is not None
                    and len(
                        df_h1
                    ) >= 5
                )
                else df_m5
            )

            if (
                ob_df is not None
                and len(
                    ob_df
                ) >= 5
            ):

                recent = (
                    ob_df.iloc[
                        -8:
                    ]
                    .copy()
                )

                o = (
                    recent[
                        "open"
                    ]
                    .astype(
                        float
                    )
                    .to_numpy()
                )

                c = (
                    recent[
                        "close"
                    ]
                    .astype(
                        float
                    )
                    .to_numpy()
                )

                h = (
                    recent[
                        "high"
                    ]
                    .astype(
                        float
                    )
                    .to_numpy()
                )

                l = (
                    recent[
                        "low"
                    ]
                    .astype(
                        float
                    )
                    .to_numpy()
                )

                for idx in range(
                    len(
                        recent
                    )
                    - 2,
                    0,
                    -1,
                ):

                    if (
                        c[
                            idx - 1
                        ]
                        < o[
                            idx - 1
                        ]
                        and c[
                            idx
                        ]
                        > o[
                            idx
                        ]
                    ):

                        results[
                            "ORDER_BLOCK_BULL"
                        ] = {
                            "detected": True,
                            "confidence": 0.65,
                            "level": float(
                                l[
                                    idx - 1
                                ]
                            ),
                            "name": (
                                "ORDER_BLOCK_BULL"
                            ),
                        }

                        break

                for idx in range(
                    len(
                        recent
                    )
                    - 2,
                    0,
                    -1,
                ):

                    if (
                        c[
                            idx - 1
                        ]
                        > o[
                            idx - 1
                        ]
                        and c[
                            idx
                        ]
                        < o[
                            idx
                        ]
                    ):

                        results[
                            "ORDER_BLOCK_BEAR"
                        ] = {
                            "detected": True,
                            "confidence": 0.65,
                            "level": float(
                                h[
                                    idx - 1
                                ]
                            ),
                            "name": (
                                "ORDER_BLOCK_BEAR"
                            ),
                        }

                        break

        except Exception:
            return results

        return results

    @staticmethod
    def get_summary(
        detected: Dict[
            str,
            Dict[
                str,
                Any,
            ],
        ],
    ) -> Tuple[
        List[str],
        float,
        Optional[str],
    ]:

        bull_patterns = {
            "ORDER_BLOCK_BULL",
            "FVG_BULL",
            "LIQUIDITY_SWEEP_LOW",
            "MSS_BULLISH",
            "DISPLACEMENT_BULL",
        }

        bear_patterns = {
            "ORDER_BLOCK_BEAR",
            "FVG_BEAR",
            "LIQUIDITY_SWEEP_HIGH",
            "MSS_BEARISH",
            "DISPLACEMENT_BEAR",
        }

        found = [
            name
            for name, payload
            in detected.items()
            if bool(
                payload.get(
                    "detected"
                )
            )
        ]

        if not found:
            return (
                [],
                0.0,
                None,
            )

        confidence = max(
            float(
                detected[
                    name
                ].get(
                    "confidence",
                    0.0,
                )
            )
            for name
            in found
        )

        bull_count = sum(
            name
            in bull_patterns
            for name
            in found
        )

        bear_count = sum(
            name
            in bear_patterns
            for name
            in found
        )

        direction: Optional[
            str
        ] = None

        if bull_count > bear_count:
            direction = (
                "bullish"
            )

        elif bear_count > bull_count:
            direction = (
                "bearish"
            )

        return (
            found,
            round(
                confidence,
                3,
            ),
            direction,
        )


@dataclass(frozen=True)
class _CausalSample:
    feature_vector: np.ndarray

    target: float
    realized_r: float

    decision_index: int
    label_end_index: int

    decision_time_utc: str

    outcome_type: str
    split: str


class PatternLearner:
    """
    Causal, shadow-first PatternLearner.

    Production confidence comes ONLY from the active ModelRegistry champion.

    Historical training methods create causal shadow datasets.

    They never:
        - overwrite the live neural network
        - save challenger as champion
        - fit synthetic outcomes into production confidence
        - use still-open higher-timeframe candles
        - let training labels cross validation/holdout boundaries
    """

    CAUSAL_LABEL_VERSION = (
        "v5.0-causal"
    )

    TRAIN_FRACTION = 0.70
    VALIDATION_FRACTION = 0.15

    DEFAULT_MAX_HOLDING_BARS = (
        100
    )

    def __init__(
        self,
        memory: ExperienceMemory,
    ):
        self.memory = memory

        self.logger = logging.getLogger(
            "PulseViper.PatternLearner"
        )

        self.patterns: Dict[
            str,
            List[
                Dict[
                    str,
                    Any,
                ]
            ],
        ] = defaultdict(
            list
        )

        self.market_regimes: Dict[
            str,
            Dict[
                str,
                Any,
            ],
        ] = {}

        self.training_stats: Dict[
            str,
            Dict[
                str,
                Any,
            ],
        ] = {}

        self.kmeans = (
            KMeansClustering(
                k=4
            )
        )

        # Legacy classifier retained for import/API compatibility only.
        self.classifier = (
            NaiveBayesClassifier()
        )

        self._nb_production_enabled = (
            False
        )

        self.model_lock = (
            threading.RLock()
        )

        self._append_lock = (
            threading.RLock()
        )

        self._shadow_lock = (
            threading.RLock()
        )

        self.nn_model = (
            PulseViperNeuralNet(
                input_dim=len(
                    FeatureExtractor
                    .FEATURE_NAMES
                )
            )
        )

        self.nn_optimizer = (
            optim.Adam(
                self.nn_model.parameters(),
                lr=0.003,
                weight_decay=1e-4,
            )
        )

        self.nn_criterion = (
            nn.BCELoss()
        )

        self.nn_ready = False

        self.active_model_version: Optional[
            str
        ] = None

        self._last_shadow_candidate = (
            None
        )

        self._last_causal_dataset: Dict[
            str,
            Any,
        ] = {}

        self._last_training_result: Dict[
            str,
            Any,
        ] = {}

        self.min_pattern_occurrence = (
            2
        )

        self.confidence_threshold = (
            0.5
        )

        self.load_patterns()
        self.load_nn_model()

    # =========================================================================
    # READINESS
    # =========================================================================

    @property
    def nb_ready(
        self,
    ) -> bool:
        """
        Legacy Naive Bayes is explicitly non-production.
        """

        return False

    # =========================================================================
    # FRAME NORMALIZATION
    # =========================================================================

    @staticmethod
    def _normalize_frame(
        frame: Optional[
            pd.DataFrame
        ],
    ) -> Optional[
        pd.DataFrame
    ]:

        if (
            frame is None
            or len(
                frame
            )
            == 0
        ):
            return None

        required = {
            "open",
            "high",
            "low",
            "close",
        }

        if not required.issubset(
            frame.columns
        ):
            return None

        df = (
            frame.copy()
        )

        try:
            index = pd.to_datetime(
                df.index,
                utc=True,
            )

        except Exception:
            return None

        df.index = (
            index
        )

        df = (
            df[
                ~df.index.duplicated(
                    keep="last"
                )
            ]
            .sort_index()
        )

        for column in required:

            df[
                column
            ] = pd.to_numeric(
                df[
                    column
                ],
                errors="coerce",
            )

        df = df.dropna(
            subset=list(
                required
            )
        )

        if len(
            df
        ) < 3:
            return None

        return df

    @staticmethod
    def _infer_bar_seconds(
        df: pd.DataFrame,
    ) -> Optional[int]:

        if (
            df is None
            or len(
                df
            ) < 3
        ):
            return None

        deltas = (
            np.diff(
                df.index.view(
                    "int64"
                )
            )
            / 1_000_000_000.0
        )

        deltas = deltas[
            np.isfinite(
                deltas
            )
            & (
                deltas
                > 0.0
            )
        ]

        if len(
            deltas
        ) == 0:
            return None

        seconds = int(
            round(
                float(
                    np.median(
                        deltas
                    )
                )
            )
        )

        return (
            seconds
            if seconds > 0
            else None
        )

    @classmethod
    def _closed_frame(
        cls,
        frame: Optional[
            pd.DataFrame
        ],
    ) -> Optional[
        pd.DataFrame
    ]:

        df = cls._normalize_frame(
            frame
        )

        if df is None:
            return None

        seconds = cls._infer_bar_seconds(
            df
        )

        if seconds is None:
            return None

        now_ns = pd.Timestamp.now(
            tz="UTC"
        ).value

        available_ns = (
            df.index.view(
                "int64"
            )
            + (
                seconds
                * 1_000_000_000
            )
        )

        mask = (
            available_ns
            <= now_ns
        )

        df = df.loc[
            mask
        ]

        return (
            df
            if len(
                df
            ) >= 3
            else None
        )

    @staticmethod
    def _last_nonzero(
        values: Sequence[
            Any
        ] | np.ndarray,
        end_index: int,
        lookback: int,
    ) -> int:

        start = max(
            0,
            (
                end_index
                - max(
                    1,
                    int(
                        lookback
                    ),
                )
                + 1
            ),
        )

        for idx in range(
            end_index,
            start - 1,
            -1,
        ):
            try:
                value = int(
                    values[
                        idx
                    ]
                )

            except Exception:
                continue

            if value != 0:
                return value

        return 0

    @staticmethod
    def _finite(
        value: Any,
    ) -> Optional[
        float
    ]:

        try:
            result = float(
                value
            )

            if math.isfinite(
                result
            ):
                return result

        except (
            TypeError,
            ValueError,
        ):
            pass

        return None

    # =========================================================================
    # VISUAL PATTERNS
    # =========================================================================

    def detect_visual_patterns(
        self,
        df: pd.DataFrame,
    ) -> List[str]:

        if (
            df is None
            or len(
                df
            ) < 2
        ):
            return []

        try:
            detected = (
                ChartPatternDetector
                .detect(
                    df
                )
            )

            (
                found,
                _,
                _,
            ) = (
                ChartPatternDetector
                .get_summary(
                    detected
                )
            )

            last = df.iloc[
                -1
            ]

            prev = df.iloc[
                -2
            ]

            body_last = float(
                last[
                    "close"
                ]
                - last[
                    "open"
                ]
            )

            body_prev = float(
                prev[
                    "close"
                ]
                - prev[
                    "open"
                ]
            )

            if (
                body_prev < 0.0
                and body_last > 0.0
                and float(
                    last[
                        "close"
                    ]
                )
                >= float(
                    prev[
                        "open"
                    ]
                )
                and float(
                    last[
                        "open"
                    ]
                )
                <= float(
                    prev[
                        "close"
                    ]
                )
            ):

                found.append(
                    "BULLISH_ENGULFING"
                )

            elif (
                body_prev > 0.0
                and body_last < 0.0
                and float(
                    last[
                        "close"
                    ]
                )
                <= float(
                    prev[
                        "open"
                    ]
                )
                and float(
                    last[
                        "open"
                    ]
                )
                >= float(
                    prev[
                        "close"
                    ]
                )
            ):

                found.append(
                    "BEARISH_ENGULFING"
                )

            return sorted(
                set(
                    found
                )
            )

        except Exception:
            return []

    def detect_visual_patterns_numpy(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
    ) -> List[str]:

        if len(
            closes
        ) < 2:
            return []

        frame = pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
            }
        )

        return (
            self.detect_visual_patterns(
                frame
            )
        )

    # =========================================================================
    # FEATURE HELPERS
    # =========================================================================

    def _quantize_smc_state(
        self,
        features: Dict[
            str,
            Any,
        ],
    ) -> str:

        bias_val = int(
            features.get(
                "active_bias",
                0,
            )
            or 0
        )

        price = float(
            features.get(
                "price",
                features.get(
                    "close",
                    0.0,
                ),
            )
            or 0.0
        )

        support = float(
            features.get(
                "support",
                0.0,
            )
            or 0.0
        )

        resistance = float(
            features.get(
                "resistance",
                0.0,
            )
            or 0.0
        )

        if (
            resistance > support
            and support > 0.0
        ):

            pct = (
                (
                    price
                    - support
                )
                / max(
                    (
                        resistance
                        - support
                    ),
                    1e-12,
                )
            )

            if pct < 0.35:
                zone = (
                    "DISCOUNT"
                )

            elif pct > 0.65:
                zone = (
                    "PREMIUM"
                )

            else:
                zone = (
                    "EQUILIBRIUM"
                )

        else:
            zone = (
                "EQUILIBRIUM"
            )

        sweep = int(
            features.get(
                "liq_sweep_type",
                0,
            )
            or 0
        )

        mss = int(
            features.get(
                "mss_signal",
                0,
            )
            or 0
        )

        if (
            sweep != 0
            and mss != 0
        ):
            setup = (
                "SHARP_TURN"
            )

        elif mss != 0:
            setup = (
                "MSS_ONLY"
            )

        elif sweep != 0:
            setup = (
                "SWEEP_ONLY"
            )

        else:
            setup = (
                "CONTINUATION"
            )

        quantized = {
            "bias": (
                "BULLISH"
                if bias_val == 1
                else (
                    "BEARISH"
                    if bias_val == -1
                    else "NEUTRAL"
                )
            ),

            "zone": zone,

            "fvg": str(
                features.get(
                    "fvg_class",
                    "none",
                )
            ).upper(),

            "setup": setup,
        }

        return str(
            sorted(
                quantized.items()
            )
        )

    @staticmethod
    def extract_temporal_embeddings(
        timestamp_str_or_float,
    ) -> list:

        return (
            FeatureExtractor
            .extract_temporal_embeddings(
                timestamp_str_or_float
            )
        )

    @staticmethod
    def extract_nn_features(
        features: dict,
    ) -> np.ndarray:

        return (
            FeatureExtractor
            .extract_nn_features(
                features
            )
        )

    # =========================================================================
    # CAUSAL OUTCOME RESOLVER
    # =========================================================================

    def _outcome_resolver(
        self,
    ):
        from core.outcome_labeler import (
            OutcomeResolver,
        )

        version = getattr(
            OutcomeResolver,
            "LABEL_VERSION",
            None,
        )

        if (
            version
            != self.CAUSAL_LABEL_VERSION
        ):
            raise RuntimeError(
                (
                    "CAUSAL_OUTCOME_RESOLVER_REQUIRED:"
                    f"expected="
                    f"{self.CAUSAL_LABEL_VERSION},"
                    f"got={version}"
                )
            )

        return OutcomeResolver

    @staticmethod
    def _bars_to_records(
        df: pd.DataFrame,
    ) -> List[
        Dict[
            str,
            float,
        ]
    ]:

        columns = [
            "open",
            "high",
            "low",
            "close",
        ]

        records: List[
            Dict[
                str,
                float,
            ]
        ] = []

        for row in df[
            columns
        ].itertuples(
            index=False,
            name=None,
        ):

            records.append(
                {
                    "open": float(
                        row[
                            0
                        ]
                    ),

                    "high": float(
                        row[
                            1
                        ]
                    ),

                    "low": float(
                        row[
                            2
                        ]
                    ),

                    "close": float(
                        row[
                            3
                        ]
                    ),
                }
            )

        return records

    def _resolve_label(
        self,
        candidate_id: str,
        action: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        future_frame: pd.DataFrame,
    ):

        if (
            future_frame is None
            or len(
                future_frame
            )
            == 0
        ):
            return None

        OutcomeResolver = (
            self._outcome_resolver()
        )

        # No fabricated costs.
        #
        # Historical spread/commission/slippage must be supplied by a
        # higher-quality replay source later if they are actually known.
        return OutcomeResolver.resolve(
            candidate_id=(
                candidate_id
            ),

            entry_price=float(
                entry_price
            ),

            stop_price=float(
                stop_price
            ),

            target_price=float(
                target_price
            ),

            action=str(
                action
            ).upper(),

            bars_future=(
                self._bars_to_records(
                    future_frame
                )
            ),

            lower_tf_bars=None,

            spread_points=0.0,
            point=0.0,

            commission_r=0.0,
            slippage_r=0.0,

            force_time_exit=False,
        )

    # =========================================================================
    # CHRONOLOGICAL SPLITS
    # =========================================================================

    @classmethod
    def _split_boundaries(
        cls,
        n: int,
    ) -> Tuple[
        int,
        int,
    ]:

        train_end = int(
            n
            * cls.TRAIN_FRACTION
        )

        validation_end = int(
            n
            * (
                cls.TRAIN_FRACTION
                + cls.VALIDATION_FRACTION
            )
        )

        train_end = max(
            1,
            min(
                train_end,
                n - 2,
            ),
        )

        validation_end = max(
            train_end + 1,
            min(
                validation_end,
                n - 1,
            ),
        )

        return (
            train_end,
            validation_end,
        )

    @classmethod
    def _split_for_index(
        cls,
        index: int,
        n: int,
    ) -> Tuple[
        str,
        int,
    ]:

        (
            train_end,
            validation_end,
        ) = (
            cls._split_boundaries(
                n
            )
        )

        if index < train_end:

            return (
                "train",
                train_end,
            )

        if index < validation_end:

            return (
                "validation",
                validation_end,
            )

        return (
            "holdout",
            n,
        )

    # =========================================================================
    # TRADE GEOMETRY
    # =========================================================================

    @classmethod
    def _geometry(
        cls,
        action: str,
        entry_price: float,
        atr: float,
        support: Optional[
            float
        ],
        resistance: Optional[
            float
        ],
        rr: float = 1.5,
    ) -> Optional[
        Tuple[
            float,
            float,
        ]
    ]:

        if (
            not math.isfinite(
                entry_price
            )
            or entry_price <= 0.0
            or not math.isfinite(
                atr
            )
            or atr <= 0.0
        ):
            return None

        action = str(
            action
        ).upper()

        rr = max(
            1.0,
            float(
                rr
            ),
        )

        if action == "BUY":

            stop = (
                entry_price
                - (
                    1.5
                    * atr
                )
            )

            if (
                support is not None
                and math.isfinite(
                    support
                )
                and support
                < entry_price
            ):

                distance = (
                    entry_price
                    - support
                )

                if (
                    0.5
                    * atr
                    <= distance
                    <= 3.0
                    * atr
                ):

                    stop = (
                        support
                        - (
                            0.25
                            * atr
                        )
                    )

            risk = (
                entry_price
                - stop
            )

            if risk <= 0.0:
                return None

            target = (
                entry_price
                + (
                    rr
                    * risk
                )
            )

            return (
                float(
                    stop
                ),
                float(
                    target
                ),
            )

        if action == "SELL":

            stop = (
                entry_price
                + (
                    1.5
                    * atr
                )
            )

            if (
                resistance
                is not None
                and math.isfinite(
                    resistance
                )
                and resistance
                > entry_price
            ):

                distance = (
                    resistance
                    - entry_price
                )

                if (
                    0.5
                    * atr
                    <= distance
                    <= 3.0
                    * atr
                ):

                    stop = (
                        resistance
                        + (
                            0.25
                            * atr
                        )
                    )

            risk = (
                stop
                - entry_price
            )

            if risk <= 0.0:
                return None

            target = (
                entry_price
                - (
                    rr
                    * risk
                )
            )

            return (
                float(
                    stop
                ),
                float(
                    target
                ),
            )

        return None

    # =========================================================================
    # SINGLE-TIMEFRAME CAUSAL DATASET
    # =========================================================================

    def _build_single_timeframe_samples(
        self,
        timeframe_data: pd.DataFrame,
        max_holding_bars: int,
    ) -> List[
        _CausalSample
    ]:

        from utils.smc_indicators import (
            SMCIndicators,
        )

        from utils.settings_manager import (
            settings_manager,
        )

        df = self._closed_frame(
            timeframe_data
        )

        if (
            df is None
            or len(
                df
            ) < 80
        ):
            return []

        swing_window = max(
            1,
            int(
                settings_manager.get(
                    "smc_swing_window",
                    3,
                )
                or 3
            ),
        )

        feat = (
            SMCIndicators
            .compute_smc_features(
                df,
                window=(
                    swing_window
                ),
            )
        )

        feat = feat.reindex(
            df.index
        )

        n = len(
            df
        )

        if len(
            feat
        ) != n:
            return []

        opens = (
            df[
                "open"
            ]
            .astype(
                float
            )
            .to_numpy()
        )

        biases = (
            feat[
                "active_bias"
            ]
            .fillna(
                0
            )
            .to_numpy()
            if "active_bias"
            in feat
            else np.zeros(
                n
            )
        )

        sweeps = (
            feat[
                "liq_sweep_type"
            ]
            .fillna(
                0
            )
            .to_numpy()
            if "liq_sweep_type"
            in feat
            else np.zeros(
                n
            )
        )

        mss_values = (
            feat[
                "mss_signal"
            ]
            .fillna(
                0
            )
            .to_numpy()
            if "mss_signal"
            in feat
            else np.zeros(
                n
            )
        )

        atr_values = (
            pd.to_numeric(
                feat[
                    "atr"
                ],
                errors="coerce",
            ).to_numpy()
            if "atr"
            in feat
            else np.full(
                n,
                np.nan,
            )
        )

        volatility_values = (
            pd.to_numeric(
                feat[
                    "volatility"
                ],
                errors="coerce",
            ).to_numpy()
            if "volatility"
            in feat
            else np.zeros(
                n
            )
        )

        support_values = (
            pd.to_numeric(
                feat[
                    "support"
                ],
                errors="coerce",
            ).to_numpy()
            if "support"
            in feat
            else np.full(
                n,
                np.nan,
            )
        )

        resistance_values = (
            pd.to_numeric(
                feat[
                    "resistance"
                ],
                errors="coerce",
            ).to_numpy()
            if "resistance"
            in feat
            else np.full(
                n,
                np.nan,
            )
        )

        fvg_values = (
            feat[
                "fvg_class"
            ].to_numpy()
            if "fvg_class"
            in feat
            else np.array(
                [
                    "none"
                ]
                * n,
                dtype=object,
            )
        )

        optional_signal_columns = {
            "ob_reaction_signal": (
                feat[
                    "ob_reaction_signal"
                ]
                .fillna(
                    0
                )
                .to_numpy()
                if "ob_reaction_signal"
                in feat
                else np.zeros(
                    n
                )
            ),

            "sr_reaction_signal": (
                feat[
                    "sr_reaction_signal"
                ]
                .fillna(
                    0
                )
                .to_numpy()
                if "sr_reaction_signal"
                in feat
                else np.zeros(
                    n
                )
            ),

            "retest_pullback_signal": (
                feat[
                    "retest_pullback_signal"
                ]
                .fillna(
                    0
                )
                .to_numpy()
                if "retest_pullback_signal"
                in feat
                else np.zeros(
                    n
                )
            ),

            "trend_shift_signal": (
                feat[
                    "trend_shift_signal"
                ]
                .fillna(
                    0
                )
                .to_numpy()
                if "trend_shift_signal"
                in feat
                else np.zeros(
                    n
                )
            ),
        }

        samples: List[
            _CausalSample
        ] = []

        max_holding_bars = max(
            5,
            min(
                5000,
                int(
                    max_holding_bars
                ),
            ),
        )

        # -------------------------------------------------------------
        # Signal on closed bar i.
        # Earliest entry: next bar open i+1.
        # -------------------------------------------------------------

        for i in range(
            max(
                20,
                swing_window
                * 4,
            ),
            n - 1,
        ):

            (
                split_name,
                region_end,
            ) = (
                self._split_for_index(
                    i,
                    n,
                )
            )

            entry_index = (
                i + 1
            )

            if (
                entry_index
                >= region_end
            ):
                continue

            try:
                bias = (
                    int(
                        biases[
                            i
                        ]
                    )
                    if np.isfinite(
                        float(
                            biases[
                                i
                            ]
                        )
                    )
                    else 0
                )

            except Exception:
                bias = 0

            sweep = (
                self._last_nonzero(
                    sweeps,
                    i,
                    10,
                )
            )

            mss = (
                self._last_nonzero(
                    mss_values,
                    i,
                    5,
                )
            )

            bullish = (
                bias == 1
                and (
                    sweep == 1
                    or mss == 1
                )
            )

            bearish = (
                bias == -1
                and (
                    sweep == -1
                    or mss == -1
                )
            )

            # Preserve neutral/range mean-reversion setup.
            if (
                bias == 0
                and not bullish
                and not bearish
            ):

                bullish = (
                    sweep == 1
                    or mss == 1
                )

                bearish = (
                    sweep == -1
                    or mss == -1
                )

            if bullish == bearish:
                continue

            action = (
                "BUY"
                if bullish
                else "SELL"
            )

            entry_price = (
                self._finite(
                    opens[
                        entry_index
                    ]
                )
            )

            atr = (
                self._finite(
                    atr_values[
                        i
                    ]
                )
            )

            if (
                entry_price is None
                or atr is None
            ):
                continue

            support = (
                self._finite(
                    support_values[
                        i
                    ]
                )
            )

            resistance = (
                self._finite(
                    resistance_values[
                        i
                    ]
                )
            )

            geometry = (
                self._geometry(
                    action,
                    entry_price,
                    atr,
                    support,
                    resistance,
                    rr=1.5,
                )
            )

            if geometry is None:
                continue

            (
                stop_price,
                target_price,
            ) = (
                geometry
            )

            # Critical:
            #
            # future data is capped at this chronological split boundary.
            #
            # Training labels can NEVER use validation candles.
            # Validation labels can NEVER use holdout candles.
            future_end = min(
                region_end,
                (
                    entry_index
                    + max_holding_bars
                ),
            )

            future = df.iloc[
                entry_index:
                future_end
            ]

            if len(
                future
            ) == 0:
                continue

            candidate_id = (
                f"STF:"
                f"{split_name}:"
                f"{df.index[i].isoformat()}:"
                f"{action}"
            )

            try:
                outcome = (
                    self._resolve_label(
                        candidate_id,
                        action,
                        entry_price,
                        stop_price,
                        target_price,
                        future,
                    )
                )

            except RuntimeError:
                raise

            except Exception as exc:

                self.logger.debug(
                    (
                        "Outcome resolution "
                        "failed: %s"
                    ),
                    exc,
                )

                continue

            if outcome is None:
                continue

            if outcome.outcome_type in {
                "AMBIGUOUS_SAME_BAR",
                "CENSORED",
                "INVALID_GEOMETRY",
            }:
                continue

            if (
                outcome.net_r is None
                or not math.isfinite(
                    float(
                        outcome.net_r
                    )
                )
            ):
                continue

            holding_bars = max(
                1,
                int(
                    outcome.holding_bars
                ),
            )

            label_end_index = min(
                region_end - 1,
                (
                    entry_index
                    + holding_bars
                    - 1
                ),
            )

            feature_dict = {
                "active_bias": (
                    bias
                ),

                "liq_sweep_type": (
                    sweep
                ),

                "mss_signal": (
                    mss
                ),

                "fvg_class": str(
                    fvg_values[
                        i
                    ]
                ),

                "volatility": float(
                    volatility_values[
                        i
                    ]
                    if np.isfinite(
                        volatility_values[
                            i
                        ]
                    )
                    else 0.0
                ),

                "atr_pct": (
                    atr
                    / max(
                        entry_price,
                        1e-12,
                    )
                ),

                "rvol": 1.0,

                "buy_pressure": (
                    50.0
                ),

                "sell_pressure": (
                    50.0
                ),

                "ob_reaction_signal": float(
                    optional_signal_columns[
                        "ob_reaction_signal"
                    ][
                        i
                    ]
                ),

                "sr_reaction_signal": float(
                    optional_signal_columns[
                        "sr_reaction_signal"
                    ][
                        i
                    ]
                ),

                "retest_pullback_signal": float(
                    optional_signal_columns[
                        "retest_pullback_signal"
                    ][
                        i
                    ]
                ),

                "trend_shift_signal": float(
                    optional_signal_columns[
                        "trend_shift_signal"
                    ][
                        i
                    ]
                ),

                "candidate_strategy": (
                    "SMC_CONCEPTS"
                ),

                "candidate_action": (
                    action
                ),

                "timestamp": float(
                    df.index[
                        i
                    ].timestamp()
                ),
            }

            try:
                vector = (
                    self.extract_nn_features(
                        feature_dict
                    )
                )

            except ValueError:
                continue

            samples.append(
                _CausalSample(
                    feature_vector=(
                        vector
                    ),

                    target=(
                        1.0
                        if float(
                            outcome.net_r
                        )
                        > 0.0
                        else 0.0
                    ),

                    realized_r=float(
                        outcome.net_r
                    ),

                    decision_index=(
                        i
                    ),

                    label_end_index=(
                        label_end_index
                    ),

                    decision_time_utc=(
                        df.index[
                            i
                        ].isoformat()
                    ),

                    outcome_type=str(
                        outcome.outcome_type
                    ),

                    split=(
                        split_name
                    ),
                )
            )

        return samples

    # =========================================================================
    # MULTI-TIMEFRAME CAUSAL DATASET
    # =========================================================================

    def _build_mtf_samples(
        self,
        df_htf: pd.DataFrame,
        df_context: pd.DataFrame,
        df_ltf: pd.DataFrame,
        max_holding_bars: int,
    ) -> List[
        _CausalSample
    ]:

        from utils.smc_indicators import (
            SMCIndicators,
        )

        from utils.settings_manager import (
            settings_manager,
        )

        htf = self._closed_frame(
            df_htf
        )

        context = self._closed_frame(
            df_context
        )

        ltf = self._closed_frame(
            df_ltf
        )

        if (
            htf is None
            or context is None
            or ltf is None
            or len(
                ltf
            ) < 80
        ):
            return []

        htf_seconds = (
            self._infer_bar_seconds(
                htf
            )
        )

        context_seconds = (
            self._infer_bar_seconds(
                context
            )
        )

        ltf_seconds = (
            self._infer_bar_seconds(
                ltf
            )
        )

        if (
            not htf_seconds
            or not context_seconds
            or not ltf_seconds
        ):
            return []

        swing_window = max(
            1,
            int(
                settings_manager.get(
                    "smc_swing_window",
                    3,
                )
                or 3
            ),
        )

        htf_feat = (
            SMCIndicators
            .compute_smc_features(
                htf,
                window=(
                    swing_window
                ),
            )
            .reindex(
                htf.index
            )
        )

        context_feat = (
            SMCIndicators
            .compute_smc_features(
                context,
                window=(
                    swing_window
                ),
            )
            .reindex(
                context.index
            )
        )

        ltf_feat = (
            SMCIndicators
            .compute_smc_features(
                ltf,
                window=(
                    swing_window
                ),
            )
            .reindex(
                ltf.index
            )
        )

        # -------------------------------------------------------------
        # CRITICAL MTF AVAILABILITY
        #
        # H1 candle opened 12:00 is not available at 12:15.
        # It becomes available at 13:00.
        # -------------------------------------------------------------

        htf_available_ns = (
            htf.index.view(
                "int64"
            )
            + (
                htf_seconds
                * 1_000_000_000
            )
        )

        context_available_ns = (
            context.index.view(
                "int64"
            )
            + (
                context_seconds
                * 1_000_000_000
            )
        )

        htf_biases = (
            htf_feat[
                "active_bias"
            ]
            .fillna(
                0
            )
            .to_numpy()
            if "active_bias"
            in htf_feat
            else np.zeros(
                len(
                    htf
                )
            )
        )

        context_sweeps = (
            context_feat[
                "liq_sweep_type"
            ]
            .fillna(
                0
            )
            .to_numpy()
            if "liq_sweep_type"
            in context_feat
            else np.zeros(
                len(
                    context
                )
            )
        )

        ltf_mss = (
            ltf_feat[
                "mss_signal"
            ]
            .fillna(
                0
            )
            .to_numpy()
            if "mss_signal"
            in ltf_feat
            else np.zeros(
                len(
                    ltf
                )
            )
        )

        atr_values = (
            pd.to_numeric(
                ltf_feat[
                    "atr"
                ],
                errors="coerce",
            ).to_numpy()
            if "atr"
            in ltf_feat
            else np.full(
                len(
                    ltf
                ),
                np.nan,
            )
        )

        volatility_values = (
            pd.to_numeric(
                ltf_feat[
                    "volatility"
                ],
                errors="coerce",
            ).to_numpy()
            if "volatility"
            in ltf_feat
            else np.zeros(
                len(
                    ltf
                )
            )
        )

        support_values = (
            pd.to_numeric(
                ltf_feat[
                    "support"
                ],
                errors="coerce",
            ).to_numpy()
            if "support"
            in ltf_feat
            else np.full(
                len(
                    ltf
                ),
                np.nan,
            )
        )

        resistance_values = (
            pd.to_numeric(
                ltf_feat[
                    "resistance"
                ],
                errors="coerce",
            ).to_numpy()
            if "resistance"
            in ltf_feat
            else np.full(
                len(
                    ltf
                ),
                np.nan,
            )
        )

        fvg_values = (
            ltf_feat[
                "fvg_class"
            ].to_numpy()
            if "fvg_class"
            in ltf_feat
            else np.array(
                [
                    "none"
                ]
                * len(
                    ltf
                ),
                dtype=object,
            )
        )

        opens = (
            ltf[
                "open"
            ]
            .astype(
                float
            )
            .to_numpy()
        )

        n = len(
            ltf
        )

        max_holding_bars = max(
            5,
            min(
                5000,
                int(
                    max_holding_bars
                ),
            ),
        )

        samples: List[
            _CausalSample
        ] = []

        for i in range(
            max(
                20,
                swing_window
                * 4,
            ),
            n - 1,
        ):

            (
                split_name,
                region_end,
            ) = (
                self._split_for_index(
                    i,
                    n,
                )
            )

            entry_index = (
                i + 1
            )

            if (
                entry_index
                >= region_end
            ):
                continue

            # Signal becomes known at LTF close.
            decision_ns = (
                ltf.index[
                    i
                ].value
                + (
                    ltf_seconds
                    * 1_000_000_000
                )
            )

            htf_idx = int(
                np.searchsorted(
                    htf_available_ns,
                    decision_ns,
                    side="right",
                )
                - 1
            )

            context_idx = int(
                np.searchsorted(
                    context_available_ns,
                    decision_ns,
                    side="right",
                )
                - 1
            )

            if (
                htf_idx < 0
                or context_idx < 0
            ):
                continue

            try:
                htf_bias = (
                    int(
                        htf_biases[
                            htf_idx
                        ]
                    )
                    if np.isfinite(
                        float(
                            htf_biases[
                                htf_idx
                            ]
                        )
                    )
                    else 0
                )

            except Exception:
                htf_bias = 0

            context_sweep = (
                self._last_nonzero(
                    context_sweeps,
                    context_idx,
                    10,
                )
            )

            mss = (
                self._last_nonzero(
                    ltf_mss,
                    i,
                    5,
                )
            )

            bullish = (
                htf_bias == 1
                and (
                    context_sweep == 1
                    or mss == 1
                )
            )

            bearish = (
                htf_bias == -1
                and (
                    context_sweep == -1
                    or mss == -1
                )
            )

            if bullish == bearish:
                continue

            action = (
                "BUY"
                if bullish
                else "SELL"
            )

            entry_price = (
                self._finite(
                    opens[
                        entry_index
                    ]
                )
            )

            atr = (
                self._finite(
                    atr_values[
                        i
                    ]
                )
            )

            if (
                entry_price is None
                or atr is None
            ):
                continue

            support = (
                self._finite(
                    support_values[
                        i
                    ]
                )
            )

            resistance = (
                self._finite(
                    resistance_values[
                        i
                    ]
                )
            )

            geometry = (
                self._geometry(
                    action,
                    entry_price,
                    atr,
                    support,
                    resistance,
                    rr=1.5,
                )
            )

            if geometry is None:
                continue

            (
                stop_price,
                target_price,
            ) = (
                geometry
            )

            future_end = min(
                region_end,
                (
                    entry_index
                    + max_holding_bars
                ),
            )

            future = ltf.iloc[
                entry_index:
                future_end
            ]

            if len(
                future
            ) == 0:
                continue

            candidate_id = (
                f"MTF:"
                f"{split_name}:"
                f"{ltf.index[i].isoformat()}:"
                f"{action}"
            )

            try:
                outcome = (
                    self._resolve_label(
                        candidate_id,
                        action,
                        entry_price,
                        stop_price,
                        target_price,
                        future,
                    )
                )

            except RuntimeError:
                raise

            except Exception as exc:

                self.logger.debug(
                    (
                        "MTF outcome resolution "
                        "failed: %s"
                    ),
                    exc,
                )

                continue

            if outcome is None:
                continue

            if outcome.outcome_type in {
                "AMBIGUOUS_SAME_BAR",
                "CENSORED",
                "INVALID_GEOMETRY",
            }:
                continue

            if (
                outcome.net_r is None
                or not math.isfinite(
                    float(
                        outcome.net_r
                    )
                )
            ):
                continue

            holding_bars = max(
                1,
                int(
                    outcome.holding_bars
                ),
            )

            label_end_index = min(
                region_end - 1,
                (
                    entry_index
                    + holding_bars
                    - 1
                ),
            )

            feature_dict = {
                "active_bias": (
                    htf_bias
                ),

                "liq_sweep_type": (
                    context_sweep
                ),

                "mss_signal": (
                    mss
                ),

                "fvg_class": str(
                    fvg_values[
                        i
                    ]
                ),

                "volatility": float(
                    volatility_values[
                        i
                    ]
                    if np.isfinite(
                        volatility_values[
                            i
                        ]
                    )
                    else 0.0
                ),

                "atr_pct": (
                    atr
                    / max(
                        entry_price,
                        1e-12,
                    )
                ),

                "rvol": 1.0,

                "buy_pressure": (
                    50.0
                ),

                "sell_pressure": (
                    50.0
                ),

                "ob_reaction_signal": float(
                    ltf_feat[
                        "ob_reaction_signal"
                    ].iloc[
                        i
                    ]
                    if (
                        "ob_reaction_signal"
                        in ltf_feat
                        and pd.notna(
                            ltf_feat[
                                "ob_reaction_signal"
                            ].iloc[
                                i
                            ]
                        )
                    )
                    else 0.0
                ),

                "sr_reaction_signal": float(
                    ltf_feat[
                        "sr_reaction_signal"
                    ].iloc[
                        i
                    ]
                    if (
                        "sr_reaction_signal"
                        in ltf_feat
                        and pd.notna(
                            ltf_feat[
                                "sr_reaction_signal"
                            ].iloc[
                                i
                            ]
                        )
                    )
                    else 0.0
                ),

                "retest_pullback_signal": float(
                    ltf_feat[
                        "retest_pullback_signal"
                    ].iloc[
                        i
                    ]
                    if (
                        "retest_pullback_signal"
                        in ltf_feat
                        and pd.notna(
                            ltf_feat[
                                "retest_pullback_signal"
                            ].iloc[
                                i
                            ]
                        )
                    )
                    else 0.0
                ),

                "trend_shift_signal": float(
                    ltf_feat[
                        "trend_shift_signal"
                    ].iloc[
                        i
                    ]
                    if (
                        "trend_shift_signal"
                        in ltf_feat
                        and pd.notna(
                            ltf_feat[
                                "trend_shift_signal"
                            ].iloc[
                                i
                            ]
                        )
                    )
                    else 0.0
                ),

                "candidate_strategy": (
                    "SMC_CONCEPTS"
                ),

                "candidate_action": (
                    action
                ),

                "timestamp": float(
                    ltf.index[
                        i
                    ].timestamp()
                ),
            }

            try:
                vector = (
                    self.extract_nn_features(
                        feature_dict
                    )
                )

            except ValueError:
                continue

            samples.append(
                _CausalSample(
                    feature_vector=(
                        vector
                    ),

                    target=(
                        1.0
                        if float(
                            outcome.net_r
                        )
                        > 0.0
                        else 0.0
                    ),

                    realized_r=float(
                        outcome.net_r
                    ),

                    decision_index=(
                        i
                    ),

                    label_end_index=(
                        label_end_index
                    ),

                    decision_time_utc=(
                        ltf.index[
                            i
                        ].isoformat()
                    ),

                    outcome_type=str(
                        outcome.outcome_type
                    ),

                    split=(
                        split_name
                    ),
                )
            )

        return samples

    # =========================================================================
    # DATASET OUTPUT
    # =========================================================================

    @staticmethod
    def _samples_to_dataset(
        samples: Sequence[
            _CausalSample
        ],
    ) -> Dict[
        str,
        Any,
    ]:

        if not samples:

            return {
                "features": (
                    np.empty(
                        (
                            0,
                            len(
                                FeatureExtractor
                                .FEATURE_NAMES
                            ),
                        ),
                        dtype=np.float32,
                    )
                ),

                "targets": (
                    np.empty(
                        (
                            0,
                            1,
                        ),
                        dtype=np.float32,
                    )
                ),

                "realized_r": (
                    np.empty(
                        (
                            0,
                        ),
                        dtype=np.float32,
                    )
                ),

                "metadata": [],
            }

        return {
            "features": (
                np.asarray(
                    [
                        sample.feature_vector
                        for sample
                        in samples
                    ],
                    dtype=np.float32,
                )
            ),

            "targets": (
                np.asarray(
                    [
                        [
                            sample.target
                        ]
                        for sample
                        in samples
                    ],
                    dtype=np.float32,
                )
            ),

            "realized_r": (
                np.asarray(
                    [
                        sample.realized_r
                        for sample
                        in samples
                    ],
                    dtype=np.float32,
                )
            ),

            "metadata": [
                {
                    "decision_index": (
                        sample.decision_index
                    ),

                    "label_end_index": (
                        sample.label_end_index
                    ),

                    "decision_time_utc": (
                        sample.decision_time_utc
                    ),

                    "outcome_type": (
                        sample.outcome_type
                    ),

                    "split": (
                        sample.split
                    ),
                }
                for sample
                in samples
            ],
        }

    def extract_causal_dataset(
        self,
        timeframe_data: pd.DataFrame,
        split: str = "all",
        max_holding_bars: int = (
            DEFAULT_MAX_HOLDING_BARS
        ),
    ) -> Dict[
        str,
        Any,
    ]:

        samples = (
            self._build_single_timeframe_samples(
                timeframe_data,
                max_holding_bars=(
                    max_holding_bars
                ),
            )
        )

        split = (
            str(
                split
            )
            .lower()
            .strip()
        )

        if split != "all":

            if split not in {
                "train",
                "validation",
                "holdout",
            }:

                raise ValueError(
                    (
                        "split must be "
                        "train, validation, "
                        "holdout, or all"
                    )
                )

            samples = [
                sample
                for sample
                in samples
                if sample.split
                == split
            ]

        dataset = (
            self._samples_to_dataset(
                samples
            )
        )

        dataset[
            "label_version"
        ] = (
            self.CAUSAL_LABEL_VERSION
        )

        dataset[
            "cost_assumption"
        ] = (
            "ZERO_EXPLICIT_COSTS_"
            "UNLESS_REPLAY_SUPPLIES_"
            "REAL_COSTS"
        )

        return dataset

    def extract_vectorized_features(
        self,
        timeframe_data: pd.DataFrame,
        split: str = "train",
    ) -> Tuple[
        torch.Tensor,
        torch.Tensor,
    ]:
        """
        Compatibility API.

        Default is TRAIN only.

        Validation and final holdout are never returned to the
        asynchronous trainer by default.
        """

        try:
            dataset = (
                self.extract_causal_dataset(
                    timeframe_data,
                    split=(
                        split
                    ),
                )
            )

            features = dataset[
                "features"
            ]

            targets = dataset[
                "targets"
            ]

            if len(
                features
            ) == 0:

                return (
                    torch.empty(
                        (
                            0,
                            len(
                                FeatureExtractor
                                .FEATURE_NAMES
                            ),
                        )
                    ),

                    torch.empty(
                        (
                            0,
                            1,
                        )
                    ),
                )

            return (
                torch.tensor(
                    features,
                    dtype=torch.float32,
                ),

                torch.tensor(
                    targets,
                    dtype=torch.float32,
                ),
            )

        except RuntimeError as exc:

            self.logger.error(
                (
                    "Causal dataset "
                    "unavailable: %s"
                ),
                exc,
            )

            return (
                torch.empty(
                    (
                        0,
                        len(
                            FeatureExtractor
                            .FEATURE_NAMES
                        ),
                    )
                ),

                torch.empty(
                    (
                        0,
                        1,
                    )
                ),
            )

        except Exception as exc:

            self.logger.exception(
                (
                    "Feature extraction "
                    "failed closed: %s"
                ),
                exc,
            )

            return (
                torch.empty(
                    (
                        0,
                        len(
                            FeatureExtractor
                            .FEATURE_NAMES
                        ),
                    )
                ),

                torch.empty(
                    (
                        0,
                        1,
                    )
                ),
            )

    # =========================================================================
    # HISTORICAL ENTRYPOINTS
    # =========================================================================

    def _record_dataset_stats(
        self,
        symbol: str,
        samples: Sequence[
            _CausalSample
        ],
        source: str,
    ) -> Dict[
        str,
        Any,
    ]:

        by_split = {
            split: [
                sample
                for sample
                in samples
                if sample.split
                == split
            ]
            for split
            in (
                "train",
                "validation",
                "holdout",
            )
        }

        stats = {
            "source": (
                source
            ),

            "label_version": (
                self.CAUSAL_LABEL_VERSION
            ),

            "train_samples": len(
                by_split[
                    "train"
                ]
            ),

            "validation_samples": len(
                by_split[
                    "validation"
                ]
            ),

            "holdout_samples": len(
                by_split[
                    "holdout"
                ]
            ),

            "total_samples": len(
                samples
            ),

            "train_realized_r": round(
                float(
                    sum(
                        sample.realized_r
                        for sample
                        in by_split[
                            "train"
                        ]
                    )
                ),
                6,
            ),

            "validation_realized_r": round(
                float(
                    sum(
                        sample.realized_r
                        for sample
                        in by_split[
                            "validation"
                        ]
                    )
                ),
                6,
            ),

            "holdout_realized_r": round(
                float(
                    sum(
                        sample.realized_r
                        for sample
                        in by_split[
                            "holdout"
                        ]
                    )
                ),
                6,
            ),

            "last_train_time": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "production_mutation": (
                False
            ),

            "status": (
                "SHADOW_DATASET_READY"
                if samples
                else "NO_CAUSAL_SAMPLES"
            ),
        }

        self.training_stats[
            symbol
        ] = stats

        self._last_training_result = (
            dict(
                stats
            )
        )

        return stats

    def train_on_history(
        self,
        symbol: str,
        df_htf: pd.DataFrame,
        df_context: pd.DataFrame,
        df_ltf: pd.DataFrame,
    ) -> Dict[
        str,
        Any,
    ]:
        """
        Build a causal MTF shadow dataset.

        Production NN is NOT changed.
        """

        try:
            samples = (
                self._build_mtf_samples(
                    df_htf,
                    df_context,
                    df_ltf,
                    (
                        self
                        .DEFAULT_MAX_HOLDING_BARS
                    ),
                )
            )

            dataset = (
                self._samples_to_dataset(
                    samples
                )
            )

            dataset[
                "label_version"
            ] = (
                self.CAUSAL_LABEL_VERSION
            )

            with self._shadow_lock:

                self._last_causal_dataset = (
                    dataset
                )

            stats = (
                self._record_dataset_stats(
                    symbol,
                    samples,
                    "MTF_CAUSAL",
                )
            )

            # Descriptive cluster only.
            # TRAIN split only.
            train_vectors = [
                sample.feature_vector[
                    :3
                ]
                for sample
                in samples
                if sample.split
                == "train"
            ]

            if train_vectors:

                self.kmeans.fit(
                    np.asarray(
                        train_vectors,
                        dtype=float,
                    )
                )

            self.save_patterns()

            return stats

        except Exception as exc:

            self.logger.exception(
                (
                    "MTF shadow dataset "
                    "failed: %s"
                ),
                exc,
            )

            result = {
                "source": (
                    "MTF_CAUSAL"
                ),

                "status": (
                    "FAILED_CLOSED"
                ),

                "reason": (
                    f"{type(exc).__name__}:"
                    f"{exc}"
                ),

                "production_mutation": (
                    False
                ),
            }

            self.training_stats[
                symbol
            ] = result

            self._last_training_result = (
                dict(
                    result
                )
            )

            return result

    def train_on_single_timeframe(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> Dict[
        str,
        Any,
    ]:

        try:
            samples = (
                self._build_single_timeframe_samples(
                    df,
                    (
                        self
                        .DEFAULT_MAX_HOLDING_BARS
                    ),
                )
            )

            dataset = (
                self._samples_to_dataset(
                    samples
                )
            )

            dataset[
                "label_version"
            ] = (
                self.CAUSAL_LABEL_VERSION
            )

            with self._shadow_lock:

                self._last_causal_dataset = (
                    dataset
                )

            stats = (
                self._record_dataset_stats(
                    symbol,
                    samples,
                    "SINGLE_TF_CAUSAL",
                )
            )

            self.save_patterns()

            return stats

        except Exception as exc:

            self.logger.exception(
                (
                    "Single-TF shadow "
                    "dataset failed: %s"
                ),
                exc,
            )

            result = {
                "source": (
                    "SINGLE_TF_CAUSAL"
                ),

                "status": (
                    "FAILED_CLOSED"
                ),

                "reason": (
                    f"{type(exc).__name__}:"
                    f"{exc}"
                ),

                "production_mutation": (
                    False
                ),
            }

            self.training_stats[
                symbol
            ] = result

            self._last_training_result = (
                dict(
                    result
                )
            )

            return result

    def train_multi_strategy(
        self,
        symbol: str = "XAUUSDm",
        dfs: Optional[
            Dict[
                str,
                Any,
            ]
        ] = None,
    ) -> Dict[
        str,
        Any,
    ]:
        """
        Legacy multi-strategy historical replay is intentionally disabled.

        THIS DOES NOT DISABLE LIVE STRATEGIES.

        It disables only the old historical training shortcut which:
            - sliced HTF frames by open timestamp
            - evaluated strategies on potentially open HTF candles
            - manually resolved future SL/TP
            - trained production probability directly

        A later replay implementation must produce CandidateSetup objects
        and send them through the exact causal OutcomeResolver.
        """

        result = {
            "source": (
                "MULTI_STRATEGY"
            ),

            "status": (
                "SHADOW_MULTI_STRATEGY_"
                "REPLAY_NOT_IMPLEMENTED"
            ),

            "reason": (
                "REQUIRES_CAUSAL_"
                "CANDIDATE_REPLAY_WITH_"
                "CLOSED_BAR_AVAILABILITY_"
                "AND_OUTCOME_RESOLVER"
            ),

            "production_mutation": (
                False
            ),

            "symbol": (
                symbol
            ),
        }

        self.training_stats[
            symbol
        ] = result

        self._last_training_result = (
            dict(
                result
            )
        )

        self.logger.warning(
            (
                "Unsafe legacy "
                "multi-strategy "
                "auto-training "
                "disabled for %s."
            ),
            symbol,
        )

        return result

    def train_on_synthetic_idealized_patterns(
        self,
        symbol: str,
        n_samples_per_pattern: int = 500,
    ) -> Dict[
        str,
        Any,
    ]:
        """
        Synthetic labels are RESEARCH ONLY.

        No fabricated synthetic win/loss is ever fitted into
        production confidence.
        """

        result = {
            "source": (
                "SYNTHETIC_IDEALIZED"
            ),

            "status": (
                "RESEARCH_ONLY"
            ),

            "symbol": (
                symbol
            ),

            "requested_samples_per_pattern": int(
                n_samples_per_pattern
            ),

            "samples_applied_to_production": (
                0
            ),

            "production_mutation": (
                False
            ),
        }

        self._last_training_result = (
            dict(
                result
            )
        )

        self.logger.info(
            (
                "Synthetic pattern "
                "generation retained "
                "as RESEARCH_ONLY "
                "for %s."
            ),
            symbol,
        )

        return result

    # =========================================================================
    # SHADOW TRAINING
    # =========================================================================

    def train_timeframe_layer(
        self,
        model: nn.Module,
        timeframe_data: pd.DataFrame,
    ) -> None:
        """
        Train a caller-owned challenger.

        TRAIN split only.
        """

        try:
            (
                features,
                outcomes,
            ) = (
                self.extract_vectorized_features(
                    timeframe_data,
                    split="train",
                )
            )

            if len(
                features
            ) < 30:

                self.logger.warning(
                    (
                        "Shadow timeframe "
                        "training skipped: "
                        "only %d causal "
                        "train samples."
                    ),
                    len(
                        features
                    ),
                )

                return

            model.train()

            optimizer = (
                torch.optim.AdamW(
                    model.parameters(),
                    lr=0.001,
                    weight_decay=1e-4,
                )
            )

            loss_function = (
                nn.BCELoss()
            )

            for _ in range(
                3
            ):
                optimizer.zero_grad()

                predictions = (
                    model(
                        features
                    )
                )

                loss = (
                    loss_function(
                        predictions,
                        outcomes,
                    )
                )

                loss.backward()

                torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    max_norm=5.0,
                )

                optimizer.step()

            model.eval()

            with self._shadow_lock:

                self._last_shadow_candidate = (
                    model
                )

            self.logger.info(
                (
                    "Shadow timeframe "
                    "layer trained on "
                    "%d causal TRAIN "
                    "samples."
                ),
                len(
                    features
                ),
            )

        except Exception as exc:

            self.logger.exception(
                (
                    "Shadow timeframe "
                    "training failed: %s"
                ),
                exc,
            )

            if model is not None:
                model.eval()

    def train_incremental(
        self,
        trades: List[
            Dict[
                str,
                Any,
            ]
        ],
    ):
        """
        Closed-trade incremental learning.

        Creates a shadow challenger only.

        It does not validate on its training rows.
        It does not swap the live champion.
        """

        if not trades:
            return None

        rows = sorted(
            list(
                trades
            ),
            key=lambda row: str(
                row.get(
                    "close_time_utc",
                    row.get(
                        "timestamp",
                        "",
                    ),
                )
            ),
        )

        inputs: List[
            np.ndarray
        ] = []

        targets: List[
            List[
                float
            ]
        ] = []

        for row in rows:

            features = row.get(
                "features",
                {},
            )

            if not isinstance(
                features,
                Mapping,
            ):
                continue

            try:
                vector = (
                    self.extract_nn_features(
                        dict(
                            features
                        )
                    )
                )

            except ValueError:
                continue

            realized_r = (
                self._finite(
                    row.get(
                        "net_r",
                        row.get(
                            "r_multiple",
                            row.get(
                                "pnl",
                                None,
                            ),
                        ),
                    )
                )
            )

            if realized_r is None:
                continue

            inputs.append(
                vector
            )

            targets.append(
                [
                    (
                        1.0
                        if realized_r
                        > 0.0
                        else 0.0
                    )
                ]
            )

        if len(
            inputs
        ) < 30:

            self.logger.warning(
                (
                    "Incremental shadow "
                    "training skipped: "
                    "%d usable rows."
                ),
                len(
                    inputs
                ),
            )

            return None

        # Reserve last 20%.
        # This training call never sees those rows.
        train_end = max(
            1,
            int(
                len(
                    inputs
                )
                * 0.80
            ),
        )

        train_inputs = torch.tensor(
            np.asarray(
                inputs[
                    :train_end
                ],
                dtype=np.float32,
            ),
            dtype=torch.float32,
        )

        train_targets = torch.tensor(
            np.asarray(
                targets[
                    :train_end
                ],
                dtype=np.float32,
            ),
            dtype=torch.float32,
        )

        candidate = copy.deepcopy(
            self.nn_model
        )

        candidate.train()

        optimizer = (
            optim.Adam(
                candidate.parameters(),
                lr=0.001,
                weight_decay=1e-4,
            )
        )

        optimizer.zero_grad()

        outputs = candidate(
            train_inputs
        )

        loss = (
            self.nn_criterion(
                outputs,
                train_targets,
            )
        )

        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            candidate.parameters(),
            max_norm=5.0,
        )

        optimizer.step()

        candidate.eval()

        with self._shadow_lock:

            self._last_shadow_candidate = (
                candidate
            )

            self._last_training_result = {
                "source": (
                    "INCREMENTAL_"
                    "CLOSED_TRADES"
                ),

                "status": (
                    "SHADOW_CANDIDATE_READY"
                ),

                "train_samples": (
                    train_end
                ),

                "reserved_samples": (
                    len(
                        inputs
                    )
                    - train_end
                ),

                "production_mutation": (
                    False
                ),

                "loss": float(
                    loss.item()
                ),
            }

        return candidate

    def get_last_shadow_candidate(
        self,
    ):
        with self._shadow_lock:
            return (
                self._last_shadow_candidate
            )

    def consume_shadow_candidate(
        self,
    ):
        with self._shadow_lock:

            candidate = (
                self._last_shadow_candidate
            )

            self._last_shadow_candidate = (
                None
            )

            return candidate

    def get_last_causal_dataset(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        with self._shadow_lock:
            return dict(
                self._last_causal_dataset
            )

    def get_last_training_result(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        return dict(
            self._last_training_result
        )

    # =========================================================================
    # LEGACY PROMOTION APIs - BLOCKED
    # =========================================================================

    def _validate_and_promote(
        self,
        candidate_model,
        inputs_tensor=None,
        targets_tensor=None,
    ) -> bool:
        """
        Compatibility shim.

        PatternLearner no longer has promotion authority.
        """

        self.logger.error(
            (
                "_validate_and_promote "
                "is disabled. Use frozen "
                "PromotionValidator + "
                "walk-forward + "
                "ModelRegistry authorization."
            )
        )

        return False

    def save_nn_model(
        self,
    ) -> bool:
        """
        Compatibility shim.

        An active registry model is immutable.
        PatternLearner cannot overwrite it.
        """

        self.logger.error(
            (
                "Direct save_nn_model "
                "blocked. Save challenger "
                "to a VERSIONED path and "
                "promote through ModelRegistry."
            )
        )

        return False

    # =========================================================================
    # ACTIVE CHAMPION
    # =========================================================================

    def load_nn_model(
        self,
    ) -> bool:
        """
        Load ONLY active ModelRegistry champion.
        """

        self.nn_ready = False

        self.active_model_version = (
            None
        )

        try:
            from core.model_registry import (
                model_registry,
            )

            bundle = (
                model_registry
                .get_active_bundle()
            )

            if bundle is None:

                self.logger.warning(
                    (
                        "No validated active "
                        "model bundle. "
                        "NN inference disabled."
                    )
                )

                return False

            if (
                bundle.feature_schema_hash
                != FeatureExtractor
                .FEATURE_SCHEMA_HASH
            ):

                self.logger.error(
                    (
                        "Active model schema "
                        "mismatch. "
                        "NN inference disabled."
                    )
                )

                return False

            weights_path = str(
                bundle.model_weights_path
            )

            if not os.path.isfile(
                weights_path
            ):

                self.logger.error(
                    (
                        "Active model "
                        "weights missing: %s"
                    ),
                    weights_path,
                )

                return False

            try:
                state_dict = torch.load(
                    weights_path,
                    map_location=(
                        torch.device(
                            "cpu"
                        )
                    ),
                    weights_only=True,
                )

            except TypeError:

                state_dict = torch.load(
                    weights_path,
                    map_location=(
                        torch.device(
                            "cpu"
                        )
                    ),
                )

            candidate = (
                PulseViperNeuralNet(
                    input_dim=len(
                        FeatureExtractor
                        .FEATURE_NAMES
                    )
                )
            )

            candidate.load_state_dict(
                state_dict
            )

            candidate.eval()

            test_input = torch.zeros(
                (
                    1,
                    len(
                        FeatureExtractor
                        .FEATURE_NAMES
                    ),
                ),
                dtype=torch.float32,
            )

            with torch.no_grad():

                output = candidate(
                    test_input
                )

            value = float(
                output.reshape(
                    -1
                )[
                    0
                ].item()
            )

            if (
                not math.isfinite(
                    value
                )
                or not (
                    0.0
                    <= value
                    <= 1.0
                )
            ):

                self.logger.error(
                    (
                        "Active model failed "
                        "inference sanity check."
                    )
                )

                return False

            with self.model_lock:

                self.nn_model = (
                    candidate
                )

                self.nn_optimizer = (
                    optim.Adam(
                        self.nn_model.parameters(),
                        lr=0.003,
                        weight_decay=1e-4,
                    )
                )

                self.nn_ready = (
                    True
                )

                self.active_model_version = (
                    bundle.model_version
                )

            self.logger.info(
                (
                    "Loaded validated "
                    "NN champion "
                    "version=%s."
                ),
                bundle.model_version,
            )

            return True

        except Exception as exc:

            self.logger.exception(
                (
                    "Active NN champion "
                    "load failed closed: %s"
                ),
                exc,
            )

            self.nn_ready = (
                False
            )

            self.active_model_version = (
                None
            )

            return False

    # =========================================================================
    # INFERENCE
    # =========================================================================

    def get_trading_signal(
        self,
        symbol: str,
        current_features: Dict,
        df_ltf: Optional[
            pd.DataFrame
        ] = None,
        df_m5: Optional[
            pd.DataFrame
        ] = None,
        df_h1: Optional[
            pd.DataFrame
        ] = None,
        candidate_strategy: Optional[
            str
        ] = None,
        candidate_action: Optional[
            str
        ] = None,
    ) -> Dict[
        str,
        Any,
    ]:

        visual_patterns = (
            self.detect_visual_patterns(
                df_ltf
            )
            if df_ltf
            is not None
            else []
        )

        smc_patterns: Dict[
            str,
            Dict[
                str,
                Any,
            ],
        ] = {}

        smc_found: List[
            str
        ] = []

        smc_confidence = (
            0.0
        )

        smc_direction: Optional[
            str
        ] = None

        if df_ltf is not None:

            smc_patterns = (
                ChartPatternDetector
                .detect(
                    df_m1=(
                        df_ltf
                    ),
                    df_m5=(
                        df_m5
                    ),
                    df_h1=(
                        df_h1
                    ),
                )
            )

            (
                smc_found,
                smc_confidence,
                smc_direction,
            ) = (
                ChartPatternDetector
                .get_summary(
                    smc_patterns
                )
            )

        all_patterns = sorted(
            set(
                visual_patterns
                + smc_found
            )
        )

        volatility = float(
            current_features.get(
                "volatility",
                0.0,
            )
            or 0.0
        )

        price = float(
            current_features.get(
                "price",
                current_features.get(
                    "close",
                    0.0,
                ),
            )
            or 0.0
        )

        support = float(
            current_features.get(
                "support",
                price,
            )
            or price
        )

        atr_pct = float(
            current_features.get(
                "atr_pct",
                0.0,
            )
            or 0.0
        )

        cluster_id = (
            self.kmeans.predict(
                np.asarray(
                    [
                        volatility,

                        (
                            abs(
                                price
                                - support
                            )
                            / max(
                                abs(
                                    price
                                ),
                                1e-12,
                            )
                        ),

                        atr_pct,
                    ],
                    dtype=float,
                )
            )
        )

        features_copy = (
            copy.deepcopy(
                current_features
            )
        )

        if candidate_strategy is not None:

            features_copy[
                "candidate_strategy"
            ] = (
                str(
                    candidate_strategy
                )
                .upper()
            )

        if candidate_action is not None:

            features_copy[
                "candidate_action"
            ] = (
                str(
                    candidate_action
                )
                .upper()
            )

        win_prob: Optional[
            float
        ] = None

        model_source = (
            "NO_VALID_MODEL"
        )

        # -------------------------------------------------------------
        # NO NAIVE BAYES FALLBACK
        #
        # If there is no validated champion, AI confidence is unavailable.
        # We do not invent or silently substitute an unvalidated model.
        # -------------------------------------------------------------

        if self.nn_ready:

            try:
                vector = (
                    self.extract_nn_features(
                        features_copy
                    )
                )

                tensor = torch.tensor(
                    vector,
                    dtype=torch.float32,
                ).unsqueeze(
                    0
                )

                with self.model_lock:

                    self.nn_model.eval()

                    with torch.no_grad():

                        value = (
                            self.nn_model(
                                tensor
                            )
                        )

                win_prob = float(
                    value.reshape(
                        -1
                    )[
                        0
                    ].item()
                )

                if (
                    not math.isfinite(
                        win_prob
                    )
                    or not (
                        0.0
                        <= win_prob
                        <= 1.0
                    )
                ):

                    win_prob = (
                        None
                    )

                else:
                    model_source = (
                        "NN_CHAMPION"
                    )

            except Exception as exc:

                self.logger.error(
                    (
                        "NN prediction "
                        "failed closed: %s"
                    ),
                    exc,
                )

                win_prob = (
                    None
                )

        signal_action = (
            "HOLD"
        )

        adjustment = (
            0.0
        )

        if (
            win_prob is not None
            and win_prob >= 0.58
        ):

            if (
                candidate_action
                is not None
                and str(
                    candidate_action
                ).upper()
                in {
                    "BUY",
                    "SELL",
                }
            ):

                signal_action = (
                    str(
                        candidate_action
                    )
                    .upper()
                )

            else:

                bias = int(
                    current_features.get(
                        "active_bias",
                        0,
                    )
                    or 0
                )

                if bias == 1:
                    signal_action = (
                        "BUY"
                    )

                elif bias == -1:
                    signal_action = (
                        "SELL"
                    )

            adjustment = (
                (
                    win_prob
                    - 0.5
                )
                * 0.8
            )

        return {
            "signal": (
                signal_action
            ),

            "confidence": (
                round(
                    win_prob,
                    4,
                )
                if win_prob
                is not None
                else None
            ),

            "adjustment": float(
                adjustment
            ),

            "cluster_id": (
                cluster_id
            ),

            "detected_patterns": (
                all_patterns
            ),

            "smc_patterns": (
                smc_found
            ),

            "smc_confidence": (
                smc_confidence
            ),

            "smc_direction": (
                smc_direction
            ),

            "pattern_details": {
                key: value
                for key, value
                in smc_patterns.items()
                if value.get(
                    "detected"
                )
            },

            "model_source": (
                model_source
            ),

            "model_ready": bool(
                self.nn_ready
                and win_prob
                is not None
            ),

            "model_version": (
                self.active_model_version
            ),
        }

    # =========================================================================
    # REALIZED EXPERIENCE
    # =========================================================================

    def learn_from_trade(
        self,
        trade_data: Dict[
            str,
            Any,
        ],
    ) -> None:

        symbol = str(
            trade_data.get(
                "symbol",
                "UNKNOWN",
            )
        )

        features = (
            trade_data.get(
                "features",
                {},
            )
        )

        if (
            not isinstance(
                features,
                Mapping,
            )
            or not features
        ):
            return

        outcome = (
            self._finite(
                trade_data.get(
                    "net_r",
                    trade_data.get(
                        "r_multiple",
                        trade_data.get(
                            "outcome",
                            trade_data.get(
                                "pnl",
                                None,
                            ),
                        ),
                    ),
                )
            )
        )

        if outcome is None:
            return

        timestamp = str(
            trade_data.get(
                "close_time_utc",
                datetime.now(
                    timezone.utc
                ).isoformat(),
            )
        )

        record = {
            "pattern": (
                self._quantize_smc_state(
                    dict(
                        features
                    )
                )
            ),

            "outcome": float(
                outcome
            ),

            "timestamp": (
                timestamp
            ),

            "source": (
                "REALIZED_TRADE"
            ),
        }

        bucket = (
            f"{symbol}_winning"
            if outcome > 0.0
            else f"{symbol}_losing"
        )

        with self._append_lock:

            self.patterns[
                bucket
            ].append(
                record
            )

            self.patterns[
                bucket
            ] = (
                self.patterns[
                    bucket
                ][
                    -500:
                ]
            )

            self._update_market_regime(
                symbol,
                dict(
                    features
                ),
            )

            self.save_patterns()

    def append_live_experience(
        self,
        features: dict,
        outcome_label: float,
        pnl_realized: float,
        symbol: str,
    ) -> None:

        self.learn_from_trade(
            {
                "symbol": (
                    symbol
                ),

                "features": (
                    features
                ),

                "outcome": (
                    pnl_realized
                ),

                "outcome_label": (
                    outcome_label
                ),

                "close_time_utc": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            }
        )

    # =========================================================================
    # MARKET REGIME
    # =========================================================================

    def _update_market_regime(
        self,
        symbol: str,
        features: Dict[
            str,
            Any,
        ],
    ) -> None:

        bias = int(
            features.get(
                "active_bias",
                0,
            )
            or 0
        )

        regime = (
            "BULLISH"
            if bias == 1
            else (
                "BEARISH"
                if bias == -1
                else "SIDEWAY"
            )
        )

        self.market_regimes[
            symbol
        ] = {
            "regime": (
                regime
            ),

            "timestamp": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "volatility": float(
                features.get(
                    "volatility",
                    0.0,
                )
                or 0.0
            ),

            "atr_pct": float(
                features.get(
                    "atr_pct",
                    0.0,
                )
                or 0.0
            ),
        }

    def get_market_regime(
        self,
        symbol: str,
    ) -> str:

        return str(
            self.market_regimes.get(
                symbol,
                {},
            ).get(
                "regime",
                "RANGING",
            )
        )

    # =========================================================================
    # NON-PRODUCTION MEMORY PERSISTENCE
    # =========================================================================

    def save_patterns(
        self,
    ) -> None:

        try:
            os.makedirs(
                "data",
                exist_ok=True,
            )

            path = (
                "data/smc_patterns.json"
            )

            temp_path = (
                path
                + ".tmp"
            )

            data = {
                "schema_version": (
                    2
                ),

                "patterns": dict(
                    self.patterns
                ),

                "market_regimes": (
                    self.market_regimes
                ),

                "kmeans_centroids": (
                    self.kmeans
                    .centroids
                    .tolist()
                    if isinstance(
                        self.kmeans.centroids,
                        np.ndarray,
                    )
                    else []
                ),

                "training_stats": (
                    self.training_stats
                ),

                "naive_bayes_production_enabled": (
                    False
                ),
            }

            with open(
                temp_path,
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
                temp_path,
                path,
            )

        except Exception as exc:

            self.logger.error(
                (
                    "Failed to save "
                    "pattern memory: %s"
                ),
                exc,
            )

    def load_patterns(
        self,
    ) -> None:

        path = (
            "data/smc_patterns.json"
        )

        if not os.path.exists(
            path
        ):
            return

        try:
            with open(
                path,
                "r",
                encoding="utf-8",
            ) as handle:

                data = json.load(
                    handle
                )

            self.patterns = (
                defaultdict(
                    list
                )
            )

            for key, rows in data.get(
                "patterns",
                {},
            ).items():

                if isinstance(
                    rows,
                    list,
                ):

                    self.patterns[
                        str(
                            key
                        )
                    ] = rows[
                        -500:
                    ]

            regimes = data.get(
                "market_regimes",
                {},
            )

            self.market_regimes = (
                dict(
                    regimes
                )
                if isinstance(
                    regimes,
                    Mapping,
                )
                else {}
            )

            stats = data.get(
                "training_stats",
                {},
            )

            self.training_stats = (
                dict(
                    stats
                )
                if isinstance(
                    stats,
                    Mapping,
                )
                else {}
            )

            centroids = data.get(
                "kmeans_centroids",
                [],
            )

            if (
                isinstance(
                    centroids,
                    list,
                )
                and centroids
            ):

                arr = np.asarray(
                    centroids,
                    dtype=float,
                )

                if (
                    arr.ndim == 2
                    and np.isfinite(
                        arr
                    ).all()
                ):

                    self.kmeans.centroids = (
                        arr
                    )

            # Critical:
            #
            # Do not restore old Naive Bayes parameters trained from
            # synthetic/leaky historical labels.
            self.classifier = (
                NaiveBayesClassifier()
            )

        except Exception as exc:

            self.logger.warning(
                (
                    "Failed to load "
                    "pattern memory: %s"
                ),
                exc,
            )

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_training_stats(
        self,
        symbol: Optional[
            str
        ] = None,
    ) -> Dict[
        str,
        Any,
    ]:

        if symbol is None:

            return copy.deepcopy(
                self.training_stats
            )

        return copy.deepcopy(
            self.training_stats.get(
                symbol,
                {},
            )
        )

    def get_model_status(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        return {
            "nn_ready": bool(
                self.nn_ready
            ),

            "nb_ready": (
                False
            ),

            "active_model_version": (
                self.active_model_version
            ),

            "feature_schema_hash": (
                FeatureExtractor
                .FEATURE_SCHEMA_HASH
            ),

            "shadow_candidate_ready": (
                self.get_last_shadow_candidate()
                is not None
            ),

            "promotion_inside_pattern_learner": (
                False
            ),
        }