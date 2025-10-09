# scripts/test_mt5.py
import MetaTrader5 as mt5
import time

print("Connecting to MT5...")
ok = mt5.initialize()
print("mt5.initialize() ->", ok)

try:
    ver = mt5.version()
except Exception as e:
    ver = f"error: {e}"
print("MT5 version:", ver)

# Get all symbols
symbols = mt5.symbols_get()
print(f"Total symbols available: {len(symbols)}")
print("Symbols available (sample 10):", [s.name for s in symbols[:10]])

# Use XAUUSDm since it's available in your account
symbol_to_test = "XAUUSDm"
print(f"Testing with symbol: {symbol_to_test}")

# Make sure symbol is selected in Market Watch
mt5.symbol_select(symbol_to_test, True)

# Wait a moment for symbol to be selected
time.sleep(1)

# Fetch recent rates
rates = mt5.copy_rates_from_pos(symbol_to_test, mt5.TIMEFRAME_H1, 0, 10)

if rates is not None:
    print(f"Rates sample length for {symbol_to_test}: {len(rates)}")
    if len(rates) > 0:
        print(f"First rate: {rates[0]}")
        print(f"Latest price: {rates[-1]['close']}")
else:
    print(f"Failed to get rates for {symbol_to_test}")
    # Try alternative method
    rates_alt = mt5.copy_rates_from(symbol_to_test, mt5.TIMEFRAME_H1, time.time() - 3600*24, 10)
    if rates_alt is not None:
        print(f"Alternative method result length: {len(rates_alt)}")
    else:
        print("Both methods failed to get rates")

mt5.shutdown()
print("MT5 shutdown ok")