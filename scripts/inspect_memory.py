# scripts/inspect_memory.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import AdvancedTradingEngine
import json

def inspect_experience_memory():
    """Inspect the experience memory contents"""
    print("🔍 INSPECTING EXPERIENCE MEMORY")
    print("=" * 50)
    
    # Initialize engine to access memory
    engine = AdvancedTradingEngine(symbols=['XAUUSDm'])
    
    print(f"📊 Memory Stats:")
    print(f"   Total Experiences: {len(engine.experience_memory)}")
    
    if len(engine.experience_memory) > 0:
        # Get performance metrics
        metrics = engine.experience_memory.get_performance_metrics()
        print(f"   Win Rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"   Total Trades: {metrics['total_trades']}")
        print(f"   Total PnL: {metrics['total_pnl']:.3f}")
        
        # Show recent experiences
        print(f"\n📈 Recent Experiences (last 5):")
        recent = engine.experience_memory.get_recent(5)
        for i, exp in enumerate(recent):
            print(f"   {i+1}. Action: {exp['action']} | Reward: {exp['reward']:.3f} | "
                  f"Timestamp: {exp['timestamp'].strftime('%H:%M:%S')}")
            
        # Show high reward experiences
        print(f"\n🎯 High Reward Experiences:")
        high_reward = engine.experience_memory.get_high_reward_experiences(threshold=0.2)
        for exp in high_reward[:3]:
            print(f"   ✓ Reward: {exp['reward']:.3f} | Action: {exp['action']}")
    
    else:
        print("   No experiences stored yet. Run the engine to generate data.")

def inspect_patterns():
    """Inspect learned patterns"""
    print(f"\n🔍 INSPECTING LEARNED PATTERNS")
    print("=" * 50)
    
    engine = AdvancedTradingEngine(symbols=['XAUUSDm'])
    
    patterns = engine.pattern_learner.patterns
    regimes = engine.pattern_learner.market_regimes
    
    print(f"📊 Pattern Statistics:")
    for symbol_key in patterns:
        if patterns[symbol_key]:
            print(f"   {symbol_key}: {len(patterns[symbol_key])} patterns")
    
    print(f"\n🎯 Market Regimes:")
    for symbol, regime_data in regimes.items():
        print(f"   {symbol}: {regime_data.get('regime', 'UNKNOWN')}")

if __name__ == "__main__":
    inspect_experience_memory()
    inspect_patterns()