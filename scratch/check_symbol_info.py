import MetaTrader5 as mt5

if not mt5.initialize():
    print("Failed to initialize MT5")
    exit()

symbol = "XAUUSDm"
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    print(f"Symbol {symbol} not found")
else:
    print(f"Symbol: {symbol_info.name}")
    print(f"Bid: {symbol_info.bid}, Ask: {symbol_info.ask}")
    print(f"Point: {symbol_info.point}")
    print(f"Tick Size: {symbol_info.trade_tick_size}")
    print(f"Tick Value: {symbol_info.trade_tick_value}")
    print(f"Min Vol: {symbol_info.volume_min}")
    print(f"Step Vol: {symbol_info.volume_step}")
    print(f"Trade mode: {symbol_info.trade_mode}")
    print(f"Trade Contract Size: {symbol_info.trade_contract_size}")

account_info = mt5.account_info()
if account_info:
    print(f"Account Balance: {account_info.balance}")
    print(f"Account Equity: {account_info.equity}")
    print(f"Leverage: {account_info.leverage}")

mt5.shutdown()
