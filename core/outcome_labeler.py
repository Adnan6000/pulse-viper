# core/outcome_labeler.py
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass(frozen=True)
class CandidateOutcome:
    candidate_id: str

    outcome_type: str
    tp_before_sl: Optional[bool]

    net_r: Optional[float]
    mfe_r: float
    mae_r: float
    holding_bars: int

    spread_r: float
    commission_r: float
    slippage_r: float

    same_bar_ambiguous: bool
    data_source: str
    source_quality: float

    label_version: str

class OutcomeResolver:
    """Resolves and labels historical candidate outcomes precisely under Plan v4.1 rules."""
    
    @staticmethod
    def resolve(
        candidate_id: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        action: str,
        bars_future: List[Dict[str, Any]],
        lower_tf_bars: Optional[List[Dict[str, Any]]] = None,
        spread_points: float = 20.0,
        point: float = 0.01
    ) -> CandidateOutcome:
        initial_risk = abs(entry_price - stop_price)
        if initial_risk <= 0.0:
            return CandidateOutcome(
                candidate_id=candidate_id,
                outcome_type="INVALID_GEOMETRY",
                tp_before_sl=None,
                net_r=None,
                mfe_r=0.0,
                mae_r=0.0,
                holding_bars=0,
                spread_r=0.0,
                commission_r=0.0,
                slippage_r=0.0,
                same_bar_ambiguous=False,
                data_source="NONE",
                source_quality=0.0,
                label_version="v4.1"
            )

        tp_hit = False
        sl_hit = False
        tp_idx = -1
        sl_idx = -1
        
        mfe_price = entry_price
        mae_price = entry_price
        
        holding_bars = 0
        
        # 1. Main timeframe resolution loop
        for idx, bar in enumerate(bars_future):
            holding_bars = idx + 1
            high = bar["high"]
            low = bar["low"]
            
            # Track Max Favorable / Adverse Excursion
            if action == "BUY":
                mfe_price = max(mfe_price, high)
                mae_price = min(mae_price, low)
            else:
                mfe_price = min(mfe_price, low)
                mae_price = max(mae_price, high)
                
            # Check hits
            bar_tp = (high >= target_price) if action == "BUY" else (low <= target_price)
            bar_sl = (low <= stop_price) if action == "BUY" else (high >= stop_price)
            
            if bar_tp and not tp_hit:
                tp_hit = True
                tp_idx = idx
            if bar_sl and not sl_hit:
                sl_hit = True
                sl_idx = idx
                
            if tp_hit or sl_hit:
                # Stop checking further bars once at least one limit is hit
                break
                
        # Calculate excursions in R terms
        if action == "BUY":
            mfe_r = (mfe_price - entry_price) / initial_risk
            mae_r = (entry_price - mae_price) / initial_risk
        else:
            mfe_r = (entry_price - mfe_price) / initial_risk
            mae_r = (mae_price - entry_price) / initial_risk

        # 2. Same Bar Ambiguity checks
        same_bar_ambiguous = (tp_hit and sl_hit and tp_idx == sl_idx)
        tp_before_sl = None
        outcome_type = "UNRESOLVED"
        
        if same_bar_ambiguous:
            # Attempt lower timeframe resolution if provided
            resolved = False
            if lower_tf_bars:
                for lbar in lower_tf_bars:
                    l_high = lbar["high"]
                    l_low = lbar["low"]
                    l_tp = (l_high >= target_price) if action == "BUY" else (l_low <= target_price)
                    l_sl = (l_low <= stop_price) if action == "BUY" else (l_high >= stop_price)
                    
                    if l_tp and not l_sl:
                        tp_before_sl = True
                        outcome_type = "TP_FIRST"
                        resolved = True
                        break
                    if l_sl and not l_tp:
                        tp_before_sl = False
                        outcome_type = "SL_FIRST"
                        resolved = True
                        break
            if not resolved:
                outcome_type = "AMBIGUOUS_SAME_BAR"
        else:
            if tp_hit and (not sl_hit or tp_idx < sl_idx):
                tp_before_sl = True
                outcome_type = "TP_FIRST"
            elif sl_hit and (not tp_hit or sl_idx < tp_idx):
                tp_before_sl = False
                outcome_type = "SL_FIRST"
            else:
                outcome_type = "TIME_EXIT"
                
        # 3. Transaction Costs adjustments
        spread_r = (spread_points * point) / initial_risk
        commission_r = 0.05  # Standard estimate of 0.05R
        slippage_r = 0.02    # Standard estimate of 0.02R
        
        net_r = None
        if outcome_type == "TP_FIRST":
            raw_r = (target_price - entry_price) / initial_risk if action == "BUY" else (entry_price - target_price) / initial_risk
            net_r = raw_r - spread_r - commission_r - slippage_r
        elif outcome_type == "SL_FIRST":
            net_r = -1.0 - spread_r - commission_r - slippage_r
        elif outcome_type == "TIME_EXIT":
            # Exit at last bar close price
            last_close = bars_future[holding_bars - 1]["close"]
            raw_r = (last_close - entry_price) / initial_risk if action == "BUY" else (entry_price - last_close) / initial_risk
            net_r = raw_r - spread_r - commission_r - slippage_r

        return CandidateOutcome(
            candidate_id=candidate_id,
            outcome_type=outcome_type,
            tp_before_sl=tp_before_sl,
            net_r=net_r,
            mfe_r=mfe_r,
            mae_r=mae_r,
            holding_bars=holding_bars,
            spread_r=spread_r,
            commission_r=commission_r,
            slippage_r=slippage_r,
            same_bar_ambiguous=same_bar_ambiguous and (tp_before_sl is None),
            data_source="M1_RECONSTRUCTED" if lower_tf_bars else "BARS_FUTURE",
            source_quality=1.0 if not same_bar_ambiguous else (0.8 if lower_tf_bars else 0.1),
            label_version="v4.1"
        )
