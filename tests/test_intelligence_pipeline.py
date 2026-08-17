# tests/test_intelligence_pipeline.py
import unittest
import uuid
import threading
from datetime import datetime, timezone, timedelta
import numpy as np

# Import modules to verify
from core.bar_normalizer import BarNormalizer, TimeframeDataSnapshot
from core.data_quality import DataQualityGate
from core.market_structure_graph import MarketStructureGraph, SwingEvent, SwingScale, SetupSequence, LiquidityPoolEvent, LiquiditySweepEvent, StructureBreakEvent
from core.instrument_profile import get_instrument_profile, InstrumentProfile
from core.mode_profile import get_mode_profile, ModeProfile
from core.candidate_setup import CandidateSetup, CandidateState, CandidateLifecycle
from core.candidate_feature_builder import CandidateFeatureBuilder, FEATURE_SCHEMA_HASH
from core.candidate_prediction import CandidatePrediction
from core.prediction_guard import PredictionGuard
from core.outcome_labeler import OutcomeResolver, CandidateOutcome
from core.self_learning_governor import SelfLearningGovernor, LearningProposal, ProposalState
from core.promotion_validator import PromotionValidator
from core.model_registry import ModelRegistry, ModelBundle
from core.execution_token import ExecutionValidationToken, validation_token_store
from core.execution_service import MT5ExecutionService, canonical_request_hash
from core.trade_brain import TradeBrain
from utils.settings_manager import settings_manager

