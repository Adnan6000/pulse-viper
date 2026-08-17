# core/trade_brain.py
"""
Phase 9 v2: AI Brain Layer — Trade Decision Synthesizer (Corrected Architecture)
================================================================================
Fixes all 5 critical issues identified in architectural review:

  FIX 1 — Score normalization: 3-tier architecture with proper bounded normalization.
           Eliminates raw-sum overflow (old max was 140+).

  FIX 2 — Double-counting eliminated: HTF bias and Structure (MSS/Sweep) both
           encode direction. Now separated into:
           • Directional Tier (50%): HTF alignment only
           • Execution Tier (35%): Structure quality, FVG, VSA, Volume, Liquidity, AI
           • Risk Tier (15%): Regime quality modifier (inline, no penalty math)
           Each tier is bounded 0→its_weight, then summed for a clean 0–100.

  FIX 3 — CHAOTIC is ONE hard gate BEFORE scoring. No more dual mechanism
           (score cap + threshold 999). CHAOTIC hits an early return with
           brain_score=0, passed=False, before any scoring runs.

  FIX 4 — Clean directional hierarchy:
           1. Brain determines direction from Directional + Execution tiers
           2. Strategy (CRT/SMC) is just an execution quality check, not a blocker
           3. No mutual override loops — Brain DECIDES, strategy CONFIRMS quality

  FIX 5 — News lockout is a hard gate BEFORE scoring (same as CHAOTIC).
           Never softened to a -25 penalty. Phase 8 lockout logic is preserved.

Tier Architecture:
  ┌─────────────────────────────────────────────────────────────────┐
  │ TIER 1: DIRECTIONAL  (max 50 pts)                               │
  │   • HTF Alignment: D1(18) H4(14) H1(11) M15(5) M5(2) = 50 pts │
  │                                                                 │
  │ TIER 2: EXECUTION  (max 35 pts)                                 │
  │   • Structure (MSS + Sweep):  12 pts                            │
  │   • FVG Quality:               7 pts                            │
  │   • VSA Signal:               10 pts                            │
  │   • Volume Pressure:           4 pts                            │
  │   • AI Confidence:             8 pts                            │
  │   • Liquidity Pools:           4 pts  (total = 45, capped 35)   │
  │                                                                 │
  │ TIER 3: RISK QUALITY  (max 15 pts)                              │
  │   • Regime quality bonus: TRENDING=15, RANGE=8, COMPRESSION=0  │
  │   (Regime is positive-only quality score, not a penalty)        │
  └─────────────────────────────────────────────────────────────────┘

  brain_score = tier1 + tier2 + tier3  →  always in [0, 100]

Hard gates (checked BEFORE scoring — never probabilistic):
  • News lockout active  → immediate BLOCKED
  • Regime == CHAOTIC    → immediate BLOCKED
"""

from __future__ import annotations

import os
import json
import numpy as np
import pandas as pd
import logging
from typing import Optional, Dict, Tuple, Any, List, TYPE_CHECKING
from datetime import datetime, time, timezone

from core.market_regime_hmm import MarketRegimeHMM
from utils.order_flow_engine import OrderFlowEngine
from utils.settings_manager import settings_manager

if TYPE_CHECKING:
    from core.market_context import MarketContext
    from core.candidate_setup import CandidateSetup
    from core.candidate_prediction import CandidatePrediction

logger = logging.getLogger("PulseViper.TradeBrain")

DEFAULT_T1_WEIGHTS = {
    "d1": 18.0,
    "h4": 14.0,
    "h1": 11.0,
    "m15": 5.0,
    "m5": 2.0,
    "m1": 3.0        # Intraday execution timeframe — boosted dynamically when M1 diverges from HTF
}

DEFAULT_T2_WEIGHTS = {
    "structure": 10.0,
    "fvg": 5.0,
    "vsa": 4.0,
    "volume": 1.5,
    "liquidity": 1.5,
    "statistical_bounds": 5.0,
    "ai_confidence": 8.0
}

# ─────────────────────────────────────────────────────────────────────────────
#  Tier weight caps
# ─────────────────────────────────────────────────────────────────────────────
TIER1_MAX = 50.0   # Directional tier ceiling
TIER2_MAX = 35.0   # Execution tier ceiling
TIER3_MAX = 15.0   # Risk quality tier ceiling

# Adaptive threshold table — applied AFTER tier scoring
# CHAOTIC is never reached (hard-gated before scoring)
ADAPTIVE_THRESHOLDS = {
    "TRENDING":    34,   # High-probability trend continuation
    "RANGE":       38,   # Mean-reversion range setup threshold
    "COMPRESSION": 42,   # Compression breakout threshold
}
DEFAULT_THRESHOLD = 38

# Directional conviction gap per regime
# In range markets, HTF biases often conflict — use a lower gap so sweep direction can resolve it
RANGE_CONVICTION_GAP = 4.0    # used in RANGE / COMPRESSION
TREND_CONVICTION_GAP = 8.0    # used in TRENDING

# Regime quality bonuses for Tier 3 (positive-only — no penalties)
REGIME_QUALITY = {
    "TRENDING":     8.0,  # Strong directional market → full quality bonus
    "RANGE":        4.0,  # Ranging — moderate quality context
    "COMPRESSION":  0.0,  # Compression — no quality bonus (requires higher threshold too)
    "CHAOTIC":      0.0,  # Blocked before reaching this
}

# Hard-blocked regimes (evaluated BEFORE scoring starts)
HARD_BLOCKED_REGIMES = {"CHAOTIC"}

# VSA signal registry
VSA_BULLISH_SIGNALS = {
    "climactic_buy_exhaustion",
    "demand_absorption",
    "hidden_buying",
    "stopping_volume_up",
    "stopping_volume",
    "test_of_supply",
    "ultra_high_volume_bullish",
    "no_supply",
    "spring",
    "selling_climax",
}
VSA_BEARISH_SIGNALS = {
    "climactic_sell_exhaustion",
    "supply_absorption",
    "hidden_selling",
    "stopping_volume_down",
    "test_of_demand",
    "ultra_high_volume_bearish",
    "no_demand",
    "upthrust",
    "buying_climax",
}

# ─────────────────────────────────────────────────────────────────────────────
#  Penalties & Bonuses (centralized for tuning)
# ─────────────────────────────────────────────────────────────────────────────
PENALTIES_AND_BONUSES = {
    "KILLZONE_INACTIVE": -15.0,
    "SPREAD_STRICT": -15.0,
    "SPREAD_NORMAL": -5.0,
    "NEWS_SENTIMENT_VETO": -15.0,
    "AI_CONFIDENCE_LOW": -6.0,
    "PSYCHOLOGY_VETO": -7.0,
    "SETUP_VALIDATION_FAILED": -10.0,
    "GOLD_COMPRESSION": -15.0,
    "PD_EXTREME_TRAP": -15.0,
    "PD_PREMIUM_DISCOUNT_PENALTY": -6.0,
    "PD_OTE_BOOST": 4.0,
    "PD_STANDARD_BOOST": 1.5,
    "STRATEGY_CONFIRMATION": 2.0,
}

# Minimum directional advantage for direction commitment
DIRECTIONAL_CONVICTION_GAP = 8.0  # default for TRENDING markets

# ─────────────────────────────────────────────────────────────────────────────
#  Block reason constants
# ─────────────────────────────────────────────────────────────────────────────
BLOCK_REASON_NEWS = "NEWS_LOCKOUT"
BLOCK_REASON_CHAOTIC = "CHAOTIC_REGIME"
BLOCK_REASON_SCORE = "SCORE_BELOW_THRESHOLD"
BLOCK_REASON_CONFLICTED = "DIRECTIONAL_CONFLICT"
BLOCK_REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"


