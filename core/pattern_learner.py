# core/pattern_learner.py
import os
import json
from core.feature_extractor import FeatureExtractor
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import logging
from collections import defaultdict
import torch
import torch.nn as nn
import torch.optim as optim
from core.experience_memory import ExperienceMemory

class PulseViperNeuralNet(nn.Module):
    def __init__(self, input_dim: int = 30, hidden_dim: int = 32):
        super(PulseViperNeuralNet, self).__init__()
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
            nn.Sigmoid()
        )
        
    def forward(self, x):
        if x.dim() == 1:
            x = x.unsqueeze(0)
            return self.network(x).squeeze(0)
        return self.network(x)

class KMeansClustering:
    def __init__(self, k: int = 4):
        self.k = k
        self.centroids: float | np.ndarray | List = []
        
    def fit(self, X: np.ndarray, max_iters: int = 20):
        if len(X) == 0:
            return
        if len(X) < self.k:
            self.centroids = np.array([X[i] for i in range(len(X))] + [[0.0] * X.shape[1]] * (self.k - len(X)))
            return
        
        # Initialize centroids randomly
        indices = np.random.choice(X.shape[0], self.k, replace=False)
        self.centroids = X[indices].copy()
        
        for _ in range(max_iters):
            clusters = [[] for _ in range(self.k)]
            for point in X:
                distances = np.linalg.norm(self.centroids - point, axis=1)
                cluster_idx = np.argmin(distances)
                clusters[cluster_idx].append(point)
                
            new_centroids = []
            for idx in range(self.k):
                if len(clusters[idx]) > 0:
                    new_centroids.append(np.mean(clusters[idx], axis=0))
                else:
                    new_centroids.append(self.centroids[idx])
            self.centroids = np.array(new_centroids)
            
    def predict(self, point: np.ndarray) -> int:
        if isinstance(self.centroids, np.ndarray) and self.centroids.size == 0:
            return 0
        if isinstance(self.centroids, list) and len(self.centroids) == 0:
            return 0
        distances = np.linalg.norm(self.centroids - point, axis=1)
        return int(np.argmin(distances))

class NaiveBayesClassifier:
    def __init__(self):
        self.class_priors = {0: 0.5, 1: 0.5}
        self.discrete_conds = {}
        self.continuous_conds = {}
        
    def fit(self, X_discrete: List[Dict[str, str]], X_continuous: List[Dict[str, float]], y: List[int]):
        n = len(y)
        if n < 5:
            return
            
        classes = [0, 1]
        self.class_priors[1] = sum(y) / n
        self.class_priors[0] = 1.0 - self.class_priors[1]
        
        # Discrete conditional probabilities
        self.discrete_conds = {c: {} for c in classes}
        discrete_keys = X_discrete[0].keys() if X_discrete else []
        for key in discrete_keys:
            for c in classes:
                matching_y = [i for i, val in enumerate(y) if val == c]
                total_c = len(matching_y)
                values_in_c = [X_discrete[i][key] for i in matching_y]
                
                counts = defaultdict(int)
                for val in values_in_c:
                    counts[val] += 1
                
                unique_vals = set(counts.keys())
                self.discrete_conds[c][key] = {}
                for val in unique_vals:
                    self.discrete_conds[c][key][val] = (counts[val] + 1) / (total_c + len(unique_vals) + 1e-9)
                    
        # Continuous conditionals (Gaussian parameters)
        self.continuous_conds = {c: {} for c in classes}
        continuous_keys = X_continuous[0].keys() if X_continuous else []
        for key in continuous_keys:
            for c in classes:
                matching_y = [i for i, val in enumerate(y) if val == c]
                values_in_c = [X_continuous[i][key] for i in matching_y]
                if len(values_in_c) > 1:
                    mean = float(np.mean(values_in_c))
                    std = float(np.std(values_in_c)) + 1e-5
                else:
                    mean = 0.0
                    std = 1.0
                self.continuous_conds[c][key] = (mean, std)
                
    def predict_probability(self, x_discrete: Dict[str, str], x_continuous: Dict[str, float]) -> float:
        posteriors = {}
        for c in [0, 1]:
            prior = self.class_priors[c]
            prob = np.log(prior + 1e-9)
            
            for key, val in x_discrete.items():
                if c in self.discrete_conds and key in self.discrete_conds[c] and val in self.discrete_conds[c][key]:
                    prob += np.log(self.discrete_conds[c][key][val] + 1e-9)
                else:
                    prob += np.log(0.1)
                    
            for key, val in x_continuous.items():
                if c in self.continuous_conds and key in self.continuous_conds[c]:
                    mean, std = self.continuous_conds[c][key]
                    exponent = np.exp(-((val - mean) ** 2) / (2 * (std ** 2) + 1e-9))
                    pdf = (1 / (np.sqrt(2 * np.pi) * std + 1e-9)) * exponent
                    prob += np.log(pdf + 1e-9)
                    
            posteriors[c] = prob
            
        max_val = max(posteriors[0], posteriors[1])
        e0 = np.exp(posteriors[0] - max_val)
        e1 = np.exp(posteriors[1] - max_val)
        return float(e1 / (e0 + e1 + 1e-9))


class ChartPatternDetector:
    """
    Institutional SMC Chart Pattern Detector.
    Detects patterns from M1/M5/H1 dataframes and returns confidence scores.

    Patterns detected:
      ORDER_BLOCK      — Last bearish/bullish candle before a strong impulsive move
      FVG              — Fair Value Gap (imbalance between candle[-2].high and candle[0].low)
      BREAKER_BLOCK    — Previously broken OB that flipped to opposite polarity
      LIQUIDITY_SWEEP  — Wick beyond prior swing H/L with body close back inside
      MSS              — Market Structure Shift: first close beyond internal swing
      DISPLACEMENT     — Series of 3+ strong directional closes
      INDUCEMENT       — Small false break before real reversal move
      CRT_MANIPULATION — Candle that sweeps both high AND low within the range then closes inside
    """

    @staticmethod
    def detect(df_m1: pd.DataFrame,
               df_m5: Optional[pd.DataFrame] = None,
               df_h1: Optional[pd.DataFrame] = None,
               window: int = 5) -> Dict:
        """
        Detect all SMC patterns across available timeframes.
        Returns dict: {pattern_name: {'detected': bool, 'confidence': float, 'level': float|None}}
        """
        results = {}

        def _score(conditions: list) -> float:
            """Return normalized confidence from a list of bool conditions."""
            if not conditions:
                return 0.0
            return round(sum(conditions) / len(conditions), 3)

        try:
            # ── ORDER BLOCK (H1 preferred, fallback M5) ────────────────────────
            ob_df = df_h1 if (df_h1 is not None and len(df_h1) >= 10) else df_m5
            if ob_df is not None and len(ob_df) >= 10:
                closes = ob_df['close'].values
                opens = ob_df['open'].values
                highs = ob_df['high'].values
                lows = ob_df['low'].values
                # OB: last bearish candle (close<open) before 3 bullish candles
                ob_bull_level = None
                ob_bear_level = None
                for i in range(len(closes) - 4, max(0, len(closes) - 15), -1):
                    # Bullish OB: bearish candle[i] → 3 bullish candles after
                    if closes[i] < opens[i]:
                        subsequent = closes[i+1:i+4] if i+4 <= len(closes) else closes[i+1:]
                        if len(subsequent) >= 2 and all(subsequent > opens[i+1:i+1+len(subsequent)]):
                            ob_bull_level = highs[i]
                            break
                    # Bearish OB: bullish candle[i] → 3 bearish candles after
                    if closes[i] > opens[i]:
                        subsequent = closes[i+1:i+4] if i+4 <= len(closes) else closes[i+1:]
                        if len(subsequent) >= 2 and all(subsequent < opens[i+1:i+1+len(subsequent)]):
                            ob_bear_level = lows[i]
                            break
                results['ORDER_BLOCK_BULL'] = {
                    'detected': ob_bull_level is not None,
                    'confidence': 0.80 if ob_bull_level is not None else 0.0,
                    'level': ob_bull_level
                }
                results['ORDER_BLOCK_BEAR'] = {
                    'detected': ob_bear_level is not None,
                    'confidence': 0.80 if ob_bear_level is not None else 0.0,
                    'level': ob_bear_level
                }

            # ── FVG (M1-level for precision) ──────────────────────────────────
            if df_m1 is not None and len(df_m1) >= 5:
                highs_m1 = df_m1['high'].values
                lows_m1 = df_m1['low'].values
                fvg_bull = None
                fvg_bear = None
                for i in range(len(highs_m1) - 3, max(0, len(highs_m1) - 20), -1):
                    # Bullish FVG: candle[i-1].high < candle[i+1].low
                    if i + 1 < len(highs_m1) and highs_m1[i-1] < lows_m1[i+1]:
                        fvg_bull = (highs_m1[i-1] + lows_m1[i+1]) / 2
                        break
                for i in range(len(lows_m1) - 3, max(0, len(lows_m1) - 20), -1):
                    # Bearish FVG: candle[i-1].low > candle[i+1].high
                    if i + 1 < len(lows_m1) and lows_m1[i-1] > highs_m1[i+1]:
                        fvg_bear = (lows_m1[i-1] + highs_m1[i+1]) / 2
                        break
                results['FVG_BULL'] = {
                    'detected': fvg_bull is not None,
                    'confidence': 0.75 if fvg_bull is not None else 0.0,
                    'level': fvg_bull
                }
                results['FVG_BEAR'] = {
                    'detected': fvg_bear is not None,
                    'confidence': 0.75 if fvg_bear is not None else 0.0,
                    'level': fvg_bear
                }

            # ── LIQUIDITY SWEEP (M1) ──────────────────────────────────────────
            if df_m1 is not None and len(df_m1) >= 10:
                m1_h = df_m1['high'].values
                m1_l = df_m1['low'].values
                m1_c = df_m1['close'].values
                # Find prior swing high/low over last window bars
                lookback = min(window + 5, len(m1_h) - 3)
                prior_high = max(m1_h[-lookback:-3])
                prior_low = min(m1_l[-lookback:-3])
                last_high = m1_h[-2]
                last_low = m1_l[-2]
                last_close = m1_c[-2]
                sweep_high = last_high > prior_high and last_close < prior_high
                sweep_low = last_low < prior_low and last_close > prior_low
                results['LIQUIDITY_SWEEP_HIGH'] = {
                    'detected': sweep_high,
                    'confidence': _score([sweep_high, last_high > prior_high * 1.001]),
                    'level': prior_high if sweep_high else None
                }
                results['LIQUIDITY_SWEEP_LOW'] = {
                    'detected': sweep_low,
                    'confidence': _score([sweep_low, last_low < prior_low * 0.999]),
                    'level': prior_low if sweep_low else None
                }

            # ── MSS (Market Structure Shift) on M1 ───────────────────────────
            if df_m1 is not None and len(df_m1) >= 15:
                m1_c = df_m1['close'].values
                m1_h = df_m1['high'].values
                m1_l = df_m1['low'].values
                # Internal swing high broken by close above it = bullish MSS
                internal_swing_high = max(m1_h[-12:-4])
                internal_swing_low = min(m1_l[-12:-4])
                last_c = m1_c[-2]
                mss_bull = last_c > internal_swing_high
                mss_bear = last_c < internal_swing_low
                results['MSS_BULLISH'] = {
                    'detected': mss_bull,
                    'confidence': 0.72 if mss_bull else 0.0,
                    'level': internal_swing_high if mss_bull else None
                }
                results['MSS_BEARISH'] = {
                    'detected': mss_bear,
                    'confidence': 0.72 if mss_bear else 0.0,
                    'level': internal_swing_low if mss_bear else None
                }

            # ── DISPLACEMENT (3+ consecutive strong closes in one direction) ─
            if df_m1 is not None and len(df_m1) >= 8:
                closes_m1 = df_m1['close'].values
                opens_m1 = df_m1['open'].values
                bodies = closes_m1[-6:] - opens_m1[-6:]
                bull_displacement = all(bodies[-3:] > 0) and sum(bodies[-3:]) > 0
                bear_displacement = all(bodies[-3:] < 0) and sum(bodies[-3:]) < 0
                results['DISPLACEMENT_BULL'] = {
                    'detected': bull_displacement,
                    'confidence': 0.65 if bull_displacement else 0.0,
                    'level': None
                }
                results['DISPLACEMENT_BEAR'] = {
                    'detected': bear_displacement,
                    'confidence': 0.65 if bear_displacement else 0.0,
                    'level': None
                }

            # ── CRT MANIPULATION (sweeps both high and low then closes inside) 
            if df_m1 is not None and len(df_m1) >= 10:
                # The CRT manipulation candle sweeps the range high AND low
                crt_ref_high = max(df_m1['high'].values[-10:-3])
                crt_ref_low = min(df_m1['low'].values[-10:-3])
                last_m1 = df_m1.iloc[-2]
                crt_manip = (last_m1['high'] > crt_ref_high and
                             last_m1['low'] < crt_ref_low and
                             crt_ref_low < last_m1['close'] < crt_ref_high)
                results['CRT_MANIPULATION'] = {
                    'detected': crt_manip,
                    'confidence': 0.90 if crt_manip else 0.0,
                    'level': (crt_ref_high + crt_ref_low) / 2 if crt_manip else None
                }

            # ── VSA PATTERNS (using detect_vsa_signals) ──────────────────────
            from utils.volume_analyzer import VolumeAnalyzer
            vsa_signals = []
            if df_m1 is not None and 'atr' in df_m1.columns:
                vsa_signals += VolumeAnalyzer.detect_vsa_signals(df_m1, df_m1['atr'], lookback=5)
            if df_m5 is not None and 'atr' in df_m5.columns:
                vsa_signals += VolumeAnalyzer.detect_vsa_signals(df_m5, df_m5['atr'], lookback=5)
                
            vsa_patterns_list = [
                'VSA_SPRING', 'VSA_UPTHRUST', 'VSA_STOPPING_VOLUME',
                'VSA_NO_SUPPLY', 'VSA_NO_DEMAND', 'VSA_BUYING_CLIMAX', 'VSA_SELLING_CLIMAX'
            ]
            for pat in vsa_patterns_list:
                results[pat] = {'detected': False, 'confidence': 0.0, 'level': None}
                
            for sig in vsa_signals:
                pat_name = f"VSA_{sig['pattern']}"
                results[pat_name] = {
                    'detected': True,
                    'confidence': sig['confidence'],
                    'level': sig['price']
                }

        except Exception as e:
            pass  # Fail silently — pattern detection is advisory only

        return results

    @staticmethod
    def get_summary(detected: Dict) -> Tuple[List[str], float, Optional[str]]:
        """
        Summarize detected patterns into:
        - List of detected pattern names
        - Overall confidence (max of detected confidences)
        - Directional bias ('bullish', 'bearish', None)
        """
        bull_patterns = {'ORDER_BLOCK_BULL', 'FVG_BULL', 'LIQUIDITY_SWEEP_LOW',
                         'MSS_BULLISH', 'DISPLACEMENT_BULL',
                         'VSA_SPRING', 'VSA_STOPPING_VOLUME', 'VSA_NO_SUPPLY', 'VSA_SELLING_CLIMAX'}
        bear_patterns = {'ORDER_BLOCK_BEAR', 'FVG_BEAR', 'LIQUIDITY_SWEEP_HIGH',
                         'MSS_BEARISH', 'DISPLACEMENT_BEAR',
                         'VSA_UPTHRUST', 'VSA_NO_DEMAND', 'VSA_BUYING_CLIMAX'}

        found = [k for k, v in detected.items() if v.get('detected')]
        if not found:
            return [], 0.0, None

        max_conf = max(detected[k]['confidence'] for k in found)
        bull_count = sum(1 for p in found if p in bull_patterns)
        bear_count = sum(1 for p in found if p in bear_patterns)

        direction = None
        if bull_count > bear_count:
            direction = 'bullish'
        elif bear_count > bull_count:
            direction = 'bearish'

        return found, round(max_conf, 3), direction


