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

import os
import json
import numpy as np
import logging
from typing import Optional, Dict, Tuple, Any

logger = logging.getLogger("PulseViper.TradeBrain")

DEFAULT_T1_WEIGHTS = {
    "d1": 18.0,
    "h4": 14.0,
    "h1": 11.0,
    "m15": 5.0,
    "m5": 2.0
}

DEFAULT_T2_WEIGHTS = {
    "structure": 12.0,
    "fvg": 7.0,
    "vsa": 10.0,
    "volume": 4.0,
    "liquidity": 4.0,
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
    "TRENDING":    48,   # Looser — trend continuation is higher probability
    "RANGE":       55,   # Standard — needs good structure + execution
    "COMPRESSION": 65,   # Tight — only exceptional setups
}
DEFAULT_THRESHOLD = 55

# Regime quality bonuses for Tier 3 (positive-only — no penalties)
REGIME_QUALITY = {
    "TRENDING":    15.0,  # Strong directional market → full quality bonus
    "RANGE":        8.0,  # Ranging — moderate quality context
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
    "test_of_supply",
    "ultra_high_volume_bullish",
    "no_supply",
}
VSA_BEARISH_SIGNALS = {
    "climactic_sell_exhaustion",
    "supply_absorption",
    "hidden_selling",
    "stopping_volume_down",
    "test_of_demand",
    "ultra_high_volume_bearish",
    "no_demand",
}

# Minimum directional advantage for direction commitment
DIRECTIONAL_CONVICTION_GAP = 8.0