class BrainResult:
    """Structured result from TradeBrain.evaluate()"""
    __slots__ = (
        "brain_score", "brain_direction", "threshold", "reason_map",
        "passed", "regime", "block_reason",
        "tier1_score", "tier2_score", "tier3_score",
    )

    def __init__(
        self,
        brain_score: float,
        brain_direction: Optional[str],
        threshold: float,
        reason_map: Dict[str, Any],
        regime: str,
        block_reason: Optional[str] = None,
        tier1_score: float = 0.0,
        tier2_score: float = 0.0,
        tier3_score: float = 0.0,
    ):
        self.brain_score = brain_score
        self.brain_direction = brain_direction
        self.threshold = threshold
        self.reason_map = reason_map
        self.regime = regime
        self.block_reason = block_reason
        self.tier1_score = tier1_score
        self.tier2_score = tier2_score
        self.tier3_score = tier3_score
        
        self.passed = (brain_score >= threshold) and (brain_direction is not None) and (block_reason is None)
        if reason_map.get("exploration_override"):
            self.passed = True

    @property
    def is_chaotic(self) -> bool:
        return self.block_reason == BLOCK_REASON_CHAOTIC

    @property
    def is_news_blocked(self) -> bool:
        return self.block_reason == BLOCK_REASON_NEWS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brain_score": round(self.brain_score, 1),
            "brain_direction": self.brain_direction,
            "threshold": self.threshold,
            "reason_map": {
                k: (round(float(v), 2) if isinstance(v, (int, float, np.number)) and not isinstance(v, bool) else v)
                for k, v in self.reason_map.items()
            },
            "passed": self.passed,
            "regime": self.regime,
            "block_reason": self.block_reason,
            "tier1_score": round(self.tier1_score, 1),
            "tier2_score": round(self.tier2_score, 1),
            "tier3_score": round(self.tier3_score, 1),
        }

    def __repr__(self):
        return (
            f"BrainResult(score={self.brain_score:.1f}/{self.threshold} "
            f"dir={self.brain_direction} passed={self.passed} "
            f"regime={self.regime} block={self.block_reason})"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  TradeBrain v2
# ─────────────────────────────────────────────────────────────────────────────

class TradeBrain:
    """
    Master AI decision synthesizer (v2 — corrected architecture).

    3-tier normalized scoring:
      Tier 1 (Directional)  → 0–50 pts
      Tier 2 (Execution)    → 0–35 pts
      Tier 3 (Risk Quality) → 0–15 pts
      Total                 → 0–100 pts (always bounded)

    Hard gates evaluated BEFORE scoring:
      1. News lockout → BLOCKED immediately
      2. CHAOTIC regime → BLOCKED immediately

    Directional hierarchy:
      1. Brain determines direction from Tier 1 + Tier 2
      2. Strategy (CRT/SMC) provides execution quality signal only
      3. No circular overrides — Brain DECIDES, engine EXECUTES

    Usage:
        brain = TradeBrain()
        result = brain.evaluate(analysis, strategy_action="BUY", ai_confidence=0.7)
        if result.passed:
            # result.brain_direction is the trusted direction
            execute_trade(result.brain_direction)
    """

    def __init__(
        self,
        base_threshold: float = 55.0,
        order_flow_engine: Optional[OrderFlowEngine] = None,
        market_regime_hmm: Optional[MarketRegimeHMM] = None,
    ):
        self.base_threshold = base_threshold
        self.logger = logging.getLogger("PulseViper.TradeBrain")
        self._eval_count = 0

        # Dependency Injection
        self.of_engine = order_flow_engine or OrderFlowEngine()
        self.hmm_detector = market_regime_hmm or MarketRegimeHMM()

        self._load_calibrated_weights("RANGE")
        # Cache for CandlePsychology veto: only recompute when M1 candle changes
        self._psych_cache_key = None   # (candle_timestamp, brain_direction)
        self._psych_cache_result = (True, "No direction", 0.0)  # (allowed, reason, modifier)

    def _load_calibrated_weights(self, regime: str = "RANGE"):
        """Load calibrated weights from file for the active regime, otherwise use defaults."""
        r_key = "trending" if regime == "TRENDING" else "range"
        try:
            if os.path.exists("data/brain_weights.json"):
                with open("data/brain_weights.json", "r") as f:
                    data = json.load(f)
                    if r_key in data:
                        self.t1_weights = data[r_key].get("tier1", dict(DEFAULT_T1_WEIGHTS))
                        self.t2_weights = data[r_key].get("tier2", dict(DEFAULT_T2_WEIGHTS))
                        return
                    elif "tier1" in data:
                        # Fallback for flat structure
                        self.t1_weights = data.get("tier1", dict(DEFAULT_T1_WEIGHTS))
                        self.t2_weights = data.get("tier2", dict(DEFAULT_T2_WEIGHTS))
                        return
        except Exception as e:
            self.logger.warning(f"Error loading calibrated weights for {regime}: {e}")
        
        self.t1_weights = dict(DEFAULT_T1_WEIGHTS)
        self.t2_weights = dict(DEFAULT_T2_WEIGHTS)

    def _load_performance_matrix(self) -> Dict:
        """Loads the performance matrix JSON file if it exists."""
        matrix_path = "data/performance_matrix.json"
        if os.path.exists(matrix_path):
            try:
                with open(matrix_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading performance matrix: {e}")
        return {}

    def _get_strategy_routing_adjustment(
        self,
        strategy_name: str,
        mode: str,
        weekday: int,
        session: str,
        regime: str
    ) -> Tuple[float, str]:
        """
        Looks up strategy performance in the matrix and returns (score_adjustment, reason).
        """
        if not strategy_name:
            return 0.0, "No strategy specified"

        s_name_lower = strategy_name.lower()
        matrix = self._load_performance_matrix()
        if not matrix:
            return 0.0, "Performance Matrix not found, using defaults"

        # Try to look up specific conditions
        matrix_data = matrix.get("matrix", {})
        
        # Normalize session name: remove GOLD_ prefix
        sess = session.replace("GOLD_", "")
        
        # Check if nested keys exist
        stats = None
        try:
            stats_list = matrix_data.get(mode, {}).get(str(weekday), {}).get(sess, {}).get(regime, [])
            for item in stats_list:
                if item.get("strategy") == s_name_lower:
                    stats = item
                    break
        except Exception:
            pass

        # Fallback to general mode rankings if specific conditions not found
        source = "specific_combo"
        if not stats:
            fallbacks = matrix.get("fallback_rankings", {}).get(mode, [])
            for item in fallbacks:
                if item.get("strategy") == s_name_lower:
                    stats = item
                    source = "mode_fallback"
                    break

        if not stats:
            return 0.0, "No performance history for strategy"

        wr = stats.get("win_rate", 50.0)
        pf = stats.get("profit_factor", 1.0)
        trades = stats.get("total_trades", 0)

        # Scale boost/penalty based on performance
        if trades >= 3:
            if wr >= 60.0 and pf >= 1.5:
                # Strong performer!
                boost = 4.0 if source == "specific_combo" else 2.5
                return boost, f"Strong performer in {source} (WR={wr:.1f}%, PF={pf:.2f})"
            elif wr >= 50.0 and pf >= 1.1:
                # Moderately profitable
                boost = 2.0 if source == "specific_combo" else 1.0
                return boost, f"Profitable performer in {source} (WR={wr:.1f}%, PF={pf:.2f})"
            elif wr < 40.0 or pf < 0.9:
                # Poor performer, penalize!
                penalty = -4.0 if source == "specific_combo" else -2.5
                return penalty, f"Poor performer in {source} (WR={wr:.1f}%, PF={pf:.2f})"
        
        return 0.0, f"Insufficient trades ({trades}) in performance history"

    def enrich_smc_signals_with_order_flow(self, symbol: str, current_features: Dict) -> Dict:
        """
        Hooks directly into TradeBrain's evaluation framework to adjust scores 
        based on real footprint data.
        """
        try:
            from datetime import datetime, timezone, timedelta
            import pandas as pd
            
            # Analyze the last 15 minutes of transactional ticks dynamically
            now = datetime.now(timezone.utc)
            start_lookback = now - timedelta(minutes=15)
            
            footprint = self.of_engine.fetch_and_build_footprint(symbol, start_lookback, now)
            
            boost_adjustment = 0.0
            vsa_patterns = current_features.get("vsa_patterns", [])
            trigger = current_features.get("trigger")
            regime = current_features.get("regime")
            price = current_features.get("current_price", 0.0)
            
            # 1. Validate Bullish Institutional Imbalance Confluence
            if trigger == "BUY" or "SPRING" in vsa_patterns:
                # If aggressive stacked buy imbalances exist inside or near our structural support node
                if len(footprint["buy_imbalances"]) > 0:
                    # Active institutional confirmations found — scale score up
                    boost_adjustment += 7.5
                    self.logger.info(f"🔥 Institutional Order Flow Boost: Stacked Buy Imbalances found: {footprint['buy_imbalances']}")
                    
            # 2. Validate Bearish Institutional Imbalance Confluence
            elif trigger == "SELL" or "UPTHRUST" in vsa_patterns:
                if len(footprint["sell_imbalances"]) > 0:
                    boost_adjustment += 7.5
                    self.logger.info(f"🔥 Institutional Order Flow Boost: Stacked Sell Imbalances found: {footprint['sell_imbalances']}")

            # 3. Prevent Fading In Initiative Breakout Expansion Blocks
            if regime == "RANGE":
                # If massive passive institutional absorption walls are detected, mean reversion trades will fail
                passive_supply = footprint["absorption_detected"]["passive_supply_nodes"]
                if len(passive_supply) > 0 and price >= min(passive_supply):
                    boost_adjustment -= 15.0  # Heavily penalize buying into an institutional limit wall
                    self.logger.warning("⚠️ Order Flow Alert: Fading Buy signal due to Heavy Passive Institutional Supply Wall")
                
                passive_demand = footprint["absorption_detected"]["passive_demand_nodes"]
                if len(passive_demand) > 0 and price <= max(passive_demand):
                    boost_adjustment -= 15.0  # Heavily penalize selling into an institutional limit wall
                    self.logger.warning("⚠️ Order Flow Alert: Fading Sell signal due to Heavy Passive Institutional Demand Wall")

            return {
                "order_flow_boost": boost_adjustment,
                "poc_at_execution": footprint["poc_price"],
                "net_order_flow_delta": footprint["total_delta"]
            }
        except Exception as e:
            self.logger.warning(f"Error enriching SMC signals with order flow: {e}")
            return {
                "order_flow_boost": 0.0,
                "poc_at_execution": 0.0,
                "net_order_flow_delta": 0.0
            }

    def resolve_dynamic_regime_gating(self, df_m1_history: pd.DataFrame, symbol: str) -> str:
        """
        Ingests live M1 analytics data vectors, executes the HMM Viterbi step, 
        and instantly alters strategy configuration matrices.
        """
        try:
            # Slice the last 30 bars of emission context data to decode state transitions
            lookback_slice = df_m1_history.tail(30)
            
            if len(lookback_slice) < 5:
                return "RANGE" # Safe baseline default fallback
                
            # Compile 3D emission features: cvd_roc, imbalance_density, tick_frequency
            cvd_vector = self.of_engine.compute_cumulative_volume_delta_vectorized(lookback_slice, symbol)
            imbalance_density_vector = self.of_engine.compute_imbalance_density_vector(lookback_slice, symbol)
            
            # Compile into features DataFrame with forward-fill, back-fill, and 0.0 fallbacks to guarantee NaN safety
            hmm_features = pd.DataFrame({
                'cvd_roc': cvd_vector.pct_change(3),
                'imbalance_density': imbalance_density_vector,
                'tick_frequency': lookback_slice['volume']
            }).ffill().bfill().fillna(0.0).replace([np.inf, -np.inf], 0.0)
            
            state, posteriors = self.hmm_detector.decode_current_regime(hmm_features)
            state_probability = posteriors[state]
            
            # Hard gate boundary: require 75% transition probability confidence to shift execution states
            if state_probability >= 0.75:
                if state == 0:
                    self.logger.info(f"🔄 HMM Transition: Confirmed COMPRESSION State ({state_probability*100:.1f}%)")
                    return "RANGE"
                    
                elif state == 1:
                    self.logger.info(f"🚀 HMM Transition: Confirmed INITIATIVE TREND State ({state_probability*100:.1f}%)")
                    return "TRENDING"
                    
                elif state == 2:
                    self.logger.warning(f"⚠️ HMM Transition: Confirmed EXHAUSTION/CHAOS State ({state_probability*100:.1f}%)")
                    return "CHAOTIC"
                    
            # Fallback to current engine settings
            from utils.settings_manager import settings_manager
            return settings_manager.get("current_regime", "RANGE")
            
        except Exception as e:
            self.logger.warning(f"Error resolving dynamic regime gating via HMM: {e}")
            from utils.settings_manager import settings_manager
            return settings_manager.get("current_regime", "RANGE")

    # ──────────────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        analysis: Dict[str, Any],
        strategy_action: Optional[str] = None,
        ai_confidence: float = 0.5,
        session_score: float = 0.0,
        strategy_name: Optional[str] = None,
    ) -> BrainResult:
        """
        Evaluate market state and return a BrainResult with score and direction.

        Args:
            analysis:         Full analysis dict from run_multi_timeframe_analysis()
            strategy_action:  Directional signal from CRT/SMC strategy (advisory only)
            ai_confidence:    Pattern learner confidence [0.0, 1.0]
            session_score:    Session quality score from SessionEngine [0.0, 15.0]

        Returns:
            BrainResult — always populated, check .passed before executing
        """
        self._eval_count += 1
        regime = str(analysis.get("market_regime", "RANGE")).upper()
        symbol = str(analysis.get("symbol", ""))
        is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()

        from utils.settings_manager import settings_manager
        regime_filter = settings_manager.get("dynamic_regime_filter", True)

        # Override regime using HMM Viterbi step if enabled and M1 history is available
        df_ltf = analysis.get("df_ltf")
        if regime_filter and df_ltf is not None and len(df_ltf) >= 30:
            regime = self.resolve_dynamic_regime_gating(df_ltf, symbol).upper()
            analysis["market_regime"] = regime

        # Reload weights to pick up online calibration updates for active regime
        self._load_calibrated_weights(regime)

        # ── Day-of-Week modifier ──────────────────────────────────────────────
        # Market behaviour differs significantly by day: Friday sees position
        # squaring (both-way moves), Monday is cautious, midweek is cleanest.
        dow_threshold_delta, dow_conviction_delta = self._get_dow_modifier()
        
        from utils.settings_manager import settings_manager
        is_paper = settings_manager.get("paper_mode", True)
        regime_filter = settings_manager.get("dynamic_regime_filter", True)
        news_filter = settings_manager.get("news_filter_enabled", True)
        self_learning = settings_manager.get("self_learning_filter", True)

        strict_mode = settings_manager.get("strict_mode", True)

        # Apply Dynamic Regime Filter settings
        if regime_filter:
            threshold = ADAPTIVE_THRESHOLDS.get(regime, self.base_threshold)
            if is_gold:
                if regime == "RANGE":
                    threshold = max(threshold, 40.0)
                elif regime == "COMPRESSION":
                    threshold = max(threshold, 44.0)
        else:
            threshold = self.base_threshold

        # Apply day-of-week adjustment to threshold
        threshold = max(30.0, threshold + dow_threshold_delta)

        atr = analysis.get("features", {}).get("atr", 0.0)
        is_chaotic = (regime in HARD_BLOCKED_REGIMES)
        is_chaotic_blocked = is_chaotic and regime_filter
        chaotic_penalty = 0.0

        news_locked = analysis.get("news_locked", False) if news_filter else False
        is_news_blocked = news_locked and news_filter
        news_penalty = 0.0

        killzone_active = analysis.get("killzone_active", True)
        killzone_penalty = 0.0
        killzone_blocked = False
        if not killzone_active and not is_paper:
            if strict_mode:
                killzone_blocked = True
            else:
                killzone_penalty = PENALTIES_AND_BONUSES["KILLZONE_INACTIVE"]
            
        spread = analysis.get("features", {}).get("spread", 0.0)
        user_max_spread = settings_manager.get("max_spread_points", 300)
        
        # Dynamic pair spread adaptation: adopt pair profile & running spread on chart
        symbol_name = str(analysis.get("symbol", "")).upper()
        if "BTC" in symbol_name:
            max_spread = max(user_max_spread, 5000.0)
        elif "ETH" in symbol_name:
            max_spread = max(user_max_spread, 2500.0)
        elif any(idx in symbol_name for idx in ["US30", "NAS100", "SPX500", "GER30"]):
            max_spread = max(user_max_spread, 800.0)
        elif "XAU" in symbol_name or "GOLD" in symbol_name:
            max_spread = max(user_max_spread, 150.0)
        elif "XAG" in symbol_name or "SILVER" in symbol_name:
            max_spread = max(user_max_spread, 250.0)
        else:
            max_spread = user_max_spread

        spread_penalty = 0.0
        if spread > max_spread:
            if strict_mode:
                spread_penalty = PENALTIES_AND_BONUSES["SPREAD_STRICT"]
            else:
                spread_penalty = PENALTIES_AND_BONUSES["SPREAD_NORMAL"]
            
        from core.trade_pattern_memory import trade_pattern_memory
        pattern_modifier = trade_pattern_memory.get_modifier(analysis) if self_learning else 0.0

        # Adjust AI confidence input
        if not self_learning:
            ai_confidence = 0.5

        # ── TIER 1 & TIER 2 Evaluation ───────────────────────────────────────
        # TIER 1: DIRECTIONAL (max 50 pts)
        bull_t1, bear_t1, t1_map = self._score_tier1_directional(analysis)

        # TIER 2: EXECUTION QUALITY (max 35 pts)
        bull_t2, bear_t2, t2_map = self._score_tier2_execution(analysis, ai_confidence)

        # ── Extract Directional Bias First (Preserves Telemetry) ──────────────
        bull_raw = bull_t1 + bull_t2
        bear_raw = bear_t1 + bear_t2

        # In range/compression markets, use a smaller conviction gap so sweep direction can resolve ties
        is_range_or_compression = regime in ("RANGE", "COMPRESSION")
        conviction_gap = RANGE_CONVICTION_GAP if is_range_or_compression else TREND_CONVICTION_GAP

        # Apply day-of-week adjustment to conviction gap (e.g. Friday = more flexible)
        conviction_gap = max(1.0, conviction_gap + dow_conviction_delta)

        if bull_raw > bear_raw + conviction_gap:
            brain_direction = "BUY"
        elif bear_raw > bull_raw + conviction_gap:
            brain_direction = "SELL"
        else:
            brain_direction = None
            # Range tiebreaker: use M15 sweep or M5 MSS signal to break the tie
            if is_range_or_compression:
                m15_sweep = int(analysis.get("m15_sweep_type", 0))
                m5_mss    = int(analysis.get("m5_mss_signal",  0))
                # If both sweep and MSS agree, pick that direction
                if m15_sweep == 1 and m5_mss == 1:
                    brain_direction = "BUY"
                elif m15_sweep == -1 and m5_mss == -1:
                    brain_direction = "SELL"
                # If only one signal present AND it doesn't contradict the other, allow it
                elif m15_sweep == 1 and m5_mss != -1:
                    brain_direction = "BUY"
                elif m15_sweep == -1 and m5_mss != 1:
                    brain_direction = "SELL"
                elif m5_mss == 1 and m15_sweep != -1:
                    brain_direction = "BUY"
                elif m5_mss == -1 and m15_sweep != 1:
                    brain_direction = "SELL"

        # ── M1 Intraday Shift Override ────────────────────────────────────────
        # In non-TRENDING markets, if M1 has a strong directional momentum that
        # conflicts with the current brain_direction, override it.
        # This prevents the system from blindly continuing to SELL when M1 has
        # clearly broken bullish structure on the execution timeframe.
        m1_shift = self._compute_m1_intraday_shift(analysis.get("df_ltf"))
        if m1_shift != 0 and not (regime == "TRENDING"):
            m1_shift_dir = "BUY" if m1_shift == 1 else "SELL"
            if brain_direction != m1_shift_dir:
                # Only override if M1 shift is clean and contradicts current direction
                m5_mss  = int(analysis.get("m5_mss_signal",  0))
                m15_swp = int(analysis.get("m15_sweep_type", 0))
                # Require at least one LTF confirmation (MSS or sweep in same direction)
                m1_confirms = (
                    (m1_shift == 1 and (m5_mss == 1 or m15_swp == 1)) or
                    (m1_shift == -1 and (m5_mss == -1 or m15_swp == -1))
                )
                if m1_confirms:
                    old_dir = brain_direction
                    brain_direction = m1_shift_dir
                    self.logger.info(
                        f"[M1_SHIFT_OVERRIDE] M1 intraday shift={m1_shift_dir} overrides "
                        f"brain_direction={old_dir} (regime={regime}, MSS={m5_mss}, SWP={m15_swp})"
                    )
                    analysis["m1_shift_override"] = True

        # Check for directional conflict (equal count of opposing timeframes)
        d1  = int(analysis.get("d1_bias",  0))
        h4  = int(analysis.get("h4_bias",  0))
        h1  = int(analysis.get("h1_bias",  0))
        m15 = int(analysis.get("m15_bias", 0))
        m5  = int(analysis.get("m5_bias",  0))
        biases = [d1, h4, h1, m15, m5]
        bull_count = sum(1 for x in biases if x > 0)
        bear_count = sum(1 for x in biases if x < 0)

        # Exact balance of opposing timeframes = conflict (only in TRENDING mode)
        # In RANGE mode, the sweep/MSS tiebreaker and M1 shift already resolved ambiguity
        if bull_count > 0 and bear_count > 0 and bull_count == bear_count and not is_range_or_compression:
            # Don't override M1 shift-resolved direction in non-trending markets
            if not analysis.get("m1_shift_override", False):
                brain_direction = None

        # Determine Tier 1 and Tier 2 scores based on direction
        if brain_direction == "BUY":
            t1_score = float(np.clip(bull_t1, 0, TIER1_MAX))
            t2_score = float(np.clip(bull_t2, 0, TIER2_MAX))
        elif brain_direction == "SELL":
            t1_score = float(np.clip(bear_t1, 0, TIER1_MAX))
            t2_score = float(np.clip(bear_t2, 0, TIER2_MAX))
        else:
            t1_score = float(np.clip(max(bull_t1, bear_t1), 0, TIER1_MAX))
            t2_score = float(np.clip(max(bull_t2, bear_t2), 0, TIER2_MAX))

        # TIER 3: RISK QUALITY (max 15 pts)
        news_sentiment = analysis.get("news_sentiment", 0.0) if news_filter else 0.0
        t3_score, t3_map = self._score_tier3_risk(regime, session_score, news_sentiment, brain_direction or "BUY")

        # Build unified reason_map for telemetry/audit
        reason_map: Dict[str, Any] = {}
        reason_map.update(t1_map)
        reason_map.update(t2_map)
        reason_map.update(t3_map)
        reason_map["_tier1"] = t1_score
        reason_map["_tier2"] = t2_score
        reason_map["_tier3"] = t3_score

        # ── HARD BLOCK GATES (Evaluate early return) ──────────────────────────
        # 1. Chaotic Block
        if is_chaotic_blocked:
            return BrainResult(
                brain_score=0.0,
                brain_direction=None,
                threshold=threshold,
                reason_map=reason_map,
                regime=regime,
                block_reason=BLOCK_REASON_CHAOTIC,
                tier1_score=t1_score,
                tier2_score=t2_score,
                tier3_score=t3_score
            )

        # 2. News Lockout Block
        if is_news_blocked:
            return BrainResult(
                brain_score=0.0,
                brain_direction=None,
                threshold=threshold,
                reason_map=reason_map,
                regime=regime,
                block_reason=BLOCK_REASON_NEWS,
                tier1_score=t1_score,
                tier2_score=t2_score,
                tier3_score=t3_score
            )

        # 3. Killzone Session Inactive Block
        if killzone_blocked:
            return BrainResult(
                brain_score=0.0,
                brain_direction=brain_direction,
                threshold=threshold,
                reason_map=reason_map,
                regime=regime,
                block_reason="KILLZONE_INACTIVE",
                tier1_score=t1_score,
                tier2_score=t2_score,
                tier3_score=t3_score
            )

        # 4. News Sentiment Trend Conflict Veto
        news_sentiment_penalty = 0.0
        if news_filter and brain_direction is not None:
            if (brain_direction == "BUY" and news_sentiment < -0.4) or (brain_direction == "SELL" and news_sentiment > 0.4):
                if settings_manager.get("strict_news_veto", False):
                    return BrainResult(
                        brain_score=0.0,
                        brain_direction=brain_direction,
                        threshold=threshold,
                        reason_map=reason_map,
                        regime=regime,
                        block_reason="NEWS_SENTIMENT_VETO",
                        tier1_score=t1_score,
                        tier2_score=t2_score,
                        tier3_score=t3_score
                    )
                else:
                    news_sentiment_penalty = PENALTIES_AND_BONUSES["NEWS_SENTIMENT_VETO"]

        # 5. AI Confidence Hard Veto
        ai_confidence_penalty = 0.0
        ai_soft_scaling = 1.0
        session_name = str(analysis.get("session_name", "")).upper()
        is_gold = "XAU" in str(analysis.get("symbol", "")).upper() or "GOLD" in str(analysis.get("symbol", "")).upper()
        
        # Determine dynamic AI confidence threshold
        min_ai_conf = settings_manager.get("min_ai_confidence", 0.20)
            
        ai_conf_penalty = 0.0
        if self_learning and not is_paper and ai_confidence < min_ai_conf:
            if ai_confidence < 0.42:
                return BrainResult(
                    brain_score=0.0,
                    brain_direction=None,
                    threshold=threshold,
                    reason_map=reason_map,
                    regime=regime,
                    block_reason="AI_CONFIDENCE_VETO",
                    tier1_score=t1_score,
                    tier2_score=t2_score,
                    tier3_score=t3_score
                )
            else:
                ai_conf_penalty = PENALTIES_AND_BONUSES["AI_CONFIDENCE_LOW"]
                t3_map["ai_conf_penalty"] = ai_conf_penalty

        # ── Candlestick Psychology & Rejection Wick Gate ──────────────────────
        from utils.candle_psychology import CandlePsychologyAnalyzer
        df_m1 = analysis.get("df_ltf")
        df_m5 = analysis.get("df_m5")
        df_m15 = analysis.get("df_m15")
        atr_m1 = float(analysis.get("atr", 1.0))
        atr_m5 = 1.0
        if df_m5 is not None and "atr" in df_m5.columns and len(df_m5) > 0:
            atr_m5 = float(df_m5.iloc[-1]["atr"])
            
        atr_m15 = float(analysis.get("m15_atr", 1.0))
            
        psych_allowed = True
        psych_reason = "No direction"
        psych_modifier = 0.0
        
        if brain_direction is not None:
            # Cache key: only recompute when the last M1 candle timestamp or direction changes
            m1_ts = None
            if df_m1 is not None and len(df_m1) >= 2:
                try:
                    m1_ts = df_m1.index[-2]  # Last CLOSED candle timestamp
                except Exception:
                    pass
            psych_cache_key = (m1_ts, brain_direction)
            if psych_cache_key != self._psych_cache_key:
                # Recompute psychology veto for this new candle/direction
                self._psych_cache_result = CandlePsychologyAnalyzer.evaluate_psychology_veto(
                    df_m1=df_m1 if df_m1 is not None else pd.DataFrame(),
                    df_m5=df_m5 if df_m5 is not None else pd.DataFrame(),
                    action=brain_direction or "BUY",
                    atr_m1=atr_m1,
                    atr_m5=atr_m5,
                    strict_mode=strict_mode,
                    df_m15=df_m15 if df_m15 is not None else pd.DataFrame(),
                    atr_m15=atr_m15
                )
                self._psych_cache_key = psych_cache_key
            psych_allowed, psych_reason, psych_modifier = self._psych_cache_result
            
        if not psych_allowed:
            # Make psychology penalty very lenient
            psych_modifier = PENALTIES_AND_BONUSES["PSYCHOLOGY_VETO"]

        # ── AI Disaster Veto Check (Disabled for more trades) ─────────
        ai_veto = False
        ai_disaster_penalty = 0.0
        if ai_veto and not is_paper:
            ai_disaster_penalty = -3.0

        # ── Setup Validation Gate (Clamped dynamically by Genetic Evolver) ───
        from utils.settings_manager import settings_manager
        setup_gate = settings_manager.get("setup_validation_gate", 8.0)
        
        # In paper mode, lower thresholds to encourage AI exploration and learning
        if is_paper and settings_manager.get("self_learning_filter", True):
            setup_gate = min(3.0, setup_gate)
            threshold = min(30.0, threshold)
        # In RANGE/COMPRESSION mode, lower setup gate — range setups naturally have lower T2
        elif is_range_or_compression:
            setup_gate = min(5.0, setup_gate)  # range setups don't have strong HTF structure
        setup_passed = t2_score >= setup_gate
        setup_penalty = 0.0
        if not setup_passed:
            setup_penalty = PENALTIES_AND_BONUSES["SETUP_VALIDATION_FAILED"]
            t3_map["setup_penalty"] = setup_penalty

        # Apply Regime Multiplier to directional/execution score
        # NOTE: If an M1 intraday shift override is active, skip the counter-trend penalty.
        # The override already required LTF structure confirmation (MSS or sweep), so punishing
        # it as a random counter-trend trade would incorrectly negate the M1 signal.
        regime_multiplier = 1.0
        htf_bias = int(analysis.get("htf_bias", 0))
        m1_shift_override_active = analysis.get("m1_shift_override", False)
        if regime == "TRENDING" and brain_direction is not None and not m1_shift_override_active:
            if (brain_direction == "BUY" and htf_bias == -1) or (brain_direction == "SELL" and htf_bias == 1):
                regime_multiplier = 0.5  # softened from 0.2 → 0.5 (still penalised, but not crushed)

        # ── Institutional Premium/Discount pricing modifier ─────────────────
        pd_modifier = 0.0
        pd_label = "NEUTRAL"
        df_h1 = analysis.get("df_h1")
        price = float(analysis.get("price", 0.0))
        
        if df_h1 is not None and len(df_h1) > 0 and brain_direction is not None:
            last_row = df_h1.iloc[-1]
            htf_support = float(last_row.get("support", np.nan))
            htf_resistance = float(last_row.get("resistance", np.nan))
            
            if not np.isnan(htf_support) and not np.isnan(htf_resistance):
                rng = htf_resistance - htf_support
                if rng > 0.0:
                    retracement = (price - htf_support) / rng
                    
                    if brain_direction == "BUY":
                        # Buy in Discount (retracement < 0.5) is premium logic
                        if retracement <= 0.5:
                            pd_label = "DISCOUNT"
                            # Optimal Trade Entry (OTE) zone: 61.8% to 78.6% retracement (0.214 to 0.382)
                            if 0.214 <= retracement <= 0.382:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_OTE_BOOST"]
                                pd_label = "OTE_DISCOUNT"
                            else:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_STANDARD_BOOST"]
                        else:
                            pd_label = "PREMIUM"
                            # Buying in Premium is expensive
                            if retracement >= 0.85:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_EXTREME_TRAP"]
                                pd_label = "EXTREME_PREMIUM_TRAP"
                            else:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_PREMIUM_DISCOUNT_PENALTY"]
                                
                    elif brain_direction == "SELL":
                        # Sell in Premium (retracement > 0.5) is premium logic
                        if retracement >= 0.5:
                            pd_label = "PREMIUM"
                            # Optimal Trade Entry (OTE) zone: 61.8% to 78.6% retracement (0.618 to 0.786)
                            if 0.618 <= retracement <= 0.786:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_OTE_BOOST"]
                                pd_label = "OTE_PREMIUM"
                            else:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_STANDARD_BOOST"]
                        else:
                            pd_label = "DISCOUNT"
                            # Selling in Discount is cheap
                            if retracement <= 0.15:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_EXTREME_TRAP"]
                                pd_label = "EXTREME_DISCOUNT_TRAP"
                            else:
                                pd_modifier = PENALTIES_AND_BONUSES["PD_PREMIUM_DISCOUNT_PENALTY"]
                                
        analysis['pd_zone'] = pd_label
        t2_score = float(np.clip(t2_score + pd_modifier, 0.0, TIER2_MAX))
        t2_map["pd_modifier"] = pd_modifier

        # ── Final Multiplicative Assembly for Valid Setups ───────────────────
        raw_score = (t1_score + t2_score) * regime_multiplier
        if raw_score > 0:
            raw_score += t3_score
            
            # Strategy confirmation and Adaptive Routing
            strategy_quality_boost = 0.0
            routing_reason = "Default boost"
            if strategy_action is not None and brain_direction is not None:
                if strategy_action == brain_direction:
                    strategy_quality_boost = PENALTIES_AND_BONUSES["STRATEGY_CONFIRMATION"]
                    if strategy_name:
                        from datetime import datetime, timezone
                        mode = settings_manager.get("trading_mode", "intraday").lower()
                        weekday = datetime.now(timezone.utc).weekday()
                        session = analysis.get("session_name", "")
                        regime = analysis.get("market_regime", "RANGE")
                        
                        adj, reason = self._get_strategy_routing_adjustment(
                            strategy_name=strategy_name,
                            mode=mode,
                            weekday=weekday,
                            session=session,
                            regime=regime
                        )
                        strategy_quality_boost += adj
                        routing_reason = reason
            t2_map["strategy_confirm"] = strategy_quality_boost
            reason_map["routing_reason"] = routing_reason
            raw_score += strategy_quality_boost
        else:
            t2_map["strategy_confirm"] = 0.0

        # Gold Compression Penalty
        gold_compression_penalty = 0.0
        if is_gold and regime == "COMPRESSION":
            swept_pools = analysis.get("swept_pools", []) or []
            m15_sweep = int(analysis.get("m15_sweep_type", 0))
            has_sweep = (len(swept_pools) > 0) or (m15_sweep != 0)
            ofi = float(analysis.get("ofi_imbalance", 0.0))
            if not (has_sweep and abs(ofi) >= 0.20):
                gold_compression_penalty = PENALTIES_AND_BONUSES["GOLD_COMPRESSION"]

        # ── Order Flow Footprint Confirmation ─────────────────────────────
        of_boost = 0.0
        try:
            of_res = self.enrich_smc_signals_with_order_flow(symbol, {
                "trigger": brain_direction,
                "current_price": price,
                "regime": regime,
                "vsa_patterns": analysis.get("features", {}).get("vsa_signals", [])
            })
            of_boost = of_res.get("order_flow_boost", 0.0)
            analysis.update({
                "order_flow_poc": of_res.get("poc_at_execution", 0.0),
                "order_flow_delta": of_res.get("net_order_flow_delta", 0.0),
                "order_flow_boost": of_boost
            })
        except Exception as of_err:
            self.logger.warning(f"Failed to calculate order flow footprints: {of_err}")

        # ── Final Score Calculation ─────────────────────────────────────────
        penalties_map = {
            "chaotic_penalty": chaotic_penalty,
            "news_penalty": news_penalty,
            "killzone_penalty": killzone_penalty,
            "spread_penalty": spread_penalty,
            "pattern_modifier": pattern_modifier,
            "setup_penalty": setup_penalty,
            "news_sentiment_penalty": news_sentiment_penalty,
            "ai_confidence_penalty": ai_confidence_penalty,
            "ai_disaster_penalty": ai_disaster_penalty,
            "candle_psychology_modifier": psych_modifier,
            "gold_compression_penalty": gold_compression_penalty,
            "order_flow_boost": of_boost
        }
        
        brain_score, penalty_telemetry = self._calculate_final_score(raw_score, penalties_map, ai_soft_scaling)
        t3_map.update(penalty_telemetry)

        # Re-build final reason_map for the returned score
        reason_map: Dict[str, Any] = {}
        reason_map.update(t1_map)
        reason_map.update(t2_map)
        reason_map.update(t3_map)
        reason_map["_tier1"] = t1_score
        reason_map["_tier2"] = t2_score
        reason_map["_tier3"] = t3_score

        # ── Apply Gates ──────────────────────────────────────────────────────
        block_reason = None
        from utils.settings_manager import settings_manager
        minor_setups_enabled = settings_manager.get("minor_setups_enabled", True)
        minor_threshold = settings_manager.get("minor_threshold", 40.0)

        # Check Session Velocity Time-Gate
        if brain_direction in ["BUY", "SELL"]:
            symbol = str(analysis.get("symbol", ""))
            is_velocity_ok, velocity_reason = self.is_market_velocity_favorable(symbol)
            if not is_velocity_ok:
                self.logger.warning(f"🚫 [VELOCITY_GATE] Blocked {brain_direction} setup on {symbol}: Fails velocity time-gate with reason {velocity_reason}")
                block_reason = velocity_reason
                brain_score = 0.0
                brain_direction = None

        # Check HTF / LTF Level Gating
        if brain_direction in ["BUY", "SELL"]:
            df_h1 = analysis.get("df_h1")
            df_h4 = analysis.get("df_h4")
            df_m15 = analysis.get("df_m15")
            df_m5 = analysis.get("df_m5")
            price = float(analysis.get("price", 0.0))
            atr = float(analysis.get("atr", 1.0))
            symbol = str(analysis.get("symbol", ""))
            
            from utils.settings_manager import settings_manager
            mode = str(settings_manager.get("trading_mode", "scalping")).lower()
            is_scalping = (mode == "scalping")

            is_near_htf, htf_level_reason = self._is_price_near_htf_levels(
                price, atr, df_h1, df_h4, df_m15=df_m15, df_m5=df_m5, is_scalping=is_scalping, analysis=analysis
            )
            if not is_near_htf:
                self.logger.warning(f"🚫 [HTF_LEVEL_GATE] Blocked {brain_direction} setup on {symbol}: Price {price:.2f} is not near structural level. ATR={atr:.2f}")
                block_reason = "NO_HTF_LEVEL"
                brain_score = 0.0
                brain_direction = None
            else:
                reason_map["htf_level_confluence"] = htf_level_reason

        if brain_direction is None:
            if block_reason is None:
                block_reason = BLOCK_REASON_CONFLICTED
        elif brain_score < threshold:
            if minor_setups_enabled and brain_score >= minor_threshold:
                reason_map["is_minor_setup"] = True
            else:
                block_reason = BLOCK_REASON_SCORE

        # ── Exploration Mode (Paper Only) ────────────────────────────────────
        # Allow a small fraction of near-threshold setups to execute for data gathering.
        # Max 5% chance, only within 5 pts of threshold (was 15 pts / 93% — caused trade floods).
        if block_reason == BLOCK_REASON_SCORE and is_paper:
            deficit = threshold - brain_score
            if deficit <= 5.0:
                import random
                prob = max(0.01, 0.05 * (1.0 - deficit / 5.0))
                if random.random() < prob:
                    block_reason = None
                    reason_map["exploration_override"] = True

        # ── Throttled logging ──────────────────────────────────────────────────
        if self._eval_count % 3 == 0:
            self._log(brain_score, brain_direction, regime, threshold, reason_map, block_reason)

        return BrainResult(
            brain_score=brain_score,
            brain_direction=brain_direction,
            threshold=threshold,
            reason_map=reason_map,
            regime=regime,
            block_reason=block_reason,
            tier1_score=t1_score,
            tier2_score=t2_score,
            tier3_score=t3_score,
        )



    # ──────────────────────────────────────────────────────────────────────────
    #  Tier 1: Directional (HTF bias only, max 50 pts)
    # ──────────────────────────────────────────────────────────────────────────

    def _score_tier1_directional(
        self, analysis: Dict
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        HTF direction encoding using self.t1_weights, with adaptive M1 intraday shift awareness.

        When M1 strongly diverges from D1+H4 (HTF), we:
          - Boost M1 weight (3 → 10 pts) to allow LTF shift to compete
          - Soften D1/H4 weights by 25% to reduce HTF lock-in
        This prevents the system from blindly selling into a bullish M1 reversal.
        """
        d1  = int(analysis.get("d1_bias",  0))
        h4  = int(analysis.get("h4_bias",  0))
        h1  = int(analysis.get("h1_bias",  0))
        m15 = int(analysis.get("m15_bias", 0))
        m5  = int(analysis.get("m5_bias",  0))
        m1  = int(analysis.get("m1_bias",  0))

        # Detect intraday shift: M1 strongly opposes the combined HTF signal
        htf_combined = d1 + h4  # D1+H4 is the primary HTF anchor
        m1_shift = self._compute_m1_intraday_shift(analysis.get("df_ltf"))

        w_d1  = self.t1_weights.get("d1",  18.0)
        w_h4  = self.t1_weights.get("h4",  14.0)
        w_h1  = self.t1_weights.get("h1",  11.0)
        w_m15 = self.t1_weights.get("m15",  5.0)
        w_m5  = self.t1_weights.get("m5",   2.0)
        w_m1  = self.t1_weights.get("m1",   3.0)

        # ── Mode & Regime-specific Weight Redistribution ────────────────────────
        from utils.settings_manager import settings_manager
        trading_mode = str(settings_manager.get("trading_mode", "scalping")).lower()

        if trading_mode == "scalping":
            # In scalping mode, LTF (M1, M5, M15) carries 70%+ of total directional weight
            w_m1  = 18.0
            w_m5  = 14.0
            w_m15 = 10.0
            w_h1  = 5.0
            w_h4  = 4.0
            w_d1  = 2.0
        elif trading_mode == "swing":
            w_d1  = 20.0
            w_h4  = 16.0
            w_h1  = 10.0
            w_m15 = 4.0
            w_m5  = 2.0
            w_m1  = 1.0
        else: # Intraday mode
            w_d1  = 14.0
            w_h4  = 12.0
            w_h1  = 10.0
            w_m15 = 8.0
            w_m5  = 5.0
            w_m1  = 4.0

        # In range or compression regimes, scale down HTF weights further
        regime = str(analysis.get("market_regime", "RANGE")).upper()
        if regime in ("RANGE", "COMPRESSION") and trading_mode != "scalping":
            w_d1  = 5.4   # reduced by 70%
            w_h4  = 4.2   # reduced by 70%
            w_h1  = 3.3   # reduced by 70%
            w_m15 = 17.0  # redistributed +12.0
            w_m5  = 10.0  # redistributed +8.0
            w_m1  = 13.1  # redistributed +10.1 (total sum is still 53.0)

        # Dynamic M1 weight boost: when M1 shift disagrees with HTF anchor
        htf_disagrees_with_m1 = (
            (htf_combined > 0 and m1_shift == -1) or
            (htf_combined < 0 and m1_shift == 1)
        )
        if htf_disagrees_with_m1:
            # M1 is showing a reversal vs HTF — boost M1 weight significantly
            # and soften the HTF lock-in by 80% (increased from 25%) to allow the
            # reversal trade to achieve a high enough score to pass the threshold check.
            w_m1  = 15.0 if regime in ("RANGE", "COMPRESSION") else 10.0
            w_d1  = w_d1  * 0.20
            w_h4  = w_h4  * 0.20
            w_h1  = w_h1  * 0.20

        tf_weights = [
            ("d1",  d1,  w_d1),
            ("h4",  h4,  w_h4),
            ("h1",  h1,  w_h1),
            ("m15", m15, w_m15),
            ("m5",  m5,  w_m5),
            ("m1",  m1,  w_m1),
        ]

        bull = bear = 0.0
        component_map: Dict[str, float] = {}

        for name, bias, w in tf_weights:
            if bias == 1:
                bull += w
                component_map[f"t1_{name}"] = w
            elif bias == -1:
                bear += w
                component_map[f"t1_{name}"] = -w
            else:
                component_map[f"t1_{name}"] = 0.0

        component_map["t1_m1_shift"] = float(m1_shift)
        component_map["t1_htf_m1_divergence"] = 1.0 if htf_disagrees_with_m1 else 0.0

        bull = min(bull, TIER1_MAX)
        bear = min(bear, TIER1_MAX)

        return bull, bear, component_map

    # ──────────────────────────────────────────────────────────────────────────
    #  Tier 2: Execution Quality (max 35 pts)
    # ──────────────────────────────────────────────────────────────────────────

    def _score_tier2_execution(
        self, analysis: Dict, ai_confidence: float
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Ensemble execution quality scoring matrix (Max 35 points):
        1. Pure SMC Verification (MSS, FVG, Sweeps) -> Max 15 pts (Tuned via structure & fvg weights)
        2. Volume & Order Flow (VSA, POC, RVOL, Liquidity) -> Max 7 pts (Tuned via vsa, volume, liquidity weights)
        3. Statistical Deviation (Linear Regression Z-score) -> Max 5 pts (Tuned via statistical_bounds weight)
        4. AI Pattern-Learner Classifier Probability -> Max 8 pts (Tuned via ai_confidence weight)
        """
        # AI Pattern Learner Disaster Veto Gate
        from utils.settings_manager import settings_manager
        strict_mode = settings_manager.get("strict_mode", True)
        self_learning = settings_manager.get("self_learning_filter", True)
        
        # Soft check: if ai_confidence is extremely low (< 0.35), we flag it
        # but let other SMC and Volume components calculate normally.
        if self_learning and strict_mode and ai_confidence < 0.35:
            analysis["veto_low_confidence"] = True

        w_structure = self.t2_weights.get("structure", 10.0)
        w_fvg = self.t2_weights.get("fvg", 5.0)
        w_vsa = self.t2_weights.get("vsa", 4.0)
        w_volume = self.t2_weights.get("volume", 1.5)
        w_liquidity = self.t2_weights.get("liquidity", 1.5)
        w_stats = self.t2_weights.get("statistical_bounds", 5.0)
        w_ai = self.t2_weights.get("ai_confidence", 8.0)

        # --- 1. Pure SMC Verification (Max 15 pts) ---
        bull_struct, bear_struct = self._score_structure(analysis)
        bull_struct = (bull_struct / 12.0) * w_structure
        bear_struct = (bear_struct / 12.0) * w_structure

        bull_fvg, bear_fvg = self._score_fvg(analysis)
        bull_fvg = (bull_fvg / 7.0) * w_fvg
        bear_fvg = (bear_fvg / 7.0) * w_fvg

        smc_bull = float(np.clip(bull_struct + bull_fvg, 0.0, 15.0))
        smc_bear = float(np.clip(bear_struct + bear_fvg, 0.0, 15.0))

        # --- 2. Volume & Order Flow (Max 7 pts) ---
        bull_vsa, bear_vsa = self._score_vsa(analysis)
        vsa_bull = (bull_vsa / 10.0) * w_vsa
        vsa_bear = (bear_vsa / 10.0) * w_vsa

        bull_vp, bear_vp = self._score_volume_pressure(analysis)
        vp_bull = (bull_vp / 4.0) * w_volume
        vp_bear = (bear_vp / 4.0) * w_volume

        bull_liq, bear_liq = self._score_liquidity(analysis)
        liq_bull = (bull_liq / 4.0) * w_liquidity
        liq_bear = (bear_liq / 4.0) * w_liquidity

        rvol = float(analysis.get("rvol", 1.0))
        rvol_pts = 1.0 if rvol > 1.4 else 0.0

        # Micro-Structure Order Flow Imbalance (OFI) Tick Proxy
        ofi = float(analysis.get("ofi_imbalance", 0.0))
        ofi_bull = float(np.clip(ofi * 2.0, 0.0, 2.0)) if ofi > 0.0 else 0.0
        ofi_bear = float(np.clip(-ofi * 2.0, 0.0, 2.0)) if ofi < 0.0 else 0.0

        vol_bull = float(np.clip(vsa_bull + vp_bull + liq_bull + rvol_pts + ofi_bull, 0.0, 7.0))
        vol_bear = float(np.clip(vsa_bear + vp_bear + liq_bear + rvol_pts + ofi_bear, 0.0, 7.0))

        # --- 3. Statistical Boundary Check (Max 5 pts) ---
        z_score = float(analysis.get("regression_zscore", 0.0))
        stat_bull = 5.0
        stat_bear = 5.0
        # If overbought, penalize buy setup. If oversold, penalize sell setup.
        if z_score > 1.0:
            stat_bull = float(np.clip(5.0 - (z_score - 1.0) * 2.5, 0.0, 5.0))
        if z_score < -1.0:
            stat_bear = float(np.clip(5.0 - (-z_score - 1.0) * 2.5, 0.0, 5.0))

        stat_bull = stat_bull * (w_stats / 5.0)
        stat_bear = stat_bear * (w_stats / 5.0)

        # --- 4. AI Pattern Learner Classifier Probability (Max 8 pts) ---
        ai_raw = (ai_confidence * 16.0) - 8.0 if ai_confidence >= 0.5 else 0.0
        ai_pts = float(np.clip(ai_raw * (w_ai / 8.0), 0.0, 8.0))

        # Setup-type professional strategy bonuses (gated by TIER2_MAX)
        bonus_bull = 0.0
        bonus_bear = 0.0

        # Raja Banks Strategy
        raja_action = analysis.get("raja_action")
        raja_meta = analysis.get("raja_metadata", {})
        if raja_action == "BUY":
            bonus_bull += 8.0
        elif raja_action == "SELL":
            bonus_bear += 8.0

        # ICT Strategy & Kill Zone & FVG Fill
        ict_action = analysis.get("ict_action")
        ict_meta = analysis.get("ict_metadata", {})
        if ict_action == "BUY":
            bonus_bull += 8.0
            if ict_meta.get("killzone_active", False) or analysis.get("killzone_active", False):
                bonus_bull += 8.0
            if "fvg" in ict_meta.get("trigger", ""):
                bonus_bull += 5.0
        elif ict_action == "SELL":
            bonus_bear += 8.0
            if ict_meta.get("killzone_active", False) or analysis.get("killzone_active", False):
                bonus_bear += 8.0
            if "fvg" in ict_meta.get("trigger", ""):
                bonus_bear += 5.0

        # Bank Strategy / OB alignment / POC Profile
        bank_action = analysis.get("bank_action")
        bank_meta = analysis.get("bank_metadata", {})
        if bank_action == "BUY":
            bonus_bull += 6.0
            if bank_meta.get("ob_aligned", False):
                bonus_bull += 6.0
        elif bank_action == "SELL":
            bonus_bear += 6.0
            if bank_meta.get("ob_aligned", False):
                bonus_bear += 6.0

        # AVC Strategy
        avc_action = analysis.get("avc_action")
        if avc_action == "BUY":
            bonus_bull += 7.0
        elif avc_action == "SELL":
            bonus_bear += 7.0

        # M1 Scalping Strategies
        m1_scalping_action = analysis.get("m1_scalping_action")
        if m1_scalping_action == "BUY":
            bonus_bull += 7.0
        elif m1_scalping_action == "SELL":
            bonus_bear += 7.0

        # VSA trigger checks
        vsa_signals = analysis.get("vsa_signals", [])
        if any(s in ['SPRING', 'STOPPING_VOLUME', 'EFFORT_VS_RESULT_BULLISH', 'TEST_OF_SUPPLY', 'NO_SUPPLY'] for s in vsa_signals):
            bonus_bull += 6.0
        if any(s in ['UPTHRUST', 'BUYING_CLIMAX', 'EFFORT_VS_RESULT_BEARISH', 'TEST_OF_DEMAND', 'NO_DEMAND'] for s in vsa_signals):
            bonus_bear += 6.0

        # VWAP Strategy
        vwap_action = analysis.get("vwap_action")
        if vwap_action == "BUY":
            bonus_bull += 6.0
        elif vwap_action == "SELL":
            bonus_bear += 6.0

        # Cap strategy bonus pool to prevent saturation of Tier 2.
        # Without cap, bonuses alone (up to 67 pts) can fill all 35 pts, making
        # structure/FVG/volume/stats scoring completely irrelevant.
        bonus_bull = min(bonus_bull, 15.0)
        bonus_bear = min(bonus_bear, 15.0)

        # Sum Tier 2 components
        bull_t2 = float(np.clip(smc_bull + vol_bull + stat_bull + ai_pts + bonus_bull, 0.0, TIER2_MAX))
        bear_t2 = float(np.clip(smc_bear + vol_bear + stat_bear + ai_pts + bonus_bear, 0.0, TIER2_MAX))

        is_bull = (bull_t2 >= bear_t2)
        structure_val = bull_struct if is_bull else bear_struct
        fvg_val = bull_fvg if is_bull else bear_fvg
        vsa_val = vsa_bull if is_bull else vsa_bear
        
        vol_val = vol_bull if is_bull else vol_bear

        component_map = {
            "t2_structure": round(structure_val, 2),
            "t2_fvg": round(fvg_val, 2),
            "t2_vsa": round(vsa_val, 2),
            "t2_volume": round(vol_val, 2),
            "t2_ai_confidence": round(ai_pts, 2),
        }

        return bull_t2, bear_t2, component_map

    def is_market_velocity_favorable(self, symbol: str) -> Tuple[bool, str]:
        """
        Acts as an absolute operational time-gate. Disables entry triggers
        during known low-velocity sessions and high-risk rollover spread hours.
        """
        current_time_utc = datetime.now(timezone.utc).time()
        
        # 1. Enforce the Absolute Rollover Spread Lockout (All Assets except Crypto)
        if "BTC" not in symbol.upper():
            # Block entries between 21:55 and 22:15 UTC (The Toxic Rollover Window)
            if time(21, 55) <= current_time_utc <= time(22, 15):
                return False, "BLOCK_REASON_ROLLOVER_LIQUIDITY_GAP"
                
        # 2. Assign Symbol-Specific Execution Windows
        if "XAU" in symbol.upper() or "GOLD" in symbol.upper():
            # Gold executes optimally during London and NY overlaps (07:00 to 17:00 UTC)
            if not (time(7, 0) <= current_time_utc <= time(18, 0)):
                return False, "BLOCK_REASON_GOLD_DEAD_ZONE"
                
        elif "EURUSD" in symbol.upper() or "GBPUSD" in symbol.upper() or "USDJPY" in symbol.upper() or "USDCHF" in symbol.upper():
            # Forex majors flatline completely during late Asian hours
            if time(19, 0) <= current_time_utc <= time(6, 0):
                return False, "BLOCK_REASON_FX_LOW_VELOCITY"
                
        # Crypto pairs bypass time windows but remain bound by raw tick-frequency filters
        return True, "VELOCITY_APPROVED"

    def _is_price_near_htf_levels(
        self,
        price: float,
        atr: float,
        df_h1: Optional[pd.DataFrame],
        df_h4: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        is_scalping: bool = False,
        analysis: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """
        Scans historical windows of closed H1/H4 (and M5/M15 in scalping mode) candles to verify if the 
        execution price resides inside an unmitigated structural level or valid LTF setup zone.
        """
        # Define an absolute proximity envelope (e.g., +/- 0.25 * execution ATR for scalping)
        envelope = (0.25 if is_scalping else 0.15) * atr

        # If scalping mode is active, check active LTF structural triggers first
        if is_scalping and analysis is not None:
            # Check for M1/M5 sweeps, MSS, or M1 scalping triggers
            m15_sweep = int(analysis.get("m15_sweep_type", 0))
            m5_mss = int(analysis.get("m5_mss_signal", 0))
            swept_pools = analysis.get("swept_pools", []) or []
            m1_action = analysis.get("m1_scalping_action")

            if m15_sweep != 0 or m5_mss != 0 or len(swept_pools) > 0 or m1_action is not None:
                return True, "LTF_SCALPING_STRUCTURE_CONFLUENCE"

        # Evaluate M5 / M15 levels in scalping mode
        if is_scalping and df_m5 is not None and len(df_m5) >= 20:
            m5_history = df_m5.iloc[-20:-1]
            supports = m5_history['support'].dropna().values if 'support' in m5_history.columns else np.array([])
            resistances = m5_history['resistance'].dropna().values if 'resistance' in m5_history.columns else np.array([])
            for sup in supports:
                if abs(price - sup) <= envelope:
                    return True, "M5_SUPPORT_CONFLUENCE"
            for res in resistances:
                if abs(price - res) <= envelope:
                    return True, "M5_RESISTANCE_CONFLUENCE"

        if is_scalping and df_m15 is not None and len(df_m15) >= 20:
            m15_history = df_m15.iloc[-20:-1]
            ob_tops = m15_history['ob_top'].dropna().values if 'ob_top' in m15_history.columns else np.array([])
            ob_bottoms = m15_history['ob_bottom'].dropna().values if 'ob_bottom' in m15_history.columns else np.array([])
            for top, bottom in zip(ob_tops, ob_bottoms):
                if bottom - envelope <= price <= top + envelope:
                    return True, "M15_ORDER_BLOCK_CONFLUENCE"
        
        # Evaluate H1 levels over a 50-hour trailing window, ignoring the forming candle [-1]
        if df_h1 is not None and len(df_h1) >= 52:
            h1_closed_history = df_h1.iloc[-51:-1] # Strictly closed bars
            
            # Extract vectorized arrays of historical structural levels (with safety checks)
            ob_tops = h1_closed_history['ob_top'].dropna().values if 'ob_top' in h1_closed_history.columns else np.array([])
            ob_bottoms = h1_closed_history['ob_bottom'].dropna().values if 'ob_bottom' in h1_closed_history.columns else np.array([])
            supports = h1_closed_history['support'].dropna().values if 'support' in h1_closed_history.columns else np.array([])
            resistances = h1_closed_history['resistance'].dropna().values if 'resistance' in h1_closed_history.columns else np.array([])
            
            # 1. Check if price is inside an unmitigated H1 Order Block
            for top, bottom in zip(ob_tops, ob_bottoms):
                if bottom - envelope <= price <= top + envelope:
                    return True, "H1_ORDER_BLOCK_CONFLUENCE"
                    
            # 2. Check proximity to historical Key S/R levels
            for sup in supports:
                if abs(price - sup) <= envelope:
                    return True, "H1_SUPPORT_CONFLUENCE"
            for res in resistances:
                if abs(price - res) <= envelope:
                    return True, "H1_RESISTANCE_CONFLUENCE"

        # Evaluate H4 levels over a trailing window (e.g. 30 candles)
        if df_h4 is not None and len(df_h4) >= 32:
            h4_closed_history = df_h4.iloc[-31:-1]
            
            ob_tops_h4 = h4_closed_history['ob_top'].dropna().values if 'ob_top' in h4_closed_history.columns else np.array([])
            ob_bottoms_h4 = h4_closed_history['ob_bottom'].dropna().values if 'ob_bottom' in h4_closed_history.columns else np.array([])
            
            for top, bottom in zip(ob_tops_h4, ob_bottoms_h4):
                if bottom - envelope <= price <= top + envelope:
                    return True, "H4_ORDER_BLOCK_CONFLUENCE"

        # Fallback for scalping mode: allow active scalp setup if threshold is met
        if is_scalping:
            return True, "SCALPING_FLEXIBLE_LEVEL"

        return False, "NO_HTF_LEVEL_MATCH"

    # ──────────────────────────────────────────────────────────────────────────
    #  Tier 3: Risk Quality (max 15 pts)
    # ──────────────────────────────────────────────────────────────────────────

    def _score_tier3_risk(self, regime: str, session_score: float = 0.0, news_sentiment: float = 0.0, direction: Optional[str] = None) -> Tuple[float, Dict[str, float]]:
        """
        Regime quality bonus + Session quality bonus + Sentiment Alignment. Max 15 pts.
        - Regime Quality (max 8 pts): TRENDING=8.0, RANGE=4.0, COMPRESSION=0.0
        - Session Quality (max 7 pts): scaled from session_score (0-15) => session_score * (7.0/15.0)
        - Sentiment (bonus/penalty): +/- 5.0 based on alignment with direction
        """
        regime_pts = REGIME_QUALITY.get(regime.upper(), 0.0)
        session_pts = session_score * (7.0 / 15.0)
        
        # Sentiment alignment (-1.0 to 1.0)
        sentiment_pts = 0.0
        if direction == "BUY":
            sentiment_pts = news_sentiment * 5.0
        elif direction == "SELL":
            sentiment_pts = -news_sentiment * 5.0
            
        total = float(np.clip(regime_pts + session_pts + sentiment_pts, 0.0, TIER3_MAX))
        
        return total, {
            "t3_regime_quality": round(regime_pts, 2),
            "t3_session_quality": round(session_pts, 2),
            "t3_sentiment": round(sentiment_pts, 2)
        }

    # ──────────────────────────────────────────────────────────────────────────
    #  Execution sub-scorers (called by Tier 2)
    # ──────────────────────────────────────────────────────────────────────────

    def _score_structure(self, analysis: Dict) -> Tuple[float, float]:
        """
        Market Structure Shift (MSS) + Liquidity Sweep = 12 pts max.
        Bonus for both (SHARP_TURN pattern) = capped via component max.
        """
        sweep = int(analysis.get("m15_sweep_type", 0))
        mss   = int(analysis.get("m5_mss_signal",  0))

        bull = bear = 0.0

        if sweep == 1:  bull += 5.0
        elif sweep == -1: bear += 5.0

        if mss == 1:  bull += 5.0
        elif mss == -1: bear += 5.0

        # SHARP_TURN bonus when both align
        if sweep == 1 and mss == 1:   bull += 2.0
        elif sweep == -1 and mss == -1: bear += 2.0

        return float(np.clip(bull, 0, 12)), float(np.clip(bear, 0, 12))

    def _score_fvg(self, analysis: Dict) -> Tuple[float, float]:
        """
        FVG class quality: fresh=7, institutional=6, active=5, stale=2.
        Assigned to bull/bear based on FVG direction.
        """
        fvg_class = str(analysis.get("m5_fvg_class", "none")).lower()
        fvg_type  = str(analysis.get("m5_fvg_type",  "none")).lower()

        quality_map = {
            "fresh": 7.0, "pfvg": 7.0,
            "institutional": 6.0, "bag": 6.0,
            "active": 5.0, "rfvg": 3.0,
            "stale": 2.0, "none": 0.0,
        }
        pts = quality_map.get(fvg_class, 0.0)

        if fvg_type == "bullish":   return pts, 0.0
        elif fvg_type == "bearish": return 0.0, pts
        else: return pts * 0.4, pts * 0.4  # Neutral FVG — partial credit

    def _score_vsa(self, analysis: Dict) -> Tuple[float, float]:
        """
        VSA signal alignment. Max 10 pts per direction.
        Each matching signal adds 5 pts (capped at 10).
        """
        vsa_signals = analysis.get("vsa_signals", [])
        if isinstance(vsa_signals, str):
            vsa_signals = [vsa_signals] if vsa_signals else []

        bull = bear = 0.0
        for sig in vsa_signals:
            s = str(sig).lower()
            if s in VSA_BULLISH_SIGNALS: bull += 5.0
            elif s in VSA_BEARISH_SIGNALS: bear += 5.0

        return float(np.clip(bull, 0, 10)), float(np.clip(bear, 0, 10))

    def _score_volume_pressure(self, analysis: Dict) -> Tuple[float, float]:
        """
        Buy/sell pressure imbalance. Max 4 pts per direction.
        Only pressure above 55% contributes (avoids noise from near-equal splits).
        """
        buy_pct  = float(analysis.get("buy_pressure",  50.0))
        sell_pct = float(analysis.get("sell_pressure", 50.0))

        # Only meaningful if pressure is decisively one-sided (>55%)
        if buy_pct >= 55.0:
            advantage = (buy_pct - 55.0) / 45.0  # 0.0 → 1.0
            return float(np.clip(advantage * 4.0, 0, 4)), 0.0
        elif sell_pct >= 55.0:
            advantage = (sell_pct - 55.0) / 45.0
            return 0.0, float(np.clip(advantage * 4.0, 0, 4))
        return 0.0, 0.0

    def _score_ai_confidence(self, confidence: float) -> float:
        """
        Pattern learner AI confidence → 0–8 pts (direction-neutral).
        Below 0.5: contributes 0 (undecided model).
        0.5–1.0: scales linearly to 8 pts.
        """
        c = float(np.clip(confidence, 0.0, 1.0))
        if c < 0.5: return 0.0
        return float(np.clip((c - 0.5) * 2.0 * 8.0, 0.0, 8.0))

    def _score_liquidity(self, analysis: Dict) -> Tuple[float, float]:
        """
        Structural liquidity pool confirmation. Max 4 pts per direction.
        Swept pools (institutional confirmation): 3 pts.
        Resting pools within 1 ATR: 2 pts.
        """
        swept_pools   = analysis.get("swept_pools",   []) or []
        resting_pools = analysis.get("resting_pools", []) or []
        price = float(analysis.get("price", 0.0))
        atr   = float(analysis.get("atr", 1.0))

        bull = bear = 0.0

        for pool in swept_pools:
            ptype = str(pool.get("type", "")).lower()
            pid = str(pool.get("pool_id", "")).lower()
            pdesc = str(pool.get("description", "")).lower()
            
            # Bearish liquidity sweep (swept high/resistance/buy_stop)
            if "buy_stop" in ptype or "high" in ptype or "resistance" in ptype or "pdh" in pid or "eqh" in pid or "high" in pdesc:
                bear += 3.0
            # Bullish liquidity sweep (swept low/support/sell_stop)
            elif "sell_stop" in ptype or "low" in ptype or "support" in ptype or "pdl" in pid or "eql" in pid or "low" in pdesc:
                bull += 3.0

        for pool in resting_pools:
            level = pool.get("price") or pool.get("level")
            if level is None:
                continue
            level = float(level)
            ptype = str(pool.get("type", "")).lower()
            pid = str(pool.get("pool_id", "")).lower()
            pdesc = str(pool.get("description", "")).lower()
            
            if abs(price - level) < atr:
                # Bearish resting liquidity (high/resistance/buy_stop)
                if "buy_stop" in ptype or "high" in ptype or "resistance" in ptype or "pdh" in pid or "eqh" in pid or "high" in pdesc:
                    bear += 2.0
                # Bullish resting liquidity (low/support/sell_stop)
                elif "sell_stop" in ptype or "low" in ptype or "support" in ptype or "pdl" in pid or "eql" in pid or "low" in pdesc:
                    bull += 2.0

        return float(np.clip(bull, 0, 4)), float(np.clip(bear, 0, 4))

    def _calculate_final_score(
        self,
        raw_score: float,
        penalties_map: Dict[str, float],
        scaling_factor: float = 1.0
    ) -> Tuple[float, Dict[str, float]]:
        """Sums penalties and boosts, applies them to raw_score, and returns final score and telemetry."""
        
        final_score = raw_score
        for value in penalties_map.values():
            final_score += value
            
        final_score *= scaling_factor
        
        clipped_score = float(np.clip(final_score, 0.0, 100.0))
        return clipped_score, penalties_map

    # ──────────────────────────────────────────────────────────────────────────
    #  Intraday Shift & Day-of-Week helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_m1_intraday_shift(self, df_ltf) -> int:
        """
        Compute M1 intraday momentum bias from the last N candles.

        Returns:
            +1  — strong bullish M1 shift (price above EMA, majority of recent candles bullish)
            -1  — strong bearish M1 shift
             0  — neutral / insufficient data

        Logic:
          1. Take last 12 M1 candles.
          2. Count bullish candles (close > open) vs bearish.
          3. Check current close vs EMA20 (if available) to confirm trend direction.
          4. Require ≥ 8/12 candles agreeing AND EMA alignment for a shift signal.
        """
        try:
            if df_ltf is None or len(df_ltf) < 12:
                return 0

            recent = df_ltf.iloc[-12:]
            closes = recent['close'].values
            opens  = recent['open'].values

            bull_count = int(np.sum(closes > opens))
            bear_count = int(np.sum(closes < opens))

            # EMA20 alignment check (if the column exists)
            ema_alignment = 0
            if 'ema_fast' in df_ltf.columns:
                ema_val = float(df_ltf['ema_fast'].iloc[-1])
                last_close = float(closes[-1])
                if last_close > ema_val:
                    ema_alignment = 1
                elif last_close < ema_val:
                    ema_alignment = -1
            elif 'ema20' in df_ltf.columns:
                ema_val = float(df_ltf['ema20'].iloc[-1])
                last_close = float(closes[-1])
                ema_alignment = 1 if last_close > ema_val else (-1 if last_close < ema_val else 0)

            # Momentum slope: compare average of last 3 closes vs average of prior 3 closes
            momentum_slope = 0
            if len(closes) >= 6:
                recent_avg = float(np.mean(closes[-3:]))
                prior_avg  = float(np.mean(closes[-6:-3]))
                if recent_avg > prior_avg:
                    momentum_slope = 1
                elif recent_avg < prior_avg:
                    momentum_slope = -1

            # Decision: require candle majority + at least one of EMA or momentum
            if bull_count >= 8:
                if ema_alignment >= 0 or momentum_slope >= 0:  # not conflicting
                    return 1
            elif bear_count >= 8:
                if ema_alignment <= 0 or momentum_slope <= 0:
                    return -1

            # Moderate shift: 7/12 + EMA AND momentum both agree
            if bull_count >= 7 and ema_alignment == 1 and momentum_slope == 1:
                return 1
            if bear_count >= 7 and ema_alignment == -1 and momentum_slope == -1:
                return -1

        except Exception as e:
            self.logger.debug(f"[M1_SHIFT] Compute failed: {e}")

        return 0

    def _get_dow_modifier(self) -> Tuple[float, float]:
        """
        Day-of-Week threshold and conviction gap modifiers.

        Returns:
            (threshold_delta, conviction_gap_delta)

        Rationale:
          - Monday: Market opens cautiously, many gaps. Raise threshold (+3) and gap (+2)
            to avoid trading the chaos of the open.
          - Tue–Thu: Cleanest trending days. No adjustment (0, 0).
          - Friday: Position squaring causes sharp two-way moves. Lower threshold (-5)
            and conviction gap (-2) so the system can trade BOTH directions flexibly
            without being stuck on the weekly bias.
          - Saturday/Sunday: Market closed — no adjustment needed (but just in case).
        """
        from datetime import datetime, timezone
        dow = datetime.now(timezone.utc).weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        if dow == 0:    # Monday
            return (+3.0, +2.0)   # Cautious open — raise bar
        elif dow == 4:  # Friday
            return (-5.0, -2.0)   # Two-way moves — more flexible
        else:           # Tue, Wed, Thu (cleanest), Sat, Sun
            return (0.0, 0.0)

    # ──────────────────────────────────────────────────────────────────────────
    #  Utilities
    # ──────────────────────────────────────────────────────────────────────────

    def _log(
        self, score: float, direction: Optional[str], regime: str,
        threshold: float, reason_map: Dict, block_reason: Optional[str]
    ) -> None:
        t1 = reason_map.get("_tier1", 0)
        t2 = reason_map.get("_tier2", 0)
        t3 = reason_map.get("_tier3", 0)
        self.logger.info(
            f"Brain={score:.1f}/{threshold} dir={direction} regime={regime} "
            f"T1={t1:.1f}/50 T2={t2:.1f}/35 T3={t3:.1f}/15 "
            f"block={block_reason or 'none'}"
        )

    def get_score_label(self, score: float) -> str:
        """Human-readable label for brain score zones"""
        if score >= 80:   return "ULTRA_CONVICTION"
        elif score >= 65: return "HIGH_CONVICTION"
        elif score >= 55: return "STANDARD"
        elif score >= 40: return "LOW"
        else:             return "BLOCKED"

    def get_color_zone(self, score: float) -> str:
        """CSS color zone for dashboard rendering"""
        if score >= 75:   return "#00ff88"   # Green
        elif score >= 55: return "#ffcc00"   # Yellow
        elif score >= 40: return "#ff8800"   # Orange
        else:             return "#ff3366"   # Red

    def get_tier_summary(self, result: "BrainResult") -> str:
        """One-line summary of tier scores for logging"""
        return (
            f"T1(dir)={result.tier1_score:.0f}/50 "
            f"T2(exec)={result.tier2_score:.0f}/35 "
            f"T3(risk)={result.tier3_score:.0f}/15"
        )

    def route_experts(self, regime: str) -> set:
        """Determines the active expert strategy set permitted to trade in the given regime."""
        r = regime.upper()
        if r in ("TREND_PULLBACK", "TREND_CONTINUATION"):
            return {"ICT", "SMC_CONCEPTS", "VWAP_VAS", "BANK_TO_BANK"}
        elif r in ("RANGE_ROTATION", "RANGE_EDGE_REVERSAL", "LIQUIDITY_REVERSAL"):
            return {"CRT_TBS", "SRC", "VWAP_VAS"}
        elif r in ("BREAKOUT_EXPANSION", "COMPRESSION_BREAKOUT"):
            return {"AMD", "AVC", "SMC_CONCEPTS"}
        return set()

    def evaluate_candidates(
        self,
        context: "MarketContext",
        candidates: List[Tuple["CandidateSetup", "CandidatePrediction"]],
        mode_profile,
        prediction_guard
    ) -> List[Tuple["CandidateSetup", "CandidatePrediction", float]]:
        """
        Filters, validates, and ranks candidates based on conservative expected value (EV)
        and regime-aware strategy routing rules.
        """
        from core.candidate_setup import CandidateLifecycle, CandidateState
        from typing import List, Tuple
        
        # 1. Regime Certainty Gate
        regime = context.regime_label.upper()
        max_prob = max(context.regime_probabilities.values()) if context.regime_probabilities else 0.0
        
        use_regime_filter = settings_manager.get("dynamic_regime_filter", False)
        strict_mode = settings_manager.get("strict_mode", False)
        
        # Only abstain if regime filter and strict_mode are explicitly enabled
        if use_regime_filter and strict_mode and (max_prob < 0.3 or regime in ("CHAOTIC", "ILLIQUID")):
            self.logger.warning(f"Abstaining: Unsuitable regime context ({regime} with prob {max_prob:.2f})")
            return []

        active_experts = self.route_experts(regime)
        
        eligible = []
        for candidate, prediction in candidates:
            lifecycle = CandidateLifecycle(candidate)
            
            # 2. Regime-Strategy Routing Filter
            strat = candidate.strategy_name.upper()
            if strat not in active_experts:
                self.logger.warning(f"Candidate {candidate.candidate_id} rejected: {strat} is not an active expert in regime {regime}")
                continue
            
            # 3. Prediction Guard / Abstain Check
            abstain_reason = prediction_guard.should_abstain(prediction, context)
            if abstain_reason:
                try:
                    lifecycle.transition_to(CandidateState.CONTEXT_VALIDATED)
                    lifecycle.transition_to(CandidateState.GEOMETRY_VALIDATED)
                    lifecycle.transition_to(CandidateState.FEATURED)
                    lifecycle.transition_to(CandidateState.ABSTAINED)
                except Exception:
                    pass
                continue

            # 4. Strategy Min RR Check
            if candidate.planned_rr < mode_profile.minimum_rr:
                continue

            # 5. Calculate Conservative EV
            prob_lower = prediction.probability_lower_bound
            uncertainty_penalty = 0.1 * prediction.epistemic_uncertainty
            
            conservative_ev = (
                prob_lower * candidate.planned_rr
                - (1.0 - prob_lower) * 1.0
                - prediction.execution_cost_r
                - uncertainty_penalty
            )

            # 6. Filter Negative or Low EV (min target: 0.15)
            min_ev = float(settings_manager.get("minimum_required_ev", 0.15))
            if conservative_ev < min_ev:
                continue

            # 7. Transition to ELIGIBLE state
            try:
                lifecycle.transition_to(CandidateState.CONTEXT_VALIDATED)
                lifecycle.transition_to(CandidateState.GEOMETRY_VALIDATED)
                lifecycle.transition_to(CandidateState.FEATURED)
                lifecycle.transition_to(CandidateState.PREDICTED)
                lifecycle.transition_to(CandidateState.ELIGIBLE)
            except Exception:
                pass

            eligible.append((candidate, prediction, conservative_ev))

        # 8. Rank remaining by conservative expected value
        eligible.sort(key=lambda x: x[2], reverse=True)
        return eligible

