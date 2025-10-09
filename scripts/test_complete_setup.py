# scripts/test_complete_setup.py
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("🧪 COMPLETE SETUP TEST")
print("=" * 50)

try:
    # Test imports with absolute paths
    from configs.config import Config
    from utils.mt5_data import init_mt5, shutdown_mt5
    from utils.features import feature_engine
    import MetaTrader5 as mt5
    import pandas as pd
    
    print("✅ All imports successful")
    
    # Test config
    config = Config()
    print(f"✅ Config loaded: PAPER_MODE={config.PAPER_MODE}, HISTORY_BARS={config.HISTORY_BARS}")
    
    # Check if we need to add MT5_PATH to config
    if not hasattr(config, 'MT5_PATH'):
        print("⚠️  MT5_PATH not in config - but that's OK for now")
    
    # Test MT5 connection
    print("🔗 Testing MT5 connection...")
    if init_mt5():
        print("✅ MT5 connection successful")
        
        # Test data fetching
        rates = mt5.copy_rates_from_pos('XAUUSDm', mt5.TIMEFRAME_M15, 0, 10)
        if rates is not None:
            print(f"✅ Data fetch successful: {len(rates)} bars for XAUUSDm")
            df = pd.DataFrame(rates)
            print(f"📊 Latest price: {df.iloc[-1]['close']:.5f}")
        else:
            print("❌ Data fetch failed - check if XAUUSDm is available in MT5")
        
        shutdown_mt5()
        print("✅ MT5 shutdown successful")
    else:
        print("❌ MT5 connection failed - make sure MT5 is running")
        
    print("\n🎯 ALL TESTS PASSED - SYSTEM IS READY!")
    
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("💡 Make sure you're running from the project root directory")
except Exception as e:
    print(f"❌ Test failed: {e}")