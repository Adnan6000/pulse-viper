# core/trade_pattern_memory.py
import json
import os
import logging
import numpy as np
from typing import Dict, Any, List, Tuple

class TradePatternMemory:
    """
    Phase 11: Trade Pattern Memory (Unified)
    Tracks feature vectors of executed trades and their eventual outcomes.
    Uses distance-based clustering (K-Nearest Neighbors approach) to find
    similar past market environments.
    Returns score boosts for setups resembling known winners,
    and penalties for setups resembling known false-positive traps.
    """
    def __init__(self, filepath="data/trade_pattern_memory.json"):
        self.filepath = filepath
        self.logger = logging.getLogger("PulseViper.TradePatternMemory")
        self.memory_bank: List[Dict[str, Any]] = []
        self.load_memory()

    def load_memory(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.memory_bank = json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load trade pattern memory: {e}")
                self.memory_bank = []

    def save_memory(self):
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w") as f:
                json.dump(self.memory_bank, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save trade pattern memory: {e}")

    def _extract_vector(self, analysis: Dict) -> List[float]:
        """Extract a normalized numerical feature vector from analysis state."""
        # We need a stable vector to compute Euclidean distance
        price = analysis.get('close', analysis.get('bid', 0.0))
        atr = analysis.get('atr', 0.0001)
        if price == 0: price = 1.0
        if atr == 0: atr = 0.0001

        # Normalized Volatility (ATR / Price) * 10000
        norm_vol = (atr / price) * 10000

        # AI Confidence (0.0 to 1.0)
        ai_conf = analysis.get('ai_confidence', 0.5)

        # Spread ratio
        spread = analysis.get('spread', 1.0)
        norm_spread = spread / 10.0  # Normalize around typical 10 point spread

        # Regime Encoding
        regime_map = {"TRENDING": 1.0, "RANGE": 0.5, "COMPRESSION": 0.2, "CHAOTIC": 2.0}
        regime = regime_map.get(analysis.get('market_regime', 'RANGE'), 0.5)

        # Session overlap encoding (London+NY = 1.0, Asian = 0.3, etc)
        session_score = analysis.get('session_score', 0.0)

        # --- SPATIAL MEMORY EXTENSION ---
        # Distance to support/resistance (normalized by ATR)
        support = analysis.get('support', price)
        resistance = analysis.get('resistance', price)
        if support is None or np.isnan(support): support = price
        if resistance is None or np.isnan(resistance): resistance = price
        dist_supp = min(10.0, abs(price - support) / atr)
        dist_res = min(10.0, abs(price - resistance) / atr)
        
        # Distance to Order Block
        ob_top = analysis.get('ob_top', price)
        ob_bottom = analysis.get('ob_bottom', price)
        if ob_top is None or np.isnan(ob_top): ob_top = price
        if ob_bottom is None or np.isnan(ob_bottom): ob_bottom = price
        ob_mid = (ob_top + ob_bottom) / 2.0
        dist_ob = min(10.0, abs(price - ob_mid) / atr)
        
        # Distance to FVG
        fvg_top = analysis.get('fvg_top', price)
        fvg_bottom = analysis.get('fvg_bottom', price)
        if fvg_top is None or np.isnan(fvg_top): fvg_top = price
        if fvg_bottom is None or np.isnan(fvg_bottom): fvg_bottom = price
        fvg_mid = (fvg_top + fvg_bottom) / 2.0
        dist_fvg = min(10.0, abs(price - fvg_mid) / atr)
        
        # Sweep status
        sweep = analysis.get('liq_sweep_type', 0)
        sweep_norm = 1.0 if sweep == 1 else (-1.0 if sweep == -1 else 0.0)

        # 10-Dimensional Vector
        return [
            float(norm_vol),
            float(ai_conf),
            float(norm_spread),
            float(regime),
            float(session_score),
            float(dist_supp),
            float(dist_res),
            float(dist_ob),
            float(dist_fvg),
            float(sweep_norm)
        ]

    def record_outcome(self, analysis: Dict, pnl: float):
        """Record the outcome of a closed trade."""
        vector = self._extract_vector(analysis)
        is_win = pnl > 0
        
        record = {
            "vector": vector,
            "pnl": pnl,
            "is_win": is_win,
            "symbol": analysis.get('symbol', 'UNKNOWN'),
            "regime": analysis.get('market_regime', 'UNKNOWN')
        }
        
        self.memory_bank.append(record)
        # Keep last 5000 trades to prevent unbounded growth
        if len(self.memory_bank) > 5000:
            self.memory_bank = self.memory_bank[-5000:]
        
        self.save_memory()

    def get_modifier(self, analysis: Dict, k_neighbors: int = 5) -> float:
        """
        Finds the K most similar past trades.
        If they heavily skewed towards winning, returns a positive score boost.
        If they heavily skewed towards losing, returns a negative penalty.
        """
        if len(self.memory_bank) < 10:
            return 0.0  # Not enough data yet

        current_vector = np.array(self._extract_vector(analysis))
        
        # Calculate Euclidean distances
        distances = []
        for i, record in enumerate(self.memory_bank):
            past_vec = np.array(record["vector"])
            dist = np.linalg.norm(current_vector - past_vec)
            distances.append((dist, record["is_win"], record["pnl"]))
            
        # Sort by distance (closest first)
        distances.sort(key=lambda x: x[0])
        nearest = distances[:k_neighbors]
        
        # Calculate cluster win rate
        wins = sum(1 for d in nearest if d[1])
        losses = k_neighbors - wins
        
        win_rate = wins / k_neighbors
        
        # Base modifier
        # If win rate is exactly 50%, modifier is 0
        # If win rate is 100%, modifier is +5
        # If win rate is 0%, modifier is -10 (penalties hit harder than boosts)
        if win_rate > 0.6:
            # Boost: 0 to +5 points
            modifier = (win_rate - 0.5) * 10.0
        elif win_rate < 0.4:
            # Penalty: 0 to -10 points
            modifier = (win_rate - 0.5) * 20.0
        else:
            modifier = 0.0
            
        return round(modifier, 1)

    def get_closest_similarity(self, analysis: Dict) -> Tuple[int, float]:
        """Finds the closest past trade pattern and returns its ID (index) and similarity percentage [0.0, 1.0]"""
        if not self.memory_bank:
            return -1, 0.0
            
        try:
            current_vector = np.array(self._extract_vector(analysis))
            distances = []
            for i, record in enumerate(self.memory_bank):
                past_vec = np.array(record["vector"])
                dist = np.linalg.norm(current_vector - past_vec)
                distances.append((dist, i))
                
            distances.sort(key=lambda x: x[0])
            closest_dist, closest_idx = distances[0]
            # Convert distance to similarity score in range [0, 1]
            similarity = float(1.0 / (1.0 + closest_dist))
            return closest_idx, round(similarity, 4)
        except Exception:
            return -1, 0.0

trade_pattern_memory = TradePatternMemory()
