
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.engine import AdvancedTradingEngine
from utils.mt5_gateway import mt5_gateway as mt5
from datetime import datetime, timezone

def main():
    print("=== PulseViper Entry Debug ===")
    
    print("\nCreating engine...")
    try:
        engine = AdvancedTradingEngine(
            symbols=[],
            strategy_mode='scalping',
            enable_dashboard=False
        )
    except Exception as e:
        print("❌ Engine creation failed:", str(e))
        import traceback
        print(traceback.format_exc())
        return
    print("✅ Engine created")

    print("\n=== Engine Settings ===")
    from utils.settings_manager import settings_manager
    settings = settings_manager.get_all()
    for key, val in settings.items():
        print(f"  {key:40} = {val}")

    print("\n=== Available Symbols ===")
    if len(engine.symbols) > 0:
        for sym in engine.symbols:
            info = mt5.symbol_info(sym)
            if info:
                print(f"  {sym:<15} spread: {info.spread} (point: {info.point})")
            else:
                print(f"  {sym:<15} ❌ Not found")
    else:
        print("  No symbols configured!")
        return

    print("\n=== Checking Safety Engine ===")
    from core.safety_engine import SafetyEngine
    se = SafetyEngine()
    se_stats = se.get_stats()
    print("  Safety stats:", se_stats)
    allowed, reason = se.check_entry_allowed()
    print("  Entry allowed?", allowed, "- Reason:", reason)

    print("\n=== Checking Session Engine ===")
    from core.session_engine import SessionEngine
    session_engine = SessionEngine()
    sym = engine.symbols[0]
    session_ctx = session_engine.get_session_context(symbol=sym)
    print(f"  {sym} session: name={session_ctx.get('session_name')}, score={session_ctx.get('session_score')}")

    print("\n=== Running Multi-Timeframe Analysis ===")
    try:
        analysis = engine.run_multi_timeframe_analysis(sym)
        if analysis:
            print("  Analysis keys:", list(analysis.keys()))
            print("  Bias:", analysis.get('bias'))
            print("  Regime:", analysis.get('regime'))
        else:
            print("  ❌ No analysis returned!")
    except Exception as e:
        print("  ❌ Analysis failed:", str(e))
        import traceback
        print(traceback.format_exc())

    print("\n=== Evaluating Entry Rules ===")
    try:
        setup = engine.evaluate_entry_rules(analysis, is_live_tick=True)
        if setup:
            print("  ✅ Setup found:", setup)
        else:
            print("  ❌ No setup found")
    except Exception as e:
        print("  ❌ Evaluation failed:", str(e))
        import traceback
        print(traceback.format_exc())

    print("\n=== Checking Skipped Stats ===")
    print("  Skipped stats:", engine.skipped_stats)

    print("\n=== Checking Starvation Stats ===")
    starvation_stats = engine.starvation_analyzer.get_dashboard_stats()
    print("  Starvation stats:", starvation_stats)

    print("\n✅ Done")

if __name__ == "__main__":
    main()
