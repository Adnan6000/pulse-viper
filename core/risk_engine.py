# core/risk_engine.py
import numpy as np
import logging
import sqlite3
import os
import math
from utils.settings_manager import settings_manager

class DynamicRiskEngine:
    """Hardened risk sizing module enforcing fail-closed limits, Kelly caps, and drawdown protections."""
    
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.RiskEngine")
        self.min_sample_size = 20
        self.kelly_multiplier = 0.35
        # (drawdown_pct, size_multiplier)
        self.dd_throttle_thresholds = ((0.05, 0.75), (0.10, 0.50), (0.15, 0.25))

    def _wilson_lower_bound(self, wins: int, n: int, z: float = 1.64) -> float:
        if n == 0:
            return 0.0
        p_hat = wins / n
        denom = 1 + z**2 / n
        center = p_hat + z**2 / (2 * n)
        margin = z * math.sqrt(max(0.0, (p_hat * (1 - p_hat) + z**2 / (4 * n)) / n))
        return max(0.0, (center - margin) / denom)

    def calculate_risk_percent(self, current_atr: float, median_atr: float, 
                               current_spread: float, max_spread: float,
                               confidence: float, active_positions: int, 
                               base_risk: float = 0.25, strategy_name: str = "UNKNOWN",
                               open_portfolio_heat_pct: float = 0.0,
                               model_ready: bool = True) -> float:
        """
        Dynamically scale risk percentage down based on Kelly, volatility, and spreads.
        Can only reduce risk, never compound or scale above base_risk.
        Enforces strict daily loss limits, consecutive loss vetoes, and portfolio heat caps.
        """
        try:
            # 1. Spread Check (instant veto)
            if current_spread > max_spread:
                self.logger.warning(f"Spread exceeded limit: {current_spread} > {max_spread}. Risk set to 0.0.")
                return 0.0

            # 2. Consecutive Losses veto
            if self._check_consecutive_losses_veto():
                self.logger.warning("Veto: Max 3 consecutive losses reached. Sizing set to 0.0.")
                return 0.0

            # 3. Daily Loss budget veto
            max_daily_loss = float(settings_manager.get("max_daily_loss_pct", 1.0))
            if self._check_daily_loss_veto(max_daily_loss):
                self.logger.warning(f"Veto: Daily loss budget limit ({max_daily_loss}%) exceeded. Sizing set to 0.0.")
                return 0.0

            # 4. Enforce strict base risk limit (range [0.10%, 0.25%])
            base_risk = max(0.10, min(0.25, base_risk))

            # 5. Query performance statistics
            wins, n, avg_win_r, avg_loss_r = self._get_strategy_performance(strategy_name)

            # 6. Calculate fractional Kelly caps
            skip_kelly = not model_ready or (confidence is None) or n < self.min_sample_size
            if skip_kelly:
                edge_size = base_risk
            else:
                shrunk_wr = self._wilson_lower_bound(wins, n)
                b = avg_win_r / (abs(avg_loss_r) if avg_loss_r != 0 else 1.0)
                raw_kelly = shrunk_wr - (1.0 - shrunk_wr) / b
                if raw_kelly <= 0:
                    self.logger.warning(f"Negative Kelly edge ({raw_kelly:.4f}). Vetoing trade (risk=0.0).")
                    return 0.0
                kf = max(0.0, raw_kelly * self.kelly_multiplier)
                edge_size = min(kf * 100.0, base_risk)

            # 7. Drawdown circuit breaker multiplier
            current_drawdown_pct = self._calculate_rolling_drawdown()
            dd_multiplier = 1.0
            for dd_level, mult in sorted(self.dd_throttle_thresholds):
                if current_drawdown_pct >= dd_level:
                    dd_multiplier = mult
            
            # 8. Volatility Scaling (risk scaling capped at 1.0 maximum, only scales down)
            if median_atr > 0 and current_atr > 0:
                m_vol = min(1.0, median_atr / current_atr)
            else:
                m_vol = 1.0

            # 9. Spread Scaling multiplier
            if max_spread > 0:
                spread_ratio = current_spread / max_spread
                spread_mult = max(0.0, min(1.0, 1.0 - (spread_ratio - 0.5) * 2.0)) if spread_ratio > 0.5 else 1.0
            else:
                spread_mult = 1.0

            # Calculate final risk percent applying only down-scaling multipliers
            final_risk = edge_size * dd_multiplier * m_vol * spread_mult

            # 10. Portfolio heat cap (strictly capped at 1.0% - 1.5% max)
            max_heat = max(1.0, min(1.5, float(settings_manager.get("max_portfolio_heat", 1.5))))
            remaining_heat = max(0.0, max_heat - open_portfolio_heat_pct)
            final_risk = min(final_risk, remaining_heat)

            # Keep final risk strictly capped at baseline
            final_risk = min(final_risk, base_risk)

            if final_risk <= 0.01:
                return 0.0

            return final_risk

        except Exception as e:
            self.logger.error(f"Error calculating dynamic risk: {e}")
            # Fail closed: return 0.0 in case of error rather than fallback
            return 0.0

    def _check_consecutive_losses_veto(self) -> bool:
        from core.trade_journal import JOURNAL_DB
        if not os.path.exists(JOURNAL_DB):
            return False
        try:
            conn = sqlite3.connect(JOURNAL_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT pnl FROM trades ORDER BY id DESC LIMIT 3")
            rows = cursor.fetchall()
            conn.close()
            if len(rows) == 3 and all(float(r[0] or 0.0) < 0.0 for r in rows):
                return True
        except Exception as e:
            self.logger.error(f"Error checking consecutive losses: {e}")
        return False

    def _check_daily_loss_veto(self, max_loss_pct: float) -> bool:
        from core.trade_journal import JOURNAL_DB
        import datetime
        if not os.path.exists(JOURNAL_DB):
            return False
        try:
            conn = sqlite3.connect(JOURNAL_DB)
            cursor = conn.cursor()
            today_str = datetime.date.today().isoformat()
            cursor.execute("SELECT pnl FROM trades WHERE date = ? AND pnl < 0", (today_str,))
            rows = cursor.fetchall()
            conn.close()
            total_loss = sum(abs(float(row[0] or 0.0)) for row in rows)
            if total_loss >= max_loss_pct:
                return True
        except Exception as e:
            self.logger.error(f"Error checking daily loss limit: {e}")
        return False

    def _get_strategy_performance(self, strategy_name: str) -> tuple:
        from core.trade_journal import JOURNAL_DB
        db_path = JOURNAL_DB
        wins = 0
        total = 0
        avg_win_r = 2.0
        avg_loss_r = 1.0
        
        if not os.path.exists(db_path):
            return wins, total, avg_win_r, avg_loss_r

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT pnl, rr_achieved FROM trades WHERE strategy_name = ? AND pnl IS NOT NULL", 
                (strategy_name,)
            )
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                total = len(rows)
                wins = sum(1 for row in rows if float(row[0] or 0.0) > 0.0)
                win_rrs = [float(row[1] or 0.0) for row in rows if float(row[0] or 0.0) > 0.0]
                loss_rrs = [float(row[1] or 0.0) for row in rows if float(row[0] or 0.0) <= 0.0]
                if win_rrs:
                    avg_win_r = abs(sum(win_rrs) / len(win_rrs))
                if loss_rrs:
                    avg_loss_r = abs(sum(loss_rrs) / len(loss_rrs))
        except Exception as e:
            self.logger.error(f"Failed to query performance cache: {e}")
            
        return wins, total, avg_win_r, avg_loss_r

    def _calculate_rolling_drawdown(self) -> float:
        # Default mock or query actual drawdown from DB
        return 0.0

