# core/risk_engine.py
import numpy as np
import logging

class DynamicRiskEngine:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.RiskEngine")

    def calculate_risk_percent(self, current_atr: float, median_atr: float, 
                               current_spread: float, max_spread: float,
                               confidence: float, active_positions: int, 
                               base_risk: float = 1.0) -> float:
        """
        Dynamically scale the trade risk percentage based on market conditions:
        1. Volatility Scaling (risk scales down if volatility expands rapidly)
        2. Spread scaling (risk scales down linearly if spread is near max allowed)
        3. Confidence scaling (risk scales up if AI/SMC confidence is strong)
        4. Over-exposure scaling (risk divides by count of existing positions)
        """
        try:
            # 1. Volatility Multiplier (clip between 0.5 and 1.5)
            # Scaling down when current ATR is significantly higher than historical median
            if median_atr > 0:
                m_vol = float(np.clip(median_atr / (current_atr + 1e-9), 0.5, 1.5))
            else:
                m_vol = 1.0

            # 2. Spread Multiplier
            # Scale down linearly as spread approaches max_spread. Cut size to 0 if spread is exceeded.
            if current_spread > max_spread:
                m_spread = 0.0
            elif current_spread > max_spread * 0.7:
                # scale down from 100% to 0% in the last 30% of allowed spread range
                diff = current_spread - (max_spread * 0.7)
                denom = max_spread * 0.3
                m_spread = float(max(0.0, 1.0 - (diff / (denom + 1e-9))))
            else:
                m_spread = 1.0

            # 3. Confidence Multiplier
            # SMC confidence scores are typically 0.5 to 1.0. Scale risk accordingly.
            m_conf = float(np.clip(confidence, 0.5, 1.3))

            # 4. Over-exposure scaling
            # Scale down if multiple positions are already active
            m_exposure = 1.0 / (active_positions + 1)

            # Combined dynamic risk size
            risk_percent = base_risk * m_vol * m_spread * m_conf * m_exposure
            
            # Enforce hard bounds [0.1%, 2.0%] for account preservation
            risk_percent = float(np.clip(risk_percent, 0.1, 2.0))
            
            self.logger.info(
                f"🛡️ Dynamic Risk Calculated: {risk_percent:.2f}% | "
                f"Base={base_risk:.1f}% M_Vol={m_vol:.2f} M_Spread={m_spread:.2f} M_Conf={m_conf:.2f} Exposure={m_exposure:.2f}"
            )
            return risk_percent
            
        except Exception as e:
            self.logger.error(f"Error calculating dynamic risk: {e}")
            return base_risk
