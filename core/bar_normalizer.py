# core/bar_normalizer.py
import hashlib
import pandas as pd
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Tuple, Dict, Any

TIMEFRAME_TO_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400
}

@dataclass(frozen=True)
class TimeframeDataSnapshot:
    symbol: str
    timeframe: str
    bars: tuple  # Tuple of dicts representing OHLCV
    first_bar_time: datetime
    last_closed_bar_time: datetime
    generated_at_utc: datetime
    expected_bar_count: int
    actual_bar_count: int
    missing_bar_count: int
    stale_seconds: float
    data_hash: str

class BarNormalizer:
    """Ensures raw dataframes only contain completed closed bars and logs data health stats."""
    
    @staticmethod
    def normalize(df: pd.DataFrame, symbol: str, timeframe: str) -> TimeframeDataSnapshot:
        """
        Processes a raw DataFrame: converts timestamps, drops forming candle,
        and returns a TimeframeDataSnapshot.
        """
        if df is None or df.empty:
            raise ValueError(f"BarNormalizer: empty data for {symbol} on {timeframe}")

        # Ensure index or time column is datetime
        df = df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
            else:
                raise ValueError("BarNormalizer: DataFrame must have a DatetimeIndex or a 'time' column.")

        df.sort_index(inplace=True)
        
        # Authoritative UTC now
        utc_now = datetime.now(timezone.utc)
        
        # Determine timeframe duration
        duration_sec = TIMEFRAME_TO_SECONDS.get(timeframe, 60)
        
        # Filter out forming bar
        # If index contains tz information, localize/convert. Otherwise assume local/broker time
        # Standardizing all index timestamps to UTC timezone aware
        if not hasattr(df.index, 'tz') or df.index.tz is None:  # type: ignore[union-attr]
            # Assume broker time is close to UTC or convert it
            df.index = df.index.tz_localize(timezone.utc)  # type: ignore[union-attr]
            
        closed_mask = df.index + timedelta(seconds=duration_sec) <= utc_now
        df_closed = df.loc[closed_mask]
        
        if df_closed.empty:
            raise ValueError(f"BarNormalizer: No closed bars found for {symbol} on {timeframe}")
            
        # Stats
        actual_count = len(df_closed)
        first_time = df_closed.index[0].to_pydatetime()
        last_time = df_closed.index[-1].to_pydatetime()
        
        # Expected count based on time difference
        time_diff_sec = (last_time - first_time).total_seconds()
        expected_count = int(time_diff_sec / duration_sec) + 1
        missing_count = max(0, expected_count - actual_count)
        
        stale_sec = max(0.0, (utc_now - (last_time + timedelta(seconds=duration_sec))).total_seconds())
        
        # Convert df rows to list of dicts for freezing
        bars_list = []
        for t, row in df_closed.iterrows():
            bars_list.append({
                "time": t.isoformat(),
                "open": float(row.get("open", 0.0)),
                "high": float(row.get("high", 0.0)),
                "low": float(row.get("low", 0.0)),
                "close": float(row.get("close", 0.0)),
                "tick_volume": int(row.get("tick_volume", 0))
            })
        bars_tuple = tuple(bars_list)
        
        # Generate data hash
        raw_str = f"{symbol}_{timeframe}_{last_time.isoformat()}_{actual_count}_{df_closed.iloc[-1].get('close', 0.0)}"
        data_hash = hashlib.md5(raw_str.encode('utf-8')).hexdigest()
        
        return TimeframeDataSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars_tuple,
            first_bar_time=first_time,
            last_closed_bar_time=last_time,
            generated_at_utc=utc_now,
            expected_bar_count=expected_count,
            actual_bar_count=actual_count,
            missing_bar_count=missing_count,
            stale_seconds=stale_sec,
            data_hash=data_hash
        )
