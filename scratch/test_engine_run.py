# scratch/test_engine_run.py
import sys
import os
import json
import numpy as np

# Add workspace directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.engine import AdvancedTradingEngine
from utils.mt5_data import init_mt5, shutdown_mt5

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
        
    if not init_mt5():
        print("Failed to initialize MT5")
        sys.exit(1)
        
    print("MT5 initialized successfully")
    
    try:
        engine = AdvancedTradingEngine(
            symbols=["XAUUSDm"],
            strategy_mode="scalping",
            enable_dashboard=False
        )
        
        print("Running multi-timeframe analysis for XAUUSDm...")
        analysis = engine.run_multi_timeframe_analysis("XAUUSDm")
        
        if analysis:
            print("SUCCESS! Analysis completed.")
            print("\nKey Metrics:")
            print(f"Price: {analysis.get('price')}")
            print(f"Master HTF Bias: {analysis.get('htf_bias')} (D1: {analysis.get('d1_bias')}, H4: {analysis.get('h4_bias')}, H1: {analysis.get('h1_bias')})")
            print(f"M15 Sweep Type: {analysis.get('m15_sweep_type')}")
            print(f"M5 MSS Signal: {analysis.get('m5_mss_signal')}")
            print(f"Market Regime: {analysis.get('market_regime')}")
            print(f"News Locked: {analysis.get('news_locked')} (Reason: {analysis.get('news_lockout_reason')})")
            print(f"Resting Pools Mapped: {len(analysis.get('resting_pools', []))}")
            
            # Print full alignment state
            print("\n6-TF Alignment State:")
            tf_align = analysis.get("tf_alignment", {})
            for tf, state in tf_align.items():
                if tf == 'aligned':
                    print(f"  Overall Aligned: {state}")
                elif tf == 'htf_bias':
                    print(f"  HTF Bias: {state}")
                else:
                    print(f"  {tf}: bias={state.get('bias')}, label={state.get('label')}")
            
            # Print SMC patterns
            print("\nSMC Pattern Learner Output:")
            features = analysis.get("features", {})
            ai_signal = engine.pattern_learner.get_trading_signal(
                "XAUUSDm",
                features,
                df_ltf=analysis.get('df_ltf'),
                df_m5=analysis.get('df_m5'),
                df_h1=analysis.get('df_h1')
            )
            print(f"  SMC Direction: {ai_signal.get('smc_direction')}")
            print(f"  SMC Confidence: {ai_signal.get('smc_confidence')}")
            print(f"  SMC Win Prob: {ai_signal.get('win_prob')}")
            print(f"  Adjusted Win Prob: {ai_signal.get('adjusted_win_prob')}")
            print(f"  Confidence: {ai_signal.get('confidence')}")
            
            # Test evaluate entry rules
            print("\nTesting evaluate_entry_rules...")
            engine.evaluate_entry_rules(analysis)
            print("Evaluation completed without crash.")
            print(f"TradeBrain Result:")
            print(f"  Score: {analysis.get('brain_score')}")
            print(f"  Direction: {analysis.get('brain_direction')}")
            print(f"  Block Reason: {analysis.get('brain_block_reason')}")
            
        else:
            print("FAILED! Analysis returned None.")
            
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        shutdown_mt5()
        print("MT5 shutdown")

if __name__ == "__main__":
    main()
