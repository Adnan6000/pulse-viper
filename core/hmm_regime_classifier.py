# core/hmm_regime_classifier.py
import os
import json
import logging
import numpy as np
from scipy.stats import norm
from sklearn.cluster import KMeans
from typing import Dict, List, Tuple, Optional

HMM_PARAMS_FILE = "data/hmm_parameters.json"

class GaussianHMM:
    """
    Custom continuous Gaussian Hidden Markov Model (HMM) with diagonal covariance.
    Implemented in NumPy/SciPy for stability and PyInstaller compatibility.
    """
    def __init__(self, n_states: int = 4, max_iter: int = 30, tol: float = 1e-4):
        self.n_states = n_states
        self.max_iter = max_iter
        self.tol = tol
        self.logger = logging.getLogger("PulseViper.GaussianHMM")
        
        # Parameters
        self.start_prob = np.ones(n_states) / n_states
        self.trans_mat = np.ones((n_states, n_states)) / n_states
        self.means = None  # shape: (n_states, n_features)
        self.covs = None   # shape: (n_states, n_features)
        self.state_mapping = {}  # maps state_id (0..3) to Regime name ("TRENDING", "RANGE", etc.)
        self.is_fitted = False
        self.load_parameters()

    def _pdf(self, x: np.ndarray, state: int) -> np.ndarray:
        """
        Evaluate probability density function of observation x under diagonal Gaussian distribution.
        x shape: (T, n_features)
        """
        T, D = x.shape
        assert self.means is not None and self.covs is not None
        probs = np.ones(T)
        for d in range(D):
            # Compute univariate normal PDF for each feature and multiply (since covariance is diagonal)
            mean = self.means[state, d]
            std = np.sqrt(self.covs[state, d] + 1e-6)
            probs *= norm.pdf(x[:, d], loc=mean, scale=std)
        # Avoid absolute zeros to maintain numerical log stability
        return np.maximum(probs, 1e-100)

    def fit(self, X: np.ndarray):
        """
        Fit the Gaussian HMM parameters using the Baum-Welch (Expectation-Maximization) algorithm.
        X shape: (T, n_features)
        """
        T, D = X.shape
        if T < self.n_states * 4:
            self.logger.warning(f"Not enough data to fit HMM ({T} bars). Skipping.")
            return

        self.logger.info(f"Fitting Gaussian HMM over {T} samples with {self.n_states} states...")

        # 1. Initialize parameters using KMeans clustering
        try:
            kmeans = KMeans(n_clusters=self.n_states, n_init=5, random_state=42)
            labels = kmeans.fit_predict(X)
            self.means = kmeans.cluster_centers_
            self.covs = np.zeros((self.n_states, D))
            for i in range(self.n_states):
                cluster_pts = X[labels == i]
                if len(cluster_pts) > 1:
                    self.covs[i] = np.var(cluster_pts, axis=0) + 1e-4
                else:
                    self.covs[i] = np.var(X, axis=0) + 1e-4
            
            # Simple start & transition matrices initialization
            self.start_prob = np.ones(self.n_states) / self.n_states
            self.trans_mat = np.ones((self.n_states, self.n_states)) / self.n_states
            for i in range(self.n_states - 1):
                self.trans_mat[i, i] = 0.7
                self.trans_mat[i, i+1] = 0.3
            self.trans_mat[-1, -1] = 0.8
            self.trans_mat[-1, 0] = 0.2
        except Exception as e:
            self.logger.error(f"Error during HMM initialization: {e}")
            return

        # 2. EM Loop
        log_lik_old = -np.inf
        for it in range(self.max_iter):
            # Compute emissions: shape (T, n_states)
            B = np.zeros((T, self.n_states))
            for s in range(self.n_states):
                B[:, s] = self._pdf(X, s)

            # --- Forward Pass (with scaling) ---
            alpha = np.zeros((T, self.n_states))
            c = np.zeros(T)  # Scaling factors
            
            alpha[0] = self.start_prob * B[0]
            c[0] = 1.0 / (np.sum(alpha[0]) + 1e-10)
            alpha[0] *= c[0]
            
            for t in range(1, T):
                alpha[t] = np.dot(alpha[t-1], self.trans_mat) * B[t]
                c[t] = 1.0 / (np.sum(alpha[t]) + 1e-10)
                alpha[t] *= c[t]

            log_lik = -np.sum(np.log(c + 1e-10))

            # Convergence check
            if abs(log_lik - log_lik_old) < self.tol:
                self.logger.debug(f"HMM converged at iteration {it}. Log-Lik={log_lik:.2f}")
                break
            log_lik_old = log_lik

            # --- Backward Pass ---
            beta = np.zeros((T, self.n_states))
            beta[T-1] = np.ones(self.n_states) * c[T-1]
            
            for t in range(T-2, -1, -1):
                beta[t] = np.dot(self.trans_mat, B[t+1] * beta[t+1]) * c[t]

            # --- Compute Gammas & Xis ---
            gamma = np.zeros((T, self.n_states))
            for t in range(T):
                gamma[t] = alpha[t] * beta[t]
                gamma[t] /= (np.sum(gamma[t]) + 1e-10)

            xi = np.zeros((T-1, self.n_states, self.n_states))
            for t in range(T-1):
                denom = np.sum(alpha[t] * beta[t]) + 1e-10
                for i in range(self.n_states):
                    xi[t, i, :] = alpha[t, i] * self.trans_mat[i, :] * B[t+1] * beta[t+1] / denom

            # --- M-step: Update parameters ---
            self.start_prob = gamma[0] / (np.sum(gamma[0]) + 1e-10)
            
            for i in range(self.n_states):
                denom_a = np.sum(gamma[:T-1, i]) + 1e-10
                for j in range(self.n_states):
                    self.trans_mat[i, j] = np.sum(xi[:, i, j]) / denom_a
                
                denom_g = np.sum(gamma[:, i]) + 1e-10
                self.means[i] = np.sum(gamma[:, i, np.newaxis] * X, axis=0) / denom_g
                
                diff = X - self.means[i]
                self.covs[i] = np.sum(gamma[:, i, np.newaxis] * (diff**2), axis=0) / denom_g + 1e-4

        # 3. Dynamic State Mapping based on Volatility (ATR feature at index 1)
        self._map_regime_states()
        self.is_fitted = True
        self.save_parameters()

    def _map_regime_states(self):
        """
        Dynamically map hidden states (0..3) to market regimes based on volatility profiles.
        ATR is feature index 1.
        - Lowest ATR state -> COMPRESSION
        - Highest ATR state -> CHAOTIC
        - Remaining two:
           - If directional return mean (index 0) has high absolute value -> TRENDING
           - Else -> RANGE
        """
        # Sort states by learned mean volatility (ATR return mean at index 1)
        vol_means = self.means[:, 1]  # type: ignore[index]
        sorted_indices = np.argsort(vol_means)  # lowest to highest
        
        lowest_vol_idx = sorted_indices[0]
        highest_vol_idx = sorted_indices[-1]
        
        middle_indices = sorted_indices[1:-1]
        
        self.state_mapping = {}
        self.state_mapping[int(lowest_vol_idx)] = "COMPRESSION"
        self.state_mapping[int(highest_vol_idx)] = "CHAOTIC"
        
        # Check absolute mean returns (index 0) for middle states
        mid_returns = [abs(self.means[idx, 0]) for idx in middle_indices]  # type: ignore[index]
        if mid_returns[0] >= mid_returns[1]:
            self.state_mapping[int(middle_indices[0])] = "TRENDING"
            self.state_mapping[int(middle_indices[1])] = "RANGE"
        else:
            self.state_mapping[int(middle_indices[0])] = "RANGE"
            self.state_mapping[int(middle_indices[1])] = "TRENDING"
            
        self.logger.info(f"📊 Decoded HMM Regime Mapping: {self.state_mapping}")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Decode the most probable hidden states using the Viterbi algorithm.
        X shape: (T, n_features)
        Returns: integer array of states of shape (T,)
        """
        T, D = X.shape
        if not self.is_fitted or self.means is None:
            return np.zeros(T, dtype=int)

        # Log probability matrices
        B_log = np.zeros((T, self.n_states))
        for s in range(self.n_states):
            # Compute log PDF
            probs = np.zeros(T)
            for d in range(D):
                mean = self.means[s, d]  # type: ignore[index]
                std = np.sqrt(self.covs[s, d] + 1e-6)  # type: ignore[index]
                probs += norm.logpdf(X[:, d], loc=mean, scale=std)
            B_log[:, s] = probs

        # Viterbi DP
        viterbi = np.zeros((T, self.n_states))
        backpointer = np.zeros((T, self.n_states), dtype=int)
        
        start_log = np.log(self.start_prob + 1e-10)
        trans_log = np.log(self.trans_mat + 1e-10)
        
        viterbi[0] = start_log + B_log[0]
        
        for t in range(1, T):
            for s in range(self.n_states):
                val = viterbi[t-1] + trans_log[:, s]
                best_state = np.argmax(val)
                viterbi[t, s] = val[best_state] + B_log[t, s]
                backpointer[t, s] = best_state

        # Traceback
        states = np.zeros(T, dtype=int)
        states[T-1] = np.argmax(viterbi[T-1])
        
        for t in range(T-2, -1, -1):
            states[t] = backpointer[t+1, states[t+1]]
            
        return states

    def predict_regime(self, X_latest: np.ndarray) -> str:
        """
        Predict the regime name for the latest feature values.
        X_latest shape: (1, n_features) or (n_features,)
        """
        if X_latest.ndim == 1:
            X_latest = X_latest[np.newaxis, :]
        
        # We need a sequence to decode, so if it is single sample we run a mock decoding
        # using the log emission probability directly.
        if not self.is_fitted or self.means is None:
            return "RANGE"

        probs = np.zeros(self.n_states)
        for s in range(self.n_states):
            for d in range(X_latest.shape[1]):
                mean = self.means[s, d]  # type: ignore[index]
                std = np.sqrt(self.covs[s, d] + 1e-6)  # type: ignore[index]
                probs[s] += norm.logpdf(X_latest[0, d], loc=mean, scale=std)
        
        best_state = int(np.argmax(probs))
        return self.state_mapping.get(best_state, "RANGE")

    def save_parameters(self):
        """Save model parameters to data/hmm_parameters.json."""
        try:
            os.makedirs("data", exist_ok=True)
            data = {
                "start_prob": self.start_prob.tolist(),
                "trans_mat": self.trans_mat.tolist(),
                "means": self.means.tolist() if self.means is not None else None,
                "covs": self.covs.tolist() if self.covs is not None else None,
                "state_mapping": {str(k): v for k, v in self.state_mapping.items()}
            }
            with open(HMM_PARAMS_FILE, "w") as f:
                json.dump(data, f, indent=4)
            self.logger.info(f"Saved fitted HMM parameters to {HMM_PARAMS_FILE}")
        except Exception as e:
            self.logger.error(f"Failed to save HMM parameters: {e}")

    def load_parameters(self):
        """Load parameters from file if exists."""
        if os.path.exists(HMM_PARAMS_FILE):
            try:
                with open(HMM_PARAMS_FILE, "r") as f:
                    data = json.load(f)
                if data.get("means") is not None:
                    self.start_prob = np.array(data["start_prob"])
                    self.trans_mat = np.array(data["trans_mat"])
                    self.means = np.array(data["means"])
                    self.covs = np.array(data["covs"])
                    self.state_mapping = {int(k): v for k, v in data["state_mapping"].items()}
                    self.is_fitted = True
                    self.logger.info(f"Loaded HMM parameters from {HMM_PARAMS_FILE}")
            except Exception as e:
                self.logger.error(f"Failed to load HMM parameters: {e}")
