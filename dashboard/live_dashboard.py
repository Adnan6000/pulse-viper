# dashboard/live_dashboard.py
import sys
import os
import time
import threading
import numpy as np
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Enable ANSI colors on Windows
if os.name == 'nt':
    os.system('')

class LiveDashboard:
    # Premium ANSI terminal colors
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def __init__(self, trading_engine):
        self.engine = trading_engine
        self.running = False
        self.thread = None
        self.last_update = None
        self.blink_state = False
        
    def start(self):
        """Start the live dashboard"""
        self.running = True
        self.thread = threading.Thread(target=self._dashboard_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the dashboard"""
        self.running = False
        if self.thread:
            self.thread.join()
            
    def _dashboard_loop(self):
        """Main dashboard loop with smooth updates"""
        while self.running:
            try:
                self._clear_screen()
                self._display_dashboard()
                self.blink_state = not self.blink_state  # For blinking indicators
                time.sleep(2)  # Smooth 2-second updates
            except Exception as e:
                # Print to error log if print fails during shutdown
                try:
                    print(f"Dashboard error: {e}")
                except:
                    pass
                time.sleep(5)
                
    def _clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
    def _display_dashboard(self):
        """Display the professional dashboard"""
        # Header with blinking status
        status_indicator = f"{self.GREEN}🟢{self.RESET}" if self.blink_state else f"{self.YELLOW}🟡{self.RESET}"
        
        print(f" {status_indicator} {self.BOLD}{self.CYAN}PULSE VIPER - SMC PROFESSIONAL EA{self.RESET} {status_indicator}")
        print(f"{self.BLUE}{'=' * 75}{self.RESET}")
        print(f" Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} | Cycle: {self.engine.cycle_count}")
        print()
        
        # Account & Portfolio Performance Section
        self._display_trading_performance()
        
        # Market Overview Section
        self._display_market_overview()
        
        # AI Learning Section
        self._display_ai_learning()
        
        # System Status Section
        self._display_system_status()
        
        print()
        print(f"{self.BLUE}{'=' * 75}{self.RESET}")
        print(f" {self.WHITE}Real-time monitoring | Auto-refresh: 2s | Press Ctrl+C to stop trading{self.RESET}")
        
    def _display_market_overview(self):
        """Display market overview with clean layout"""
        print(f"📊 {self.BOLD}{self.WHITE}MARKET OVERVIEW (SMC ALIGNMENT){self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        if not self.engine.market_state:
            print("   Waiting for market analysis cycle...")
            print()
            return
            
        for symbol, state in self.engine.market_state.items():
            if 'last_analysis' in state:
                analysis = state['last_analysis']
                
                # Dynamic check for test structure vs real engine structure
                if 'intraday' in analysis:
                    price = analysis['intraday'].get('price', 0.0)
                    h1_bias = analysis['swing'].get('trend', 0)
                    m15_sweep = 0
                    m5_mss = analysis['intraday'].get('signal', 0)
                    fvg_class = "none"
                    sup = 0.0
                    res = 0.0
                    regime = analysis['swing'].get('regime', 'unknown')
                else:
                    price = analysis.get('price', 0.0)
                    h1_bias = analysis.get('h1_bias', 0)
                    m15_sweep = analysis.get('m15_sweep_type', 0)
                    m5_mss = analysis.get('m5_mss_signal', 0)
                    fvg_class = analysis.get('m5_fvg_class', 'none')
                    sup = analysis.get('support', 0.0)
                    res = analysis.get('resistance', 0.0)
                    regime = self.engine.pattern_learner.get_market_regime(symbol) if hasattr(self.engine, 'pattern_learner') else 'unknown'
                
                # Format variables with colors
                if h1_bias == 1:
                    bias_str = f"{self.GREEN}🟢 BULLISH{self.RESET}"
                elif h1_bias == -1:
                    bias_str = f"{self.RED}🔴 BEARISH{self.RESET}"
                else:
                    bias_str = f"{self.YELLOW}🟡 NEUTRAL{self.RESET}"
                    
                if m15_sweep == 1:
                    sweep_str = f"{self.GREEN}🟢 BULLISH SWEEP{self.RESET}"
                elif m15_sweep == -1:
                    sweep_str = f"{self.RED}🔴 BEARISH SWEEP{self.RESET}"
                else:
                    sweep_str = f"{self.WHITE}⚪ NONE{self.RESET}"
                    
                if m5_mss == 1:
                    mss_str = f"{self.GREEN}🟢 BULLISH MSS{self.RESET}"
                elif m5_mss == -1:
                    mss_str = f"{self.RED}🔴 BEARISH MSS{self.RESET}"
                else:
                    mss_str = f"{self.WHITE}⚪ NONE{self.RESET}"
                
                fvg_color = self.GREEN if fvg_class == 'pfvg' else self.RED if fvg_class == 'rfvg' else self.YELLOW
                fvg_str = f"{fvg_color}{fvg_class.upper()}{self.RESET}"
                
                print(f"   {self.BOLD}{self.YELLOW}{symbol}{self.RESET} | Bid/Close: {self.BOLD}${price:.2f}{self.RESET}")
                print(f"   ├─ H1 Structural Bias  : {bias_str}")
                print(f"   ├─ M15 Liquidity Sweep : {sweep_str}")
                print(f"   ├─ M5 Structure Shift  : {mss_str}")
                print(f"   ├─ M5 FVG Category     : {fvg_str}")
                if sup > 0 and res > 0:
                    print(f"   ├─ M5 Structure Support: ${sup:.2f} | Resistance: ${res:.2f}")
                print(f"   └─ Market Regime       : {self.CYAN}{regime.upper()}{self.RESET}")
                print()
    
    def _display_trading_performance(self):
        """Display trading performance metrics and active orders"""
        print(f"💰 {self.BOLD}{self.WHITE}ACCOUNT & PORTFOLIO STATUS{self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        # Get account balance & equity
        is_paper = getattr(self.engine.config, 'PAPER_MODE', True)
        if is_paper:
            balance = getattr(self.engine.trade_manager, 'virtual_balance', 10000.0)
            equity = getattr(self.engine.trade_manager, 'virtual_equity', 10000.0)
            mode_str = f"{self.CYAN}🎮 PAPER TRADING (SIMULATION){self.RESET}"
        else:
            account = mt5.account_info()
            balance = account.balance if account else 0.0
            equity = account.equity if account else 0.0
            mode_str = f"{self.RED}⚠️ LIVE TRADING (REAL ACCOUNT){self.RESET}"
            
        floating_pnl = equity - balance
        pnl_color = self.GREEN if floating_pnl > 0 else self.RED if floating_pnl < 0 else self.WHITE
        
        print(f"   Mode: {mode_str}")
        print(f"   Account Balance: ${balance:,.2f} | Account Equity: ${equity:,.2f}")
        print(f"   Floating PnL: {pnl_color}${floating_pnl:+,.2f}{self.RESET}")
        print()
        
        # Active Positions Section
        open_positions = []
        if hasattr(self.engine, 'trade_manager') and hasattr(self.engine.trade_manager, 'positions'):
            open_positions = list(self.engine.trade_manager.positions.values())
            
        print("   Active Positions:")
        if not open_positions:
            print(f"      {self.WHITE}No active open positions.{self.RESET}")
        else:
            print("      " + "-" * 75)
            print(f"      {'Ticket':<8} | {'Symbol':<8} | {'Action':<6} | {'Lots':<5} | {'Entry':<9} | {'SL':<9} | {'TP':<9} | {'PnL':<8}")
            print("      " + "-" * 75)
            for pos in open_positions:
                pos_pnl_color = self.GREEN if pos.pnl > 0 else self.RED if pos.pnl < 0 else self.WHITE
                act_color = self.GREEN if pos.action == 'BUY' else self.RED
                print(f"      {pos.id:<8} | {self.YELLOW}{pos.symbol:<8}{self.RESET} | {act_color}{pos.action:<6}{self.RESET} | {pos.volume:<5.2f} | {pos.entry_price:<9.2f} | {pos.sl:<9.2f} | {pos.tp:<9.2f} | {pos_pnl_color}${pos.pnl:<7.2f}{self.RESET}")
            print("      " + "-" * 75)
        print()
        
        # Closed Trade Stats from ExperienceMemory
        print("   Closed Trade Performance:")
        if hasattr(self.engine, 'experience_memory'):
            metrics = self.engine.experience_memory.get_performance_metrics()
            total_trades = metrics.get('total_trades', 0)
            
            if total_trades == 0:
                print(f"      {self.WHITE}No closed trades recorded yet.{self.RESET}")
            else:
                win_rate = metrics.get('win_rate', 0.0)
                profit_factor = metrics.get('profit_factor', 0.0)
                total_pnl = metrics.get('total_pnl', 0.0)
                winning_trades = metrics.get('winning_trades', 0)
                losing_trades = metrics.get('losing_trades', 0)
                avg_win = metrics.get('avg_win', 0.0)
                avg_loss = metrics.get('avg_loss', 0.0)
                
                pnl_total_color = self.GREEN if total_pnl > 0 else self.RED if total_pnl < 0 else self.WHITE
                
                # Calculate current streaks from performance history
                trades_list = list(self.engine.performance_history)
                win_streak = 0
                loss_streak = 0
                # Calculate current win streak
                for t in reversed(trades_list):
                    if t.get('pnl', 0) > 0:
                        win_streak += 1
                    elif t.get('pnl', 0) < 0:
                        break
                # Calculate current loss streak
                for t in reversed(trades_list):
                    if t.get('pnl', 0) < 0:
                        loss_streak += 1
                    elif t.get('pnl', 0) > 0:
                        break
                
                print(f"      Total Trades Closed: {total_trades} (Wins: {self.GREEN}{winning_trades}{self.RESET} / Losses: {self.RED}{losing_trades}{self.RESET})")
                print(f"      Win Rate: {self.BOLD}{win_rate:.1f}%{self.RESET} | Profit Factor: {self.BOLD}{profit_factor:.2f}{self.RESET}")
                print(f"      Average Win: ${avg_win:.2f} | Average Loss: ${avg_loss:.2f}")
                print(f"      Streaks: Current Win Streak: {self.GREEN}{win_streak}{self.RESET} | Loss Streak: {self.RED}{loss_streak}{self.RESET}")
                print(f"      Closed Trade PnL: {pnl_total_color}${total_pnl:+.2f}{self.RESET}")
        else:
            print("      No experience memory stats available.")
        print()
    
    def _display_ai_learning(self):
        """Display AI learning progress"""
        print(f"🧠 {self.BOLD}{self.WHITE}AI LEARNING ENGINE{self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        if not hasattr(self.engine, 'experience_memory'):
            print("   Learning system initializing...")
            print()
            return
            
        memory_size = len(self.engine.experience_memory)
        
        if memory_size == 0:
            print("   Collecting training experiences...")
            print()
            return
            
        # Pattern learning stats
        if hasattr(self.engine, 'pattern_learner'):
            patterns = self.engine.pattern_learner.patterns
            total_patterns = sum(len(p) for p in patterns.values())
            
            # Sum all winning/losing patterns dynamically across all symbols
            winning_patterns = sum(len(v) for k, v in patterns.items() if k.endswith('_winning'))
            losing_patterns = sum(len(v) for k, v in patterns.items() if k.endswith('_losing'))
        else:
            total_patterns = winning_patterns = losing_patterns = 0
        
        print(f"   Experience Buffer Size: {memory_size} / {self.engine.experience_memory.capacity}")
        print(f"   Pattern Database Size: {total_patterns} quantized patterns")
        print(f"   ├─ Winning Patterns   : {self.GREEN}{winning_patterns}{self.RESET}")
        print(f"   └─ Losing Patterns    : {self.RED}{losing_patterns}{self.RESET}")
        print()
    
    def _display_system_status(self):
        """Display system status"""
        print(f"⚙️ {self.BOLD}{self.WHITE}SYSTEM & TERMINAL STATUS{self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        status = f"{self.GREEN}🟢 CONNECTED{self.RESET}" if self.engine.connected else f"{self.RED}🔴 DISCONNECTED{self.RESET}"
        uptime = self._calculate_uptime()
        
        print(f"   MT5 Connection: {status}")
        print(f"   Active Symbols: {self.YELLOW}{', '.join(self.engine.symbols)}{self.RESET}")
        print(f"   Analysis Cycles: {self.engine.cycle_count}")
        print(f"   System Uptime: {uptime}")
        print(f"   Engine Mode: {self.engine.strategy_mode.upper()}")
    
    def _calculate_uptime(self):
        """Calculate system uptime"""
        if self.engine.cycle_count == 0:
            return "0s"
        
        total_seconds = self.engine.cycle_count * 15  # Estimate based on interval
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

# Factory function for easy dashboard creation
def create_dashboard(engine):
    """Create and return a dashboard instance"""
    return LiveDashboard(engine)