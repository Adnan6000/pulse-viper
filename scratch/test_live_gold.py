import MetaTrader5 as mt5
import sys

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        sys.exit(1)
        
    symbol = "XAUUSDm"
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"{symbol} not found")
        mt5.shutdown()
        sys.exit(1)
        
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"Failed to get tick for {symbol}")
        mt5.shutdown()
        sys.exit(1)
        
    price = tick.ask
    # Set a stop loss 5.00 dollars below entry, and take profit 10.00 dollars above
    sl = price - 5.0
    tp = price + 10.0
    magic = 123456
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": 0.01,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": magic,
        "comment": " manual gold open test",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Successfully opened trade: Ticket {res.order} @ {res.price}")
        
        # Close the trade immediately
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_SELL,
            "position": res.order,
            "price": mt5.symbol_info_tick(symbol).bid,
            "deviation": 20,
            "magic": magic,
            "comment": "manual gold close test",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        close_res = mt5.order_send(close_request)
        if close_res and close_res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Successfully closed trade: Ticket {close_res.order} @ {close_res.price}")
        else:
            print(f"❌ Failed to close trade: {close_res.comment if close_res else 'None'} | retcode: {close_res.retcode if close_res else 'None'}")
    else:
        print(f"❌ Failed to open trade: {res.comment if res else 'None'} | retcode: {res.retcode if res else 'None'}")
        if res:
            print(f"Details: retcode={res.retcode}, comment={res.comment}, margin={res.margin}, bid={res.bid}, ask={res.ask}")
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
