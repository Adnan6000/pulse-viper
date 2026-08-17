# core/risk_engine.py

from __future__ import annotations

import logging
import math
import os
import sqlite3

from dataclasses import dataclass
from typing import Optional, Tuple

from utils.settings_manager import settings_manager
from utils.mt5_gateway import mt5_gateway as mt5
from core.safety_engine import SafetyEngine


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class StrategyPerformance:
    """
    Conservative historical performance snapshot.

    All risk values used by this module are percentage points:
        0.05 = 0.05%
        0.10 = 0.10%
        1.00 = 1.00%
    """

    wins: int = 0
    losses: int = 0
    total: int = 0

    win_rate: float = 0.0

    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0

    sample_ready: bool = False


@dataclass(frozen=True)
class RiskSizingSnapshot:
    """
    Diagnostic output for dashboard/tests.

    `final_risk_pct` is the actual risk percentage returned by
    calculate_risk_percent().
    """

    allowed: bool

    configured_base_risk_pct: float
    final_risk_pct: float

    open_portfolio_heat_pct: float
    max_portfolio_heat_pct: float
    remaining_portfolio_heat_pct: float

    volatility_multiplier: float
    spread_multiplier: float
    drawdown_multiplier: float

    edge_cap_pct: Optional[float]

    safety_reason: str
    reason: str


# =============================================================================
# HELPERS
# =============================================================================


def _finite_float(
    value,
    default: float = 0.0,
) -> float:
    try:
        result = float(value)

        if math.isfinite(result):
            return result

    except (TypeError, ValueError):
        pass

    return default


def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


# =============================================================================
# DYNAMIC RISK ENGINE
# =============================================================================


