# core/market_regime_hmm.py
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List, Optional

class MarketRegimeHMM:
    def __init__(self):
        # Hidden State Mapping: 0 = Range/Compression, 1 = Trend, 2 = Exhaustion/Chaos
        self.num_states = 3
        self.num_features = 3
        
        # Initial State Probabilities (Pi) - Default uniform log priors
        self.log_pi = np.log(np.array([0.6, 0.3, 0.1]))
        
        # Transition Probability Matrix (A) - High self-transition priors to avoid jitter
        self.A = np.array([
            [0.85, 0.12, 0.03],  # From State 0 (Range)
            [0.10, 0.85, 0.05],  # From State 1 (Trend)
            [0.20, 0.20, 0.60]   # From State 2 (Exhaustion)
        ])
        self.log_A = np.log(self.A)
        
        # Emission Parameters (B): Means (mu) and Std Devs (sigma) for [CVD_ROC, Imbalance_Density, Tick_Freq]
        # These act as baseline anchors before online training/updates
        self.means = np.array([
            [0.0,  0.2,  10.0],  # State 0: Flat CVD, low imbalances, low velocity
            [4.5,  2.8,  45.0],  # State 1: Directional CVD, high imbalances, high velocity
            [0.0,  5.0,  120.0]  # State 2: Chaotic CVD swings, erratic imbalances, extreme frequency
        ])
        
        self.sigmas = np.array([
            [1.5,  0.4,  5.0],   # State 0 variances
            [3.0,  1.2,  15.0],  # State 1 variances
            [10.0, 3.5,  40.0]   # State 2 variances
        ])

    def _calculate_log_emission(self, X_t: np.ndarray) -> np.ndarray:
        """
        Computes the log-likelihood of emission vector X_t for all 3 hidden states.
        X_t shape: (3,) -> [cvd_roc, imbalance_density, tick_freq]
        """
        log_b = np.zeros(self.num_states)
        for j in range(self.num_states):
            # Evaluate independent Gaussian log probabilities across features
            var = self.sigmas[j] ** 2
            var_safe = np.where(var == 0, 1e-6, var)  # Prevent division by absolute zero
            log_pdf = -0.5 * np.log(2 * np.pi * var_safe) - ((X_t - self.means[j]) ** 2) / (2 * var_safe)
            log_b[j] = np.sum(log_pdf)
        return log_b

    def decode_current_regime(self, df_m1_features: pd.DataFrame) -> Tuple[int, Dict[int, float]]:
        """
        Runs the log-space Viterbi forward trellis match over the recent window 
        to extract the current state and localized state posterior distribution.
        """
        # Feature Matrix Extraction: Expected columns [cvd_roc, imbalance_density, tick_frequency]
        X = df_m1_features[['cvd_roc', 'imbalance_density', 'tick_frequency']].values
        T = len(X)
        
        if T == 0:
            return 0, {0: 1.0, 1: 0.0, 2: 0.0}

        # Trellis matrix initialization
        viterbi_log_delta = np.zeros((T, self.num_states))
        
        # Seed first step
        log_b_0 = self._calculate_log_emission(X[0])
        viterbi_log_delta[0] = self.log_pi + log_b_0
        
        # Forward Viterbi loop
        for t in range(1, T):
            log_b_t = self._calculate_log_emission(X[t])
            for j in range(self.num_states):
                # Matrix vectorized match: trellis state(t-1) + transition(i->j)
                transition_score = viterbi_log_delta[t-1] + self.log_A[:, j]
                viterbi_log_delta[t, j] = np.max(transition_score) + log_b_t[j]

        # Extract current optimal log state space
        current_log_probs = viterbi_log_delta[-1]
        
        # Convert log probabilities safely back to soft probability distribution percentages
        max_log = np.max(current_log_probs)
        exp_probs = np.exp(current_log_probs - max_log)  # Safe numeric translation
        state_posteriors = exp_probs / np.sum(exp_probs)
        
        current_state = int(np.argmax(state_posteriors))
        
        return current_state, {i: float(state_posteriors[i]) for i in range(self.num_states)}
