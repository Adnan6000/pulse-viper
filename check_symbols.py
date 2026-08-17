
from utils.mt5_gateway import mt5_gateway as mt5
import pandas as pd

if not mt5.initialize():
    print("mt5.initialize failed!")
    mt5.shutdown()
else:
    symbols = mt5.symbols_get()
    print(f"Total symbols: {len(symbols)}")
    print("First 20 symbols:")
    for s in symbols[:20]:
        print(s.name)
    
    gold_symbols = [s.name for s in symbols if 'XAU' in s.name.upper() or 'GOLD' in s.name.upper()]
    print("\nGold symbols:")
    for s in gold_symbols:
        print(s)
    mt5.shutdown()
