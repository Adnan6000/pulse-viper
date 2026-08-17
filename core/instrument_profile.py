# core/instrument_profile.py
from dataclasses import dataclass
from typing import Tuple, Dict

@dataclass(frozen=True)
class InstrumentProfile:
    profile_id: str
    symbol_family: str
    asset_class: str

    point: float
    tick_size: float
    contract_size: float

    volume_source_quality: str
    weekend_trading: bool
    session_model: str

    maximum_spread_atr_ratio: float
    minimum_tick_coverage: float
    allowed_modes: Tuple[str, ...]

INSTRUMENT_REGISTRY: Dict[str, InstrumentProfile] = {
    "XAUUSD": InstrumentProfile(
        profile_id="XAUUSD",
        symbol_family="GOLD",
        asset_class="METALS",
        point=0.01,
        tick_size=0.01,
        contract_size=100.0,
        volume_source_quality="MEDIUM",
        weekend_trading=False,
        session_model="23_5",
        maximum_spread_atr_ratio=0.15,
        minimum_tick_coverage=0.90,
        allowed_modes=("scalping", "intraday", "swing")
    ),
    "EURUSD": InstrumentProfile(
        profile_id="EURUSD",
        symbol_family="FOREX_MAJOR",
        asset_class="FX",
        point=0.00001,
        tick_size=0.00001,
        contract_size=100000.0,
        volume_source_quality="LOW",
        weekend_trading=False,
        session_model="24_5",
        maximum_spread_atr_ratio=0.10,
        minimum_tick_coverage=0.95,
        allowed_modes=("scalping", "intraday", "swing")
    ),
    "BTCUSD": InstrumentProfile(
        profile_id="BTCUSD",
        symbol_family="CRYPTO_MAJOR",
        asset_class="CRYPTO",
        point=0.01,
        tick_size=0.01,
        contract_size=1.0,
        volume_source_quality="HIGH",
        weekend_trading=True,
        session_model="24_7",
        maximum_spread_atr_ratio=0.20,
        minimum_tick_coverage=0.80,
        allowed_modes=("scalping", "intraday")
    ),
    "NAS100": InstrumentProfile(
        profile_id="NAS100",
        symbol_family="INDEX_US",
        asset_class="EQUITY_INDEX",
        point=0.01,
        tick_size=0.01,
        contract_size=10.0,
        volume_source_quality="HIGH",
        weekend_trading=False,
        session_model="US_MARKETS",
        maximum_spread_atr_ratio=0.25,
        minimum_tick_coverage=0.85,
        allowed_modes=("intraday", "swing")
    )
}

def get_instrument_profile(symbol: str) -> InstrumentProfile:
    """Retrieves or builds a profile for ANY MT5 broker symbol (Forex, Gold, Crypto, Indices, Energies)."""
    from utils.mt5_gateway import mt5_gateway as mt5
    sym_up = symbol.upper()
    info = mt5.symbol_info(symbol)
    
    # 1. Determine Asset Family & Class
    if any(c in sym_up for c in ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "MATIC", "BNB", "LINK", "LTC"]):
        sym_family = "CRYPTO_MAJOR"
        asset_class = "CRYPTO"
        weekend_trading = True
        session_model = "24_7"
        spread_atr_ratio = 0.25
        allowed = ("scalping", "intraday", "swing")
    elif any(m in sym_up for m in ["XAU", "GOLD", "XAG", "SILVER", "XPT", "XPD"]):
        sym_family = "GOLD"
        asset_class = "METALS"
        weekend_trading = False
        session_model = "23_5"
        spread_atr_ratio = 0.20
        allowed = ("scalping", "intraday", "swing")
    elif any(idx in sym_up for idx in ["US30", "US100", "US500", "NAS100", "SPX500", "GER30", "GER40", "UK100", "JPN225", "USTEC", "DE30", "DE40"]):
        sym_family = "INDEX"
        asset_class = "EQUITY_INDEX"
        weekend_trading = False
        session_model = "US_MARKETS"
        spread_atr_ratio = 0.25
        allowed = ("scalping", "intraday", "swing")
    elif any(n in sym_up for n in ["USOIL", "UKOIL", "WTI", "BRENT", "XTI", "XBR", "NATGAS"]):
        sym_family = "ENERGY"
        asset_class = "COMMODITIES"
        weekend_trading = False
        session_model = "23_5"
        spread_atr_ratio = 0.20
        allowed = ("scalping", "intraday", "swing")
    else:
        sym_family = "FX_MAJOR" if any(fx in sym_up for fx in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]) else "FX_MINOR"
        asset_class = "FX"
        weekend_trading = False
        session_model = "24_5"
        spread_atr_ratio = 0.15
        allowed = ("scalping", "intraday", "swing")
        
    point_val = info.point if (info and hasattr(info, 'point') and info.point > 0) else (0.01 if asset_class in ["CRYPTO", "METALS", "EQUITY_INDEX"] else 0.00001)
    tick_val = info.trade_tick_size if (info and hasattr(info, 'trade_tick_size') and info.trade_tick_size > 0) else point_val
    contract_val = info.trade_contract_size if (info and hasattr(info, 'trade_contract_size') and info.trade_contract_size > 0) else (1.0 if asset_class == "CRYPTO" else (100.0 if asset_class == "METALS" else 100000.0))

    return InstrumentProfile(
        profile_id=symbol,
        symbol_family=sym_family,
        asset_class=asset_class,
        point=point_val,
        tick_size=tick_val,
        contract_size=contract_val,
        volume_source_quality="HIGH" if asset_class in ["CRYPTO", "EQUITY_INDEX"] else "MEDIUM",
        weekend_trading=weekend_trading,
        session_model=session_model,
        maximum_spread_atr_ratio=spread_atr_ratio,
        minimum_tick_coverage=0.85,
        allowed_modes=allowed
    )
