# core/pattern_learner.py
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging
from collections import defaultdict
from core.experience_memory import ExperienceMemory

class PatternLearner:
    def __init__(self, memory: ExperienceMemory):
        self.memory = memory
        self.patterns = defaultdict(list)
        self.market_regimes = {}
        self.logger = logging.getLogger('PulseViper.PatternLearner')
        
        # Pattern detection parameters
        self.min_pattern_occurrence = 2
        self.confidence_threshold = 0.5
        
        # Load saved patterns if exist
        self.load_patterns()
        
    def _quantize_smc_state(self, features: Dict) -> str:
        """
        Quantize continuous market indicators into discrete SMC categories.
        Ensures high probability of pattern matching by grouping continuous noise.
        """
        quantized = {}
        
        # 1. HTF Trend / Bias
        bias_val = features.get('active_bias', 0)
        quantized['bias'] = 'BULLISH' if bias_val == 1 else ('BEARISH' if bias_val == -1 else 'NEUTRAL')
        
        # 2. Premium / Discount Zone
        price = features.get('price', features.get('close', 0.0))
        support = features.get('support', 0.0)
        resistance = features.get('resistance', 0.0)
        if resistance > support and support > 0:
            pct = (price - support) / (resistance - support)
            if pct < 0.35:
                quantized['zone'] = 'DISCOUNT'  # Good for BUY
            elif pct > 0.65:
                quantized['zone'] = 'PREMIUM'   # Good for SELL
            else:
                quantized['zone'] = 'EQUILIBRIUM'
        else:
            quantized['zone'] = 'EQUILIBRIUM'
            
        # 3. FVG Type
        fvg_class = features.get('fvg_class', 'none')
        quantized['fvg'] = str(fvg_class).upper()
        
        # 4. Pattern Setup (Sweeps and Market Structure Shifts)
        had_sweep = features.get('liq_sweep_type', 0) != 0
        had_mss = features.get('mss_signal', 0) != 0
        if had_sweep and had_mss:
            quantized['setup'] = 'SHARP_TURN'  # Sweet spot entry
        elif had_mss:
            quantized['setup'] = 'MSS_ONLY'
        elif had_sweep:
            quantized['setup'] = 'SWEEP_ONLY'
        else:
            quantized['setup'] = 'CONTINUATION'
            
        # 5. Volatility Regime
        volatility = features.get('volatility', 0.0)
        atr_pct = features.get('atr_pct', 0.0)
        if atr_pct > 0.003:
            quantized['volatility'] = 'HIGH'
        elif atr_pct < 0.001:
            quantized['volatility'] = 'LOW'
        else:
            quantized['volatility'] = 'NORMAL'
            
        # Sort key to enforce deterministic string conversion
        return str(sorted(quantized.items()))

    def train_on_history(self, symbol: str, df_h1: pd.DataFrame, df_m15: pd.DataFrame, df_m5: pd.DataFrame):
        """
        Scan historical candles to identify setups, simulate entry and resolve trade outcomes.
        Pre-populates the pattern database for AI learning.
        """
        self.logger.info(f"⏳ Starting historical auto-training on {symbol}...")
        
        # Compute SMC features
        from utils.smc_indicators import SMCIndicators
        df_h1_feat = SMCIndicators.compute_smc_features(df_h1)
        df_m15_feat = SMCIndicators.compute_smc_features(df_m15)
        df_m5_feat = SMCIndicators.compute_smc_features(df_m5)
        
        # We also need ATR for volatility and SL calculations
        atr_m5 = df_m5_feat['atr']
        
        n_m5 = len(df_m5_feat)
        recorded_wins = 0
        recorded_losses = 0
        
        # Pre-cache indices for faster lookup
        h1_indices = df_h1_feat.index
        m15_indices = df_m15_feat.index

        # Avoid scanning the very end of history to ensure outcomes can be resolved
        for i in range(100, n_m5 - 100):
            t = df_m5_feat.index[i]
            
            # Find the corresponding H1 and M15 states (at or before time t)
            idx_h1 = h1_indices.searchsorted(t, side='right')
            idx_m15 = m15_indices.searchsorted(t, side='right')
            
            if idx_h1 == 0 or idx_m15 == 0:
                continue
                
            h1_row = df_h1_feat.iloc[idx_h1 - 1]
            m15_row = df_m15_feat.iloc[idx_m15 - 1]
            m5_row = df_m5_feat.iloc[i]
            
            h1_bias = h1_row['active_bias']
            
            # Check last 20 context candles for any sweep (scan backward)
            m15_sweep = 0
            for k in range(idx_m15 - 1, max(-1, idx_m15 - 21), -1):
                sweep_val = df_m15_feat.iloc[k]['liq_sweep_type']
                if sweep_val != 0:
                    m15_sweep = int(sweep_val)
                    break
                    
            # Check last 10 LTF candles for any MSS (scan backward)
            m5_mss = 0
            for k in range(i, max(-1, i - 10), -1):
                mss_val = df_m5_feat.iloc[k]['mss_signal']
                if mss_val != 0:
                    m5_mss = int(mss_val)
                    break
                    
            # Check last 5 candles for FVG
            fvg_class = 'none'
            fvg_type = 0
            fvg_top = m5_row['fvg_top']
            fvg_bottom = m5_row['fvg_bottom']
            for k in range(i, max(-1, i - 5), -1):
                row_val = df_m5_feat.iloc[k]
                cls_val = row_val['fvg_class']
                if cls_val != 'none' and cls_val != 'rfvg':
                    fvg_class = cls_val
                    fvg_type = row_val['fvg_type']
                    fvg_top = row_val['fvg_top']
                    fvg_bottom = row_val['fvg_bottom']
                    break
            if fvg_class == 'none':
                fvg_class = m5_row['fvg_class']
                fvg_type = m5_row['fvg_type']
            
            # Recreate evaluate_entry_rules logic
            action = None
            sl_price = 0.0
            tp_price = 0.0
            
            # Bullish setup (strict bias)
            is_bullish = (h1_bias == 1) and (m15_sweep == 1) and (m5_mss == 1)
            # Bearish setup (strict bias)
            is_bearish = (h1_bias == -1) and (m15_sweep == -1) and (m5_mss == -1)
            
            atr_val = atr_m5.iloc[i]
            entry_price = m5_row['close']
            
            if is_bullish:
                action = "BUY"
                sl_price = m5_row['support'] - (0.2 * atr_val)
                sl_price = min(sl_price, entry_price - (1.5 * atr_val))
                tp_price = entry_price + (2.0 * (entry_price - sl_price))
                if m5_row['resistance'] > entry_price:
                    tp_price = max(tp_price, m5_row['resistance'])
            elif is_bearish:
                action = "SELL"
                sl_price = m5_row['resistance'] + (0.2 * atr_val)
                sl_price = max(sl_price, entry_price + (1.5 * atr_val))
                tp_price = entry_price - (2.0 * (sl_price - entry_price))
                if m5_row['support'] < entry_price:
                    tp_price = min(tp_price, m5_row['support'])
                    
            if action is None:
                continue
                
            # Resolve outcome
            pnl = 0.0
            resolved = False
            for j in range(i + 1, n_m5):
                future_row = df_m5_feat.iloc[j]
                if action == "BUY":
                    if future_row['low'] <= sl_price:
                        pnl = -1.0  # Loss
                        resolved = True
                        break
                    elif future_row['high'] >= tp_price:
                        pnl = 2.0   # Win (2.0 RR)
                        resolved = True
                        break
                elif action == "SELL":
                    if future_row['high'] >= sl_price:
                        pnl = -1.0  # Loss
                        resolved = True
                        break
                    elif future_row['low'] <= tp_price:
                        pnl = 2.0   # Win (2.0 RR)
                        resolved = True
                        break
            
            if resolved:
                # Prepare features dict for quantization
                features_dict = {
                    'active_bias': h1_bias,
                    'price': entry_price,
                    'close': entry_price,
                    'support': m5_row['support'],
                    'resistance': m5_row['resistance'],
                    'fvg_class': fvg_class,
                    'liq_sweep_type': m15_sweep,
                    'mss_signal': m5_mss,
                    'volatility': atr_val,
                    'atr_pct': atr_val / (entry_price + 1e-9)
                }
                
                pattern_id = self._quantize_smc_state(features_dict)
                
                record = {
                    'pattern': pattern_id,
                    'outcome': pnl,
                    'timestamp': str(t),
                    'indicators': {k: str(v) for k, v in features_dict.items()}
                }
                
                # Store in winning/losing list
                if pnl > 0:
                    self.patterns[f"{symbol}_winning"].append(record)
                    recorded_wins += 1
                else:
                    self.patterns[f"{symbol}_losing"].append(record)
                    recorded_losses += 1
                    
        # Update and save
        self.save_patterns()
        self.logger.info(f"✅ Historical training completed for {symbol}! Recorded {recorded_wins} Wins and {recorded_losses} Losses.")

    def learn_from_trade(self, trade_data: Dict):
        """Learn from actual closed trade outcome (PnL-based reward)"""
        symbol = trade_data.get('symbol', 'UNKNOWN')
        outcome = trade_data.get('outcome', 0.0)  # Actual trade PnL
        features = trade_data.get('features', {})
        
        if not features:
            return
            
        pattern_id = self._quantize_smc_state(features)
        
        record = {
            'pattern': pattern_id,
            'outcome': outcome,
            'timestamp': str(pd.Timestamp.now()),
            'indicators': {k: str(v) for k, v in features.items() if isinstance(v, (int, float, str))}
        }
        
        # Store in winning/losing list
        if outcome > 0:
            self.patterns[f"{symbol}_winning"].append(record)
            self.logger.info(f"📚 Pattern Learner: Recorded WINNING SMC pattern for {symbol}")
        else:
            self.patterns[f"{symbol}_losing"].append(record)
            self.logger.info(f"📚 Pattern Learner: Recorded LOSING SMC pattern for {symbol}")
            
        # Cap size to avoid bloating
        if len(self.patterns[f"{symbol}_winning"]) > 200:
            self.patterns[f"{symbol}_winning"] = self.patterns[f"{symbol}_winning"][-100:]
        if len(self.patterns[f"{symbol}_losing"]) > 200:
            self.patterns[f"{symbol}_losing"] = self.patterns[f"{symbol}_losing"][-100:]
            
        # Update market regimes
        self._update_market_regime(symbol, features)
        self.save_patterns()
        
    def get_trading_signal(self, symbol: str, current_features: Dict) -> Dict:
        """Evaluate current market state and adjust execution confidence based on matches"""
        current_pattern = self._quantize_smc_state(current_features)
        
        # Count matching historical outcomes
        winning_matches = [p for p in self.patterns.get(f"{symbol}_winning", []) if p['pattern'] == current_pattern]
        losing_matches = [p for p in self.patterns.get(f"{symbol}_losing", []) if p['pattern'] == current_pattern]
        
        total_matches = len(winning_matches) + len(losing_matches)
        
        if total_matches < self.min_pattern_occurrence:
            # Insufficient matches, return neutral adjustment
            return {
                'signal': 'HOLD',
                'confidence': 0.5,
                'adjustment': 0.0,
                'matches': total_matches
            }
            
        win_rate = len(winning_matches) / total_matches
        
        # Calculate signal filter adjustment
        if win_rate > 0.65:
            # Highly profitable pattern matched
            return {
                'signal': 'BUY',
                'confidence': win_rate,
                'adjustment': 0.2,  # Boost position size / confidence
                'matches': total_matches
            }
        elif win_rate < 0.35:
            # High failure rate pattern matched
            return {
                'signal': 'SELL',  # Refuse or trade opposite
                'confidence': 1.0 - win_rate,
                'adjustment': -0.4, # Strongly reduce position size or avoid
                'matches': total_matches
            }
        else:
            return {
                'signal': 'HOLD',
                'confidence': 0.5,
                'adjustment': 0.0,
                'matches': total_matches
            }

    def _update_market_regime(self, symbol: str, features: Dict):
        """Detect and store market regime"""
        volatility = features.get('volatility', 0.0)
        atr_pct = features.get('atr_pct', 0.0)
        active_bias = features.get('active_bias', 0)
        
        if active_bias == 1:
            regime = 'BULLISH'
        elif active_bias == -1:
            regime = 'BEARISH'
        else:
            regime = 'SIDEWAY'
            
        self.market_regimes[symbol] = {
            'regime': regime,
            'timestamp': str(pd.Timestamp.now()),
            'volatility': volatility,
            'atr_pct': atr_pct
        }

    def get_market_regime(self, symbol: str) -> str:
        return self.market_regimes.get(symbol, {}).get('regime', 'RANGING')

    def save_patterns(self):
        """Save pattern DB to JSON file"""
        try:
            os.makedirs('data', exist_ok=True)
            filepath = 'data/smc_patterns.json'
            # Convert default dict to normal dict for serialization
            data = {
                'patterns': dict(self.patterns),
                'market_regimes': self.market_regimes
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save patterns to file: {e}")

    def load_patterns(self):
        """Load pattern DB from JSON file"""
        filepath = 'data/smc_patterns.json'
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                # Convert keys back to default dict
                self.patterns = defaultdict(list)
                for k, v in data.get('patterns', {}).items():
                    self.patterns[k] = v
                self.market_regimes = data.get('market_regimes', {})
                self.logger.info(f"Loaded {sum(len(p) for p in self.patterns.values())} SMC patterns from disk")
            except Exception as e:
                self.logger.error(f"Failed to load patterns from file: {e}")