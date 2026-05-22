# scripts/test_live_execution.py
import MetaTrader5 as mt5
import sys
import os
import time

# Add root folder to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.config import Config
from core.trade_manager import LiveTradeManager
from utils.settings_manager import settings_manager

def main():
    print("Running Live Trade Execution Test...")
    
    # Initialize MT5
    if not mt5.initialize():
        print("Failed to initialize MT5")
        sys.exit(1)
        
    print("MT5 initialized successfully")
    
    # Ensure paper mode is False in settings
    settings_manager.set("paper_mode", False)
    # Set risk_percent to 20.0% to force 0.02 lot size calculation on $10 balance
    settings_manager.set("risk_percent", 20.0)
    
    config = Config()
    manager = LiveTradeManager(config)
    
    symbol = "EURUSDm"
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"Failed to get tick for {symbol}")
        mt5.shutdown()
        sys.exit(1)
        
    bid = tick.bid
    ask = tick.ask
    print(f"Current prices for {symbol}: Bid = {bid:.5f}, Ask = {ask:.5f}")
    
    # Define SL & TP for EURUSDm (5 decimals)
    # SL is 100 points (10 pips) below
    # TP1 is 100 points above, TP2 is 200 points above
    sl_price = round(ask - 0.00100, 5)
    tp1_price = round(ask + 0.00100, 5)
    tp2_price = round(ask + 0.00200, 5)
    
    print(f"Calculated levels: SL = {sl_price:.5f}, TP1 = {tp1_price:.5f}, TP2 = {tp2_price:.5f}")
    
    # Open split positions
    pos = manager.open_position(
        symbol=symbol,
        action="BUY",
        entry_price=ask,
        sl_price=sl_price,
        tp1_price=tp1_price,
        tp2_price=tp2_price
    )
    
    if pos:
        print("Position opening request executed successfully!")
        print(f"Ticket 1: {pos.id} | Vol: {pos.volume:.2f} | SL: {pos.sl:.5f} | TP: {pos.tp:.5f}")
        if pos.sibling_id:
            print(f"Ticket 2 (Sibling): {pos.sibling_id} | TP: {pos.tp2:.5f}")
    else:
        print("Failed to open split positions")
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
