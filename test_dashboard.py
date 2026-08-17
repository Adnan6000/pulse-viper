
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.engine import AdvancedTradingEngine

print("Starting Pulse Viper...")
engine = AdvancedTradingEngine(
    symbols=['XAUUSD'],  # We'll use XAUUSD since we saw it's available
    strategy_mode='scalping',
    enable_dashboard=True
)

print("Dashboard is LIVE at http://localhost:18080")
print("Press Ctrl+C to stop")

try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down...")
    engine.shutdown()