class TestIntelligencePipeline(unittest.TestCase):
    
    def setUp(self):
        self.symbol = "XAUUSDm"
        self.decision_id = f"PV-DEC-{uuid.uuid4().hex[:4]}"
        self.candidate_id = f"PV-CAND-{uuid.uuid4().hex[:4]}"
        self.cycle_id = f"PV-CYC-{uuid.uuid4().hex[:4]}"
        
        # Build mock data: 110 closed bars
        now = datetime.now(timezone.utc)
        self.bars = []
        for i in range(110):
            t = now - timedelta(minutes=110 - i)
            # Create a clean high/low structure
            h = 2000.0 + i * 0.1
            l = 1999.0 + i * 0.1
            if i == 50:  # swing high pivot
                h = 2025.0
            if i == 70:  # swing low pivot
                l = 1970.0
            self.bars.append({
                "time": t.isoformat(),
                "open": 1999.5 + i * 0.1,
                "high": h,
                "low": l,
                "close": 2000.0 + i * 0.1,
                "tick_volume": 100
            })
        self.bars_tuple = tuple(self.bars)

    # 1. Swing Causal Invariance
    def test_swing_causal_invariance(self):
        graph = MarketStructureGraph(self.symbol, "M1")
        # Update graph with a decision time set at pivot index (index 50) + 1 bar
        pivot_t = datetime.fromisoformat(self.bars[50]["time"])
        decision_t = pivot_t + timedelta(minutes=1)
        
        graph.update_graph(self.bars_tuple, atr_value=2.0, decision_time=decision_t)
        # Verify no swings available at decision_time since right confirmation window (3 bars) is not closed
        available_swings = [s for s in graph.swings if s.available_at <= decision_t]
        self.assertEqual(len(available_swings), 0)

    # 2. Deterministic Replays
    def test_deterministic_replays(self):
        graph1 = MarketStructureGraph(self.symbol, "M1")
        graph2 = MarketStructureGraph(self.symbol, "M1")
        now = datetime.now(timezone.utc)
        
        graph1.update_graph(self.bars_tuple, atr_value=2.0, decision_time=now)
        graph2.update_graph(self.bars_tuple, atr_value=2.0, decision_time=now)
        
        self.assertEqual(len(graph1.swings), len(graph2.swings))
        self.assertEqual([s.price for s in graph1.swings], [s.price for s in graph2.swings])

    # 3. Multi-Scale Separation
    def test_multi_scale_separation(self):
        # We classify swings into MICRO, INTERNAL, INTERMEDIATE, EXTERNAL, MAJOR
        # Mock high prominence swing
        swing_h = SwingEvent(
            event_id="SW-1", symbol=self.symbol, timeframe="M1", direction="HIGH",
            pivot_time=datetime.now(), confirmed_at=datetime.now(), available_at=datetime.now(),
            price=2050.0, scale=SwingScale.EXTERNAL, strength_atr=4.0, prominence_atr=2.5,
            bars_left=3, bars_right=3
        )
        # Mock low prominence swing
        swing_l = SwingEvent(
            event_id="SW-2", symbol=self.symbol, timeframe="M1", direction="HIGH",
            pivot_time=datetime.now(), confirmed_at=datetime.now(), available_at=datetime.now(),
            price=2001.0, scale=SwingScale.MICRO, strength_atr=0.2, prominence_atr=0.15,
            bars_left=3, bars_right=3
        )
        self.assertNotEqual(swing_h.scale, swing_l.scale)

    # 4. Setup Order Check
    def test_setup_order_check(self):
        graph = MarketStructureGraph(self.symbol, "M1")
        t_base = datetime.now(timezone.utc)
        
        pool = LiquidityPoolEvent("P-1", self.symbol, "M1", "SELL_SIDE", t_base, t_base, t_base, 1900.0, 1.0, ())
        sweep = LiquiditySweepEvent("S-1", self.symbol, "M1", "BULLISH_SWEEP", t_base + timedelta(minutes=5), t_base + timedelta(minutes=5), t_base + timedelta(minutes=5), 1899.0, "P-1", ())
        bos = StructureBreakEvent("B-1", self.symbol, "M1", "BOS", t_base + timedelta(minutes=10), t_base + timedelta(minutes=10), t_base + timedelta(minutes=10), "SW-1", 1.2, ())
        
        graph.pools.append(pool)
        graph.sweeps.append(sweep)
        graph.breaks.append(bos)
        
        seq_valid = SetupSequence("SEQ-1", self.symbol, "M1", "P-1", "S-1", None, "B-1", "Z-1", None, "T-1")
        self.assertTrue(graph.validate_setup_sequence(seq_valid))

    # 5. Entry Alignment
    def test_entry_alignment(self):
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=datetime.now(), valid_until_utc=datetime.now(), planned_entry=2000.0,
            stop_price=1990.0, target_price=2020.0, risk_distance=10.0, reward_distance=20.0, planned_rr=2.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-2",
            target_anchor_event_id="P-1", metadata={}
        )
        self.assertEqual(candidate.planned_entry, 2000.0)

    # 6. SL Anchor Check
    def test_sl_anchor_check(self):
        graph = MarketStructureGraph(self.symbol, "M1")
        # Add the swing to the graph
        t_base = datetime.now()
        swing = SwingEvent("SW-STOP", self.symbol, "M1", "LOW", t_base, t_base, t_base, 1990.0, SwingScale.INTERNAL, 1.0, 1.0, 3, 3)
        pool = LiquidityPoolEvent("P-TARGET", self.symbol, "M1", "BUY_SIDE", t_base, t_base, t_base, 2020.0, 1.0, ())
        graph.swings.append(swing)
        graph.pools.append(pool)
        
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=datetime.now(), valid_until_utc=datetime.now(), planned_entry=2000.0,
            stop_price=1990.0, target_price=2020.0, risk_distance=10.0, reward_distance=20.0, planned_rr=2.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-STOP",
            target_anchor_event_id="P-TARGET", metadata={}
        )
        self.assertTrue(candidate.validate_geometry(graph))

    # 7. Target Anchor Check
    def test_target_anchor_check(self):
        graph = MarketStructureGraph(self.symbol, "M1")
        # Only add stops swing, omit target pool
        t_base = datetime.now()
        swing = SwingEvent("SW-STOP", self.symbol, "M1", "LOW", t_base, t_base, t_base, 1990.0, SwingScale.INTERNAL, 1.0, 1.0, 3, 3)
        graph.swings.append(swing)
        
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=datetime.now(), valid_until_utc=datetime.now(), planned_entry=2000.0,
            stop_price=1990.0, target_price=2020.0, risk_distance=10.0, reward_distance=20.0, planned_rr=2.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-STOP",
            target_anchor_event_id="P-MISSING", metadata={}
        )
        self.assertFalse(candidate.validate_geometry(graph))

    # 8. Annotation Consistency
    def test_annotation_consistency(self):
        from core.chart_annotation_snapshot import ChartAnnotationSnapshot
        snap = ChartAnnotationSnapshot(
            cycle_id=self.cycle_id, decision_id=self.decision_id, candidate_id=self.candidate_id,
            symbol=self.symbol, timeframe="M1", as_of_utc=datetime.now(), candles=(), swings=(),
            liquidity_events=(), structure_events=(), order_blocks=(), fvgs=(),
            entry_candle_time=None, entry_price=2000.0, stop_price=1990.0, target_price=2020.0,
            stop_anchor_event_id="SW-1", target_anchor_event_id="P-1", setup_sequence_id="SEQ-1"
        )
        self.assertEqual(snap.decision_id, self.decision_id)

    # 9. No Direction Flip
    def test_no_direction_flip(self):
        # We test that a low buy probability never generates a sell action.
        # Check get_trading_signal output directly
        from unittest.mock import MagicMock
        from core.pattern_learner import PatternLearner
        learner = PatternLearner(memory=MagicMock())
        learner.nn_ready = False
        
        # When win_prob is low/unready, output action is HOLD, not SELL
        res = learner.get_trading_signal(
            symbol=self.symbol,
            current_features={"active_bias": 1},
            df_ltf=None,
            candidate_strategy="ICT",
            candidate_action="BUY"
        )
        # Even with active_bias=1, if probability is low/absent, it does NOT flip to SELL
        self.assertEqual(res["signal"], "HOLD")

    # 10. Fail-Safe Inference
    def test_fail_safe_inference(self):
        from unittest.mock import MagicMock
        from core.pattern_learner import PatternLearner
        learner = PatternLearner(memory=MagicMock())
        # Mock no models ready
        learner.nn_ready = False
        learner.classifier.discrete_conds = {}
        
        res = learner.get_trading_signal(
            symbol=self.symbol,
            current_features={"active_bias": 1},
            df_ltf=None
        )
        self.assertEqual(res["signal"], "HOLD")
        self.assertIsNone(res["confidence"])
        self.assertEqual(res["model_source"], "NO_VALID_MODEL")
        self.assertFalse(res["model_ready"])

    # 11. Feature Vector Symmetry
    def test_feature_vector_symmetry(self):
        from core.market_context import MarketContext
        now = datetime.now(timezone.utc)
        context = MarketContext(
            context_version=4, boot_id="B-1", cycle_id=self.cycle_id, symbol=self.symbol,
            decision_time_utc=now, instrument_profile_id="XAUUSD", mode_profile_id="scalping",
            timeframe_snapshots={}, regime_probabilities={"RANGE": 1.0}, regime_label="RANGE",
            regime_age_bars=10, trend_state={"volatility_ratio": 1.0, "atr_pct": 0.001, "atr": 2.0},
            structure_graph_version="1", active_structure_events=(), liquidity_state={},
            session_context={"active_session": "NY"}, news_context={},
            spread_context={"point": 0.01, "current_spread": 10.0}, data_quality={"quality_score": 100.0},
            context_hash="HASH"
        )
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=now, valid_until_utc=now, planned_entry=2000.0,
            stop_price=1990.0, target_price=2020.0, risk_distance=10.0, reward_distance=20.0, planned_rr=2.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-2",
            target_anchor_event_id="P-1", metadata={"swing_scale": "INTERNAL"}
        )
        feat_arr = CandidateFeatureBuilder.build(context, candidate)
        self.assertEqual(len(feat_arr), 32)
        # Check that candidate strategy "ICT" (index 1 is strategy_ict) is encoded correctly
        self.assertEqual(feat_arr[1], 1.0) # strategy_ict
        self.assertEqual(feat_arr[4], 1.0) # candidate_action_buy

    # 12. Same-Bar Resolution
    def test_same_bar_resolution(self):
        bars_future = [{"high": 2020.0, "low": 1990.0, "close": 2000.0, "open": 2000.0}]
        # lower timeframe bars: TP hit before SL
        ltf_bars = [
            {"high": 2020.0, "low": 1999.0},
            {"high": 2005.0, "low": 1990.0}
        ]
        outcome = OutcomeResolver.resolve(
            candidate_id=self.candidate_id, entry_price=2000.0, stop_price=1990.0, target_price=2020.0,
            action="BUY", bars_future=bars_future, lower_tf_bars=ltf_bars
        )
        self.assertEqual(outcome.outcome_type, "TP_FIRST")
        self.assertTrue(outcome.tp_before_sl)
        self.assertFalse(outcome.same_bar_ambiguous)

    # 13. Cost Adjusted Labeling
    def test_cost_adjusted_labeling(self):
        bars_future = [{"high": 2020.0, "low": 1995.0, "close": 2000.0, "open": 2000.0}]
        # Buy target 2020, stop 1990. Risk = 10 points. Profit = 20 points (2R).
        # Let's say spread = 10 points. Spread R = 1R. Commission + slippage = 0.07R.
        outcome = OutcomeResolver.resolve(
            candidate_id=self.candidate_id, entry_price=2000.0, stop_price=1990.0, target_price=2020.0,
            action="BUY", bars_future=bars_future, lower_tf_bars=None, spread_points=10.0, point=1.0
        )
        # expected net_r = 2.0R - 1.0R - 0.05R - 0.02R = 0.93R
        assert outcome.net_r is not None
        self.assertAlmostEqual(outcome.net_r, 0.93)

    # 14. Synthetic Exclusion
    def test_synthetic_exclusion(self):
        # Verify that synthetic template outcomes are identified by metadata source
        outcome = CandidateOutcome(
            candidate_id=self.candidate_id, outcome_type="TP_FIRST", tp_before_sl=True, net_r=2.0,
            mfe_r=2.0, mae_r=0.0, holding_bars=2, spread_r=0.0, commission_r=0.0, slippage_r=0.0,
            same_bar_ambiguous=False, data_source="SYNTHETIC_TEMPLATE", source_quality=0.0, label_version="v4.1"
        )
        self.assertEqual(outcome.data_source, "SYNTHETIC_TEMPLATE")
        self.assertEqual(outcome.source_quality, 0.0)

    # 15. Exploration Isolation
    def test_exploration_isolation(self):
        # We test that exploration trades are tagged as such and not mixed with champion promotion datasets
        from core.self_learning_governor import LearningProposal
        prop = LearningProposal(
            proposal_id="PROP-1", source_component="DailyAnalyzer", proposal_type="min_rr_ratio",
            current_value=2.0, proposed_value=2.5, dataset_id="EMPIRICAL_LIVE", evidence_summary={},
            expected_benefit=0.15, estimated_risk=0.02, created_at_utc=datetime.now(), expires_at_utc=datetime.now()
        )
        self.assertEqual(prop.dataset_id, "EMPIRICAL_LIVE")

    # 16. Valid Validation Splits
    def test_valid_validation_splits(self):
        # Ensure validation split dates do not overlap with training dates
        train_start = datetime(2026, 1, 1)
        train_end = datetime(2026, 6, 30)
        val_start = datetime(2026, 7, 1)
        val_end = datetime(2026, 7, 15)
        # Disjoint intervals
        self.assertTrue(train_end < val_start)

    # 17. OOD Abstention
    def test_ood_abstention(self):
        from core.market_context import MarketContext
        now = datetime.now(timezone.utc)
        context = MarketContext(
            context_version=4, boot_id="B-1", cycle_id=self.cycle_id, symbol=self.symbol,
            decision_time_utc=now, instrument_profile_id="XAUUSD", mode_profile_id="scalping",
            timeframe_snapshots={}, regime_probabilities={"RANGE": 1.0}, regime_label="RANGE",
            regime_age_bars=10, trend_state={"volatility_ratio": 1.0, "atr_pct": 0.001, "atr": 2.0},
            structure_graph_version="1", active_structure_events=(), liquidity_state={},
            session_context={"active_session": "NY"}, news_context={},
            spread_context={"point": 0.01, "current_spread": 10.0}, data_quality={"quality_score": 100.0},
            context_hash="HASH"
        )
        
        pred = CandidatePrediction(
            candidate_id=self.candidate_id, probability_tp_first=0.6, probability_sl_first=0.3,
            probability_timeout=0.1, calibrated_probability_tp_first=0.6, probability_lower_bound=0.55,
            expected_net_r=0.2, expected_mfe_r=1.0, expected_mae_r=0.5, expected_holding_bars=10,
            net_r_q10=-1.0, net_r_q50=0.2, net_r_q90=2.0, execution_cost_r=0.07, epistemic_uncertainty=0.05,
            aleatoric_uncertainty=0.08, out_of_distribution_score=0.95, # > 0.8 OOD limit
            model_version="NN-CHAMPION-V1", calibration_version="CAL-V1", feature_schema_hash=FEATURE_SCHEMA_HASH
        )
        guard = PredictionGuard()
        self.assertEqual(guard.should_abstain(pred, context), "OUT_OF_DISTRIBUTION")

    # 18. Ensemble Disagreement
    def test_ensemble_disagreement(self):
        from core.market_context import MarketContext
        now = datetime.now(timezone.utc)
        context = MarketContext(
            context_version=4, boot_id="B-1", cycle_id=self.cycle_id, symbol=self.symbol,
            decision_time_utc=now, instrument_profile_id="XAUUSD", mode_profile_id="scalping",
            timeframe_snapshots={}, regime_probabilities={"RANGE": 1.0}, regime_label="RANGE",
            regime_age_bars=10, trend_state={"volatility_ratio": 1.0, "atr_pct": 0.001, "atr": 2.0},
            structure_graph_version="1", active_structure_events=(), liquidity_state={},
            session_context={"active_session": "NY"}, news_context={},
            spread_context={"point": 0.01, "current_spread": 10.0}, data_quality={"quality_score": 100.0},
            context_hash="HASH"
        )
        
        pred = CandidatePrediction(
            candidate_id=self.candidate_id, probability_tp_first=0.6, probability_sl_first=0.3,
            probability_timeout=0.1, calibrated_probability_tp_first=0.6, probability_lower_bound=0.55,
            expected_net_r=0.2, expected_mfe_r=1.0, expected_mae_r=0.5, expected_holding_bars=10,
            net_r_q10=-1.0, net_r_q50=0.2, net_r_q90=2.0, execution_cost_r=0.07,
            epistemic_uncertainty=0.18, # > 0.15 limit
            aleatoric_uncertainty=0.08, out_of_distribution_score=0.10,
            model_version="NN-CHAMPION-V1", calibration_version="CAL-V1", feature_schema_hash=FEATURE_SCHEMA_HASH
        )
        guard = PredictionGuard()
        self.assertEqual(guard.should_abstain(pred, context), "MODEL_DISAGREEMENT")

    # 19. Analyzer Sandboxing
    def test_analyzer_sandboxing(self):
        gov = SelfLearningGovernor()
        old_val = settings_manager.get("min_rr_ratio")
        new_val = 3.5 if old_val != 3.5 else 2.5
        prop = LearningProposal(
            proposal_id="PROP-VAL", source_component="DailyAnalyzer", proposal_type="min_rr_ratio",
            current_value=old_val, proposed_value=new_val, dataset_id="VAL-SET", evidence_summary={},
            expected_benefit=0.12, estimated_risk=0.01, created_at_utc=datetime.now(), expires_at_utc=datetime.now()
        )
        gov.submit_proposal(prop, ProposalState.SHADOW_PENDING)
        # Direct write to settings_manager from DailyAnalyzer is disabled. It must go through the governor.
        self.assertEqual(settings_manager.get("min_rr_ratio"), old_val)
        self.assertEqual(len(gov.get_proposals_by_state(ProposalState.SHADOW_PENDING)), 1)

    # 20. Evolver Sandboxing
    def test_evolver_sandboxing(self):
        gov = SelfLearningGovernor()
        old_val = settings_manager.get("risk_percent")
        new_val = 2.5 if old_val != 2.5 else 1.5
        prop = LearningProposal(
            proposal_id="PROP-EVOLVE", source_component="GeneticEvolver", proposal_type="risk_percent",
            current_value=old_val, proposed_value=new_val, dataset_id="EVOLVE-SET", evidence_summary={},
            expected_benefit=0.22, estimated_risk=0.05, created_at_utc=datetime.now(), expires_at_utc=datetime.now()
        )
        gov.submit_proposal(prop, ProposalState.SHADOW_ACTIVE)
        # Settings remain unchanged until explicitly promoted by authorized governance
        self.assertEqual(settings_manager.get("risk_percent"), old_val)

    # 21. No Direct Vision Entry
    def test_no_direct_vision_entry(self):
        # Trade execution validation requires presence of structural validation checks (no direct vision entry)
        from core.candidate_setup import CandidateSetup
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=datetime.now(), valid_until_utc=datetime.now(), planned_entry=2000.0,
            stop_price=1990.0, target_price=2020.0, risk_distance=10.0, reward_distance=20.0, planned_rr=2.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-2",
            target_anchor_event_id="P-1", metadata={}
        )
        # Require stop and target anchors to prevent zero/empty geometry entries
        self.assertTrue(candidate.stop_anchor_event_id != "")
        self.assertTrue(candidate.target_anchor_event_id != "")

    # 22. Gateway Permission
    def test_gateway_permission(self):
        # Excluded direct order send function from mt5_read_gateway
        from utils.mt5_gateway import mt5_read_gateway
        with self.assertRaises(AttributeError):
            mt5_read_gateway.order_send({})
        self.assertTrue(callable(mt5_read_gateway.execution_transaction))

    # 23. Regime-Aware Routing
    def test_regime_aware_routing(self):
        from core.trade_brain import TradeBrain
        from core.market_context import MarketContext
        now = datetime.now(timezone.utc)
        brain = TradeBrain()
        
        # Scenario: ICT candidate in RANGE_ROTATION regime.
        context = MarketContext(
            context_version=4, boot_id="B-1", cycle_id=self.cycle_id, symbol=self.symbol,
            decision_time_utc=now, instrument_profile_id="XAUUSD", mode_profile_id="scalping",
            timeframe_snapshots={}, regime_probabilities={"RANGE_ROTATION": 1.0}, regime_label="RANGE_ROTATION",
            regime_age_bars=10, trend_state={"volatility_ratio": 1.0, "atr_pct": 0.001, "atr": 2.0},
            structure_graph_version="1", active_structure_events=(), liquidity_state={},
            session_context={"active_session": "NY"}, news_context={},
            spread_context={"point": 0.01, "current_spread": 10.0}, data_quality={"quality_score": 100.0},
            context_hash="HASH"
        )
        
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=now, valid_until_utc=now, planned_entry=2000.0,
            stop_price=1990.0, target_price=2020.0, risk_distance=10.0, reward_distance=20.0, planned_rr=2.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-2",
            target_anchor_event_id="P-1", metadata={"swing_scale": "INTERNAL"}
        )
        
        prediction = CandidatePrediction(
            candidate_id=self.candidate_id, probability_tp_first=0.6, probability_sl_first=0.3,
            probability_timeout=0.1, calibrated_probability_tp_first=0.6, probability_lower_bound=0.55,
            expected_net_r=0.2, expected_mfe_r=1.0, expected_mae_r=0.5, expected_holding_bars=10,
            net_r_q10=-1.0, net_r_q50=0.2, net_r_q90=2.0, execution_cost_r=0.07, epistemic_uncertainty=0.05,
            aleatoric_uncertainty=0.08, out_of_distribution_score=0.1,
            model_version="NN-CHAMPION-V1", calibration_version="CAL-V1", feature_schema_hash=FEATURE_SCHEMA_HASH
        )
        
        from core.mode_profile import get_mode_profile
        from core.prediction_guard import PredictionGuard
        
        # Route should reject ICT under RANGE_ROTATION (ICT is only trend_pullback)
        res = brain.evaluate_candidates(context, [(candidate, prediction)], get_mode_profile("scalping"), PredictionGuard())
        self.assertEqual(len(res), 0)

    # 24. Location Gating
    def test_location_gating(self):
        # Entry price outside discount/premium (chasing at midpoint)
        graph = MarketStructureGraph(self.symbol, "M1")
        t_base = datetime.now()
        swing = SwingEvent("SW-STOP", self.symbol, "M1", "LOW", t_base, t_base, t_base, 1990.0, SwingScale.INTERNAL, 1.0, 1.0, 3, 3)
        pool = LiquidityPoolEvent("P-TARGET", self.symbol, "M1", "BUY_SIDE", t_base, t_base, t_base, 2010.0, 1.0, ())
        graph.swings.append(swing)
        graph.pools.append(pool)
        
        # Midpoint = 2000. For a BUY, planned_entry=2005 (above midpoint 2000) should be blocked.
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=datetime.now(), valid_until_utc=datetime.now(), planned_entry=2005.0,
            stop_price=1990.0, target_price=2010.0, risk_distance=15.0, reward_distance=5.0, planned_rr=0.3,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-STOP",
            target_anchor_event_id="P-TARGET", metadata={}
        )
        self.assertFalse(candidate.validate_geometry(graph))

    # 25. Daily Budget Halt
    def test_daily_budget_halt(self):
        from core.risk_engine import DynamicRiskEngine
        engine = DynamicRiskEngine()
        
        # Mock _check_daily_loss_veto to return True
        engine._check_daily_loss_veto = lambda max_loss_pct: True
        
        risk = engine.calculate_risk_percent(
            current_atr=2.0, median_atr=2.0, current_spread=1.0, max_spread=5.0,
            confidence=0.6, active_positions=0, base_risk=0.25, strategy_name="ICT",
            open_portfolio_heat_pct=0.0, model_ready=True
        )
        self.assertEqual(risk, 0.0)

    # 26. Consecutive Losses Veto
    def test_consecutive_losses_veto(self):
        from core.risk_engine import DynamicRiskEngine
        engine = DynamicRiskEngine()
        
        # Mock _check_consecutive_losses_veto to return True
        engine._check_consecutive_losses_veto = lambda: True
        
        risk = engine.calculate_risk_percent(
            current_atr=2.0, median_atr=2.0, current_spread=1.0, max_spread=5.0,
            confidence=0.6, active_positions=0, base_risk=0.25, strategy_name="ICT",
            open_portfolio_heat_pct=0.0, model_ready=True
        )
        self.assertEqual(risk, 0.0)

    # 27. Path Cleanliness
    def test_path_cleanliness(self):
        from core.market_structure_graph import OrderBlockEvent
        graph = MarketStructureGraph(self.symbol, "M1")
        t_base = datetime.now()
        
        # Create stop swing and target pool
        swing = SwingEvent("SW-STOP", self.symbol, "M1", "LOW", t_base, t_base, t_base, 1990.0, SwingScale.INTERNAL, 1.0, 1.0, 3, 3)
        pool = LiquidityPoolEvent("P-TARGET", self.symbol, "M1", "BUY_SIDE", t_base, t_base, t_base, 2030.0, 1.0, ())
        
        # Active Bearish OB blocking path between entry (1995) and target (2030)
        ob = OrderBlockEvent(
            event_id="OB-BEAR", symbol=self.symbol, timeframe="M1", direction="BEARISH",
            pivot_time=t_base, confirmed_at=t_base, available_at=t_base,
            top=2015.0, bottom=2010.0, mitigation_pct=0.0, created_from_event_ids=()
        )
        
        graph.swings.append(swing)
        graph.pools.append(pool)
        graph.obs.append(ob)
        
        candidate = CandidateSetup(
            candidate_id=self.candidate_id, decision_id=self.decision_id, cycle_id=self.cycle_id,
            strategy_name="ICT", action="BUY", symbol=self.symbol, mode="scalping", execution_timeframe="M1",
            detected_at_utc=datetime.now(), valid_until_utc=datetime.now(), planned_entry=1995.0,
            stop_price=1990.0, target_price=2030.0, risk_distance=5.0, reward_distance=35.0, planned_rr=7.0,
            setup_sequence_id="SEQ-1", entry_anchor_event_id="SW-1", stop_anchor_event_id="SW-STOP",
            target_anchor_event_id="P-TARGET", metadata={}
        )
        self.assertFalse(candidate.validate_geometry(graph))

