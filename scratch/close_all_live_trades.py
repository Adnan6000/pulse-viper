import MetaTrader5 as mt5
import sys

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        sys.exit(1)
        
    positions = mt5.positions_get()
    if not positions:
        print("No open positions found.")
        mt5.shutdown()
        return
        
    print(f"Found {len(positions)} open position(s)")
    for pos in positions:
        print(f"Closing position: ticket={pos.ticket}, symbol={pos.symbol}, volume={pos.volume}, type={pos.type}")
        action_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": action_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": pos.magic,
            "comment": "manual emergency close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"Successfully closed Ticket {pos.ticket} @ {res.price}")
        else:
            comment = res.comment if res else "None"
            retcode = res.retcode if res else "None"
            print(f"Failed to close Ticket {pos.ticket}: {comment} (retcode: {retcode})")
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
