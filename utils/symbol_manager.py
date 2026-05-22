# utils/symbol_manager.py
import MetaTrader5 as mt5
from typing import List, Dict, Any

class SymbolManager:
    def __init__(self):
        self.available_symbols = []
        self.enabled_symbols = []
    
    def detect_available_symbols(self) -> List[str]:
        """Detect all symbols available in MT5"""
        try:
            all_symbols = mt5.symbols_get()
            if all_symbols:
                self.available_symbols = [s.name for s in all_symbols]
            else:
                self.available_symbols = []
            return self.available_symbols
        except Exception as e:
            print(f"❌ Error detecting symbols: {e}")
            return []
    
    def detect_enabled_symbols(self) -> List[str]:
        """Detect symbols enabled in Market Watch"""
        try:
            all_symbols = mt5.symbols_get()
            if all_symbols:
                self.enabled_symbols = [s.name for s in all_symbols if s.visible]
            else:
                self.enabled_symbols = []
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
        commodities = ['XAUUSD', 'XAUUSDm', 'XAUUSDc', 'GOLD', 'XAGUSD', 'XPTUSD', 'XPDUSD']
        return [c for c in commodities if c in self.available_symbols]
    
    def auto_detect_trading_symbols(self, max_symbols=5) -> List[str]:
        """Automatically detect best symbols to trade"""
        enabled = self.detect_enabled_symbols()
        
        # If we have enabled symbols, use them
        if enabled:
            # Prioritize Gold if enabled
            gold_syms = ['XAUUSDm', 'XAUUSDc', 'GOLD', 'XAUUSD']
            gold_enabled = [g for g in gold_syms if g in enabled]
            other_enabled = [s for s in enabled if s not in gold_syms]
            return (gold_enabled + other_enabled)[:max_symbols]
        
        # Otherwise, try to detect popular symbols
        self.detect_available_symbols()
        symbols_to_try = self.get_commodities() + self.get_major_pairs()
        enabled_symbols = []
        
        for symbol in symbols_to_try:
            if len(enabled_symbols) >= max_symbols:
                break
            if symbol in self.available_symbols and self.enable_symbol(symbol):
                enabled_symbols.append(symbol)
        
        return enabled_symbols
    
    def get_broker_profile(self, symbol: str) -> Dict[str, Any]:
        """
        Detect broker server details and adjust specifications for symbol:
        XM, Exness Standard, Exness Cent, etc.
        """
        profile = {
            "broker": "GENERIC",
            "account_type": "STANDARD",
            "symbol": symbol,
            "contract_size": 100.0,
            "max_spread_points": 40,
            "is_cent_account": False,
            "pip_factor": 1.0
        }
        
        try:
            account = mt5.account_info()
            symbol_info = mt5.symbol_info(symbol)
            
            if symbol_info:
                profile["contract_size"] = symbol_info.trade_contract_size
            
            company = account.company.upper() if account else "GENERIC"
            server = account.server.upper() if account else "GENERIC"
            
            usd_limit = 0.4  # Generic default
            
            # Detect Exness
            if "EXNESS" in company or "EXNESS" in server:
                profile["broker"] = "EXNESS"
                if symbol.endswith("c") or "CENT" in server or (account and account.currency == "USC"):
                    profile["account_type"] = "CENT"
                    profile["is_cent_account"] = True
                    usd_limit = 5.0  # Relaxed to 5.0 USD spread limit for Gold/Forex cent
                else:
                    profile["account_type"] = "STANDARD"
                    usd_limit = 4.5  # Relaxed to 4.5 USD spread limit for Gold/Forex standard
                    
            # Detect XM
            elif "XM" in company or "XM" in server or symbol == "GOLD":
                profile["broker"] = "XM"
                profile["account_type"] = "STANDARD"
                usd_limit = 5.0  # Relaxed to 5.0 USD spread limit for Gold
                
            # Fallback based on symbol name
            else:
                if symbol == "GOLD":
                    profile["broker"] = "XM"
                    usd_limit = 5.0
                elif symbol == "XAUUSDc":
                    profile["broker"] = "EXNESS"
                    profile["account_type"] = "CENT"
                    profile["is_cent_account"] = True
                    usd_limit = 5.0
                elif symbol == "XAUUSDm":
                    profile["broker"] = "EXNESS"
                    usd_limit = 4.5
                else:
                    usd_limit = 2.0
            
            if symbol_info and symbol_info.point > 0:
                profile["max_spread_points"] = int(round(usd_limit / symbol_info.point))
            else:
                profile["max_spread_points"] = int(usd_limit * 100)
                
        except Exception as e:
            print(f"⚠️ Error getting broker profile: {e}")
            
        return profile

    def test_symbol_data(self, symbol: str, timeframe=mt5.TIMEFRAME_M15, bars=10) -> bool:
        """Test if we can get data for a symbol"""
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
            return rates is not None and len(rates) >= bars
        except:
            return False

# Global instance
symbol_manager = SymbolManager()