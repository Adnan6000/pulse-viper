# core/pattern_learner.py
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from collections import defaultdict
from core.experience_memory import ExperienceMemory

class KMeansClustering:
    def __init__(self, k: int = 4):
        self.k = k
        self.centroids = []
        
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
        if len(self.centroids) == 0:
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
        
        # Pattern detection parameters
        self.min_pattern_occurrence = 2
        self.confidence_threshold = 0.5
        
        # Load saved models and patterns
        self.load_patterns()
        
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

        for i in range(50, n_ltf - 50):
            t = ltf_timestamps[i]
            
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
            
            entry_price = ltf_closes_feat[i]
            atr_val = ltf_atrs[i]
            support_val = ltf_supports[i]
            resistance_val = ltf_resistances[i]
            volatility_val = ltf_volatilities[i]
            fvg_class_val = ltf_fvg_classes[i]
            
            # Unsupervised clustering feature collection
            # Vector: [volatility, price_diff_ratio, atr_pct]
            cluster_feature_matrix.append([
                float(volatility_val),
                float(abs(entry_price - support_val) / (entry_price + 1e-9)),
                float(atr_val / (entry_price + 1e-9))
            ])
            
            # Swing patterns detection
            start_idx = max(0, i - 20)
            end_idx = i + 1
            visual_patterns = self.detect_visual_patterns_numpy(
                ltf_opens[start_idx:end_idx],
                ltf_highs[start_idx:end_idx],
                ltf_lows[start_idx:end_idx],
                ltf_closes[start_idx:end_idx]
            )
            pattern_str = "|".join(visual_patterns) if visual_patterns else "NONE"
            
            # Resolve simulated trade outcome
            action = None
            sl_price = 0.0
            tp_price = 0.0
            
            is_bullish = (htf_bias == 1) and (context_sweep == 1 or ltf_mss == 1)
            is_bearish = (htf_bias == -1) and (context_sweep == -1 or ltf_mss == -1)
            
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
            # Max lookahead window of 600 bars to resolve trades (prevents CPU bottlenecks on deep history)
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
                # Prepare features for ML models
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
                
                # Quantized dictionary storage
                q_id = self._quantize_smc_state({
                    'active_bias': htf_bias,
                    'price': entry_price,
                    'support': support_val,
                    'resistance': resistance_val,
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
 
        # Fit Unsupervised K-Means
        if cluster_feature_matrix:
            X_clust = np.array(cluster_feature_matrix)
            self.kmeans.fit(X_clust)
            self.logger.info(f"Unsupervised K-Means centroids fitted with {self.kmeans.k} clusters.")
            
        # Fit Supervised Naive Bayes Classifier
        if training_data_discrete and outcomes:
            self.classifier.fit(training_data_discrete, training_data_continuous, outcomes)
            self.logger.info(f"Supervised Naive Bayes Classifier fitted on {len(outcomes)} sample trades.")
            
        self.training_stats[symbol] = {
            "wins": recorded_wins,
            "losses": recorded_losses,
            "total_samples": len(outcomes),
            "win_rate": round(recorded_wins / len(outcomes) * 100.0, 1) if outcomes else 0.0,
            "last_train_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_patterns()
        self.logger.info(f"✅ ML Historical training completed for {symbol}! Wins={recorded_wins}, Losses={recorded_losses}")

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
                    'volatility': float(volatility),
                    'atr_pct': float(atr_pct)
                }
                
                training_data_discrete.append(disc_feat)
                training_data_continuous.append(cont_feat)
                outcomes.append(target_outcome)
                
                cluster_feature_matrix.append([
                    float(volatility),
                    float(dist_ratio),
                    float(atr_pct)
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
        
    def get_trading_signal(self, symbol: str, current_features: Dict, df_ltf: Optional[pd.DataFrame] = None) -> Dict:
        """Evaluate current market state and output Win Probability (AI Confidence) using Naive Bayes"""
        # Detect patterns
        visual_patterns = []
        if df_ltf is not None:
            visual_patterns = self.detect_visual_patterns(df_ltf)
        pattern_str = "|".join(visual_patterns) if visual_patterns else "NONE"
        
        # 1. Unsupervised Cluster Regime Prediction
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
        
        # 2. Supervised Win Probability Classification
        h1_bias = current_features.get('active_bias', 0)
        m15_sweep = current_features.get('liq_sweep_type', 0)
        m5_mss = current_features.get('mss_signal', 0)
        fvg_class = current_features.get('fvg_class', 'none')
        
        disc_feat = {
            'bias': 'BULLISH' if h1_bias == 1 else ('BEARISH' if h1_bias == -1 else 'NEUTRAL'),
            'setup': 'SHARP_TURN' if (m15_sweep != 0 and m5_mss != 0) else 'MSS_OR_SWEEP',
            'fvg': str(fvg_class).upper(),
            'visual_patterns': pattern_str
        }
        cont_feat = {
            'volatility': float(volatility),
            'atr_pct': float(atr_pct)
        }
        
        win_prob = self.classifier.predict_probability(disc_feat, cont_feat)
        
        # Determine signal action based on win probability and bias direction
        signal_action = 'HOLD'
        adjustment = 0.0
        if win_prob >= 0.58:
            if h1_bias == 1:
                signal_action = 'BUY'
            elif h1_bias == -1:
                signal_action = 'SELL'
            adjustment = float((win_prob - 0.5) * 0.8) # positive boost
        elif win_prob <= 0.42:
            if h1_bias == 1:
                signal_action = 'SELL'
            elif h1_bias == -1:
                signal_action = 'BUY'
            adjustment = float((win_prob - 0.5) * 0.8) # negative filter reduction
            
        return {
            'signal': signal_action,
            'confidence': win_prob,
            'adjustment': adjustment,
            'cluster_id': cluster_id,
            'detected_patterns': visual_patterns
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