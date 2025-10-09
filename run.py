# run.py - FIXED VERSION
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import argparse
import traceback

def main():
    parser = argparse.ArgumentParser(description='PulseViper Trading Engine')
    parser.add_argument('--symbols', nargs='+', default=['XAUUSDm', 'EURUSD'],
                       help='Trading symbols')
    parser.add_argument('--mode', choices=['scalping', 'intraday', 'swing'], 
                       default='intraday', help='Trading mode')
    parser.add_argument('--interval', type=int, default=15,
                       help='Analysis interval in seconds')
    
    args = parser.parse_args()
    
    print("🐍 PULSE VIPER ULTRA - ENHANCED ENGINE")
    print("=" * 50)
    
    try:
        # Try to import and use the advanced engine
        from core.engine import AdvancedTradingEngine
        
        print("✅ AdvancedTradingEngine imported successfully")
        
        # Use advanced engine
        engine = AdvancedTradingEngine(
            symbols=args.symbols,
            strategy_mode=args.mode
        )
        
        engine.run_engine(sleep_seconds=args.interval)
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("\n🔧 Trying alternative engine...")
        use_alternative_engine(args)
    except Exception as e:
        print(f"💥 Engine Error: {e}")
        traceback.print_exc()

def use_alternative_engine(args):
    """Use a simpler engine if the advanced one fails"""
    print("🔄 Using Alternative Engine...")
    
    import MetaTrader5 as mt5
    import pandas as pd
    import time
    from datetime import datetime
    from utils.mt5_data import init_mt5, shutdown_mt5
    
    class AlternativeEngine:
        def __init__(self, symbols):
            self.symbols = symbols
            self.cycle = 0
            
        def run(self, sleep_seconds=15):
            print(f"🎯 Starting for: {self.symbols}")
            
            if not init_mt5():
                print("❌ MT5 failed")
                return
                
            print("✅ MT5 connected!")
            
            try:
                while True:
                    self.cycle += 1
                    print(f"\n🔄 Cycle {self.cycle} | {datetime.now().strftime('%H:%M:%S')}")
                    print("-" * 40)
                    
                    for symbol in self.symbols:
                        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20)
                        if rates is not None:
                            df = pd.DataFrame(rates)
                            price = df.iloc[-1]['close']
                            
                            # Simple RSI
                            closes = df['close']
                            delta = closes.diff()
                            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                            rs = gain / loss
                            rsi = 100 - (100 / (1 + rs))
                            current_rsi = rsi.iloc[-1] if not rsi.empty else 50
                            
                            if current_rsi < 30:
                                action = "BUY"
                                emoji = "🟢"
                            elif current_rsi > 70:
                                action = "SELL" 
                                emoji = "🔴"
                            else:
                                action = "HOLD"
                                emoji = "⚪"
                                
                            print(f"{emoji} {symbol}: {action} | RSI: {current_rsi:.1f} | Price: {price:.5f}")
                        else:
                            print(f"❌ {symbol}: No data")
                    
                    print(f"⏳ Waiting {sleep_seconds}s...")
                    time.sleep(sleep_seconds)
                    
            except KeyboardInterrupt:
                print("\n🛑 Stopped")
            finally:
                shutdown_mt5()
    
    engine = AlternativeEngine(args.symbols)
    engine.run(args.interval)

if __name__ == "__main__":
    main()