class DynamicRiskEngine:
    """
    Risk SIZING engine.

    Architecture
    ------------

    SafetyEngine:
        decides whether a new trade is allowed at all.

    DynamicRiskEngine:
        decides how much of the configured risk budget may be used.

    ExecutionValidator:
        independently validates the final broker order.

    Important invariants
    --------------------

    1. Never increase user configured base risk.
    2. Never invent an independent daily-loss/consecutive-loss policy.
    3. Never override configured portfolio heat with another hidden range.
    4. Optional ML/Kelly logic may only reduce risk.
    5. Missing model/history data does NOT create artificial confidence.
    6. Spread and volatility may only reduce risk.
    7. Safety failure is fail-closed.
    """

    def __init__(
        self,
        safety_engine: Optional[SafetyEngine] = None,
    ):
        self.logger = logging.getLogger(
            "PulseViper.RiskEngine"
        )

        self.safety_engine = (
            safety_engine
            if safety_engine is not None
            else SafetyEngine()
        )

        # Require meaningful strategy history before any Kelly calculation.
        self.min_sample_size = 30

        # Fractional Kelly.
        #
        # Even after Wilson shrinkage, only use 25% of calculated Kelly.
        # The result is then capped at configured base risk.
        self.kelly_fraction = 0.25

        # Limit DB sample so very old market regimes do not dominate forever.
        self.performance_lookback = 200

        self.last_snapshot = RiskSizingSnapshot(
            allowed=False,
            configured_base_risk_pct=0.0,
            final_risk_pct=0.0,
            open_portfolio_heat_pct=0.0,
            max_portfolio_heat_pct=0.0,
            remaining_portfolio_heat_pct=0.0,
            volatility_multiplier=1.0,
            spread_multiplier=1.0,
            drawdown_multiplier=1.0,
            edge_cap_pct=None,
            safety_reason="NOT_EVALUATED",
            reason="NOT_EVALUATED",
        )

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def calculate_risk_percent(
        self,
        current_atr: float,
        median_atr: float,
        current_spread: float,
        max_spread: float,
        confidence: float,
        active_positions: int,
        base_risk: float = 0.25,
        strategy_name: str = "UNKNOWN",
        open_portfolio_heat_pct: float = 0.0,
        model_ready: bool = True,
    ) -> float:
        """
        Return final allowed account-risk percentage.

        Compatibility:
            Preserves the original PulseViper method signature.

        Example:
            configured risk_percent = 0.05
            -> maximum possible output = 0.05

        This function can NEVER turn 0.05 into 0.10 or 0.25.
        """

        # active_positions retained for call compatibility and future telemetry.
        del active_positions

        try:
            # -----------------------------------------------------------------
            # 1. Normalize inputs
            # -----------------------------------------------------------------

            configured_risk = max(
                0.0,
                _finite_float(
                    base_risk,
                    0.0,
                ),
            )

            # Settings are authoritative if available.
            setting_risk = _finite_float(
                settings_manager.get(
                    "risk_percent",
                    configured_risk,
                ),
                configured_risk,
            )

            # Caller may intentionally pass a smaller risk budget.
            #
            # Never allow either side to increase the other.
            if configured_risk > 0.0:
                configured_risk = min(
                    configured_risk,
                    max(
                        0.0,
                        setting_risk,
                    ),
                )

            else:
                configured_risk = max(
                    0.0,
                    setting_risk,
                )

            if configured_risk <= 0.0:
                return self._reject(
                    configured_risk=0.0,
                    open_heat=open_portfolio_heat_pct,
                    max_heat=self._max_portfolio_heat(),
                    safety_reason="RISK_DISABLED",
                    reason="CONFIGURED_RISK_IS_ZERO",
                )

            current_atr = max(
                0.0,
                _finite_float(
                    current_atr,
                    0.0,
                ),
            )

            median_atr = max(
                0.0,
                _finite_float(
                    median_atr,
                    0.0,
                ),
            )

            current_spread = max(
                0.0,
                _finite_float(
                    current_spread,
                    0.0,
                ),
            )

            max_spread = max(
                0.0,
                _finite_float(
                    max_spread,
                    0.0,
                ),
            )

            open_heat = max(
                0.0,
                _finite_float(
                    open_portfolio_heat_pct,
                    0.0,
                ),
            )

            confidence = _clamp(
                _finite_float(
                    confidence,
                    0.5,
                ),
                0.0,
                1.0,
            )

            # -----------------------------------------------------------------
            # 2. SafetyEngine is the ONLY hard account-risk veto authority
            # -----------------------------------------------------------------

            try:
                allowed, safety_reason = (
                    self.safety_engine
                    .check_entry_allowed()
                )

            except Exception as exc:
                self.logger.error(
                    "SafetyEngine failure during sizing: %s",
                    exc,
                )

                return self._reject(
                    configured_risk=configured_risk,
                    open_heat=open_heat,
                    max_heat=self._max_portfolio_heat(),
                    safety_reason="SAFETY_ENGINE_ERROR",
                    reason="SAFETY_ENGINE_ERROR",
                )

            if not allowed:
                self.logger.warning(
                    "Risk sizing blocked by SafetyEngine: %s",
                    safety_reason,
                )

                return self._reject(
                    configured_risk=configured_risk,
                    open_heat=open_heat,
                    max_heat=self._max_portfolio_heat(),
                    safety_reason=str(
                        safety_reason
                    ),
                    reason="SAFETY_ENGINE_VETO",
                )

            # -----------------------------------------------------------------
            # 3. Spread hard boundary
            #
            # ExecutionValidator also independently verifies this.
            # -----------------------------------------------------------------

            if max_spread <= 0.0:
                return self._reject(
                    configured_risk=configured_risk,
                    open_heat=open_heat,
                    max_heat=self._max_portfolio_heat(),
                    safety_reason=str(
                        safety_reason
                    ),
                    reason="INVALID_MAX_SPREAD",
                )

            if current_spread > max_spread:
                return self._reject(
                    configured_risk=configured_risk,
                    open_heat=open_heat,
                    max_heat=self._max_portfolio_heat(),
                    safety_reason=str(
                        safety_reason
                    ),
                    reason="SPREAD_EXCEEDED",
                )

            # -----------------------------------------------------------------
            # 4. One authoritative portfolio-heat setting
            # -----------------------------------------------------------------

            max_heat = (
                self._max_portfolio_heat()
            )

            remaining_heat = max(
                0.0,
                max_heat
                - open_heat,
            )

            if remaining_heat <= 0.0:
                return self._reject(
                    configured_risk=configured_risk,
                    open_heat=open_heat,
                    max_heat=max_heat,
                    safety_reason=str(
                        safety_reason
                    ),
                    reason="PORTFOLIO_HEAT_EXHAUSTED",
                )

            # Risk budget starts at USER configured risk.
            risk = min(
                configured_risk,
                remaining_heat,
            )

            # -----------------------------------------------------------------
            # 5. Volatility multiplier
            #
            # Normal/lower ATR = 1.0
            # Higher-than-normal ATR = reduce.
            # -----------------------------------------------------------------

            volatility_multiplier = (
                self._volatility_multiplier(
                    current_atr=current_atr,
                    median_atr=median_atr,
                )
            )

            risk *= (
                volatility_multiplier
            )

            # -----------------------------------------------------------------
            # 6. Spread quality multiplier
            #
            # Spread is already within hard limit.
            # Risk is progressively reduced as spread approaches the limit.
            # -----------------------------------------------------------------

            spread_multiplier = (
                self._spread_multiplier(
                    current_spread=(
                        current_spread
                    ),
                    max_spread=(
                        max_spread
                    ),
                )
            )

            risk *= (
                spread_multiplier
            )

            # -----------------------------------------------------------------
            # 7. Drawdown throttle
            #
            # SafetyEngine owns the hard halt.
            # RiskEngine only reduces size as the account approaches that halt.
            # -----------------------------------------------------------------

            drawdown_multiplier = (
                self._drawdown_multiplier()
            )

            risk *= (
                drawdown_multiplier
            )

            # -----------------------------------------------------------------
            # 8. Statistical edge / Kelly CAP
            #
            # This is optional.
            #
            # If model isn't ready or sample is small:
            #     no Kelly adjustment.
            #
            # If enough real outcomes exist:
            #     conservative Wilson + fractional Kelly can only cap LOWER.
            # -----------------------------------------------------------------

            edge_cap_pct = None

            if bool(model_ready):
                performance = (
                    self._get_strategy_performance(
                        strategy_name
                    )
                )

                if (
                    performance.sample_ready
                    and performance.total
                    >= self.min_sample_size
                ):
                    edge_cap_pct = (
                        self._calculate_edge_cap_pct(
                            performance=performance,
                            confidence=confidence,
                        )
                    )

                    # A validated negative edge is a legitimate sizing veto.
                    if edge_cap_pct <= 0.0:
                        return self._reject(
                            configured_risk=configured_risk,
                            open_heat=open_heat,
                            max_heat=max_heat,
                            safety_reason=str(
                                safety_reason
                            ),
                            reason="NO_POSITIVE_STATISTICAL_EDGE",
                            volatility_multiplier=(
                                volatility_multiplier
                            ),
                            spread_multiplier=(
                                spread_multiplier
                            ),
                            drawdown_multiplier=(
                                drawdown_multiplier
                            ),
                            edge_cap_pct=0.0,
                        )

                    risk = min(
                        risk,
                        edge_cap_pct,
                    )

            # -----------------------------------------------------------------
            # 9. Final immutable bounds
            # -----------------------------------------------------------------

            risk = min(
                risk,
                configured_risk,
                remaining_heat,
            )

            risk = max(
                0.0,
                risk,
            )

            # Avoid floating-point garbage such as 3e-18.
            if risk < 0.0001:
                risk = 0.0

            reason = (
                "RISK_APPROVED"
                if risk > 0.0
                else "RISK_REDUCED_TO_ZERO"
            )

            self.last_snapshot = (
                RiskSizingSnapshot(
                    allowed=(
                        risk > 0.0
                    ),
                    configured_base_risk_pct=(
                        configured_risk
                    ),
                    final_risk_pct=(
                        risk
                    ),
                    open_portfolio_heat_pct=(
                        open_heat
                    ),
                    max_portfolio_heat_pct=(
                        max_heat
                    ),
                    remaining_portfolio_heat_pct=(
                        remaining_heat
                    ),
                    volatility_multiplier=(
                        volatility_multiplier
                    ),
                    spread_multiplier=(
                        spread_multiplier
                    ),
                    drawdown_multiplier=(
                        drawdown_multiplier
                    ),
                    edge_cap_pct=(
                        edge_cap_pct
                    ),
                    safety_reason=str(
                        safety_reason
                    ),
                    reason=reason,
                )
            )

            self.logger.info(
                (
                    "Risk approved | strategy=%s "
                    "base=%.4f%% final=%.4f%% "
                    "heat=%.4f/%.4f%% "
                    "vol=%.3f spread=%.3f dd=%.3f "
                    "edge_cap=%s"
                ),
                strategy_name,
                configured_risk,
                risk,
                open_heat,
                max_heat,
                volatility_multiplier,
                spread_multiplier,
                drawdown_multiplier,
                (
                    f"{edge_cap_pct:.4f}%"
                    if edge_cap_pct is not None
                    else "N/A"
                ),
            )

            return risk

        except Exception as exc:
            # Unknown sizing errors fail closed.
            self.logger.exception(
                "Unexpected risk sizing failure: %s",
                exc,
            )

            return self._reject(
                configured_risk=max(
                    0.0,
                    _finite_float(
                        base_risk,
                        0.0,
                    ),
                ),
                open_heat=max(
                    0.0,
                    _finite_float(
                        open_portfolio_heat_pct,
                        0.0,
                    ),
                ),
                max_heat=self._max_portfolio_heat(),
                safety_reason="RISK_ENGINE_EXCEPTION",
                reason="RISK_ENGINE_EXCEPTION",
            )

    # =========================================================================
    # PORTFOLIO HEAT
    # =========================================================================

    def _max_portfolio_heat(
        self,
    ) -> float:
        """
        Return exactly the configured portfolio-heat budget.

        No hidden 1.0–1.5 clamp.
        """

        value = _finite_float(
            settings_manager.get(
                "max_portfolio_heat",
                5.0,
            ),
            5.0,
        )

        return max(
            0.0,
            value,
        )

    # =========================================================================
    # VOLATILITY
    # =========================================================================

    @staticmethod
    def _volatility_multiplier(
        current_atr: float,
        median_atr: float,
    ) -> float:
        """
        Volatility cannot increase risk.

        If current ATR <= median:
            multiplier = 1

        If current ATR > median:
            multiplier = median / current
        """

        current_atr = max(
            0.0,
            _finite_float(
                current_atr,
                0.0,
            ),
        )

        median_atr = max(
            0.0,
            _finite_float(
                median_atr,
                0.0,
            ),
        )

        if (
            current_atr <= 0.0
            or median_atr <= 0.0
        ):
            return 1.0

        if current_atr <= median_atr:
            return 1.0

        ratio = (
            median_atr
            / current_atr
        )

        # Do not let one ATR spike silently turn a valid setup into
        # microscopic numerical risk; hard safety remains separate.
        return _clamp(
            ratio,
            0.25,
            1.0,
        )

    # =========================================================================
    # SPREAD
    # =========================================================================

    @staticmethod
    def _spread_multiplier(
        current_spread: float,
        max_spread: float,
    ) -> float:
        """
        Reduce size as spread consumes more of allowed spread budget.

        <= 50% max spread:
            1.00

        75%:
            0.75

        90%:
            ~0.45

        100%:
            0.25

        Spread above max is rejected before this function.
        """

        if max_spread <= 0.0:
            return 0.0

        ratio = _clamp(
            current_spread
            / max_spread,
            0.0,
            1.0,
        )

        if ratio <= 0.50:
            return 1.0

        # Linear interpolation:
        # ratio .50 -> 1.00
        # ratio 1.0 -> .25
        multiplier = (
            1.0
            - (
                (
                    ratio - 0.50
                )
                / 0.50
            )
            * 0.75
        )

        return _clamp(
            multiplier,
            0.25,
            1.0,
        )

    # =========================================================================
    # DRAWDOWN THROTTLE
    # =========================================================================

    def _drawdown_multiplier(
        self,
    ) -> float:
        """
        Reduce size as current realized loss approaches SafetyEngine's
        configured daily/weekly hard limits.

        SafetyEngine remains the hard veto authority.

        This function never compares currency directly with percentages.
        """

        try:
            # Future SafetyEngine replacement exposes this method.
            #
            # Use it when available.
            budget_method = getattr(
                self.safety_engine,
                "get_risk_budget_state",
                None,
            )

            if callable(
                budget_method
            ):
                state = (
                    budget_method()
                    or {}
                )

                daily_utilization = _clamp(
                    _finite_float(
                        state.get(
                            "daily_drawdown_utilization",
                            0.0,
                        )
                    ),
                    0.0,
                    1.0,
                )

                weekly_utilization = _clamp(
                    _finite_float(
                        state.get(
                            "weekly_drawdown_utilization",
                            0.0,
                        )
                    ),
                    0.0,
                    1.0,
                )

                utilization = max(
                    daily_utilization,
                    weekly_utilization,
                )

                return (
                    self._drawdown_utilization_to_multiplier(
                        utilization
                    )
                )

            # -----------------------------------------------------------------
            # Compatibility with current SafetyEngine.
            # -----------------------------------------------------------------

            stats = (
                self.safety_engine
                .get_stats()
            )

            if not isinstance(
                stats,
                dict,
            ):
                return 1.0

            balance = (
                self._get_reference_balance()
            )

            if balance <= 0.0:
                return 1.0

            daily_pnl = _finite_float(
                stats.get(
                    "daily_pnl",
                    0.0,
                )
            )

            weekly_pnl = _finite_float(
                stats.get(
                    "weekly_pnl",
                    0.0,
                )
            )

            daily_dd_pct = (
                max(
                    0.0,
                    -daily_pnl,
                )
                / balance
                * 100.0
            )

            weekly_dd_pct = (
                max(
                    0.0,
                    -weekly_pnl,
                )
                / balance
                * 100.0
            )

            daily_limit = max(
                0.0,
                _finite_float(
                    settings_manager.get(
                        "max_daily_drawdown_pct",
                        10.0,
                    ),
                    10.0,
                ),
            )

            weekly_limit = max(
                0.0,
                _finite_float(
                    settings_manager.get(
                        "max_weekly_drawdown_pct",
                        25.0,
                    ),
                    25.0,
                ),
            )

            # Current SafetyEngine doubles thresholds in paper mode.
            # Mirror it only for compatibility until SafetyEngine is replaced.
            if bool(
                settings_manager.get(
                    "paper_mode",
                    True,
                )
            ):
                daily_limit *= 2.0
                weekly_limit *= 2.0

            daily_utilization = (
                daily_dd_pct
                / daily_limit
                if daily_limit > 0.0
                else 0.0
            )

            weekly_utilization = (
                weekly_dd_pct
                / weekly_limit
                if weekly_limit > 0.0
                else 0.0
            )

            utilization = _clamp(
                max(
                    daily_utilization,
                    weekly_utilization,
                ),
                0.0,
                1.0,
            )

            return (
                self._drawdown_utilization_to_multiplier(
                    utilization
                )
            )

        except Exception as exc:
            # Drawdown analytics is a sizing modifier.
            # The hard safety check has already succeeded above.
            self.logger.warning(
                "Drawdown throttle unavailable: %s",
                exc,
            )

            return 1.0

    @staticmethod
    def _drawdown_utilization_to_multiplier(
        utilization: float,
    ) -> float:
        """
        utilization = fraction of hard SafetyEngine drawdown limit consumed.

        <25%:
            normal risk

        25–50%:
            75%

        50–75%:
            50%

        >=75%:
            25%
        """

        utilization = _clamp(
            utilization,
            0.0,
            1.0,
        )

        if utilization >= 0.75:
            return 0.25

        if utilization >= 0.50:
            return 0.50

        if utilization >= 0.25:
            return 0.75

        return 1.0

    def _get_reference_balance(
        self,
    ) -> float:
        """
        Obtain balance using the same unit as realized PnL.

        Paper:
            Config.INITIAL_BALANCE

        Live:
            MT5 account balance
        """

        is_paper = bool(
            settings_manager.get(
                "paper_mode",
                True,
            )
        )

        if is_paper:
            try:
                from configs.config import Config

                return max(
                    0.0,
                    _finite_float(
                        Config.INITIAL_BALANCE,
                        10000.0,
                    ),
                )

            except Exception:
                return 10000.0

        try:
            account = (
                mt5.account_info()
            )

            if account is None:
                return 0.0

            return max(
                0.0,
                _finite_float(
                    getattr(
                        account,
                        "balance",
                        0.0,
                    )
                ),
            )

        except Exception:
            return 0.0

    # =========================================================================
    # PERFORMANCE / EDGE
    # =========================================================================

    @staticmethod
    def _wilson_lower_bound(
        wins: int,
        total: int,
        z: float = 1.645,
    ) -> float:
        """
        Lower bound of win probability.

        z=1.645 ~= one-sided 95% confidence.
        """

        if (
            total <= 0
            or wins < 0
        ):
            return 0.0

        wins = min(
            wins,
            total,
        )

        p = (
            wins
            / total
        )

        z2 = (
            z * z
        )

        denominator = (
            1.0
            + z2 / total
        )

        center = (
            p
            + z2
            / (
                2.0
                * total
            )
        )

        margin = (
            z
            * math.sqrt(
                (
                    p
                    * (
                        1.0 - p
                    )
                    + z2
                    / (
                        4.0
                        * total
                    )
                )
                / total
            )
        )

        return _clamp(
            (
                center - margin
            )
            / denominator,
            0.0,
            1.0,
        )

    def _get_strategy_performance(
        self,
        strategy_name: str,
    ) -> StrategyPerformance:
        """
        Read actual CLOSED journal outcomes.

        No fabricated fallback performance.
        """

        try:
            from core.trade_journal import (
                JOURNAL_DB,
            )

        except Exception:
            return StrategyPerformance()

        if not os.path.exists(
            JOURNAL_DB
        ):
            return StrategyPerformance()

        strategy_name = str(
            strategy_name
            or "UNKNOWN"
        ).upper()

        connection = None

        try:
            connection = sqlite3.connect(
                JOURNAL_DB
            )

            cursor = (
                connection.cursor()
            )

            # Check schema first so migration/old DB cannot crash sizing.
            cursor.execute(
                "PRAGMA table_info(trades)"
            )

            columns = {
                str(row[1])
                for row
                in cursor.fetchall()
            }

            if (
                "pnl" not in columns
                or "strategy_name"
                not in columns
            ):
                return (
                    StrategyPerformance()
                )

            rr_column = (
                "rr_achieved"
                if "rr_achieved"
                in columns
                else None
            )

            if rr_column:
                query = """
                    SELECT pnl, rr_achieved
                    FROM trades
                    WHERE UPPER(strategy_name) = ?
                      AND pnl IS NOT NULL
                    ORDER BY id DESC
                    LIMIT ?
                """

            else:
                query = """
                    SELECT pnl, NULL
                    FROM trades
                    WHERE UPPER(strategy_name) = ?
                      AND pnl IS NOT NULL
                    ORDER BY id DESC
                    LIMIT ?
                """

            cursor.execute(
                query,
                (
                    strategy_name,
                    self.performance_lookback,
                ),
            )

            rows = (
                cursor.fetchall()
            )

        except Exception as exc:
            self.logger.warning(
                "Strategy performance query failed: %s",
                exc,
            )

            return StrategyPerformance()

        finally:
            if connection is not None:
                try:
                    connection.close()

                except Exception:
                    pass

        if not rows:
            return StrategyPerformance()

        wins = 0
        losses = 0

        win_rs = []
        loss_rs = []

        for pnl_raw, rr_raw in rows:
            pnl = _finite_float(
                pnl_raw,
                0.0,
            )

            rr = abs(
                _finite_float(
                    rr_raw,
                    0.0,
                )
            )

            if pnl > 0.0:
                wins += 1

                if rr > 0.0:
                    win_rs.append(
                        rr
                    )

            elif pnl < 0.0:
                losses += 1

                if rr > 0.0:
                    loss_rs.append(
                        rr
                    )

        total = (
            wins + losses
        )

        if total <= 0:
            return StrategyPerformance()

        win_rate = (
            wins
            / total
        )

        avg_win_r = (
            sum(win_rs)
            / len(win_rs)
            if win_rs
            else 0.0
        )

        avg_loss_r = (
            sum(loss_rs)
            / len(loss_rs)
            if loss_rs
            else 0.0
        )

        sample_ready = bool(
            total
            >= self.min_sample_size
            and len(win_rs) >= 5
            and len(loss_rs) >= 5
            and avg_win_r > 0.0
            and avg_loss_r > 0.0
        )

        return StrategyPerformance(
            wins=wins,
            losses=losses,
            total=total,
            win_rate=win_rate,
            avg_win_r=avg_win_r,
            avg_loss_r=avg_loss_r,
            sample_ready=sample_ready,
        )

    def _calculate_edge_cap_pct(
        self,
        performance: StrategyPerformance,
        confidence: float,
    ) -> float:
        """
        Conservative fractional-Kelly risk cap.

        Uses:
            Wilson LOWER win probability
            observed average win/loss R
            fractional Kelly
            optional model confidence reduction

        It never raises risk above configured base risk because caller uses min().
        """

        if not performance.sample_ready:
            return float(
                "inf"
            )

        p = (
            self._wilson_lower_bound(
                performance.wins,
                performance.total,
            )
        )

        avg_loss_r = max(
            1e-9,
            performance.avg_loss_r,
        )

        payoff_ratio = (
            performance.avg_win_r
            / avg_loss_r
        )

        if payoff_ratio <= 0.0:
            return 0.0

        q = (
            1.0 - p
        )

        raw_kelly_fraction = (
            p
            - q
            / payoff_ratio
        )

        if raw_kelly_fraction <= 0.0:
            return 0.0

        fractional_kelly = (
            raw_kelly_fraction
            * self.kelly_fraction
        )

        # Convert account fraction -> percentage points.
        #
        # 0.001 = 0.10%
        kelly_cap_pct = (
            fractional_kelly
            * 100.0
        )

        # Model probability can only REDUCE the statistically derived cap.
        confidence = _clamp(
            confidence,
            0.0,
            1.0,
        )

        minimum_confidence = _clamp(
            _finite_float(
                settings_manager.get(
                    "min_ai_confidence",
                    0.75,
                ),
                0.75,
            ),
            0.0,
            1.0,
        )

        if confidence < minimum_confidence:
            if minimum_confidence > 0.0:
                confidence_multiplier = (
                    confidence
                    / minimum_confidence
                )

            else:
                confidence_multiplier = 1.0

            kelly_cap_pct *= (
                _clamp(
                    confidence_multiplier,
                    0.25,
                    1.0,
                )
            )

        return max(
            0.0,
            kelly_cap_pct,
        )

    # =========================================================================
    # DIAGNOSTICS
    # =========================================================================

    def get_last_snapshot(
        self,
    ) -> RiskSizingSnapshot:
        return self.last_snapshot

    def get_last_snapshot_dict(
        self,
    ) -> dict:
        snapshot = (
            self.last_snapshot
        )

        return {
            "allowed": (
                snapshot.allowed
            ),
            "configured_base_risk_pct": (
                snapshot.configured_base_risk_pct
            ),
            "final_risk_pct": (
                snapshot.final_risk_pct
            ),
            "open_portfolio_heat_pct": (
                snapshot.open_portfolio_heat_pct
            ),
            "max_portfolio_heat_pct": (
                snapshot.max_portfolio_heat_pct
            ),
            "remaining_portfolio_heat_pct": (
                snapshot.remaining_portfolio_heat_pct
            ),
            "volatility_multiplier": (
                snapshot.volatility_multiplier
            ),
            "spread_multiplier": (
                snapshot.spread_multiplier
            ),
            "drawdown_multiplier": (
                snapshot.drawdown_multiplier
            ),
            "edge_cap_pct": (
                snapshot.edge_cap_pct
            ),
            "safety_reason": (
                snapshot.safety_reason
            ),
            "reason": (
                snapshot.reason
            ),
        }

    # =========================================================================
    # REJECTION
    # =========================================================================

    def _reject(
        self,
        configured_risk: float,
        open_heat: float,
        max_heat: float,
        safety_reason: str,
        reason: str,
        volatility_multiplier: float = 1.0,
        spread_multiplier: float = 1.0,
        drawdown_multiplier: float = 1.0,
        edge_cap_pct: Optional[float] = None,
    ) -> float:
        remaining = max(
            0.0,
            max_heat - open_heat,
        )

        self.last_snapshot = (
            RiskSizingSnapshot(
                allowed=False,
                configured_base_risk_pct=max(
                    0.0,
                    configured_risk,
                ),
                final_risk_pct=0.0,
                open_portfolio_heat_pct=max(
                    0.0,
                    open_heat,
                ),
                max_portfolio_heat_pct=max(
                    0.0,
                    max_heat,
                ),
                remaining_portfolio_heat_pct=(
                    remaining
                ),
                volatility_multiplier=(
                    volatility_multiplier
                ),
                spread_multiplier=(
                    spread_multiplier
                ),
                drawdown_multiplier=(
                    drawdown_multiplier
                ),
                edge_cap_pct=(
                    edge_cap_pct
                ),
                safety_reason=str(
                    safety_reason
                ),
                reason=str(
                    reason
                ),
            )
        )

        self.logger.warning(
            "Risk rejected: %s | safety=%s",
            reason,
            safety_reason,
        )

        return 0.0