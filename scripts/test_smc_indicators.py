# scripts/test_smc_indicators.py
import sys
import os
import time
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import MetaTrader5 as mt5
from utils.mt5_data import init_mt5, shutdown_mt5
from utils.smc_indicators import SMCIndicators

def main():
    print("🧪 TESTING SMC/ICT INDICATOR ENGINE")
    print("=" * 50)
    
    if not init_mt5():
        print("❌ MT5 Initialization failed")
        return
        
    print("✅ Connected to MT5")
    
    # Auto-detect Gold symbol with retries
    gold_symbol = None
    for attempt in range(5):
        all_symbols = mt5.symbols_get()
        if all_symbols:
            available_symbols = [s.name for s in all_symbols]
            print(f"📊 Total symbols loaded: {len(available_symbols)}")
            for sym in ['GOLD', 'XAUUSDm', 'XAUUSD']:
                if sym in available_symbols:
                    gold_symbol = sym
                    break
            if gold_symbol:
                break
        print("⏳ Waiting for MT5 symbols to load...")
        time.sleep(1.5)
    if not gold_symbol:
        print("❌ Gold symbol not found in available symbols")
        shutdown_mt5()
        return
        
    print(f"📊 Gold symbol selected: {gold_symbol}")
    mt5.symbol_select(gold_symbol, True)
    time.sleep(1)
    
    # Fetch 500 bars on M15 timeframe
    print(f"📥 Fetching 500 historical bars of {gold_symbol} on M15...")
    rates = mt5.copy_rates_from_pos(gold_symbol, mt5.TIMEFRAME_M15, 0, 500)
    
    if rates is None or len(rates) == 0:
        print("❌ Failed to fetch rates from MT5")
        shutdown_mt5()
        return
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'tick_volume']].rename(columns={'tick_volume': 'volume'})
    
    print(f"✅ Data fetched successfully. Shape: {df.shape}")
    print("🔄 Running SMC Indicators...")
    
    smc_df = SMCIndicators.compute_smc_features(df, window=2)
    
    print("=" * 50)
    print("📊 SMC ANALYSIS RESULTS SUMMARY")
    print("=" * 50)
    print(f"Total bars analyzed: {len(smc_df)}")
    print(f"Detected Swing Highs: {smc_df['is_swing_high'].sum()}")
    print(f"Detected Swing Lows:  {smc_df['is_swing_low'].sum()}")
    print(f"Detected STH (followed by bearish FVG): {smc_df['is_sth'].sum()}")
    print(f"Detected STL (followed by bullish FVG): {smc_df['is_stl'].sum()}")
    print(f"Detected ITH (Intermediate Highs):      {smc_df['is_ith'].sum()}")
    print(f"Detected ITL (Intermediate Lows):       {smc_df['is_itl'].sum()}")
    print(f"Detected FVGs (Total): {smc_df[smc_df['fvg_type'] != 0].shape[0]}")
    print(f"  └─ Perfect FVGs (PFVG): {smc_df[smc_df['fvg_class'] == 'pfvg'].shape[0]}")
    print(f"  └─ Rejection FVGs (RFVG): {smc_df[smc_df['fvg_class'] == 'rfvg'].shape[0]}")
    print(f"  └─ Breakaway Gaps (BAG): {smc_df[smc_df['fvg_class'] == 'bag'].shape[0]}")
    print(f"Detected Liquidity Sweeps (Sweeps): {smc_df[smc_df['liq_sweep_type'] != 0].shape[0]}")
    print(f"Detected Market Structure Shifts (MSS): {smc_df[smc_df['mss_signal'] != 0].shape[0]}")
    
    # Print the latest 5 signals
    print("\n🔍 LATEST 5 SIGNALS DETECTED:")
    recent_signals = smc_df[(smc_df['mss_signal'] != 0) | (smc_df['liq_sweep_type'] != 0)].tail(5)
    for idx, row in recent_signals.iterrows():
        print(f"🕒 {idx.strftime('%Y-%m-%d %H:%M')} | Close: {row['close']:.2f}")
        if row['mss_signal'] != 0:
            direction = "BULLISH" if row['mss_signal'] == 1 else "BEARISH"
            print(f"  📢 MSS (Market Structure Shift): {direction}")
        if row['liq_sweep_type'] != 0:
            sweep_dir = "BULLISH (Swept Low)" if row['liq_sweep_type'] == 1 else "BEARISH (Swept High)"
            print(f"  🏹 Liquidity Sweep: {sweep_dir} @ level {row['liq_sweep_level']:.2f}")
            
    shutdown_mt5()
    print("=" * 50)
    print("✅ TEST COMPLETE")

if __name__ == "__main__":
    main()
