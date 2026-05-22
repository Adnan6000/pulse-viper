# scripts/live_monitor.py
import sys
import os
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import AdvancedTradingEngine

def live_data_monitor():
    """Monitor data storage in real-time"""
    print("📊 LIVE DATA STORAGE MONITOR")
    print("=" * 50)
    
    engine = AdvancedTradingEngine(symbols=['XAUUSDm'])
    
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print(f"🕒 {datetime.now().strftime('%H:%M:%S')} - Live Data Monitor")
            print("=" * 40)
            
            # Memory Statistics
            print("🧠 EXPERIENCE MEMORY:")
            print(f"   Stored Experiences: {len(engine.experience_memory)}")
            if len(engine.experience_memory) > 0:
                metrics = engine.experience_memory.get_performance_metrics()
                print(f"   Win Rate: {metrics.get('win_rate', 0):.1f}%")
                print(f"   Total PnL: {metrics['total_pnl']:.3f}")
                
                # Show latest experience
                latest = engine.experience_memory.get_recent(1)
                if latest:
                    exp = latest[0]
                    print(f"   Latest: Action {exp['action']}, Reward {exp['reward']:.3f}")
            
            # Pattern Statistics
            print(f"\n🎯 LEARNED PATTERNS:")
            patterns = engine.pattern_learner.patterns
            for key in patterns:
                if patterns[key]:
                    print(f"   {key}: {len(patterns[key])} patterns")
            
            # Performance History
            print(f"\n📈 PERFORMANCE HISTORY:")
            print(f"   Total Trades: {len(engine.performance_history)}")
            if engine.performance_history:
                latest_trade = list(engine.performance_history)[-1]
                print(f"   Latest: {latest_trade['symbol']} {latest_trade['action']} "
                      f"@ {latest_trade['price']:.5f}")
            
            print(f"\n⏳ Refreshing in 5 seconds... (Ctrl+C to stop)")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitor stopped")

if __name__ == "__main__":
    live_data_monitor()