# scratch/test_phase8_modules.py
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# Ensure workspace path is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.market_regime import MarketRegimeDetector, RegimeType
from core.liquidity_map import LiquidityMap
from core.risk_engine import DynamicRiskEngine
from core.news_engine import NewsIntelligenceEngine

def test_market_regime():
    print("Testing MarketRegimeDetector...")
    # Create trending data (linear upward slope)
    trending_data = {
        'high': np.linspace(100, 200, 50),
        'low': np.linspace(95, 195, 50),
        'close': np.linspace(98, 198, 50),
        'atr': np.ones(50) * 5.0
    }
    df_trend = pd.DataFrame(trending_data)
    regime_trend = MarketRegimeDetector.detect_regime(df_trend, rvol_val=1.5)
    print(f"  Trending data regime: {regime_trend.name} (Expected: TRENDING or CHAOTIC)")

    # Create consolidation data (small range oscillations)
    consol_data = {
        'high': [100.0 + (i % 2) * 2.0 for i in range(50)],
        'low': [97.0 - (i % 2) * 2.0 for i in range(50)],
        'close': [98.5 + (i % 2) * 1.0 for i in range(50)],
        'atr': np.ones(50) * 2.0
    }
    df_consol = pd.DataFrame(consol_data)
    regime_consol = MarketRegimeDetector.detect_regime(df_consol, rvol_val=0.5)
    print(f"  Consolidation data regime: {regime_consol.name} (Expected: COMPRESSION or RANGE)")

def test_liquidity_map():
    print("\nTesting LiquidityMap...")
    lm = LiquidityMap()
    
    # Create mock H1 data
    df_h1 = pd.DataFrame({
        'high': [2000.0, 2001.0, 2000.5] + [1990.0] * 30,
        'low': [1980.0, 1979.5, 1980.2] + [1990.0] * 30,
        'atr': [5.0] * 33
    })
    
    # Create mock D1 data
    df_d1 = pd.DataFrame({
        'high': [2010.0, 2015.0],
        'low': [1970.0, 1965.0]
    })
    
    # Update pools
    lm.update_pools(df_d1=df_d1, df_h1=df_h1, asian_range=(1995.0, 1985.0))
    print(f"  Resting pools: {lm.get_resting_pools()}")
    
    # Check sweeps (price goes above PDH at 2015.0, high is 2016.0)
    sweeps = lm.check_sweeps(current_price=2016.0, atr=5.0)
    print(f"  Sweeps at 2016.0: {sweeps}")
    
    # Check that touched pool touch-count is incremented
    pdh_pool = lm.pools.get("PDH")
    if pdh_pool:
        print(f"  PDH touches after sweep: {pdh_pool['touches']}")

def test_risk_engine():
    print("\nTesting DynamicRiskEngine...")
    re = DynamicRiskEngine()
    
    # Test case 1: Standard normal conditions
    risk1 = re.calculate_risk_percent(
        current_atr=2.0, median_atr=2.0,
        current_spread=5.0, max_spread=20.0,
        confidence=1.0, active_positions=0,
        base_risk=1.0
    )
    print(f"  Standard risk: {risk1:.2f}% (Expected: ~1.00%)")
    
    # Test case 2: High spread (should cut risk to 0%)
    risk2 = re.calculate_risk_percent(
        current_atr=2.0, median_atr=2.0,
        current_spread=25.0, max_spread=20.0,
        confidence=1.0, active_positions=0,
        base_risk=1.0
    )
    print(f"  High spread risk: {risk2:.2f}% (Expected: 0.10% due to hard clipping bounds)")

    # Test case 3: High volatility (risk scales down)
    risk3 = re.calculate_risk_percent(
        current_atr=5.0, median_atr=2.0,
        current_spread=5.0, max_spread=20.0,
        confidence=1.0, active_positions=0,
        base_risk=1.0
    )
    print(f"  High volatility risk: {risk3:.2f}% (Expected: < 1.00%)")

def test_news_engine():
    print("\nTesting NewsIntelligenceEngine...")
    ne = NewsIntelligenceEngine()
    
    # Load fallback calendar
    ne._load_fallback_events()
    print(f"  Loaded {len(ne.events)} fallback news events.")
    
    # Find one high impact event
    event = ne.events[0]
    event_time = datetime.strptime(event["date_iso"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    print(f"  Test event: {event['event']} at {event['date_iso']}")
    
    # Test lockout: exactly 10 minutes before the event
    test_time = event_time - timedelta(minutes=10)
    locked, reason = ne.is_execution_locked(test_time, lockout_mins=30, cooldown_mins=15)
    print(f"  Is locked 10 mins before? {locked} (Reason: {reason})")
    
    # Test cooldown: exactly 5 minutes after the event
    test_time_post = event_time + timedelta(minutes=5)
    locked_post, reason_post = ne.is_execution_locked(test_time_post, lockout_mins=30, cooldown_mins=15)
    print(f"  Is locked 5 mins after? {locked_post} (Reason: {reason_post})")
    
    # Test outside: 45 minutes before the event
    test_time_out = event_time - timedelta(minutes=45)
    locked_out, reason_out = ne.is_execution_locked(test_time_out, lockout_mins=30, cooldown_mins=15)
    print(f"  Is locked 45 mins before? {locked_out}")

if __name__ == "__main__":
    print("=== STARTING PHASE 8 MODULES TEST ===")
    test_market_regime()
    test_liquidity_map()
    test_risk_engine()
    test_news_engine()
    print("=== TESTS COMPLETED ===")
