# run.py - CORRECTED VERSION
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import argparse
import traceback

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
        
    parser = argparse.ArgumentParser(description='PulseViper Professional Trading Bot')
    parser.add_argument('--symbols', nargs='+', default=['XAUUSDm'],
                       help='Trading symbols')
    parser.add_argument('--mode', choices=['scalping', 'intraday', 'swing'], 
                       default='intraday', help='Trading mode')
    parser.add_argument('--interval', type=int, default=15,
                       help='Analysis interval in seconds')
    parser.add_argument('--no-dashboard', action='store_true',
                       help='Disable dashboard')
    parser.add_argument('--port', type=int, default=8000,
                       help='Dashboard port')

    args = parser.parse_args()

    print("🐍 PULSE VIPER - ADVANCED TRADING ENGINE")
    print("=" * 50)
    
    try:
        from core.engine import AdvancedTradingEngine
        
        print("✅ AdvancedTradingEngine imported successfully")
        
        engine = AdvancedTradingEngine(
            symbols=args.symbols,
            strategy_mode=args.mode,
            enable_dashboard=not args.no_dashboard,
            port=args.port
        )
        
        print(f"🚀 Starting engine with symbols: {args.symbols}")
        print(f"🎯 Trading mode: {args.mode}")
        print(f"⏰ Analysis interval: {args.interval} seconds")
        print(f"📊 Dashboard: {'ENABLED' if not args.no_dashboard else 'DISABLED'}")
        print(f"🔌 Port: {args.port}")
        
        engine.run_engine(sleep_seconds=args.interval)
        
    except Exception as e:
        print(f"💥 Engine Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()