# ─────────────────────────────────────────────────────────────────────────────
#  Block reason constants
# ─────────────────────────────────────────────────────────────────────────────
BLOCK_REASON_NEWS = "NEWS_LOCKOUT"
BLOCK_REASON_CHAOTIC = "CHAOTIC_REGIME"
BLOCK_REASON_SCORE = "SCORE_BELOW_THRESHOLD"
BLOCK_REASON_CONFLICTED = "DIRECTIONAL_CONFLICT"


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
        reason_map: Dict[str, float],
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
        self.passed = (brain_score >= threshold) and (brain_direction is not None)

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
            "reason_map": {k: round(v, 2) for k, v in self.reason_map.items()},
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

    def __init__(self, base_threshold: float = 55.0):
        self.base_threshold = base_threshold
        self.logger = logging.getLogger("PulseViper.TradeBrain")
        self._eval_count = 0
        self._load_calibrated_weights()

    def _load_calibrated_weights(self):
        """Load calibrated weights from file if available, otherwise use defaults."""
        try:
            if os.path.exists("data/brain_weights.json"):
                with open("data/brain_weights.json", "r") as f:
                    data = json.load(f)
                    self.t1_weights = data.get("tier1", dict(DEFAULT_T1_WEIGHTS))
                    self.t2_weights = data.get("tier2", dict(DEFAULT_T2_WEIGHTS))
                    return
        except Exception as e:
            self.logger.warning(f"Error loading calibrated weights: {e}")
        
        self.t1_weights = dict(DEFAULT_T1_WEIGHTS)
        self.t2_weights = dict(DEFAULT_T2_WEIGHTS)

    # ──────────────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        analysis: Dict[str, Any],
        strategy_action: Optional[str] = None,
        ai_confidence: float = 0.5,
        session_score: float = 0.0,
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
        
        # Reload weights to pick up online calibration updates
        self._load_calibrated_weights()
        
        regime = str(analysis.get("market_regime", "RANGE")).upper()
        threshold = ADAPTIVE_THRESHOLDS.get(regime, self.base_threshold)

        def _blocked(reason: str) -> BrainResult:
            return BrainResult(
                brain_score=0.0,
                brain_direction=None,
                threshold=threshold,
                reason_map={"block_reason": 0.0},
                regime=regime,
                block_reason=reason,
            )

        # ── FIX 5 + FIX 3: Hard gates BEFORE scoring ──────────────────────────
        # Gate 1: News lockout is always a hard block — never a soft penalty
        if analysis.get("news_locked", False):
            self._log(0.0, None, regime, threshold, {}, "NEWS_LOCKED")
            return _blocked(BLOCK_REASON_NEWS)

        # Gate 2: CHAOTIC regime is always a hard block — one mechanism, clean
        if regime in HARD_BLOCKED_REGIMES:
            self._log(0.0, None, regime, threshold, {}, "CHAOTIC")
            return _blocked(BLOCK_REASON_CHAOTIC)

        # ── FIX 1 + FIX 2: 3-Tier normalized scoring ─────────────────────────

        # TIER 1: DIRECTIONAL (max 50 pts)
        bull_t1, bear_t1, t1_map = self._score_tier1_directional(analysis)

        # TIER 2: EXECUTION QUALITY (max 35 pts)
        bull_t2, bear_t2, t2_map = self._score_tier2_execution(analysis, ai_confidence)

        # ── FIX 4: Direction determined cleanly from Tier 1 + Tier 2 ──────────
        bull_raw = bull_t1 + bull_t2
        bear_raw = bear_t1 + bear_t2

        if bull_raw > bear_raw + DIRECTIONAL_CONVICTION_GAP:
            brain_direction = "BUY"
            directional_score = bull_raw
        elif bear_raw > bull_raw + DIRECTIONAL_CONVICTION_GAP:
            brain_direction = "SELL"
            directional_score = bear_raw
        else:
            brain_direction = None
            directional_score = max(bull_raw, bear_raw)

        # Normalize directional score to [0, 85] (T1_MAX + T2_MAX)
        dir_max = TIER1_MAX + TIER2_MAX  # 85
        t1_score = float(np.clip(bull_t1 if brain_direction == "BUY" else bear_t1, 0, TIER1_MAX))
        t2_score = float(np.clip(bull_t2 if brain_direction == "BUY" else bear_t2, 0, TIER2_MAX))

        # TIER 3: RISK QUALITY (max 15 pts)
        # Regime quality (0-8) + Session quality (0-7)
        t3_score, t3_map = self._score_tier3_risk(regime, session_score)

        # Final brain score — always in [0, 100]
        raw_score = t1_score + t2_score + t3_score
        brain_score = float(np.clip(raw_score, 0.0, 100.0))

        # ── Strategy confirmation (advisory only, no direction override) ──────
        strategy_quality_boost = 0.0
        if strategy_action is not None and brain_direction is not None:
            if strategy_action == brain_direction:
                strategy_quality_boost = 2.0  # Modest bonus — confirms entry
        t2_map["strategy_confirm"] = strategy_quality_boost
        brain_score = float(np.clip(brain_score + strategy_quality_boost, 0.0, 100.0))

        # ── Build unified reason_map ───────────────────────────────────────────
        reason_map: Dict[str, float] = {}
        reason_map.update(t1_map)
        reason_map.update(t2_map)
        reason_map.update(t3_map)
        reason_map["_tier1"] = t1_score
        reason_map["_tier2"] = t2_score
        reason_map["_tier3"] = t3_score

        # ── Apply threshold gate ───────────────────────────────────────────────
        block_reason = None
        if brain_direction is None:
            block_reason = BLOCK_REASON_CONFLICTED
        elif brain_score < threshold:
            block_reason = BLOCK_REASON_SCORE
            brain_direction = None  # score failed threshold — block direction

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
        Pure HTF direction encoding using self.t1_weights.
        """
        d1  = int(analysis.get("d1_bias",  0))
        h4  = int(analysis.get("h4_bias",  0))
        h1  = int(analysis.get("h1_bias",  0))
        m15 = int(analysis.get("m15_bias", 0))
        m5  = int(analysis.get("m5_bias",  0))

        tf_weights = [
            ("d1", d1, self.t1_weights.get("d1", 18.0)),
            ("h4", h4, self.t1_weights.get("h4", 14.0)),
            ("h1", h1, self.t1_weights.get("h1", 11.0)),
            ("m15", m15, self.t1_weights.get("m15", 5.0)),
            ("m5", m5, self.t1_weights.get("m5", 2.0))
        ]

        bull = bear = 0.0
        component_map: Dict[str, float] = {}

        for name, bias, w in tf_weights:
            if bias == 1:
                bull += w
                component_map[f"t1_{name}"] = float(w)
            elif bias == -1:
                bear += w
                component_map[f"t1_{name}"] = float(-w)
            else:
                component_map[f"t1_{name}"] = 0.0

        bull = min(bull, TIER1_MAX)
        bear = min(bear, TIER1_MAX)

        return float(bull), float(bear), component_map

    # ──────────────────────────────────────────────────────────────────────────
    #  Tier 2: Execution Quality (max 35 pts)
    # ──────────────────────────────────────────────────────────────────────────

    def _score_tier2_execution(
        self, analysis: Dict, ai_confidence: float
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Execution quality components using self.t2_weights.
        """
        w_structure = self.t2_weights.get("structure", 12.0)
        w_fvg = self.t2_weights.get("fvg", 7.0)
        w_vsa = self.t2_weights.get("vsa", 10.0)
        w_volume = self.t2_weights.get("volume", 4.0)
        w_liquidity = self.t2_weights.get("liquidity", 4.0)
        w_ai = self.t2_weights.get("ai_confidence", 8.0)

        RAW_MAX = w_structure + w_fvg + w_vsa + w_volume + w_liquidity + w_ai
        if RAW_MAX <= 0:
            RAW_MAX = 45.0

        bull_struct, bear_struct = self._score_structure(analysis)
        bull_struct = bull_struct * (w_structure / 12.0)
        bear_struct = bear_struct * (w_structure / 12.0)

        bull_fvg, bear_fvg       = self._score_fvg(analysis)
        bull_fvg = bull_fvg * (w_fvg / 7.0)
        bear_fvg = bear_fvg * (w_fvg / 7.0)

        bull_vsa, bear_vsa       = self._score_vsa(analysis)
        bull_vsa = bull_vsa * (w_vsa / 10.0)
        bear_vsa = bear_vsa * (w_vsa / 10.0)

        bull_vp, bear_vp         = self._score_volume_pressure(analysis)
        bull_vp = bull_vp * (w_volume / 4.0)
        bear_vp = bear_vp * (w_volume / 4.0)

        bull_liq, bear_liq       = self._score_liquidity(analysis)
        bull_liq = bull_liq * (w_liquidity / 4.0)
        bear_liq = bear_liq * (w_liquidity / 4.0)

        ai_pts                   = self._score_ai_confidence(ai_confidence)
        ai_pts = ai_pts * (w_ai / 8.0)

        bull_raw = bull_struct + bull_fvg + bull_vsa + bull_vp + bull_liq + ai_pts
        bear_raw = bear_struct + bear_fvg + bear_vsa + bear_vp + bear_liq + ai_pts

        scale = TIER2_MAX / RAW_MAX
        bull_t2 = float(np.clip(bull_raw * scale, 0.0, TIER2_MAX))
        bear_t2 = float(np.clip(bear_raw * scale, 0.0, TIER2_MAX))

        component_map = {
            "t2_structure":      round(bull_struct * scale if bull_t2 >= bear_t2 else bear_struct * scale, 2),
            "t2_fvg":            round(bull_fvg * scale    if bull_t2 >= bear_t2 else bear_fvg * scale,    2),
            "t2_vsa":            round(bull_vsa * scale    if bull_t2 >= bear_t2 else bear_vsa * scale,    2),
            "t2_volume":         round(bull_vp * scale     if bull_t2 >= bear_t2 else bear_vp * scale,     2),
            "t2_liquidity":      round(bull_liq * scale    if bull_t2 >= bear_t2 else bear_liq * scale,    2),
            "t2_ai_confidence":  round(ai_pts * scale, 2),
        }

        return bull_t2, bear_t2, component_map

    # ──────────────────────────────────────────────────────────────────────────
    #  Tier 3: Risk Quality (max 15 pts)
    # ──────────────────────────────────────────────────────────────────────────

    def _score_tier3_risk(self, regime: str, session_score: float = 0.0) -> Tuple[float, Dict[str, float]]:
        """
        Regime quality bonus + Session quality bonus. Max 15 pts.
        - Regime Quality (max 8 pts): TRENDING=8.0, RANGE=4.0, COMPRESSION=0.0
        - Session Quality (max 7 pts): scaled from session_score (0-15) => session_score * (7.0/15.0)
        """
        regime_pts = 8.0 if regime == "TRENDING" else (4.0 if regime == "RANGE" else 0.0)
        session_pts = float(session_score) * (7.0 / 15.0)
        total = float(np.clip(regime_pts + session_pts, 0.0, TIER3_MAX))
        
        return total, {
            "t3_regime_quality": round(regime_pts, 2),
            "t3_session_quality": round(session_pts, 2)
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
            "fresh": 7.0, "institutional": 6.0, "active": 5.0,
            "stale": 2.0, "rfvg": 0.0, "none": 0.0,
        }
        pts = quality_map.get(fvg_class, 1.0)

        if fvg_type == "bullish":   return float(pts), 0.0
        elif fvg_type == "bearish": return 0.0, float(pts)
        else: return float(pts * 0.4), float(pts * 0.4)  # Neutral FVG — partial credit

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
            if "high" in ptype or "resistance" in ptype: bear += 3.0
            elif "low" in ptype or "support" in ptype:   bull += 3.0

        for pool in resting_pools:
            level = pool.get("level", 0) or 0
            ptype = str(pool.get("type", "")).lower()
            if abs(price - level) < atr:
                if "high" in ptype or "resistance" in ptype: bear += 2.0
                elif "low" in ptype or "support" in ptype:   bull += 2.0

        return float(np.clip(bull, 0, 4)), float(np.clip(bear, 0, 4))

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
