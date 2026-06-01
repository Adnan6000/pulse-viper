# scratch/test_session_engine.py
"""
Unit tests for SessionEngine.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, 'd:/pulse-viper')

from core.session_engine import SessionEngine

def run_tests():
    print("=" * 60)
    print("  Testing SessionEngine Classification and Scoring")
    print("=" * 60)

    engine = SessionEngine()

    # 1. Test Asian Session (04:30 UTC)
    dt_asian = datetime(2026, 6, 1, 4, 30, tzinfo=timezone.utc) # Monday
    ctx = engine.get_session_context(dt_asian)
    assert ctx["session_name"] == "ASIAN", f"Got: {ctx['session_name']}"
    assert ctx["session_score"] == 2.0, f"Got: {ctx['session_score']}"
    print("  PASS  Test 1: Asian Session detection")

    # 2. Test London Session (10:15 UTC)
    dt_london = datetime(2026, 6, 1, 10, 15, tzinfo=timezone.utc)
    ctx = engine.get_session_context(dt_london)
    assert ctx["session_name"] == "LONDON", f"Got: {ctx['session_name']}"
    assert ctx["session_score"] == 12.0, f"Got: {ctx['session_score']}"
    print("  PASS  Test 2: London Session detection")

    # 3. Test Overlap Session (14:30 UTC)
    dt_overlap = datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc)
    ctx = engine.get_session_context(dt_overlap)
    assert ctx["session_name"] == "OVERLAP", f"Got: {ctx['session_name']}"
    assert ctx["session_score"] == 15.0, f"Got: {ctx['session_score']}"
    print("  PASS  Test 3: London/NY Overlap detection")

    # 4. Test New York Session (18:00 UTC)
    dt_ny = datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc)
    ctx = engine.get_session_context(dt_ny)
    assert ctx["session_name"] == "NEW_YORK", f"Got: {ctx['session_name']}"
    assert ctx["session_score"] == 10.0, f"Got: {ctx['session_score']}"
    print("  PASS  Test 4: New York Session detection")

    # 5. Test Off-Hours (22:30 UTC)
    dt_off = datetime(2026, 6, 1, 22, 30, tzinfo=timezone.utc)
    ctx = engine.get_session_context(dt_off)
    assert ctx["session_name"] == "OFF", f"Got: {ctx['session_name']}"
    assert ctx["session_score"] == 0.0, f"Got: {ctx['session_score']}"
    print("  PASS  Test 5: Off-hours detection")

    # 6. Test Weekend (Sunday 12:00 UTC)
    dt_weekend = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc) # Sunday
    ctx = engine.get_session_context(dt_weekend)
    assert ctx["session_name"] == "WEEKEND", f"Got: {ctx['session_name']}"
    assert ctx["session_score"] == 0.0, f"Got: {ctx['session_score']}"
    print("  PASS  Test 6: Weekend detection")

    print("\nAll 6 SessionEngine tests passed successfully!")

if __name__ == "__main__":
    run_tests()
