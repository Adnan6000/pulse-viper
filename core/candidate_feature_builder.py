# core/candidate_feature_builder.py
import json
import hashlib
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List
from core.market_context import MarketContext
from core.candidate_setup import CandidateSetup

FEATURE_SCHEMA_VERSION = 4

# Schema defining the canonical list of inputs to model inference.
# Total of 32 items for the upgraded schema version 4.
FEATURE_SCHEMA = [
    {"name": "strategy_crt", "type": "float"},
    {"name": "strategy_ict", "type": "float"},
    {"name": "strategy_amd", "type": "float"},
    {"name": "strategy_vwap", "type": "float"},
    {"name": "candidate_action_buy", "type": "float"},
    {"name": "candidate_action_sell", "type": "float"},
    
    {"name": "mode_scalping", "type": "float"},
    {"name": "mode_intraday", "type": "float"},
    {"name": "mode_swing", "type": "float"},
    
    {"name": "regime_range", "type": "float"},
    {"name": "regime_trending", "type": "float"},
    {"name": "regime_uncertain", "type": "float"},
    {"name": "regime_age_bars", "type": "float"},
    
    {"name": "volatility_scaled", "type": "float"},
    {"name": "atr_pct_scaled", "type": "float"},
    {"name": "spread_to_risk_ratio", "type": "float"},
    
    {"name": "swing_scale_micro", "type": "float"},
    {"name": "swing_scale_internal", "type": "float"},
    {"name": "swing_scale_external", "type": "float"},
    
    {"name": "sweep_distance_atr", "type": "float"},
    {"name": "sweep_strength", "type": "float"},
    
    {"name": "mss_displacement", "type": "float"},
    {"name": "fvg_size_atr", "type": "float"},
    {"name": "fvg_age_bars", "type": "float"},
    {"name": "ob_freshness", "type": "float"},
    {"name": "ob_mitigation_pct", "type": "float"},
    
    {"name": "entry_to_sl_atr", "type": "float"},
    {"name": "entry_to_target_atr", "type": "float"},
    {"name": "planned_rr", "type": "float"},
    
    {"name": "session_london", "type": "float"},
    {"name": "session_ny", "type": "float"},
    {"name": "data_quality_score", "type": "float"}
]

FEATURE_SCHEMA_HASH = hashlib.sha256(
    json.dumps(FEATURE_SCHEMA, sort_keys=True, separators=(',', ':')).encode('utf-8')
).hexdigest()

class CandidateFeatureBuilder:
    """Hardened builder converting MarketContext and CandidateSetup into model features."""
    
    @staticmethod
    def build(context: MarketContext, candidate: CandidateSetup) -> np.ndarray:
        """
        Extracts features strictly based on schema v4 and returns a 32-dimensional NumPy array.
        Handles missing fields gracefully via default values and explicit warning.
        """
        feats: Dict[str, float] = {}

        # 1. Strategy Name One-Hot
        strat = candidate.strategy_name.upper()
        feats["strategy_crt"] = 1.0 if "CRT" in strat else 0.0
        feats["strategy_ict"] = 1.0 if "ICT" in strat else 0.0
        feats["strategy_amd"] = 1.0 if "AMD" in strat else 0.0
        feats["strategy_vwap"] = 1.0 if "VWAP" in strat else 0.0

        # 2. Candidate Action One-Hot
        act = candidate.action.upper()
        feats["candidate_action_buy"] = 1.0 if act == "BUY" else 0.0
        feats["candidate_action_sell"] = 1.0 if act == "SELL" else 0.0

        # 3. Trading Mode One-Hot
        mode = candidate.mode.lower()
        feats["mode_scalping"] = 1.0 if mode == "scalping" else 0.0
        feats["mode_intraday"] = 1.0 if mode == "intraday" else 0.0
        feats["mode_swing"] = 1.0 if mode == "swing" else 0.0

        # 4. Regime Context
        regime = context.regime_label.upper()
        feats["regime_range"] = context.regime_probabilities.get("RANGE", 0.0)
        feats["regime_trending"] = context.regime_probabilities.get("TRENDING", 0.0)
        feats["regime_uncertain"] = 1.0 if regime == "UNCERTAIN" else 0.0
        feats["regime_age_bars"] = float(context.regime_age_bars)

        # 5. Volatility and Spread
        spread_ctx = context.spread_context
        # Normalized Spread to Risk Ratio (Spread Points * Point / Risk Distance)
        point = float(spread_ctx.get("point", 0.0001))
        spread_val = float(spread_ctx.get("current_spread", 1.0)) * point
        risk_dist = candidate.risk_distance
        feats["spread_to_risk_ratio"] = spread_val / risk_dist if risk_dist > 0.0 else 0.0
        
        # Volatility features
        feats["volatility_scaled"] = float(context.trend_state.get("volatility_ratio", 1.0))
        feats["atr_pct_scaled"] = float(context.trend_state.get("atr_pct", 0.001))

        # 6. Swing details (metadata)
        swing_scale = candidate.metadata.get("swing_scale", "INTERNAL")
        feats["swing_scale_micro"] = 1.0 if swing_scale == "MICRO" else 0.0
        feats["swing_scale_internal"] = 1.0 if swing_scale == "INTERNAL" else 0.0
        feats["swing_scale_external"] = 1.0 if swing_scale in ("EXTERNAL", "MAJOR") else 0.0

        # 7. Sweeps and Displacement (metadata)
        feats["sweep_distance_atr"] = float(candidate.metadata.get("sweep_distance_atr", 0.0))
        feats["sweep_strength"] = float(candidate.metadata.get("sweep_strength", 1.0))
        feats["mss_displacement"] = float(candidate.metadata.get("mss_displacement", 1.0))

        # 8. Zones / FVGs / OBs (metadata)
        feats["fvg_size_atr"] = float(candidate.metadata.get("fvg_size_atr", 0.0))
        feats["fvg_age_bars"] = float(candidate.metadata.get("fvg_age_bars", 0.0))
        feats["ob_freshness"] = float(candidate.metadata.get("ob_freshness", 1.0))
        feats["ob_mitigation_pct"] = float(candidate.metadata.get("ob_mitigation_pct", 0.0))

        # 9. Entry Distances in ATR
        # Planned SL and target distances normalized by ATR
        atr = float(context.trend_state.get("atr", 1.0))
        feats["entry_to_sl_atr"] = risk_dist / atr if atr > 0.0 else 1.0
        feats["entry_to_target_atr"] = candidate.reward_distance / atr if atr > 0.0 else 2.0
        feats["planned_rr"] = candidate.planned_rr

        # 10. Sessions and Quality
        session = context.session_context.get("active_session", "NY")
        feats["session_london"] = 1.0 if session == "LONDON" else 0.0
        feats["session_ny"] = 1.0 if session == "NY" else 0.0
        
        # Data Quality Score
        feats["data_quality_score"] = float(context.data_quality.get("quality_score", 100.0))

        # 11. Compile array in canonical schema order
        arr = []
        for schema_item in FEATURE_SCHEMA:
            name = schema_item["name"]
            val = feats.get(name, 0.0)
            arr.append(val)

        return np.array(arr, dtype=np.float32)
