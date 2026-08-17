# core/intermarket_engine.py
import time
import threading
import logging
from typing import Optional

class IntermarketCorrelationGuard:
    def __init__(self, mt5_interface):
        self.mt5 = mt5_interface
        self.logger = logging.getLogger("PulseViper.CorrelationGuard")
        self.dxy_delta = 0.0
        self.us10y_delta = 0.0
        self.last_update = 0.0
        self.lock = threading.Lock()
        self.active_yield_symbol = None
        self._resolve_yield_symbol()

    def _resolve_yield_symbol(self):
        """
        Dynamically check which symbol representing US 10-Year Treasury Yields
        is active in the broker's MarketWatch.
        """
        for sym in ["US10YR", "UST10Y", "TNOTE"]:
            try:
                # mt5.symbol_select is used to check if a symbol is active or can be enabled
                if self.mt5.symbol_select(sym, True):
                    self.active_yield_symbol = sym
                    self.logger.info(f"✅ Resolved active Treasury Yield symbol: {sym}")
                    return
            except Exception:
                pass
        self.logger.warning("⚠️ No active US 10-Year Treasury Yield symbol found. Falling back to USDX only.")

    def check_correlation_veto(self, intended_direction: str) -> bool:
        """
        Non-blocking look-up to veto trades executing into massive intermarket divergence.
        If DXY or US10Y return is > +0.15% (0.0015) -> veto BUY setups.
        If DXY or US10Y return is < -0.15% (-0.0015) -> veto SELL setups.
        """
        if intended_direction not in ["BUY", "SELL"]:
            return False

        now = time.time()
        # Non-blocking async poll trigger every 60 seconds
        if now - self.last_update > 60.0:
            threading.Thread(target=self._update_intermarket_metrics, daemon=True).start()

        with self.lock:
            # Rule: If buying Gold but DXY or US10Y is pumping, trigger safety veto
            if intended_direction == "BUY":
                if self.dxy_delta > 0.0015 or self.us10y_delta > 0.0015:
                    self.logger.warning(
                        f"🚫 Correlation Veto active on BUY: DXY Delta={self.dxy_delta*100:.3f}%, "
                        f"US10Y Delta={self.us10y_delta*100:.3f}%"
                    )
                    return True
            # Rule: If selling Gold but DXY or US10Y is dumping, trigger safety veto
            elif intended_direction == "SELL":
                if self.dxy_delta < -0.0015 or self.us10y_delta < -0.0015:
                    self.logger.warning(
                        f"🚫 Correlation Veto active on SELL: DXY Delta={self.dxy_delta*100:.3f}%, "
                        f"US10Y Delta={self.us10y_delta*100:.3f}%"
                    )
                    return True

        return False

    def _update_intermarket_metrics(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            # 1. Update DXY (USDX) Delta
            dxy_rates = self.mt5.copy_rates_from_pos("USDX", self.mt5.TIMEFRAME_M5, 0, 2)
            if dxy_rates is None or len(dxy_rates) < 2:
                # Try alternative DXY name
                dxy_rates = self.mt5.copy_rates_from_pos("DXY", self.mt5.TIMEFRAME_M5, 0, 2)
                
            if dxy_rates is not None and len(dxy_rates) >= 2:
                # Delta calculated as (Current Close - Prior Close) / Prior Close
                c0 = float(dxy_rates[-2]['close'])
                c1 = float(dxy_rates[-1]['close'])
                if c0 > 1e-9:
                    self.dxy_delta = (c1 - c0) / c0
            else:
                self.dxy_delta = 0.0

            # 2. Update US10Y Delta (if available)
            if self.active_yield_symbol:
                yield_rates = self.mt5.copy_rates_from_pos(self.active_yield_symbol, self.mt5.TIMEFRAME_M5, 0, 2)
                if yield_rates is not None and len(yield_rates) >= 2:
                    y0 = float(yield_rates[-2]['close'])
                    y1 = float(yield_rates[-1]['close'])
                    if y0 > 1e-9:
                        self.us10y_delta = (y1 - y0) / y0
                else:
                    self.us10y_delta = 0.0
            else:
                self.us10y_delta = 0.0

            self.last_update = time.time()
        except Exception as e:
            self.logger.error(f"Error updating intermarket metrics: {e}")
        finally:
            self.lock.release()
