# core/feature_extractor.py
import numpy as np
import pandas as pd

class FeatureExtractor:
    @staticmethod
    def extract_temporal_embeddings(timestamp_str_or_float) -> list:
        """
        Converts raw UNIX timestamps or timestamp strings into cyclical temporal embeddings for PyTorch.
        """
        try:
            # Handle float (UNIX) or string (pandas timestamp)
            if isinstance(timestamp_str_or_float, (int, float)):
                dt = pd.to_datetime(timestamp_str_or_float, unit='s')
            else:
                dt = pd.to_datetime(timestamp_str_or_float)
            
            hour = dt.hour + (dt.minute / 60.0)
            day_of_week = dt.weekday()
            month = dt.month

            # Cyclical encoding prevents the AI from thinking 23:59 and 00:01 are far apart
            temporal_features = [
                float(np.sin(2 * np.pi * hour / 24.0)),
                float(np.cos(2 * np.pi * hour / 24.0)),
                float(np.sin(2 * np.pi * day_of_week / 7.0)),
                float(np.cos(2 * np.pi * day_of_week / 7.0)),
                float(np.sin(2 * np.pi * month / 12.0)),
                float(np.cos(2 * np.pi * month / 12.0))
            ]
            return temporal_features
        except Exception:
            return [0.0] * 6

    STRATEGY_NAMES = [
        "CRT_TBS",
        "ICT",
        "SMC_CONCEPTS",
        "AMD",
        "AVC",
        "BANK_TO_BANK",
        "RAJA_BANKS",
        "SRC",
        "VSA",
        "VWAP_VAS",
        "M1_SCALPING",
    ]

    FEATURE_SCHEMA = [
        {"name": "active_bias", "type": "float", "transform": "none"},
        {"name": "liq_sweep", "type": "float", "transform": "none"},
        {"name": "mss_signal", "type": "float", "transform": "none"},
        {"name": "fvg_quality", "type": "float", "transform": "none"},
        {"name": "volatility_scaled", "type": "float", "transform": "clip(0, 0.005) / 0.005"},
        {"name": "atr_pct_scaled", "type": "float", "transform": "clip(0, 0.002) / 0.002"},
        {"name": "rvol_scaled", "type": "float", "transform": "clip(rvol - 1.0) / 2.0"},
        {"name": "bp_pct", "type": "float", "transform": "bp / (bp + sp)"},
        {"name": "ob_react", "type": "float", "transform": "none"},
        {"name": "sr_react", "type": "float", "transform": "none"},
        {"name": "retest_pb", "type": "float", "transform": "none"},
        {"name": "trend_shift", "type": "float", "transform": "none"},
        
        {"name": "strategy_CRT_TBS", "type": "float", "transform": "one_hot"},
        {"name": "strategy_ICT", "type": "float", "transform": "one_hot"},
        {"name": "strategy_SMC_CONCEPTS", "type": "float", "transform": "one_hot"},
        {"name": "strategy_AMD", "type": "float", "transform": "one_hot"},
        {"name": "strategy_AVC", "type": "float", "transform": "one_hot"},
        {"name": "strategy_BANK_TO_BANK", "type": "float", "transform": "one_hot"},
        {"name": "strategy_RAJA_BANKS", "type": "float", "transform": "one_hot"},
        {"name": "strategy_SRC", "type": "float", "transform": "one_hot"},
        {"name": "strategy_VSA", "type": "float", "transform": "one_hot"},
        {"name": "strategy_VWAP_VAS", "type": "float", "transform": "one_hot"},
        {"name": "strategy_M1_SCALPING", "type": "float", "transform": "one_hot"},
        
        {"name": "candidate_action", "type": "categorical", "mapping": {"BUY": 1.0, "SELL": -1.0, "HOLD/OTHER": 0.0}},
        
        {"name": "hour_sin", "type": "float", "transform": "cyclical"},
        {"name": "hour_cos", "type": "float", "transform": "cyclical"},
        {"name": "weekday_sin", "type": "float", "transform": "cyclical"},
        {"name": "weekday_cos", "type": "float", "transform": "cyclical"},
        {"name": "month_sin", "type": "float", "transform": "cyclical"},
        {"name": "month_cos", "type": "float", "transform": "cyclical"}
    ]
    
    FEATURE_NAMES = [f["name"] for f in FEATURE_SCHEMA]
    
    import hashlib
    import json
    FEATURE_SCHEMA_HASH = hashlib.sha256(
        json.dumps(FEATURE_SCHEMA, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()

    @classmethod
    def extract_nn_features(cls, features: dict) -> np.ndarray:
        """
        Convert market features dict to a 30-dimensional numpy array for the PyTorch Neural Net,
        encoding strategy identity and candidate trade action.
        """
        if not features or 'active_bias' not in features:
            raise ValueError("Feature snapshot missing or empty (legacy data).")
            
        try:
            # 1. Bias
            bias = float(features.get('active_bias', 0.0))
            
            # 2. Sweep
            sweep = float(features.get('liq_sweep_type', 0.0))
            
            # 3. MSS
            mss = float(features.get('mss_signal', 0.0))
            
            # 4. FVG Class
            fvg_class_str = str(features.get('fvg_class', 'none')).lower()
            fvg_class = 0.0
            if 'fresh' in fvg_class_str or 'pfvg' in fvg_class_str:
                fvg_class = 1.0
            elif 'institutional' in fvg_class_str or 'bag' in fvg_class_str:
                fvg_class = 0.8
            elif 'active' in fvg_class_str or 'rfvg' in fvg_class_str:
                fvg_class = 0.6
            elif 'stale' in fvg_class_str:
                fvg_class = 0.3
                
            # 5. Volatility (scaled & clipped to standard range)
            volatility = float(features.get('volatility', 0.0))
            volatility_scaled = float(np.clip(volatility / 0.005, 0.0, 3.0))
            
            # 6. ATR Pct (scaled & clipped to standard range)
            atr_pct = float(features.get('atr_pct', 0.0))
            atr_pct_scaled = float(np.clip(atr_pct / 0.002, 0.0, 3.0))
            
            # 7. RVOL (scaled & clipped to standard range)
            rvol = float(features.get('rvol', 1.0))
            rvol_scaled = float(np.clip((rvol - 1.0) / 2.0, -2.0, 2.0))
            
            # 8. Volume Pressure Pct
            bp = float(features.get('buy_pressure', 50.0))
            sp = float(features.get('sell_pressure', 50.0))
            bp_pct = bp / (bp + sp + 1e-9)
            
            # 9. OB Reaction Signal
            ob_react = float(features.get('ob_reaction_signal', 0.0))
            
            # 10. S/R Reaction Signal
            sr_react = float(features.get('sr_reaction_signal', 0.0))
            
            # 11. Retest Pullback Signal
            retest_pb = float(features.get('retest_pullback_signal', 0.0))
            
            # 12. Trend Shift Signal
            trend_shift = float(features.get('trend_shift_signal', 0.0))
            
            base_features = [
                bias, sweep, mss, fvg_class, volatility_scaled, atr_pct_scaled, rvol_scaled, bp_pct,
                ob_react, sr_react, retest_pb, trend_shift
            ]
            
            # 13-23. One-hot strategy encoding
            candidate_strategy = features.get('candidate_strategy')
            if candidate_strategy is not None:
                candidate_strategy = str(candidate_strategy).upper()
                if candidate_strategy not in cls.STRATEGY_NAMES:
                    raise ValueError(f"Unknown strategy: {candidate_strategy}")
            
            strategy_features = [
                1.0 if candidate_strategy == name else 0.0
                for name in cls.STRATEGY_NAMES
            ]
            
            # 24. Candidate action encoding (BUY = 1.0, SELL = -1.0, otherwise 0.0)
            candidate_action = str(features.get('candidate_action', 'HOLD')).upper()
            action_val = 1.0 if candidate_action == "BUY" else (-1.0 if candidate_action == "SELL" else 0.0)
            
            # 25-30. Temporal Embeddings
            timestamp = features.get('timestamp', pd.Timestamp.now().timestamp())
            temporal = FeatureExtractor.extract_temporal_embeddings(timestamp)
            
            return np.array(base_features + strategy_features + [action_val] + temporal, dtype=np.float32)
        except Exception as e:
            raise ValueError(f"Feature extraction failed: {e}")
