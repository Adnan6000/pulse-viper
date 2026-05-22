# scripts/export_data.py
import sys
import os
import pandas as pd
import json
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import AdvancedTradingEngine

def export_trading_data():
    """Export all trading data to files"""
    print("💾 EXPORTING TRADING DATA")
    print("=" * 50)
    
    engine = AdvancedTradingEngine(symbols=['XAUUSDm'])
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. Export Experience Memory
    if len(engine.experience_memory) > 0:
        experiences = []
        for exp in engine.experience_memory.memory:
            exp_data = {
                'timestamp': exp['timestamp'].isoformat(),
                'action': exp['action'],
                'reward': exp['reward'],
                'state_rsi': exp['state'].get('rsi', 0),
                'state_trend': exp['state'].get('trend', 0),
                'state_regime': exp['state'].get('regime', 'unknown'),
                'metadata': json.dumps(exp.get('metadata', {}))
            }
            experiences.append(exp_data)
        
        exp_df = pd.DataFrame(experiences)
        exp_file = f"data/experiences_{timestamp}.csv"
        exp_df.to_csv(exp_file, index=False)
        print(f"✅ Experiences exported: {exp_file} ({len(exp_df)} records)")
    
    # 2. Export Performance History
    if engine.performance_history:
        performance_data = []
        for trade in engine.performance_history:
            trade_data = {
                'timestamp': trade['timestamp'].isoformat(),
                'symbol': trade['symbol'],
                'action': trade['action'],
                'confidence': trade['confidence'],
                'size': trade['size'],
                'price': trade['price'],
                'rsi': trade['rsi'],
                'reasoning': trade['reasoning']
            }
            performance_data.append(trade_data)
        
        perf_df = pd.DataFrame(performance_data)
        perf_file = f"data/performance_{timestamp}.csv"
        perf_df.to_csv(perf_file, index=False)
        print(f"✅ Performance history exported: {perf_file} ({len(perf_df)} records)")
    
    # 3. Export Pattern Data
    patterns_data = {}
    for pattern_key, patterns in engine.pattern_learner.patterns.items():
        patterns_data[pattern_key] = []
        for pattern in patterns[-10:]:  # Last 10 patterns
            patterns_data[pattern_key].append({
                'pattern': pattern['pattern'],
                'outcome': pattern['outcome'],
                'timestamp': pattern['timestamp'].isoformat()
            })
    
    patterns_file = f"data/patterns_{timestamp}.json"
    with open(patterns_file, 'w') as f:
        json.dump(patterns_data, f, indent=2)
    print(f"✅ Patterns exported: {patterns_file}")
    
    # 4. Export Memory to pickle (for reloading)
    memory_file = f"data/memory_{timestamp}.pkl"
    engine.experience_memory.save_memory(memory_file)
    print(f"✅ Memory saved: {memory_file}")
    
    print(f"\n🎯 All data exported to 'data/' directory")

if __name__ == "__main__":
    export_trading_data()