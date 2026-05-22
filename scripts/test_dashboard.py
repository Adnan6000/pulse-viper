# scripts/test_dashboard.py
import sys
import os
import time
import pandas as pd
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import AdvancedTradingEngine
from dashboard.terminal_dashboard import TerminalDashboard

def test_dashboard():
    """Test the dashboard system"""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    print("🧪 TESTING LIVE DASHBOARD")
    print("=" * 50)
    
    # Create engine with dashboard
    engine = AdvancedTradingEngine(symbols=['XAUUSDm'], enable_dashboard=True)
    
    # Start dashboard
    if engine.dashboard:
        engine.dashboard.start()
        
        print("📊 Dashboard running in background...")
        print("🔄 Simulating market data updates...")
        
        # Simulate some market data for dashboard
        # Pre-populate some mock experiences into engine memory for testing
        if hasattr(engine, 'experience_memory'):
            engine.experience_memory.performance_stats = {
                'total_trades': 5,
                'winning_trades': 3,
                'losing_trades': 2,
                'total_pnl': 150.0,
                'winning_pnl_sum': 250.0,
                'losing_pnl_sum': -100.0,
                'max_win': 120.0,
                'max_loss': -60.0,
                'avg_win': 83.33,
                'avg_loss': -50.0
            }
            # Preload some experiences in the list
            for i in range(5):
                engine.experience_memory.memory.append({
                    'state': {},
                    'action': 1 if i % 2 == 0 else 2,
                    'reward': 50.0 if i % 2 == 0 else -30.0,
                    'next_state': {},
                    'done': True,
                    'timestamp': pd.Timestamp.now(),
                    'metadata': {'symbol': 'GOLD', 'close_reason': 'TP' if i % 2 == 0 else 'SL'}
                })

        # Pre-populate a mock open position in the trade manager
        if hasattr(engine, 'trade_manager'):
            from core.trade_manager import TradePosition
            mock_pos = TradePosition(
                ticket_id=88888,
                symbol='GOLD',
                action='BUY',
                entry_price=2015.50,
                volume=0.5,
                sl=2005.00,
                tp=2035.00,
                timestamp=datetime.now()
            )
            mock_pos.pnl = 45.00
            engine.trade_manager.positions[mock_pos.id] = mock_pos

        try:
            for i in range(10):
                # Update mock market data for dashboard display
                engine.market_state['GOLD'] = {
                    'last_analysis': {
                        'price': 2024.50 + i,
                        'h1_bias': 1,
                        'm15_sweep_type': 1,
                        'm5_mss_signal': 1,
                        'm5_fvg_class': 'pfvg',
                        'support': 2005.00,
                        'resistance': 2035.00,
                        'volatility': 12.5,
                        'hour': 14
                    }
                }
                
                # Add some performance history with PnL
                if len(engine.performance_history) < 5:
                    engine.performance_history.append({
                        'symbol': 'GOLD',
                        'action': 'BUY' if i % 2 == 0 else 'SELL',
                        'pnl': 50.0 if i % 2 == 0 else -30.0,
                        'price': 2024.50 + i,
                        'timestamp': time.time()
                    })
                
                engine.cycle_count += 1
                if not hasattr(engine, 'win_streak'):
                    engine.win_streak = 0
                engine.win_streak = min(engine.win_streak + 1, 10)
                
                time.sleep(3)  # Wait for dashboard updates
                
        except KeyboardInterrupt:
            print("\n🛑 Test stopped")
        
        finally:
            engine.dashboard.stop()
            
    else:
        print("❌ Dashboard not available")

if __name__ == "__main__":
    test_dashboard()