# utils/symbol_manager.py
import MetaTrader5 as mt5
from typing import List, Dict

class SymbolManager:
    def __init__(self):
        self.available_symbols = []
        self.enabled_symbols = []
    
    def detect_available_symbols(self) -> List[str]:
        """Detect all symbols available in MT5"""
        try:
            all_symbols = mt5.symbols_get()
            self.available_symbols = [s.name for s in all_symbols]
            return self.available_symbols
        except Exception as e:
            print(f"❌ Error detecting symbols: {e}")
            return []
    
    def detect_enabled_symbols(self) -> List[str]:
        """Detect symbols enabled in Market Watch"""
        try:
            all_symbols = mt5.symbols_get()
            self.enabled_symbols = [s.name for s in all_symbols if s.visible]
            return self.enabled_symbols
        except Exception as e:
            print(f"❌ Error detecting enabled symbols: {e}")
            return []
    
    def enable_symbol(self, symbol: str) -> bool:
        """Enable a symbol in Market Watch"""
        try:
            if mt5.symbol_select(symbol, True):
                print(f"✅ Enabled {symbol} in Market Watch")
                return True
            else:
                print(f"❌ Failed to enable {symbol}")
                return False
        except Exception as e:
            print(f"❌ Error enabling {symbol}: {e}")
            return False
    
    def get_major_pairs(self) -> List[str]:
        """Get list of major forex pairs"""
        major_pairs = [
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF',
            'AUDUSD', 'USDCAD', 'NZDUSD'
        ]
        return [p for p in major_pairs if p in self.available_symbols]
    
    def get_commodities(self) -> List[str]:
        """Get list of commodities"""
        commodities = ['XAUUSD', 'XAUUSDm', 'XAGUSD', 'XPTUSD', 'XPDUSD']
        return [c for c in commodities if c in self.available_symbols]
    
    def auto_detect_trading_symbols(self, max_symbols=5) -> List[str]:
        """Automatically detect best symbols to trade"""
        enabled = self.detect_enabled_symbols()
        
        # If we have enabled symbols, use them
        if enabled:
            print(f"🎯 Using {len(enabled)} enabled symbols from Market Watch")
            return enabled[:max_symbols]
        
        # Otherwise, try to enable popular symbols
        symbols_to_try = self.get_major_pairs() + self.get_commodities()
        enabled_symbols = []
        
        for symbol in symbols_to_try[:max_symbols]:
            if self.enable_symbol(symbol):
                enabled_symbols.append(symbol)
        
        return enabled_symbols
    
    def test_symbol_data(self, symbol: str, timeframe=mt5.TIMEFRAME_M15, bars=10) -> bool:
        """Test if we can get data for a symbol"""
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
            return rates is not None and len(rates) >= bars
        except:
            return False

# Global instance
symbol_manager = SymbolManager()