
from utils.mt5_gateway import mt5_gateway as mt5
from datetime import datetime, timedelta
from core.safety_engine import SafetyEngine

if not mt5.initialize():
    print("MT5 init failed")
else:
    safety = SafetyEngine()
    print("SafetyEngine.get_stats():", safety.get_stats())
    
    # Check MT5 history deals
    print("\nChecking MT5 history deals (last 30 days):")
    now = datetime.now()
    start_consec = now - timedelta(days=30)
    deals_all = mt5.history_deals_get(start_consec, now)
    if deals_all:
        deals_recent = sorted(
            [d for d in deals_all if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT)],
            key=lambda x: x.time
        )
        for d in reversed(deals_recent):
            net_pnl = d.profit + d.commission + d.swap
            print(f"Deal time: {datetime.fromtimestamp(d.time)}, Profit: {d.profit:.2f}, Commission: {d.commission:.2f}, Swap: {d.swap:.2f}, Net: {net_pnl:.2f}")
    mt5.shutdown()
