# dashboard/live_dashboard.py
import sys
import os
import time
import threading
import numpy as np
from datetime import datetime, timezone
import pandas as pd
from utils.mt5_gateway import mt5_gateway as mt5

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Enable ANSI colors on Windows
if os.name == 'nt':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

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
        """Start the live dashboard thread-safely and idempotently"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._dashboard_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the dashboard thread-safely and idempotently"""
        if not self.running:
            return
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            self.thread = None
            
    def _dashboard_loop(self):
        """Main dashboard loop with smooth updates"""
        while self.running:
            try:
                self._clear_screen()
                self._display_dashboard()
                self.blink_state = not self.blink_state  # For blinking indicators
                time.sleep(2)  # Smooth 2-second updates
            except Exception as e:
                try:
                    print(f"Dashboard error: {e}")
                except:
                    pass
                time.sleep(5)
                
    def _clear_screen(self):
        """Clear terminal screen"""
        print("\033[H\033[J", end="")
        
    def _display_dashboard(self):
        """Display the professional dashboard from published snapshot"""
        snapshot = self.engine.get_dashboard_snapshot()
        if not snapshot:
            print(" Waiting for market analysis snapshot cycle...")
            return
            
        from utils.snapshot_helper import deep_thaw
        snap_dict = deep_thaw(snapshot)
        
        status_indicator = f"{self.GREEN}🟢{self.RESET}" if self.blink_state else f"{self.YELLOW}🟡{self.RESET}"
        
        print(f" {status_indicator} {self.BOLD}{self.CYAN}PULSE VIPER - SMC PROFESSIONAL EA{self.RESET} {status_indicator}")
        print(f"{self.BLUE}{'=' * 75}{self.RESET}")
        
        utc_now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        print(f" Last Update: {utc_now} | Cycle: {snap_dict.get('cycle_number')}")
        print()
        
        # Account & Portfolio Performance Section
        self._display_trading_performance(snap_dict)
        
        # Market Overview Section
        self._display_market_overview(snap_dict)
        
        # AI Learning Section
        self._display_ai_learning(snap_dict)
        
        # System Status Section
        self._display_system_status(snap_dict)
        
        print()
        print(f"{self.BLUE}{'=' * 75}{self.RESET}")
        print(f" {self.WHITE}Real-time monitoring | Auto-refresh: 2s | Press Ctrl+C to stop trading{self.RESET}")
        
    def _display_market_overview(self, snap_dict):
        """Display market overview with clean layout from snapshot"""
        print(f"📊 {self.BOLD}{self.WHITE}MARKET OVERVIEW (SMC ALIGNMENT){self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        tf_alignment = snap_dict.get("tf_alignment", {})
        if not tf_alignment:
            print("   Waiting for market analysis cycle...")
            print()
            return
            
        regime = snap_dict.get("market", {}).get("regime", "RANGE")
        
        h1_lbl = tf_alignment.get('H1', {}).get('label', 'Neutral')
        m15_lbl = tf_alignment.get('M15', {}).get('label', 'Neutral')
        m5_lbl = tf_alignment.get('M5', {}).get('label', 'Neutral')
        
        bias_str = f"{self.GREEN}🟢 {h1_lbl}{self.RESET}" if "Bullish" in h1_lbl else f"{self.RED}🔴 {h1_lbl}{self.RESET}" if "Bearish" in h1_lbl else f"{self.YELLOW}🟡 {h1_lbl}{self.RESET}"
        sweep_str = f"{self.GREEN}🟢 {m15_lbl}{self.RESET}" if "Bullish" in m15_lbl else f"{self.RED}🔴 {m15_lbl}{self.RESET}" if "Bearish" in m15_lbl else f"{self.WHITE}⚪ {m15_lbl}{self.RESET}"
        mss_str = f"{self.GREEN}🟢 {m5_lbl}{self.RESET}" if "Bullish" in m5_lbl else f"{self.RED}🔴 {m5_lbl}{self.RESET}" if "Bearish" in m5_lbl else f"{self.WHITE}⚪ {m5_lbl}{self.RESET}"
        
        symbols = snap_dict.get("symbols", ())
        symbol = symbols[0] if symbols else "EURUSD"
        
        print(f"   {self.BOLD}{self.YELLOW}{symbol}{self.RESET}")
        print(f"   ├─ H1 Structural Bias  : {bias_str}")
        print(f"   ├─ M15 Liquidity Sweep : {sweep_str}")
        print(f"   ├─ M5 Structure Shift  : {mss_str}")
        print(f"   └─ Market Regime       : {self.CYAN}{regime.upper()}{self.RESET}")
        print()
    
    def _display_trading_performance(self, snap_dict):
        """Display trading performance metrics and active orders using snapshot data"""
        print(f"💰 {self.BOLD}{self.WHITE}ACCOUNT & PORTFOLIO STATUS{self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        acc = snap_dict.get("account", {})
        is_paper = snap_dict.get("risk_status", {}).get("paper_mode", True)
        if is_paper:
            mode_str = f"{self.CYAN}🎮 PAPER TRADING (SIMULATION){self.RESET}"
        else:
            mode_str = f"{self.RED}⚠️ LIVE TRADING (REAL ACCOUNT){self.RESET}"
            
        balance = acc.get("balance", 0.0)
        equity = acc.get("equity", 0.0)
        floating_pnl = acc.get("profit", 0.0)
        pnl_color = self.GREEN if floating_pnl > 0 else self.RED if floating_pnl < 0 else self.WHITE
        
        print(f"   Mode: {mode_str}")
        print(f"   Account Balance: ${balance:,.2f} | Account Equity: ${equity:,.2f}")
        print(f"   Floating PnL: {pnl_color}${floating_pnl:+,.2f}{self.RESET}")
        print()
        
        open_positions = list(snap_dict.get("positions", ()))
        print("   Active Positions:")
        if not open_positions:
            print(f"      {self.WHITE}No active open positions.{self.RESET}")
        else:
            print("      " + "-" * 75)
            print(f"      {'Ticket':<8} | {'Symbol':<8} | {'Action':<6} | {'Lots':<5} | {'Entry':<9} | {'SL':<9} | {'TP':<9} | {'PnL':<8}")
            print("      " + "-" * 75)
            for pos in open_positions:
                pnl = pos.get("pnl", 0.0)
                pos_pnl_color = self.GREEN if pnl > 0 else self.RED if pnl < 0 else self.WHITE
                act_color = self.GREEN if pos.get("action") == 'BUY' else self.RED
                print(f"      {pos.get('ticket'):<8} | {self.YELLOW}{pos.get('symbol'):<8}{self.RESET} | {act_color}{pos.get('action'):<6}{self.RESET} | {pos.get('volume'):<5.2f} | {pos.get('entry'):<9.2f} | {pos.get('sl'):<9.2f} | {pos.get('tp'):<9.2f} | {pos_pnl_color}${pnl:<7.2f}{self.RESET}")
            print("      " + "-" * 75)
        print()
        
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
                
                trades_list = list(self.engine.performance_history)
                win_streak = 0
                loss_streak = 0
                for t in reversed(trades_list):
                    if t.get('pnl', 0) > 0:
                        win_streak += 1
                    elif t.get('pnl', 0) < 0:
                        break
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
    
    def _display_ai_learning(self, snap_dict):
        """Display AI learning progress"""
        print(f"🧠 {self.BOLD}{self.WHITE}AI LEARNING ENGINE{self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        patterns = getattr(self.engine.pattern_learner, 'patterns', {})
        total_patterns = sum(len(p) for p in patterns.values())
        winning_patterns = sum(len(v) for k, v in patterns.items() if k.endswith('_winning'))
        losing_patterns = sum(len(v) for k, v in patterns.items() if k.endswith('_losing'))
        
        print(f"   Experience Buffer Size: {len(self.engine.experience_memory)} / {self.engine.experience_memory.capacity}")
        print(f"   Pattern Database Size: {total_patterns} quantized patterns")
        print(f"   ├─ Winning Patterns   : {self.GREEN}{winning_patterns}{self.RESET}")
        print(f"   └─ Losing Patterns    : {self.RED}{losing_patterns}{self.RESET}")
        print()
    
    def _display_system_status(self, snap_dict):
        """Display system status"""
        print(f"⚙️ {self.BOLD}{self.WHITE}SYSTEM & TERMINAL STATUS{self.RESET}")
        print(f"{self.CYAN}{'-' * 45}{self.RESET}")
        
        status = f"{self.GREEN}🟢 CONNECTED{self.RESET}" if snap_dict.get("connected") else f"{self.RED}🔴 DISCONNECTED{self.RESET}"
        uptime = self._calculate_uptime()
        
        print(f"   MT5 Connection: {status}")
        print(f"   Active Symbols: {self.YELLOW}{', '.join(snap_dict.get('symbols', ()))}{self.RESET}")
        print(f"   Analysis Cycles: {snap_dict.get('cycle_number')}")
        print(f"   System Uptime: {uptime}")
        print(f"   Engine Mode: {snap_dict.get('routing', {}).get('active_strategy', 'smc').upper()}")
    
    def _calculate_uptime(self):
        """Calculate system uptime via monotonic timers"""
        total_seconds = int(time.monotonic() - getattr(self.engine, 'boot_time_monotonic', time.monotonic()))
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