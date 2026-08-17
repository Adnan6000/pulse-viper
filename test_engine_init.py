
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.engine import AdvancedTradingEngine

print("Initializing AdvancedTradingEngine...")
engine = AdvancedTradingEngine(symbols=['XAUUSD'], strategy_mode='scalping', enable_dashboard=False)
print("Engine initialized successfully!")
print("Symbols:", engine.symbols)
print("Testing run_multi_timeframe_analysis on first symbol...")
if engine.symbols:
    analysis = engine.run_multi_timeframe_analysis(engine.symbols[0])
    print("Analysis result keys:", list(analysis.keys()) if analysis else None)
print("Testing evaluate_entry_rules...")
if engine.symbols and analysis:
    entry = engine.evaluate_entry_rules(analysis, is_live_tick=True)
    print("Entry result:", entry)
print("Done!")
