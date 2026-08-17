# utils/mt5_data.py
from utils.mt5_gateway import mt5_gateway as mt5
import pandas as pd

def init_mt5():
    ok = mt5.initialize()
    if not ok:
        raise RuntimeError("MT5 initialize failed - ensure MT5 terminal is running and logged in.")
    return True

def shutdown_mt5():
    mt5.shutdown()

def fetch_ohlcv(symbol='EURUSD', timeframe=mt5.TIMEFRAME_H1, n=1000):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    res_df = pd.DataFrame(df[['open', 'high', 'low', 'close', 'tick_volume']])
    return res_df.rename(columns={'tick_volume': 'volume'})
