# scratch/test_brain_calibrator.py
"""
Unit tests for BrainCalibrator.
"""
import sys
import os

sys.path.insert(0, 'd:/pulse-viper')

import core.brain_calibrator as bc

def run_tests():
    print("=" * 60)
    print("  Testing BrainCalibrator Weight Tuning")
    print("=" * 60)

    # Clean previous weight files if they exist
    if os.path.exists(bc.CALIBRATION_FILE):
        os.remove(bc.CALIBRATION_FILE)

    calibrator = bc.BrainCalibrator()
    weights = calibrator.get_weights()

    # 1. Test initial load defaults
    assert abs(sum(weights["tier1"].values()) - 50.0) < 0.01, f"T1 sum: {sum(weights['tier1'].values())}"
    assert abs(sum(weights["tier2"].values()) - 45.0) < 0.01, f"T2 sum: {sum(weights['tier2'].values())}"
    print("  PASS  Test 1: Initial default weights structure and sums")

    # 2. Add trades to trigger calibration (needs MIN_CALIBRATION_SAMPLES=30)
    # Set high learning rate and alpha for testing to produce visible change after rounding
    bc.LEARNING_RATE = 0.8
    bc.EMA_ALPHA = 0.8
    
    # We want "t1_d1" and "t2_structure" to have 100% win rate
    # We want "t1_m5" and "t2_liquidity" to have 0% win rate
    for i in range(15):
        # Winning trades
        calibrator.record_outcome(
            reason_map={"t1_d1": 18.0, "t2_structure": 12.0},
            outcome="WIN",
            pnl=100.0
        )
        # Losing trades
        calibrator.record_outcome(
            reason_map={"t1_m5": 2.0, "t2_liquidity": 4.0},
            outcome="LOSS",
            pnl=-100.0
        )

    # Now we have 30 trades logged. We can call calibrate manually to force it.
    calibrator.calibrate()

    new_weights = calibrator.get_weights()

    # Verify normalization constraints hold
    assert abs(sum(new_weights["tier1"].values()) - 50.0) < 0.05, f"New T1 sum: {sum(new_weights['tier1'].values())}"
    assert abs(sum(new_weights["tier2"].values()) - 45.0) < 0.05, f"New T2 sum: {sum(new_weights['tier2'].values())}"
    print("  PASS  Test 2: Normalization limits verified")

    # Verify that t1_d1 weight increased and t1_m5 weight decreased
    assert new_weights["tier1"]["d1"] > bc.DEFAULT_T1_WEIGHTS["d1"], f"{new_weights['tier1']['d1']} vs {bc.DEFAULT_T1_WEIGHTS['d1']}"
    assert new_weights["tier1"]["m5"] < bc.DEFAULT_T1_WEIGHTS["m5"], f"{new_weights['tier1']['m5']} vs {bc.DEFAULT_T1_WEIGHTS['m5']}"
    print("  PASS  Test 3: Tier 1 weight adjustments verified (d1 increased, m5 decreased)")

    # Verify that t2_structure weight increased and t2_liquidity weight decreased
    assert new_weights["tier2"]["structure"] > bc.DEFAULT_T2_WEIGHTS["structure"], f"{new_weights['tier2']['structure']} vs {bc.DEFAULT_T2_WEIGHTS['structure']}"
    assert new_weights["tier2"]["liquidity"] < bc.DEFAULT_T2_WEIGHTS["liquidity"], f"{new_weights['tier2']['liquidity']} vs {bc.DEFAULT_T2_WEIGHTS['liquidity']}"
    print("  PASS  Test 4: Tier 2 weight adjustments verified (structure increased, liquidity decreased)")

    # Verify file was written
    assert os.path.exists(bc.CALIBRATION_FILE), "Calibration file was not written!"
    print("  PASS  Test 5: Persistence to disk verified")

    # Cleanup
    if os.path.exists(bc.CALIBRATION_FILE):
        os.remove(bc.CALIBRATION_FILE)

    print("\nAll 5 BrainCalibrator tests passed successfully!")

if __name__ == "__main__":
    run_tests()