class PatternLearner:
    def __init__(self, memory: ExperienceMemory):
        self.memory = memory
        self.patterns = defaultdict(list)
        self.market_regimes = {}
        self.logger = logging.getLogger('PulseViper.PatternLearner')
        
        # Supervised & Unsupervised Models
        self.kmeans = KMeansClustering(k=4)
        self.classifier = NaiveBayesClassifier()
        self.training_stats = {}
        
        # PyTorch Neural Net & Threading Lock
        import threading
        self.model_lock = threading.Lock()
        self.nn_ready = False
        
        self.nn_model = PulseViperNeuralNet()
        self.nn_optimizer = optim.Adam(self.nn_model.parameters(), lr=0.003, weight_decay=1e-4)
        self.nn_criterion = nn.BCELoss()
        self.load_nn_model()
        
        # Pattern detection parameters
        self.min_pattern_occurrence = 2
        self.confidence_threshold = 0.5
        
        # Load saved models and patterns
        self.load_patterns()
        
    @property
    def nb_ready(self) -> bool:
        """Dynamic readiness check for Naive Bayes classifier."""
        return len(self.classifier.discrete_conds) > 0
        
    def detect_visual_patterns(self, df: pd.DataFrame) -> List[str]:
        """
        Scan recent candles to locate structural and candlestick patterns:
        - DOUBLE_TOP / DOUBLE_BOTTOM
        - BULLISH_ENGULFING / BEARISH_ENGULFING
        - PIN_BAR (Hammer / Shooting Star)
        - INSIDE_BAR
        - LIQUIDITY_SWEEP (high/low wick sweeps)
        """
        patterns = []
        if len(df) < 5:
            return patterns
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        last_range = last['high'] - last['low']
        if last_range > 0:
            last_body = abs(last['close'] - last['open'])
            upper_wick = last['high'] - max(last['open'], last['close'])
            lower_wick = min(last['open'], last['close']) - last['low']
            
            # Pin Bar Hammer
            if lower_wick / last_range >= 0.45 and last_body / last_range <= 0.4:
                patterns.append("PIN_BAR_BULLISH")
            # Pin Bar Shooting Star
            elif upper_wick / last_range >= 0.45 and last_body / last_range <= 0.4:
                patterns.append("PIN_BAR_BEARISH")
                
            # Inside Bar
            if last['high'] < prev['high'] and last['low'] > prev['low']:
                patterns.append("INSIDE_BAR")
                
        # Engulfing pattern
        prev_body_dir = prev['close'] - prev['open']
        last_body_dir = last['close'] - last['open']
        if prev_body_dir < 0 and last_body_dir > 0:
            if last['close'] >= prev['open'] and last['open'] <= prev['close']:
                patterns.append("BULLISH_ENGULFING")
        elif prev_body_dir > 0 and last_body_dir < 0:
            if last['close'] <= prev['open'] and last['open'] >= prev['close']:
                patterns.append("BEARISH_ENGULFING")
                
        # Swings detection (swing high / swing low)
        swing_highs = []
        swing_lows = []
        window = 3
        highs = df['high'].values
        lows = df['low'].values
        n = len(df)
        
        for i in range(window, n - window):
            is_sh = True
            for w in range(1, window + 1):
                if highs[i] < highs[i - w] or highs[i] < highs[i + w]:
                    is_sh = False
                    break
            if is_sh:
                swing_highs.append(float(highs[i]))
                
            is_sl = True
            for w in range(1, window + 1):
                if lows[i] > lows[i - w] or lows[i] > lows[i + w]:
                    is_sl = False
                    break
            if is_sl:
                swing_lows.append(float(lows[i]))
                
        # Double Top / Double Bottom
        if len(swing_highs) >= 2:
            h1, h2 = swing_highs[-1], swing_highs[-2]
            if abs(h1 - h2) / ((h1 + h2)/2) < 0.0015:
                patterns.append("DOUBLE_TOP")
        if len(swing_lows) >= 2:
            l1, l2 = swing_lows[-1], swing_lows[-2]
            if abs(l1 - l2) / ((l1 + l2)/2) < 0.0015:
                patterns.append("DOUBLE_BOTTOM")
                
        # Liquidity Sweep
        if len(swing_highs) > 0 and last['high'] > swing_highs[-1] and last['close'] < swing_highs[-1]:
            patterns.append("LIQUIDITY_SWEEP_HIGH")
        if len(swing_lows) > 0 and last['low'] < swing_lows[-1] and last['close'] > swing_lows[-1]:
            patterns.append("LIQUIDITY_SWEEP_LOW")
            
        return patterns

    def detect_visual_patterns_numpy(self, opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> List[str]:
        """Fast numpy-based visual pattern detection from sliced arrays."""
        patterns = []
        n = len(closes)
        if n < 5:
            return patterns
            
        last_high = highs[-1]
        last_low = lows[-1]
        last_open = opens[-1]
        last_close = closes[-1]
        
        prev_high = highs[-2]
        prev_low = lows[-2]
        prev_open = opens[-2]
        prev_close = closes[-2]
        
        last_range = last_high - last_low
        last_body = abs(last_close - last_open)
        upper_wick = last_high - max(last_open, last_close)
        lower_wick = min(last_open, last_close) - last_low
        
        if last_range > 0:
            # Pin Bar Hammer
            if lower_wick / last_range >= 0.45 and last_body / last_range <= 0.4:
                patterns.append("PIN_BAR_BULLISH")
            # Pin Bar Shooting Star
            elif upper_wick / last_range >= 0.45 and last_body / last_range <= 0.4:
                patterns.append("PIN_BAR_BEARISH")
                
            # Inside Bar
            if last_high < prev_high and last_low > prev_low:
                patterns.append("INSIDE_BAR")
                
        # Engulfing pattern
        prev_body_dir = prev_close - prev_open
        last_body_dir = last_close - last_open
        if prev_body_dir < 0 and last_body_dir > 0:
            if last_close >= prev_open and last_open <= prev_close:
                patterns.append("BULLISH_ENGULFING")
        elif prev_body_dir > 0 and last_body_dir < 0:
            if last_close <= prev_open and last_open >= prev_close:
                patterns.append("BEARISH_ENGULFING")
                
        # Swings detection (swing high / swing low)
        swing_highs = []
        swing_lows = []
        window = 3
        
        for i in range(window, n - window):
            is_sh = True
            for w in range(1, window + 1):
                if highs[i] < highs[i - w] or highs[i] < highs[i + w]:
                    is_sh = False
                    break
            if is_sh:
                swing_highs.append(float(highs[i]))
                
            is_sl = True
            for w in range(1, window + 1):
                if lows[i] > lows[i - w] or lows[i] > lows[i + w]:
                    is_sl = False
                    break
            if is_sl:
                swing_lows.append(float(lows[i]))
                
        # Double Top / Double Bottom
        if len(swing_highs) >= 2:
            h1, h2 = swing_highs[-1], swing_highs[-2]
            if abs(h1 - h2) / ((h1 + h2)/2) < 0.0015:
                patterns.append("DOUBLE_TOP")
        if len(swing_lows) >= 2:
            l1, l2 = swing_lows[-1], swing_lows[-2]
            if abs(l1 - l2) / ((l1 + l2)/2) < 0.0015:
                patterns.append("DOUBLE_BOTTOM")
                
        # Liquidity Sweep
        if len(swing_highs) > 0 and last_high > swing_highs[-1] and last_close < swing_highs[-1]:
            patterns.append("LIQUIDITY_SWEEP_HIGH")
        if len(swing_lows) > 0 and last_low < swing_lows[-1] and last_close > swing_lows[-1]:
            patterns.append("LIQUIDITY_SWEEP_LOW")
            
        return patterns

    def _quantize_smc_state(self, features: Dict) -> str:
        """Quantize SMC features for simple dictionary pattern lookups"""
        quantized = {}
        bias_val = features.get('active_bias', 0)
        quantized['bias'] = 'BULLISH' if bias_val == 1 else ('BEARISH' if bias_val == -1 else 'NEUTRAL')
        
        price = features.get('price', features.get('close', 0.0))
        support = features.get('support', 0.0)
        resistance = features.get('resistance', 0.0)
        if resistance > support and support > 0:
            pct = (price - support) / (resistance - support)
            if pct < 0.35: quantized['zone'] = 'DISCOUNT'
            elif pct > 0.65: quantized['zone'] = 'PREMIUM'
            else: quantized['zone'] = 'EQUILIBRIUM'
        else:
            quantized['zone'] = 'EQUILIBRIUM'
            
        quantized['fvg'] = str(features.get('fvg_class', 'none')).upper()
        
        had_sweep = features.get('liq_sweep_type', 0) != 0
        had_mss = features.get('mss_signal', 0) != 0
        if had_sweep and had_mss: quantized['setup'] = 'SHARP_TURN'
        elif had_mss: quantized['setup'] = 'MSS_ONLY'
        elif had_sweep: quantized['setup'] = 'SWEEP_ONLY'
        else: quantized['setup'] = 'CONTINUATION'
        
        return str(sorted(quantized.items()))

    def train_on_history(self, symbol: str, df_htf: pd.DataFrame, df_context: pd.DataFrame, df_ltf: pd.DataFrame):
        """Historical auto-training scanning: detects patterns, fits K-Means and trains Naive Bayes"""
        self.logger.info(f"⏳ Starting visual & ML historical training on {symbol}...")
        
        from utils.settings_manager import settings_manager
        swing_window = settings_manager.get("smc_swing_window", 3)
        
        from utils.smc_indicators import SMCIndicators
        df_htf_feat = SMCIndicators.compute_smc_features(df_htf, window=swing_window)
        df_context_feat = SMCIndicators.compute_smc_features(df_context, window=swing_window)
        df_ltf_feat = SMCIndicators.compute_smc_features(df_ltf, window=swing_window)
        
        # Shift swing-dependent columns to prevent lookahead leakage
        leakage_cols = [
            'is_swing_high', 'is_swing_low', 'is_sth', 'is_stl', 'is_ith', 'is_itl',
            'support', 'resistance', 'liq_sweep_type', 'liq_sweep_level', 'mss_signal',
            'active_bias', 'ob_reaction_signal', 'sr_reaction_signal', 'retest_pullback_signal',
            'trend_shift_signal'
        ]
        for col in leakage_cols:
            if col in df_ltf_feat.columns:
                df_ltf_feat[col] = df_ltf_feat[col].shift(swing_window).fillna(0)
            if col in df_context_feat.columns:
                df_context_feat[col] = df_context_feat[col].shift(swing_window).fillna(0)
            if col in df_htf_feat.columns:
                df_htf_feat[col] = df_htf_feat[col].shift(swing_window).fillna(0)
        
        n_ltf = len(df_ltf_feat)
        recorded_wins = 0
        recorded_losses = 0
        
        htf_indices = df_htf_feat.index
        context_indices = df_context_feat.index

        # Pre-convert raw M1 candles columns to numpy arrays for speed
        ltf_opens = df_ltf['open'].values
        ltf_highs = df_ltf['high'].values
        ltf_lows = df_ltf['low'].values
        ltf_closes = df_ltf['close'].values

        # Convert feature dataframes to numpy arrays for lightning fast indexing
        htf_biases = df_htf_feat['active_bias'].values
        context_sweeps = df_context_feat['liq_sweep_type'].values
        
        ltf_mss_signals = df_ltf_feat['mss_signal'].values
        ltf_lows_feat = df_ltf_feat['low'].values
        ltf_highs_feat = df_ltf_feat['high'].values
        ltf_closes_feat = df_ltf_feat['close'].values
        ltf_atrs = df_ltf_feat['atr'].values
        ltf_volatilities = df_ltf_feat['volatility'].values
        ltf_supports = df_ltf_feat['support'].values
        ltf_resistances = df_ltf_feat['resistance'].values
        ltf_fvg_classes = df_ltf_feat['fvg_class'].values
        
        # Pre-convert timestamps to list/array to avoid index slicing overhead
        ltf_timestamps = df_ltf_feat.index

        training_data_discrete = []
        training_data_continuous = []
        outcomes = []
        cluster_feature_matrix = []
        nn_inputs = []
        nn_targets = []

        # Extract swing legs from df_ltf using window=5 for clean swings
        df_ltf_swings = SMCIndicators.detect_swing_points(df_ltf, window=5)
        
        swing_points = []
        ltf_highs_sw = df_ltf_swings['high'].values
        ltf_lows_sw = df_ltf_swings['low'].values
        is_sh = df_ltf_swings['is_swing_high'].values
        is_sl = df_ltf_swings['is_swing_low'].values
        ltf_timestamps_sw = df_ltf_swings.index
        
        for idx in range(len(df_ltf_swings)):
            if is_sh[idx]:
                swing_points.append({'type': 'HIGH', 'price': ltf_highs_sw[idx], 'time': ltf_timestamps_sw[idx]})
            if is_sl[idx]:
                swing_points.append({'type': 'LOW', 'price': ltf_lows_sw[idx], 'time': ltf_timestamps_sw[idx]})
                
        # Alternate HIGH and LOW points
        alternating = []
        for pt in swing_points:
            if not alternating:
                alternating.append(pt)
                continue
            last = alternating[-1]
            if last['type'] == pt['type']:
                if pt['type'] == 'HIGH':
                    if pt['price'] > last['price']:
                        alternating[-1] = pt
                else:
                    if pt['price'] < last['price']:
                        alternating[-1] = pt
            else:
                alternating.append(pt)
                
        # Create swing legs
        legs = []
        for k in range(len(alternating) - 1):
            p1 = alternating[k]
            p2 = alternating[k+1]
            legs.append({
                'type': 'BULLISH' if p1['type'] == 'LOW' else 'BEARISH',
                'start_price': p1['price'],
                'end_price': p2['price'],
                'start_time': p1['time'],
                'end_time': p2['time']
            })
            
        self.logger.info(f"Identified {len(legs)} swing legs for pattern mining.")

        for leg_idx, leg in enumerate(legs):
            t_start = leg['end_time']
            
            # Find LTF index where pullback starts
            start_idx = ltf_timestamps.searchsorted(t_start)
            if start_idx >= len(df_ltf_feat):
                continue
                
            L_swing = leg['start_price']
            H_swing = leg['end_price']
            
            end_idx = len(df_ltf_feat) - 50
            for idx in range(start_idx, len(df_ltf_feat)):
                price = ltf_closes_feat[idx]
                if leg['type'] == 'BULLISH':
                    if price > H_swing:
                        end_idx = idx
                        break
                    if price < L_swing:
                        end_idx = idx
                        break
                else: # BEARISH
                    if price < H_swing:
                        end_idx = idx
                        break
                    if price > L_swing:
                        end_idx = idx
                        break
                        
            if end_idx <= start_idx:
                continue
                
            # Limit to one trigger per swing leg to prevent duplication
            triggered_in_leg = False
            
            for i in range(start_idx, end_idx):
                if triggered_in_leg:
                    break
                    
                t = ltf_timestamps[i]
                entry_price = ltf_closes_feat[i]
                
                l_sw = float(L_swing)
                h_sw = float(H_swing)
                swing_min = min(l_sw, h_sw)
                swing_max = max(l_sw, h_sw)
                swing_mid = swing_min + 0.5 * (swing_max - swing_min)
                
                in_zone = False
                if leg['type'] == 'BULLISH':
                    if entry_price <= swing_mid:
                        in_zone = True
                else:
                    if entry_price >= swing_mid:
                        in_zone = True
                        
                if not in_zone:
                    continue
                    
                idx_htf = htf_indices.searchsorted(t, side='right')
                idx_context = context_indices.searchsorted(t, side='right')
                
                if idx_htf == 0 or idx_context == 0:
                    continue
                    
                htf_bias = htf_biases[idx_htf - 1]
                
                # Context sweeps
                context_sweep = 0
                for k in range(idx_context - 1, max(-1, idx_context - 20), -1):
                    sweep_val = context_sweeps[k]
                    if sweep_val != 0:
                        context_sweep = int(sweep_val)
                        break
                        
                # LTF MSS
                ltf_mss = 0
                for k in range(i, max(-1, i - 10), -1):
                    mss_val = ltf_mss_signals[k]
                    if mss_val != 0:
                        ltf_mss = int(mss_val)
                        break
                        
                atr_val = ltf_atrs[i]
                support_val = ltf_supports[i]
                resistance_val = ltf_resistances[i]
                volatility_val = ltf_volatilities[i]
                fvg_class_val = ltf_fvg_classes[i]
                
                action = None
                is_bullish = (htf_bias == 1) and (context_sweep == 1 or ltf_mss == 1)
                is_bearish = (htf_bias == -1) and (context_sweep == -1 or ltf_mss == -1)
                
                if is_bullish and leg['type'] == 'BULLISH':
                    action = "BUY"
                elif is_bearish and leg['type'] == 'BEARISH':
                    action = "SELL"
                    
                if action is None:
                    continue
                    
                # Unsupervised clustering feature collection
                cluster_feature_matrix.append([
                    float(volatility_val),
                    float(abs(entry_price - (support_val if not np.isnan(support_val) else entry_price)) / (entry_price + 1e-9)),
                    float(atr_val / (entry_price + 1e-9))
                ])
                
                # Swing patterns detection
                start_idx_vis = max(0, i - 20)
                end_idx_vis = i + 1
                visual_patterns = self.detect_visual_patterns_numpy(
                    ltf_opens[start_idx_vis:end_idx_vis],
                    ltf_highs[start_idx_vis:end_idx_vis],
                    ltf_lows[start_idx_vis:end_idx_vis],
                    ltf_closes[start_idx_vis:end_idx_vis]
                )
                pattern_str = "|".join(visual_patterns) if visual_patterns else "NONE"
                
                # StopLoss/TakeProfit with proper ATR buffer (min 1.5 * ATR)
                raw_sl_dist = abs(entry_price - (L_swing if action == "BUY" else H_swing))
                sl_dist = max(raw_sl_dist, 1.5 * atr_val)
                if action == "BUY":
                    sl_price = entry_price - sl_dist
                    tp_price = entry_price + (1.5 * sl_dist)
                else:
                    sl_price = entry_price + sl_dist
                    tp_price = entry_price - (1.5 * sl_dist)
                
                pnl = 0.0
                resolved = False
                max_lookahead = min(n_ltf, i + 600)
                for j in range(i + 1, max_lookahead):
                    future_low = ltf_lows_feat[j]
                    future_high = ltf_highs_feat[j]
                    if action == "BUY":
                        if future_low <= sl_price:
                            pnl = -1.0
                            resolved = True
                            break
                        elif future_high >= tp_price:
                            pnl = 1.5
                            resolved = True
                            break
                    elif action == "SELL":
                        if future_high >= sl_price:
                            pnl = -1.0
                            resolved = True
                            break
                        elif future_low <= tp_price:
                            pnl = 1.5
                            resolved = True
                            break
                            
                if resolved:
                    disc_feat = {
                        'bias': 'BULLISH' if htf_bias == 1 else ('BEARISH' if htf_bias == -1 else 'NEUTRAL'),
                        'setup': 'SHARP_TURN' if (context_sweep != 0 and ltf_mss != 0) else 'MSS_OR_SWEEP',
                        'fvg': str(fvg_class_val).upper(),
                        'visual_patterns': pattern_str
                    }
                    cont_feat = {
                        'volatility': float(volatility_val),
                        'atr_pct': float(atr_val / (entry_price + 1e-9))
                    }
                    
                    training_data_discrete.append(disc_feat)
                    training_data_continuous.append(cont_feat)
                    outcomes.append(1 if pnl > 0 else 0)
                    
                    # Extract features for PyTorch Neural Network
                    nn_feat_dict = {
                        'active_bias': htf_bias,
                        'liq_sweep_type': context_sweep,
                        'mss_signal': ltf_mss,
                        'fvg_class': str(fvg_class_val),
                        'volatility': float(volatility_val),
                        'atr_pct': atr_val / (entry_price + 1e-9),
                        'rvol': 1.0,
                        'buy_pressure': 50.0,
                        'sell_pressure': 50.0,
                        'timestamp': float(pd.Timestamp(t).timestamp() if hasattr(t, 'timestamp') else (t.value // 10**9 if hasattr(t, 'value') else i))
                    }
                    nn_inputs.append(self.extract_nn_features(nn_feat_dict))
                    nn_targets.append(1.0 if pnl > 0 else 0.0)
                    
                    # Quantized dictionary storage
                    q_id = self._quantize_smc_state({
                        'active_bias': htf_bias,
                        'price': entry_price,
                        'support': support_val if not np.isnan(support_val) else entry_price,
                        'resistance': resistance_val if not np.isnan(resistance_val) else entry_price,
                        'fvg_class': fvg_class_val,
                        'liq_sweep_type': context_sweep,
                        'mss_signal': ltf_mss
                    })
                    
                    record = {
                        'pattern': q_id,
                        'outcome': pnl,
                        'timestamp': str(t)
                    }
                    if pnl > 0:
                        self.patterns[f"{symbol}_winning"].append(record)
                        recorded_wins += 1
                    else:
                        self.patterns[f"{symbol}_losing"].append(record)
                        recorded_losses += 1
                        
                    triggered_in_leg = True
 
        # Fit Unsupervised K-Means
        if cluster_feature_matrix:
            X_clust = np.array(cluster_feature_matrix)
            self.kmeans.fit(X_clust)
            self.logger.info(f"Unsupervised K-Means centroids fitted with {self.kmeans.k} clusters.")
            
        # Fit Supervised Naive Bayes Classifier
        if training_data_discrete and outcomes:
            self.classifier.fit(training_data_discrete, training_data_continuous, outcomes)
            self.logger.info(f"Supervised Naive Bayes Classifier fitted on {len(outcomes)} sample trades.")
            
        # Fit PyTorch Neural Network model
        if nn_inputs and nn_targets:
            try:
                inputs_tensor = torch.tensor(np.array(nn_inputs, dtype=np.float32))
                targets_tensor = torch.tensor(np.array(nn_targets, dtype=np.float32)).unsqueeze(1)
                
                self.nn_model.train()
                for epoch in range(10):
                    self.nn_optimizer.zero_grad()
                    outputs = self.nn_model(inputs_tensor)
                    loss = self.nn_criterion(outputs, targets_tensor)
                    loss.backward()
                    self.nn_optimizer.step()
                self.nn_model.eval()
                
                self.save_nn_model()
                self.nn_ready = True
                self.logger.info(f"🧠 PyTorch neural net trained on {len(nn_inputs)} history samples. Final loss: {loss.item():.4f}")
            except Exception as ex:
                self.logger.error(f"Failed to train PyTorch neural net on history: {ex}")
                self.nn_model.eval()
            
        self.training_stats[symbol] = {
            "wins": recorded_wins,
            "losses": recorded_losses,
            "total_samples": len(outcomes),
            "win_rate": round(recorded_wins / len(outcomes) * 100.0, 1) if outcomes else 0.0,
            "last_train_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_patterns()
        self.logger.info(f"✅ ML Historical training completed for {symbol}! Wins={recorded_wins}, Losses={recorded_losses}")

    def train_multi_strategy(self, symbol: str = "XAUUSDm", dfs: Optional[Dict[str, Any]] = None):
        """
        Train the Naive Bayes and PyTorch Neural Network models on historical data
        by evaluating Raja, ICT, Bank-to-Bank, VSA, AVC, and M1 Scalping setups
        over a rolling window of history and resolving their trade outcomes.
        """
        self.logger.info(f"⏳ Starting multi-strategy training pipeline for {symbol}...")
        
        dfs_dict: Dict[str, Any] = {}
        if dfs is None:
            from utils.mt5_data import fetch_ohlcv
            from utils.mt5_gateway import mt5_gateway as mt5
            dfs_dict = {
                'D1': fetch_ohlcv(symbol, mt5.TIMEFRAME_D1, 300),
                'H4': fetch_ohlcv(symbol, mt5.TIMEFRAME_H4, 300),
                'H1': fetch_ohlcv(symbol, mt5.TIMEFRAME_H1, 300),
                'M30': fetch_ohlcv(symbol, mt5.TIMEFRAME_M30, 200),
                'M15': fetch_ohlcv(symbol, mt5.TIMEFRAME_M15, 200),
                'M5': fetch_ohlcv(symbol, mt5.TIMEFRAME_M5, 200),
                'M1': fetch_ohlcv(symbol, mt5.TIMEFRAME_M1, 300)
            }
        else:
            dfs_dict = dfs
        
        df_d1 = dfs_dict.get('D1')
        df_h4 = dfs_dict.get('H4')
        df_h1 = dfs_dict.get('H1')
        df_m30 = dfs_dict.get('M30')
        df_m15 = dfs_dict.get('M15')
        df_m5 = dfs_dict.get('M5')
        df_m1 = dfs_dict.get('M1')

        if df_m1 is None or len(df_m1) < 120:
            self.logger.error("Insufficient M1 data for multi-strategy training")
            return

        # Compute indicators on M1 once with 3-bar shift to prevent leakage
        from utils.smc_indicators import SMCIndicators
        df_m1_feat = SMCIndicators.compute_smc_features(df_m1, window=3)
        leakage_cols = [
            'is_swing_high', 'is_swing_low', 'is_sth', 'is_stl', 'is_ith', 'is_itl',
            'support', 'resistance', 'liq_sweep_type', 'liq_sweep_level', 'mss_signal',
            'active_bias', 'ob_reaction_signal', 'sr_reaction_signal', 'retest_pullback_signal',
            'trend_shift_signal'
        ]
        for col in leakage_cols:
            if col in df_m1_feat.columns:
                df_m1_feat[col] = df_m1_feat[col].shift(3).fillna(0)
                
        # Calculate historical volume metrics
        from utils.volume_analyzer import VolumeAnalyzer
        rvol_series = VolumeAnalyzer.calculate_rvol(df_m1, period=20)
        bp_series, sp_series = VolumeAnalyzer.calculate_buying_selling_pressure(df_m1)

        from strategies.raja_strategy import RajaStrategy
        from strategies.ict_strategy import IctStrategy
        from strategies.bank_strategy import BankStrategy
        from strategies.vsa_strategy import VsaStrategy
        from strategies.avc_strategy import AvcStrategy
        from strategies.m1_scalping_strategy import M1ScalpingStrategy
        from strategies.smc_concepts_strategy import SmcConceptsStrategy
        
        timestamps = df_m1.index
        n_samples = len(df_m1)
        
        recorded_wins = 0
        recorded_losses = 0
        
        training_data_discrete = []
        training_data_continuous = []
        outcomes = []
        nn_inputs = []
        nn_targets = []
        
        for i in range(100, n_samples - 600, 5):
            t = timestamps[i]
            
            sub_m1 = df_m1.loc[:t]
            sub_m5 = df_m5.loc[:t] if df_m5 is not None else None
            sub_m15 = df_m15.loc[:t] if df_m15 is not None else None
            sub_m30 = df_m30.loc[:t] if df_m30 is not None else None
            sub_h1 = df_h1.loc[:t] if df_h1 is not None else None
            sub_h4 = df_h4.loc[:t] if df_h4 is not None else None
            sub_d1 = df_d1.loc[:t] if df_d1 is not None else None

            if len(sub_m1) < 50:
                continue
                
            current_price = float(sub_m1['close'].iloc[-1])
            atr_val = float(sub_m1['atr'].iloc[-1]) if 'atr' in sub_m1.columns else 1.5
            
            current_rvol = float(rvol_series.iloc[i]) if not np.isnan(rvol_series.iloc[i]) else 1.0
            current_bp = float(bp_series.iloc[i]) if not np.isnan(bp_series.iloc[i]) else 50.0
            current_sp = float(sp_series.iloc[i]) if not np.isnan(sp_series.iloc[i]) else 50.0
            volume_cache = {
                "profile": {
                    "poc_price": float(sub_h1['close'].rolling(50).mean().iloc[-1]) if sub_h1 is not None and len(sub_h1) >= 50 else current_price,
                    "hvn_prices": []
                },
                "rvol": current_rvol,
                "buy_pressure": current_bp,
                "sell_pressure": current_sp,
                "ofi": 0.0
            }
            
            actions = {}
            
            # Raja Strategy
            try:
                act, sl, tp, meta = RajaStrategy.evaluate_raja(sub_m15, sub_m30, sub_h1, sub_h4, current_price, atr_val, volume_cache)
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["RAJA"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] RajaStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] RajaStrategy evaluation failed at index {i}: {e}")
            
            # ICT Strategy
            try:
                act, sl, tp, meta = IctStrategy.evaluate_ict(sub_m1, sub_m5, sub_m15, sub_h1, sub_h4, current_price, atr_val, 0, volume_cache)
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["ICT"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] IctStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] IctStrategy evaluation failed at index {i}: {e}")
            
            # Bank Strategy
            try:
                act, sl, tp, meta = BankStrategy.evaluate_bank(sub_m1, sub_m5, sub_m15, sub_h1, sub_h4, current_price, atr_val, volume_cache)
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["BANK"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] BankStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] BankStrategy evaluation failed at index {i}: {e}")
            
            # VSA Strategy
            try:
                act, sl, tp, meta = VsaStrategy.evaluate_vsa(sub_m1, sub_m5, sub_h1, current_price, atr_val, volume_cache)
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["VSA"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] VsaStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] VsaStrategy evaluation failed at index {i}: {e}")
            
            # AVC Strategy
            try:
                act, sl, tp, meta = AvcStrategy.evaluate_avc(sub_m1, sub_m5, sub_m15, current_price, atr_val, volume_cache)
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["AVC"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] AvcStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] AvcStrategy evaluation failed at index {i}: {e}")
            
            # M1 Scalping Strategy
            try:
                act, sl, tp, meta = M1ScalpingStrategy.evaluate_m1_scalping(sub_m1, sub_m5, sub_m15, current_price, atr_val, volume_cache)
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["M1_SCALPING"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] M1ScalpingStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] M1ScalpingStrategy evaluation failed at index {i}: {e}")

            # SMC Concepts Strategy
            try:
                act, sl, tp, meta = SmcConceptsStrategy.evaluate_smc(sub_m1, sub_m5, sub_m15, sub_h1, sub_h4, current_price, atr_val, 0, volume_cache, "RANGE")
                if act:
                    if act in ["BUY", "SELL"] and sl > 0 and tp > 0:
                        actions["SMC_CONCEPTS"] = (act, sl, tp, meta)
                    else:
                        self.logger.warning(f"[STRATEGY_UNDERSTANDING_ERROR] SmcConceptsStrategy returned invalid output: action={act}, sl={sl}, tp={tp}")
            except Exception as e:
                self.logger.error(f"[STRATEGY_UNDERSTANDING_ERROR] SmcConceptsStrategy evaluation failed at index {i}: {e}")
            
            if not actions:
                continue
                
            for setup_type, (action, sl_price, tp_price, meta) in actions.items():
                pnl = 0.0
                resolved = False
                
                max_lookahead = min(n_samples, i + 600)
                for j in range(i + 1, max_lookahead):
                    future_low = float(df_m1['low'].iloc[j])
                    future_high = float(df_m1['high'].iloc[j])
                    if action == "BUY":
                        if future_low <= sl_price:
                            pnl = -1.0
                            resolved = True
                            break
                        elif future_high >= tp_price:
                            pnl = 1.5
                            resolved = True
                            break
                    elif action == "SELL":
                        if future_high >= sl_price:
                            pnl = -1.0
                            resolved = True
                            break
                        elif future_low <= tp_price:
                            pnl = 1.5
                            resolved = True
                            break
                            
                if resolved:
                    disc_feat = {
                        'bias': 'BULLISH' if action == "BUY" else 'BEARISH',
                        'setup': setup_type,
                        'fvg': meta.get('trigger', 'unknown'),
                        'visual_patterns': setup_type
                    }
                    cont_feat = {
                        'volatility': float(sub_m1['volatility'].iloc[-1]) if 'volatility' in sub_m1.columns else 0.0,
                        'atr_pct': atr_val / (current_price + 1e-9)
                    }
                    
                    training_data_discrete.append(disc_feat)
                    training_data_continuous.append(cont_feat)
                    outcomes.append(1 if pnl > 0 else 0)
                    
                    nn_feat_dict = {
                        'active_bias': 1 if action == "BUY" else -1,
                        'liq_sweep_type': float(df_m1_feat['liq_sweep_type'].iloc[i]),
                        'mss_signal': float(df_m1_feat['mss_signal'].iloc[i]),
                        'fvg_class': setup_type,
                        'volatility': float(df_m1_feat['volatility'].iloc[i]),
                        'atr_pct': float(df_m1_feat['atr_pct'].iloc[i]),
                        'rvol': current_rvol,
                        'buy_pressure': current_bp,
                        'sell_pressure': current_sp,
                        'ob_reaction_signal': float(df_m1_feat.get('ob_reaction_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'sr_reaction_signal': float(df_m1_feat.get('sr_reaction_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'retest_pullback_signal': float(df_m1_feat.get('retest_pullback_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'trend_shift_signal': float(df_m1_feat.get('trend_shift_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'timestamp': float(pd.Timestamp(t).timestamp() if hasattr(t, 'timestamp') else i)
                    }
                    nn_inputs.append(self.extract_nn_features(nn_feat_dict))
                    nn_targets.append(1.0 if pnl > 0 else 0.0)
                    
                    if pnl > 0:
                        recorded_wins += 1
                    else:
                        recorded_losses += 1

        if training_data_discrete and outcomes:
            self.classifier.fit(training_data_discrete, training_data_continuous, outcomes)
            self.logger.info(f"Naive Bayes Classifier fitted on {len(outcomes)} multi-strategy sample trades.")

        if nn_inputs and nn_targets:
            try:
                import torch
                inputs_tensor = torch.tensor(np.array(nn_inputs, dtype=np.float32))
                targets_tensor = torch.tensor(np.array(nn_targets, dtype=np.float32)).unsqueeze(1)
                
                self.nn_model.train()
                for epoch in range(15):
                    self.nn_optimizer.zero_grad()
                    outputs = self.nn_model(inputs_tensor)
                    loss = self.nn_criterion(outputs, targets_tensor)
                    loss.backward()
                    self.nn_optimizer.step()
                self.nn_model.eval()
                
                self.save_nn_model()
                self.nn_ready = True
                self.logger.info(f"🧠 Neural network trained on {len(nn_inputs)} multi-strategy samples. Final loss: {loss.item():.4f}")
            except Exception as ex:
                self.logger.error(f"Failed to train PyTorch neural net: {ex}")
                self.nn_model.eval()

        self.training_stats[symbol] = {
            "wins": self.training_stats.get(symbol, {}).get("wins", 0) + recorded_wins,
            "losses": self.training_stats.get(symbol, {}).get("losses", 0) + recorded_losses,
            "total_samples": self.training_stats.get(symbol, {}).get("total_samples", 0) + len(outcomes),
            "win_rate": round(recorded_wins / (len(outcomes) + 1e-9) * 100.0, 1) if outcomes else 0.0,
            "last_train_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_patterns()
        self.logger.info(f"✅ Multi-strategy training completed! wins={recorded_wins}, losses={recorded_losses}")

    def train_on_single_timeframe(self, symbol: str, df: pd.DataFrame):
        """Historical auto-training on a single timeframe DataFrame (e.g. downloaded 10-year CSV)"""
        self.logger.info(f"⏳ Starting single-timeframe training on {symbol} with {len(df)} bars...")
        
        if len(df) < 100:
            self.logger.error("Insufficient data for training on single timeframe")
            return
            
        from utils.settings_manager import settings_manager
        swing_window = settings_manager.get("smc_swing_window", 3)
        
        from utils.smc_indicators import SMCIndicators
        df_feat = SMCIndicators.compute_smc_features(df, window=swing_window)
        n = len(df_feat)
        
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        biases = df_feat['active_bias'].values
        sweeps = df_feat['liq_sweep_type'].values
        mss_signals = df_feat['mss_signal'].values
        atrs = df_feat['atr'].values
        volatilities = df_feat['volatility'].values
        supports = df_feat['support'].values
        resistances = df_feat['resistance'].values
        fvg_classes = df_feat['fvg_class'].values
        timestamps = df_feat.index
        
        training_data_discrete = []
        training_data_continuous = []
        outcomes = []
        cluster_feature_matrix = []
        
        recorded_wins = 0
        recorded_losses = 0
        
        for i in range(50, n - 50):
            t = timestamps[i]
            bias = biases[i]
            
            # Find context sweep
            sweep = 0
            for k in range(i, max(-1, i - 20), -1):
                if sweeps[k] != 0:
                    sweep = int(sweeps[k])
                    break
                    
            # Find MSS signal
            mss = 0
            for k in range(i, max(-1, i - 10), -1):
                if mss_signals[k] != 0:
                    mss = int(mss_signals[k])
                    break
                    
            entry_price = closes[i]
            atr_val = atrs[i]
            support_val = supports[i]
            resistance_val = resistances[i]
            volatility_val = volatilities[i]
            fvg_class_val = fvg_classes[i]
            
            cluster_feature_matrix.append([
                float(volatility_val),
                float(abs(entry_price - support_val) / (entry_price + 1e-9)),
                float(atr_val / (entry_price + 1e-9))
            ])
            
            # Detect visual patterns using sliding window
            start_idx = max(0, i - 20)
            end_idx = i + 1
            visual_patterns = self.detect_visual_patterns_numpy(
                opens[start_idx:end_idx],
                highs[start_idx:end_idx],
                lows[start_idx:end_idx],
                closes[start_idx:end_idx]
            )
            pattern_str = "|".join(visual_patterns) if visual_patterns else "NONE"
            
            action = None
            sl_price = 0.0
            tp_price = 0.0
            
            is_bullish = (bias == 1) and (sweep == 1 or mss == 1)
            is_bearish = (bias == -1) and (sweep == -1 or mss == -1)
            
            if is_bullish:
                action = "BUY"
                sl_price = support_val - (1.5 * atr_val)
                tp_price = entry_price + 1.5 * (entry_price - sl_price)
            elif is_bearish:
                action = "SELL"
                sl_price = resistance_val + (1.5 * atr_val)
                tp_price = entry_price - 1.5 * (sl_price - entry_price)
                
            if action is None:
                continue
                
            pnl = 0.0
            resolved = False
            max_lookahead = min(n, i + 600)
            for j in range(i + 1, max_lookahead):
                future_low = lows[j]
                future_high = highs[j]
                if action == "BUY":
                    if future_low <= sl_price:
                        pnl = -1.0
                        resolved = True
                        break
                    elif future_high >= tp_price:
                        pnl = 1.5
                        resolved = True
                        break
                elif action == "SELL":
                    if future_high >= sl_price:
                        pnl = -1.0
                        resolved = True
                        break
                    elif future_low <= tp_price:
                        pnl = 1.5
                        resolved = True
                        break
                        
            if resolved:
                disc_feat = {
                    'bias': 'BULLISH' if bias == 1 else ('BEARISH' if bias == -1 else 'NEUTRAL'),
                    'setup': 'SHARP_TURN' if (sweep != 0 and mss != 0) else 'MSS_OR_SWEEP',
                    'fvg': str(fvg_class_val).upper(),
                    'visual_patterns': pattern_str
                }
                cont_feat = {
                    'volatility': float(volatility_val),
                    'atr_pct': float(atr_val / (entry_price + 1e-9))
                }
                
                training_data_discrete.append(disc_feat)
                training_data_continuous.append(cont_feat)
                outcomes.append(1 if pnl > 0 else 0)
                
                q_id = self._quantize_smc_state({
                    'active_bias': bias,
                    'price': entry_price,
                    'support': support_val,
                    'resistance': resistance_val,
                    'fvg_class': fvg_class_val,
                    'liq_sweep_type': sweep,
                    'mss_signal': mss
                })
                
                record = {
                    'pattern': q_id,
                    'outcome': pnl,
                    'timestamp': str(t)
                }
                if pnl > 0:
                    self.patterns[f"{symbol}_winning"].append(record)
                    recorded_wins += 1
                else:
                    self.patterns[f"{symbol}_losing"].append(record)
                    recorded_losses += 1
                    
        # Fit models
        if cluster_feature_matrix:
            X_clust = np.array(cluster_feature_matrix)
            self.kmeans.fit(X_clust)
            self.logger.info(f"K-Means fitted with {self.kmeans.k} clusters.")
            
        if training_data_discrete and outcomes:
            self.classifier.fit(training_data_discrete, training_data_continuous, outcomes)
            self.logger.info(f"Naive Bayes fitted on {len(outcomes)} single-timeframe samples.")
            
        self.training_stats[symbol] = {
            "wins": self.training_stats.get(symbol, {}).get("wins", 0) + recorded_wins,
            "losses": self.training_stats.get(symbol, {}).get("losses", 0) + recorded_losses,
            "total_samples": self.training_stats.get(symbol, {}).get("total_samples", 0) + len(outcomes),
            "win_rate": round(recorded_wins / len(outcomes) * 100.0, 1) if outcomes else 0.0,
            "last_train_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_patterns()
        self.logger.info(f"✅ Single-timeframe training complete for {symbol}! Wins={recorded_wins}, Losses={recorded_losses}")

    def train_on_synthetic_idealized_patterns(self, symbol: str, n_samples_per_pattern: int = 500):
        """
        Generate mathematically perfect ("imaginary") representation profiles for standard patterns
        and train the Naive Bayes and KMeans classifiers on them to pre-populate pattern recognition priors.
        """
        self.logger.info(f"⏳ Generating synthetic ('imaginary') pattern templates for {symbol}...")
        
        training_data_discrete = []
        training_data_continuous = []
        outcomes = []
        cluster_feature_matrix = []
        
        # Define the set of patterns to train on
        patterns_to_train = [
            ("PIN_BAR_BULLISH", "BULLISH", "SHARP_TURN", "PFVG", 1), # winning setup
            ("PIN_BAR_BEARISH", "BEARISH", "SHARP_TURN", "PFVG", 1),
            ("BULLISH_ENGULFING", "BULLISH", "MSS_OR_SWEEP", "RFVG", 1),
            ("BEARISH_ENGULFING", "BEARISH", "MSS_OR_SWEEP", "RFVG", 1),
            ("DOUBLE_BOTTOM", "BULLISH", "SHARP_TURN", "NONE", 1),
            ("DOUBLE_TOP", "BEARISH", "SHARP_TURN", "NONE", 1),
            ("LIQUIDITY_SWEEP_LOW", "BULLISH", "MSS_OR_SWEEP", "NONE", 1),
            ("LIQUIDITY_SWEEP_HIGH", "BEARISH", "MSS_OR_SWEEP", "NONE", 1),
            
            # Opposing / failing setups (leading to loss)
            ("PIN_BAR_BULLISH", "BEARISH", "CONTINUATION", "NONE", 0), # opposing bias
            ("PIN_BAR_BEARISH", "BULLISH", "CONTINUATION", "NONE", 0),
            ("NONE", "NEUTRAL", "CONTINUATION", "NONE", 0)
        ]
        
        np.random.seed(42)
        recorded_wins = 0
        recorded_losses = 0
        
        for pat_name, bias, setup, fvg, target_outcome in patterns_to_train:
            for _ in range(n_samples_per_pattern):
                # Add slight variations to continuous features
                # Volatility
                base_vol = 0.0020 if pat_name != "NONE" else 0.0008
                volatility = base_vol + np.random.normal(0, 0.0003)
                volatility = max(0.0001, volatility)
                
                # ATR %
                base_atr = 0.0015 if pat_name != "NONE" else 0.0007
                atr_pct = base_atr + np.random.normal(0, 0.0002)
                atr_pct = max(0.0001, atr_pct)
                
                # S/R distance ratio
                dist_ratio = 0.0010 + np.random.normal(0, 0.0003)
                dist_ratio = max(0.0001, dist_ratio)
                
                disc_feat = {
                    'bias': bias,
                    'setup': setup,
                    'fvg': fvg,
                    'visual_patterns': pat_name
                }
                cont_feat = {
                    'volatility': volatility,
                    'atr_pct': atr_pct
                }
                
                training_data_discrete.append(disc_feat)
                training_data_continuous.append(cont_feat)
                outcomes.append(target_outcome)
                
                cluster_feature_matrix.append([
                    volatility,
                    dist_ratio,
                    atr_pct
                ])
                
                # Save synthetic record to winning/losing databases
                q_id = f"[('bias', '{bias}'), ('fvg', '{fvg}'), ('setup', '{setup}'), ('zone', 'DISCOUNT' if target_outcome == 1 else 'PREMIUM')]"
                record = {
                    'pattern': q_id,
                    'outcome': 1.5 if target_outcome == 1 else -1.0,
                    'timestamp': "synthetic"
                }
                
                if target_outcome == 1:
                    self.patterns[f"{symbol}_winning"].append(record)
                    recorded_wins += 1
                else:
                    self.patterns[f"{symbol}_losing"].append(record)
                    recorded_losses += 1
                    
        # Fit K-Means
        if cluster_feature_matrix:
            X_clust = np.array(cluster_feature_matrix)
            self.kmeans.fit(X_clust)
            
        # Fit Naive Bayes
        if training_data_discrete and outcomes:
            self.classifier.fit(training_data_discrete, training_data_continuous, outcomes)
            
        self.training_stats[symbol] = {
            "wins": self.training_stats.get(symbol, {}).get("wins", 0) + recorded_wins,
            "losses": self.training_stats.get(symbol, {}).get("losses", 0) + recorded_losses,
            "total_samples": self.training_stats.get(symbol, {}).get("total_samples", 0) + len(outcomes),
            "win_rate": round(recorded_wins / len(outcomes) * 100.0, 1) if outcomes else 0.0,
            "last_train_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.save_patterns()
        self.logger.info(f"✅ Synthetic ('imaginary') pattern training complete for {symbol}! Samples generated={len(outcomes)}")

    def learn_from_trade(self, trade_data: Dict):
        """Learn from trade closed PnL. Re-fits supervised classifier dynamically."""
        symbol = trade_data.get('symbol', 'UNKNOWN')
        outcome = trade_data.get('outcome', 0.0)
        features = trade_data.get('features', {})
        
        if not features:
            return
            
        q_id = self._quantize_smc_state(features)
        
        record = {
            'pattern': q_id,
            'outcome': outcome,
            'timestamp': str(pd.Timestamp.now())
        }
        
        if outcome > 0:
            self.patterns[f"{symbol}_winning"].append(record)
            self.logger.info(f"📚 ML Learner: Recorded WIN for {symbol}")
        else:
            self.patterns[f"{symbol}_losing"].append(record)
            self.logger.info(f"📚 ML Learner: Recorded LOSS for {symbol}")
            
        # Cap size to avoid bloating
        self.patterns[f"{symbol}_winning"] = self.patterns[f"{symbol}_winning"][-200:]
        self.patterns[f"{symbol}_losing"] = self.patterns[f"{symbol}_losing"][-200:]
        
        # Dynamically retrain classifier on all loaded history
        self._update_market_regime(symbol, features)
        self.save_patterns()
        
    def get_trading_signal(self, symbol: str, current_features: Dict,
                           df_ltf: Optional[pd.DataFrame] = None,
                           df_m5: Optional[pd.DataFrame] = None,
                           df_h1: Optional[pd.DataFrame] = None,
                           candidate_strategy: Optional[str] = None,
                           candidate_action: Optional[str] = None) -> Dict:
        """
        Evaluate current market state and output Win Probability (AI Confidence).
        Now integrates ChartPatternDetector for institutional SMC pattern recognition.
        """
        # ── 1. Legacy visual patterns (simple candle patterns) ───────────────
        visual_patterns = []
        if df_ltf is not None:
            visual_patterns = self.detect_visual_patterns(df_ltf)

        # ── 2. Advanced SMC chart pattern detection ───────────────────────────
        smc_patterns = {}
        smc_found = []
        smc_confidence = 0.0
        smc_direction = None
        if df_ltf is not None:
            try:
                smc_patterns = ChartPatternDetector.detect(
                    df_m1=df_ltf,
                    df_m5=df_m5,
                    df_h1=df_h1
                )
                smc_found, smc_confidence, smc_direction = ChartPatternDetector.get_summary(smc_patterns)
            except Exception:
                pass

        # Merge all detected patterns for display
        all_patterns = visual_patterns + smc_found
        pattern_str = "|".join(all_patterns) if all_patterns else "NONE"

        # ── 3. Unsupervised Cluster Regime Prediction ────────────────────────
        volatility = current_features.get('volatility', 0.0)
        price = current_features.get('price', 0.0)
        support = current_features.get('support', 0.0)
        atr_pct = current_features.get('atr_pct', 0.0)

        state_point = np.array([
            float(volatility),
            float(abs(price - support) / (price + 1e-9)),
            float(atr_pct)
        ])
        cluster_id = self.kmeans.predict(state_point)

        # ── 4. Supervised Win Probability (PyTorch Neural Net / Naive Bayes Fallback) ──
        h1_bias = current_features.get('active_bias', 0)
        m15_sweep = current_features.get('liq_sweep_type', 0)
        m5_mss = current_features.get('mss_signal', 0)
        fvg_class = current_features.get('fvg_class', 'none')
        tf_aligned = current_features.get('tf_aligned', False)

        disc_feat = {
            'bias': 'BULLISH' if h1_bias == 1 else ('BEARISH' if h1_bias == -1 else 'NEUTRAL'),
            'setup': 'SHARP_TURN' if (m15_sweep != 0 and m5_mss != 0) else 'MSS_OR_SWEEP',
            'fvg': str(fvg_class).upper(),
            'visual_patterns': pattern_str,
            'tf_aligned': 'YES' if tf_aligned else 'NO'
        }
        if candidate_strategy is not None:
            disc_feat['candidate_strategy'] = candidate_strategy.upper()
        if candidate_action is not None:
            disc_feat['candidate_action'] = candidate_action.upper()

        cont_feat = {
            'volatility': float(volatility),
            'atr_pct': float(atr_pct),
            'smc_confidence': smc_confidence
        }

        # Safe feature deepcopy to inject candidate specific parameters
        import copy
        features_copy = copy.deepcopy(current_features)
        if candidate_strategy is not None:
            features_copy['candidate_strategy'] = candidate_strategy
        if candidate_action is not None:
            features_copy['candidate_action'] = candidate_action

        win_prob = None
        model_source = "NO_VALID_MODEL"
        try:
            if self.nn_ready:
                with self.model_lock:
                    feat_arr = self.extract_nn_features(features_copy)
                    feat_tensor = torch.tensor(feat_arr).unsqueeze(0)
                    with torch.no_grad():
                        win_prob = float(self.nn_model(feat_tensor).item())
                    model_source = "NN_CHAMPION"
            elif self.nb_ready:
                win_prob = self.classifier.predict_probability(disc_feat, cont_feat)
                model_source = "NAIVE_BAYES"
        except Exception as e:
            self.logger.error(f"Error during neural net prediction: {e}")
            
        # Try Naive Bayes fallback if preferred model fails/is missing
        if win_prob is None and self.nb_ready:
            try:
                win_prob = self.classifier.predict_probability(disc_feat, cont_feat)
                model_source = "NAIVE_BAYES"
            except Exception:
                pass
                
        # ── 5. SMC pattern confidence boost/penalty (DISABLED in shadow/hardened mode) ───
        # Note: Do not modify model-calibrated probability after inference.
        
        # ── 6. Signal action ──────────────────────────────────────────────────
        signal_action = 'HOLD'
        adjustment = 0.0
        if win_prob is not None:
            if win_prob >= 0.58:
                if h1_bias == 1:
                    signal_action = 'BUY'
                elif h1_bias == -1:
                    signal_action = 'SELL'
                adjustment = (win_prob - 0.5) * 0.8
        else:
            signal_action = 'HOLD'
            adjustment = 0.0
            
        return {
            'signal': signal_action,
            'confidence': round(win_prob, 4) if win_prob is not None else None,
            'adjustment': adjustment,
            'cluster_id': cluster_id,
            'detected_patterns': all_patterns,
            'smc_patterns': smc_found,
            'smc_confidence': smc_confidence,
            'smc_direction': smc_direction,
            'pattern_details': {k: v for k, v in smc_patterns.items() if v.get('detected')},
            'model_source': model_source if win_prob is not None else "NO_VALID_MODEL",
            'model_ready': (self.nn_ready or self.nb_ready) if win_prob is not None else False
        }


    def _update_market_regime(self, symbol: str, features: Dict):
        volatility = features.get('volatility', 0.0)
        atr_pct = features.get('atr_pct', 0.0)
        active_bias = features.get('active_bias', 0)
        
        regime = 'SIDEWAY'
        if active_bias == 1: regime = 'BULLISH'
        elif active_bias == -1: regime = 'BEARISH'
            
        self.market_regimes[symbol] = {
            'regime': regime,
            'timestamp': str(pd.Timestamp.now()),
            'volatility': volatility,
            'atr_pct': atr_pct
        }

    def get_market_regime(self, symbol: str) -> str:
        return self.market_regimes.get(symbol, {}).get('regime', 'RANGING')

    def save_patterns(self):
        try:
            os.makedirs('data', exist_ok=True)
            filepath = 'data/smc_patterns.json'
            
            # Serialize centroids and classifier parameters
            centroids_list = self.kmeans.centroids.tolist() if isinstance(self.kmeans.centroids, np.ndarray) else []
            
            data = {
                'patterns': dict(self.patterns),
                'market_regimes': self.market_regimes,
                'kmeans_centroids': centroids_list,
                'naive_bayes': {
                    'class_priors': self.classifier.class_priors,
                    'discrete_conds': self.classifier.discrete_conds,
                    'continuous_conds': self.classifier.continuous_conds
                },
                'training_stats': self.training_stats
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save patterns to file: {e}")

    def load_patterns(self):
        filepath = 'data/smc_patterns.json'
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                self.patterns = defaultdict(list)
                for k, v in data.get('patterns', {}).items():
                    self.patterns[k] = v
                self.market_regimes = data.get('market_regimes', {})
                self.training_stats = data.get('training_stats', {})
                
                # Restore KMeans centroids
                centroids = data.get('kmeans_centroids', [])
                if centroids:
                    self.kmeans.centroids = np.array(centroids)
                    
                # Restore Classifier parameters
                nb = data.get('naive_bayes', {})
                if nb:
                    self.classifier.class_priors = {int(k): float(v) for k, v in nb.get('class_priors', {0:0.5, 1:0.5}).items()}
                    
                    disc = nb.get('discrete_conds', {})
                    self.classifier.discrete_conds = {}
                    for c_str, feat_dict in disc.items():
                        c = int(c_str)
                        self.classifier.discrete_conds[c] = {}
                        for feat_key, val_dict in feat_dict.items():
                            self.classifier.discrete_conds[c][feat_key] = {k: float(v) for k, v in val_dict.items()}
                            
                    cont = nb.get('continuous_conds', {})
                    self.classifier.continuous_conds = {}
                    for c_str, feat_dict in cont.items():
                        c = int(c_str)
                        self.classifier.continuous_conds[c] = {}
                        for feat_key, params in feat_dict.items():
                            self.classifier.continuous_conds[c][feat_key] = (float(params[0]), float(params[1]))
                            
                self.logger.info(f"Loaded {sum(len(p) for p in self.patterns.values())} SMC patterns from disk")
            except Exception as e:
                self.logger.error(f"Failed to load patterns from file: {e}")

    def save_nn_model(self):
        """Helper to save model weights and its schema metadata."""
        try:
            os.makedirs("models", exist_ok=True)
            model_path = "models/pulse_viper_base.pth"
            metadata_path = "models/pulse_viper_base.json"
            
            # Save weights
            torch.save(self.nn_model.state_dict(), model_path)
            
            # Save metadata
            from core.feature_extractor import FeatureExtractor
            meta = {
                "model_version": "pv-nn-003",
                "feature_schema_version": 3,
                "feature_names": FeatureExtractor.FEATURE_NAMES,
                "feature_schema_hash": FeatureExtractor.FEATURE_SCHEMA_HASH,
                "input_dim": 30,
                "strategy_schema_version": 1,
                "trained_at_utc": pd.Timestamp.now(tz='UTC').isoformat()
            }
            with open(metadata_path, "w") as f:
                json.dump(meta, f, indent=4)
            self.logger.info(f"Saved active model and metadata to models/ folder.")
        except Exception as e:
            self.logger.error(f"Failed to save NN model: {e}")

    def _validate_and_promote(self, candidate_model, inputs_tensor=None, targets_tensor=None) -> bool:
        """
        Verify technical validity and statistical benchmarks of candidate model.
        Returns True if promoted, False otherwise.
        """
        try:
            from utils.settings_manager import settings_manager
            # 1. Ensure candidate model is in evaluation mode before validation and promotion
            candidate_model.eval()
            
            # 2. Technical Validity checks
            for param in candidate_model.parameters():
                if torch.isnan(param).any() or torch.isinf(param).any():
                    self.logger.warning("Technical validation failed: NaN/Inf detected in weights.")
                    return False
            
            # Verify shape and dimension
            test_input = torch.zeros((1, 30))
            with torch.no_grad():
                test_output = candidate_model(test_input)
                val = float(test_output.item())
                if val < 0.0 or val > 1.0:
                    self.logger.warning(f"Technical validation failed: Output {val} out of bounds.")
                    return False
            
            # 3. Statistical Promotion checks
            if inputs_tensor is not None and targets_tensor is not None:
                sample_count = len(inputs_tensor)
                min_samples = settings_manager.get("min_promotion_samples", 5)
                if sample_count < min_samples:
                    self.logger.warning(f"Promotion skipped: Evaluation sample size ({sample_count}) below minimum ({min_samples}).")
                    return False
                    
                with torch.no_grad():
                    # Calculate Brier score for champion and challenger
                    champ_preds = self.nn_model(inputs_tensor)
                    cand_preds = candidate_model(inputs_tensor)
                    
                    champ_brier = float(torch.mean((champ_preds - targets_tensor) ** 2).item())
                    cand_brier = float(torch.mean((cand_preds - targets_tensor) ** 2).item())
                    
                    # Challenger Brier score must be <= champion's Brier score (lower is better)
                    if cand_brier > champ_brier:
                        self.logger.warning(f"Statistical validation failed: Challenger Brier ({cand_brier:.4f}) is worse than Champion ({champ_brier:.4f}).")
                        return False
                        
                    # Max allowed Brier score check
                    max_allowed_brier = settings_manager.get("max_allowed_brier", 0.25)
                    if cand_brier > max_allowed_brier:
                        self.logger.warning(f"Statistical validation failed: Challenger Brier ({cand_brier:.4f}) exceeds maximum allowed ({max_allowed_brier:.4f}).")
                        return False
                        
                    # Catastrophic regime regression safety check (segregated by high/low volatility inputs)
                    vol_col = 4 # Index of volatility_scaled in FEATURE_NAMES (0-indexed)
                    high_vol_mask = inputs_tensor[:, vol_col] > 1.0
                    low_vol_mask = ~high_vol_mask
                    
                    for name, mask in [("HIGH_VOL", high_vol_mask), ("LOW_VOL", low_vol_mask)]:
                        if mask.any():
                            cand_regime_brier = float(torch.mean((cand_preds[mask] - targets_tensor[mask]) ** 2).item())
                            if cand_regime_brier > 0.35: # hard ceiling on catastrophic regime failure
                                self.logger.warning(f"Statistical validation failed: Catastrophic regression in {name} regime. Brier = {cand_regime_brier:.4f}")
                                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False

    def load_nn_model(self):
        """Load PyTorch neural network weights if available and validated against schema metadata."""
        model_path = "models/pulse_viper_base.pth"
        metadata_path = "models/pulse_viper_base.json"
        try:
            self.nn_ready = False
            os.makedirs("models", exist_ok=True)
            if os.path.exists(model_path) and os.path.exists(metadata_path):
                # 1. Load and verify metadata
                with open(metadata_path, "r") as f:
                    meta = json.load(f)
                
                from core.feature_extractor import FeatureExtractor
                expected_hash = FeatureExtractor.FEATURE_SCHEMA_HASH
                
                if meta.get("input_dim") != 30:
                    self.logger.warning("Model input dimension mismatch. Excluded from production.")
                    return
                if meta.get("feature_schema_hash") != expected_hash:
                    self.logger.warning("Model feature schema hash mismatch. Excluded from production.")
                    return
                if meta.get("strategy_schema_version") != 1:
                    self.logger.warning("Model strategy schema version mismatch. Excluded from production.")
                    return
                
                # 2. Load weights
                state_dict = torch.load(model_path, map_location=torch.device('cpu'))
                self.nn_model.load_state_dict(state_dict)
                self.nn_model.eval()
                self.nn_ready = True
                self.logger.info(f"🧠 PyTorch neural net weights ({meta.get('model_version')}) loaded and validated successfully.")
            else:
                self.logger.warning("PyTorch model files not found. Inference not ready.")
        except Exception as e:
            self.logger.warning(f"⚠️ PyTorch weights mismatch or loading error: {e}. Model set to NOT ready.")
            self.nn_ready = False

    @staticmethod
    def extract_temporal_embeddings(timestamp_str_or_float) -> list:
        """
        Converts raw UNIX timestamps or timestamp strings into cyclical temporal embeddings for PyTorch.
        """
        return FeatureExtractor.extract_temporal_embeddings(timestamp_str_or_float)

    @staticmethod
    def extract_nn_features(features: dict) -> np.ndarray:
        """
        Convert market features dict to an 18-dimensional numpy array for the PyTorch Neural Net.
        """
        return FeatureExtractor.extract_nn_features(features)

    def append_live_experience(self, features: dict, outcome_label: float, pnl_realized: float, symbol: str):
        """
        Thread-safe Continuous Alpha Learning Loop append.
        Vectors are sent to the continuous training buffer for the PyTorch model.
        """
        import threading
        if not hasattr(self, '_append_lock'):
            self._append_lock = threading.Lock()
            
        with self._append_lock:
            q_id = self._quantize_smc_state(features)
            record = {
                'pattern': q_id,
                'outcome': pnl_realized,
                'timestamp': str(pd.Timestamp.now())
            }
            if outcome_label == 1.0:
                self.patterns[f"{symbol}_winning"].append(record)
                self.logger.info(f"📚 CALL: Appended WINNING live experience for {symbol}")
            else:
                self.patterns[f"{symbol}_losing"].append(record)
                self.logger.info(f"📚 CALL: Appended LOSING live experience for {symbol}")
                
            # Keep bounded
            self.patterns[f"{symbol}_winning"] = self.patterns[f"{symbol}_winning"][-200:]
            self.patterns[f"{symbol}_losing"] = self.patterns[f"{symbol}_losing"][-200:]
            
            # We can optionally call incremental train here or allow a background worker to do it
            self.save_patterns()

    def train_incremental(self, trades: List[Dict]):
        """
        Run a single optimization epoch on a batch of closed trades to adjust neural net weights.
        Uses a challenger model and validates it before promoting.
        """
        try:
            if not trades:
                return
            
            inputs = []
            targets = []
            
            for t in trades:
                try:
                    feat = self.extract_nn_features(t.get('features', {}))
                    inputs.append(feat)
                    outcome = 1.0 if float(t.get('pnl', 0.0)) > 0 else 0.0
                    targets.append([outcome])
                except ValueError as ve:
                    self.logger.warning(f"Skipping legacy trade training row: {ve}")
                    continue
                    
            if not inputs:
                return
                
            inputs_tensor = torch.tensor(np.array(inputs, dtype=np.float32))
            targets_tensor = torch.tensor(np.array(targets, dtype=np.float32))
            
            # Create challenger model
            import copy
            candidate_model = copy.deepcopy(self.nn_model)
            candidate_optimizer = optim.Adam(candidate_model.parameters(), lr=0.003, weight_decay=1e-4)
            
            candidate_model.train()
            candidate_optimizer.zero_grad()
            outputs = candidate_model(inputs_tensor)
            loss = self.nn_criterion(outputs, targets_tensor)
            loss.backward()
            candidate_optimizer.step()
            candidate_model.eval()
            
            # Validate and promote
            if self._validate_and_promote(candidate_model, inputs_tensor, targets_tensor):
                with self.model_lock:
                    self.nn_model = candidate_model
                    self.nn_optimizer = candidate_optimizer
                    self.nn_ready = True
                self.save_nn_model()
                self.logger.info(f"🔄 Online Learning Epoch complete on {len(trades)} samples. Loss: {loss.item():.4f}. Challenger promoted and saved.")
            else:
                self.logger.warning("⚠️ Challenger model failed validation. Promotion aborted.")
        except Exception as e:
            self.logger.error(f"Error during incremental training: {e}")

    def train_timeframe_layer(self, model, timeframe_data):
        """
        Executes thread-safe optimization epochs without blocking active execution threads
        """
        try:
            # 1. Localize features extraction to separate thread memory allocations
            features, outcomes = self.extract_vectorized_features(timeframe_data)
            if len(features) == 0:
                return

            # 2. Train local model states safely using isolated torch gradients
            model.train() 
            local_optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
            loss_function = torch.nn.BCELoss()

            loss = None
            for epoch in range(3):
                local_optimizer.zero_grad()
                predictions = model(features)
                loss = loss_function(predictions, outcomes)
                loss.backward()
                local_optimizer.step()

            # 3. Re-freeze layers for lightning-fast inference before worker termination
            model.eval()
            if loss is not None:
                self.logger.info(f"✅ Trained timeframe layer successfully. Samples: {len(features)}. Final Loss: {loss.item():.4f}")
        except Exception as e:
            self.logger.error(f"Error in train_timeframe_layer: {e}")
            if model is not None:
                model.eval()

    def extract_vectorized_features(self, timeframe_data: pd.DataFrame) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Extracts features and target outcomes from timeframe data for PyTorch neural network training.
        """
        try:
            if timeframe_data is None or len(timeframe_data) < 20:
                return torch.empty(0), torch.empty(0)
                
            from utils.smc_indicators import SMCIndicators
            from utils.settings_manager import settings_manager
            
            swing_window = settings_manager.get("smc_swing_window", 3)
            df_feat = SMCIndicators.compute_smc_features(timeframe_data, window=swing_window)
            
            inputs = []
            targets = []
            
            n = len(df_feat)
            closes = df_feat['close'].values
            highs = df_feat['high'].values
            lows = df_feat['low'].values
            biases = df_feat['active_bias'].values if 'active_bias' in df_feat.columns else np.zeros(n)
            sweeps = df_feat['liq_sweep_type'].values if 'liq_sweep_type' in df_feat.columns else np.zeros(n)
            mss_signals = df_feat['mss_signal'].values if 'mss_signal' in df_feat.columns else np.zeros(n)
            atrs = df_feat['atr'].values if 'atr' in df_feat.columns else np.zeros(n)
            volatilities = df_feat['volatility'].values if 'volatility' in df_feat.columns else np.zeros(n)
            supports = df_feat['support'].values if 'support' in df_feat.columns else np.zeros(n)
            resistances = df_feat['resistance'].values if 'resistance' in df_feat.columns else np.zeros(n)
            fvg_classes = df_feat['fvg_class'].values if 'fvg_class' in df_feat.columns else np.zeros(n)
            timestamps = df_feat.index.view(np.int64) // 10**9 if isinstance(df_feat.index, pd.DatetimeIndex) else np.zeros(n)
            ob_reaction_signals = df_feat['ob_reaction_signal'].values if 'ob_reaction_signal' in df_feat.columns else np.zeros(n)
            sr_reaction_signals = df_feat['sr_reaction_signal'].values if 'sr_reaction_signal' in df_feat.columns else np.zeros(n)
            retest_pullback_signals = df_feat['retest_pullback_signal'].values if 'retest_pullback_signal' in df_feat.columns else np.zeros(n)
            trend_shift_signals = df_feat['trend_shift_signal'].values if 'trend_shift_signal' in df_feat.columns else np.zeros(n)
            
            for i in range(10, n - 10):
                bias = biases[i]
                # Context sweep
                sweep = 0
                for k in range(i, max(-1, i - 10), -1):
                    if sweeps[k] != 0:
                        sweep = int(sweeps[k])
                        break
                # MSS signal
                mss = 0
                for k in range(i, max(-1, i - 5), -1):
                    if mss_signals[k] != 0:
                        mss = int(mss_signals[k])
                        break
                
                entry_price = closes[i]
                atr_val = atrs[i]
                support_val = supports[i]
                resistance_val = resistances[i]
                volatility_val = volatilities[i]
                fvg_class_val = fvg_classes[i]
                
                action = None
                sl_price = 0.0
                tp_price = 0.0
                
                is_bullish = (bias == 1) and (sweep == 1 or mss == 1)
                is_bearish = (bias == -1) and (sweep == -1 or mss == -1)
                
                # Range-bounce setups: bias == 0 but a sweep or MSS provides direction
                # These are mean-reversion setups at range boundaries
                if not is_bullish and not is_bearish and bias == 0:
                    if sweep == 1 or mss == 1:
                        is_bullish = True   # swept low in neutral market → mean-reversion buy
                    elif sweep == -1 or mss == -1:
                        is_bearish = True   # swept high in neutral market → mean-reversion sell
                
                if is_bullish:
                    action = "BUY"
                    sl_price = support_val - (1.5 * atr_val)
                    tp_price = entry_price + 1.5 * (entry_price - sl_price)
                elif is_bearish:
                    action = "SELL"
                    sl_price = resistance_val + (1.5 * atr_val)
                    tp_price = entry_price - 1.5 * (sl_price - entry_price)
                    
                if action is None:
                    continue
                    
                pnl = 0.0
                resolved = False
                max_lookahead = min(n, i + 100)
                for j in range(i + 1, max_lookahead):
                    future_low = lows[j]
                    future_high = highs[j]
                    if action == "BUY":
                        if future_low <= sl_price:
                            pnl = -1.0
                            resolved = True
                            break
                        elif future_high >= tp_price:
                            pnl = 1.5
                            resolved = True
                            break
                    elif action == "SELL":
                        if future_high >= sl_price:
                            pnl = -1.0
                            resolved = True
                            break
                        elif future_low <= tp_price:
                            pnl = 1.5
                            resolved = True
                            break
                
                if resolved:
                    features_dict = {
                        'active_bias': bias,
                        'liq_sweep_type': sweep,
                        'mss_signal': mss,
                        'fvg_class': fvg_class_val,
                        'volatility': volatility_val,
                        'atr_pct': atr_val / (entry_price + 1e-9),
                        'rvol': 1.0,
                        'buy_pressure': 50.0,
                        'sell_pressure': 50.0,
                        'ob_reaction_signal': ob_reaction_signals[i],
                        'sr_reaction_signal': sr_reaction_signals[i],
                        'retest_pullback_signal': retest_pullback_signals[i],
                        'trend_shift_signal': trend_shift_signals[i],
                        'timestamp': timestamps[i]
                    }
                    feat_arr = self.extract_nn_features(features_dict)
                    inputs.append(feat_arr)
                    targets.append([1.0 if pnl > 0 else 0.0])
                    
            if not inputs:
                return torch.empty(0), torch.empty(0)
                
            features_tensor = torch.tensor(np.array(inputs, dtype=np.float32))
            outcomes_tensor = torch.tensor(np.array(targets, dtype=np.float32))
            return features_tensor, outcomes_tensor
        except Exception as e:
            self.logger.error(f"Error in extract_vectorized_features: {e}")
            return torch.empty(0), torch.empty(0)