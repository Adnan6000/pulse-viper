# utils/order_flow_engine.py
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any
from utils.mt5_gateway import mt5_gateway as mt5

class OrderFlowEngine:
    def __init__(self, tick_lookback: int = 50000):
        self.logger = logging.getLogger("PulseViper.OrderFlowEngine")
        self.tick_lookback = tick_lookback
        # Cached structure to preserve intra-candle calculations across cycles
        self.cvd_session_sum = 0.0
        self.last_processed_timestamp = 0

    def fetch_and_build_footprint(
        self, symbol: str, candle_start_time: datetime, candle_end_time: datetime, tick_size: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ingests real trade ticks directly from MT5 across the candle interval window,
        allocates transactional volume to price bins, and isolates structural footprints.
        """
        # Ensure UTC handling to prevent local machine timezone drift errors
        if candle_start_time.tzinfo is None:
            candle_start_time = candle_start_time.replace(tzinfo=timezone.utc)
        if candle_end_time.tzinfo is None:
            candle_end_time = candle_end_time.replace(tzinfo=timezone.utc)

        # Dynamically resolve tick size from symbol info if not specified
        if tick_size is None or tick_size <= 0:
            tick_size = 0.25 # Fallback default
            try:
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is not None:
                    tick_size = getattr(symbol_info, 'trade_tick_size', 0.25)
                    if tick_size <= 0:
                        tick_size = 0.25
            except Exception as e:
                self.logger.warning(f"Error fetching tick size for {symbol}: {e}")

        # Convert to integer Unix timestamps for timezone bypass
        start_ts = int(candle_start_time.timestamp())
        end_ts = int(candle_end_time.timestamp())

        # Pull raw tick stream
        ticks = mt5.copy_ticks_range(symbol, start_ts, end_ts, mt5.COPY_TICKS_ALL)
        
        if ticks is None or len(ticks) == 0:
            return self._generate_empty_footprint()

        # Extract structured data arrays via DataFrame
        df_ticks = pd.DataFrame(ticks)
        
        # MT5 Flag Definitions:
        # TICK_FLAG_BUY (1024) -> Last trade was a Buy (executed at Ask)
        # TICK_FLAG_SELL (2048) -> Last trade was a Sell (executed at Bid)
        flags = df_ticks['flags'].values
        prices = df_ticks['last'].values
        volumes = df_ticks['volume'].values
        
        # Fallback to bid/ask levels if the broker terminal does not fill the 'last' print column
        if np.all(prices == 0):
            prices = df_ticks['bid'].values

        # Fallback for OTC CFD markets (where volume is 0 or not populated on ticks)
        # We use the standard Tick Rule to classify quote directions and model volume as 1.0 per tick
        total_vol_raw = np.sum(volumes)
        if total_vol_raw <= 0:
            volumes = np.ones(len(prices))  # Model each quote tick as 1.0 volume
            diffs = np.zeros(len(prices))
            diffs[1:] = np.diff(prices)
            is_buy = diffs > 0
            is_sell = diffs < 0
            
            # Forward-fill zero difference ticks
            directions = np.zeros(len(prices))
            directions[is_buy] = 1
            directions[is_sell] = -1
            curr_dir = 0
            for idx in range(len(directions)):
                if directions[idx] != 0:
                    curr_dir = directions[idx]
                else:
                    directions[idx] = curr_dir if curr_dir != 0 else 1
            is_buy = directions == 1
            is_sell = directions == -1
        else:
            # Vectorized trade classification
            is_buy = (flags & 1024) > 0
            is_sell = (flags & 2048) > 0
            
            # Handle secondary tracking if trade flag states are ambiguous
            unclassified = ~(is_buy | is_sell)
            if np.any(unclassified):
                # If closer to Ask, classify as Buy; else Sell
                ask_prices = df_ticks['ask'].values
                bid_prices = df_ticks['bid'].values
                is_buy[unclassified] = prices[unclassified] >= (ask_prices[unclassified] - 1e-6)
                is_sell[unclassified] = prices[unclassified] <= (bid_prices[unclassified] + 1e-6)

        # Assign binned prices to round off float noise based on symbol tick granularity
        binned_prices = np.round(prices / tick_size) * tick_size

        # Group data using matrix groupings
        df_binned = pd.DataFrame({
            'price': binned_prices,
            'buy_vol': np.where(is_buy, volumes, 0.0),
            'sell_vol': np.where(is_sell, volumes, 0.0),
            'total_vol': volumes
        })

        agg_profile = df_binned.groupby('price').agg(
            bid_volume=('sell_vol', 'sum'),
            ask_volume=('buy_vol', 'sum'),
            total_volume=('total_vol', 'sum')
        ).sort_index(ascending=False)

        # Inject Delta tracking
        agg_profile['delta'] = agg_profile['ask_volume'] - agg_profile['bid_volume']
        
        return self._analyze_footprint_matrix(agg_profile, tick_size)

    def _analyze_footprint_matrix(self, profile: pd.DataFrame, tick_size: float) -> Dict[str, Any]:
        """
        Runs mathematical analysis over the footprint matrix to discover imbalances 
        and passive order-book absorption.
        """
        prices = profile.index.values
        bids = profile['bid_volume'].values
        asks = profile['ask_volume'].values
        
        imbalance_ratio_threshold = 3.5
        min_volume_threshold = 5.0  # Prevents noise classification inside micro-lots
        
        buy_imbalances = []
        sell_imbalances = []
        
        # Cross-Diagonal Imbalance Matching Logic:
        # Aggressive Ask Buyers at Price P are evaluated against Aggressive Bid Sellers at Price P - TickSize
        for idx in range(len(prices) - 1):
            current_ask_vol = asks[idx]     # Higher Price Node
            lower_bid_vol = bids[idx + 1]   # Lower Price Node
            
            # Check Buy Imbalance (Aggressive Buyers Lifting the Ask)
            if current_ask_vol > min_volume_threshold and lower_bid_vol > 0:
                if (current_ask_vol / lower_bid_vol) >= imbalance_ratio_threshold:
                    buy_imbalances.append(float(prices[idx]))
                    
            # Check Sell Imbalance (Aggressive Sellers Slapping the Bid)
            if lower_bid_vol > min_volume_threshold and current_ask_vol > 0:
                if (lower_bid_vol / current_ask_vol) >= imbalance_ratio_threshold:
                    sell_imbalances.append(float(prices[idx + 1]))

        # Calculate Point of Control (POC) by pure transaction volume concentration
        poc_price = float(profile['total_volume'].idxmax()) if len(profile) > 0 else 0.0
        total_delta = float(profile['delta'].sum())
        total_volume = float(profile['total_volume'].sum())

        return {
            "profile_matrix": profile.to_dict(orient='index'),
            "poc_price": poc_price,
            "total_delta": total_delta,
            "total_volume": total_volume,
            "buy_imbalances": buy_imbalances,
            "sell_imbalances": sell_imbalances,
            "absorption_detected": self._detect_passive_absorption(profile)
        }

    def _detect_passive_absorption(self, profile: pd.DataFrame) -> Dict[str, List[float]]:
        """
        Identifies institutional passive limit absorption blocks.
        Occurs where extreme volume is traded, but Delta remains near zero, 
        indicating an aggressive drive met by passive limit iceberg walls.
        """
        absorption_buys = []
        absorption_sells = []
        
        vol_mu = profile['total_volume'].mean()
        vol_std = profile['total_volume'].std()
        high_vol_cutoff = vol_mu + (1.5 * vol_std) if not np.isnan(vol_std) else vol_mu * 2

        for price, row in profile.iterrows():
            # If volume is exceptionally high, but delta fails to break directions cleanly
            if row['total_volume'] > high_vol_cutoff:
                delta_pct = abs(row['delta']) / row['total_volume']
                if delta_pct <= 0.15:  # Less than 15% net bias despite massive volume
                    if row['delta'] > 0:
                        absorption_sells.append(float(str(price)))  # Buyers hitting limits (Passive Supply)
                    else:
                        absorption_buys.append(float(str(price)))   # Sellers hitting limits (Passive Demand)

        return {
            "passive_demand_nodes": absorption_buys,
            "passive_supply_nodes": absorption_sells
        }

    def compute_cumulative_volume_delta_vectorized(self, df_m1: pd.DataFrame, symbol: str) -> pd.Series:
        """
        High-performance, single-query lookahead-proof CVD vector calculation.
        Pulls historical ticks in a single block and vectorizes minute allocations.
        """
        if len(df_m1) == 0:
            return pd.Series(dtype=float)

        # Fetch total start and end bounds in a single API query
        dt_idx = pd.DatetimeIndex(df_m1.index)
        start_time = pd.to_datetime(dt_idx[0])
        end_time = pd.to_datetime(dt_idx[-1]) + pd.Timedelta(minutes=1)
        
        # Convert to explicit integer Unix timestamps for the MT5 API safety gate
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())

        self.logger.info(f"📥 Pulling single historical tick block for {symbol} to calculate CVD matrix...")
        ticks = mt5.copy_ticks_range(symbol, start_ts, end_ts, mt5.COPY_TICKS_ALL)
        
        if ticks is None or len(ticks) == 0:
            return pd.Series(0.0, index=df_m1.index, name="cvd")

        df_ticks = pd.DataFrame(ticks)
        # Convert integer millisecond timestamps into a datetime index for vector grouping
        df_ticks['datetime'] = pd.to_datetime(df_ticks['time_msc'], unit='ms', utc=True)
        
        prices = df_ticks['last'].values
        if np.all(prices == 0) and 'bid' in df_ticks.columns:
            prices = df_ticks['bid'].values
            
        vols = df_ticks['volume'].values
        total_vol_raw = np.sum(vols)
        
        # Fallback for OTC CFD markets (where volume is 0 or not populated on ticks)
        if total_vol_raw <= 0:
            diffs = np.zeros(len(prices))
            diffs[1:] = np.diff(prices)
            directions = np.zeros(len(prices))
            directions[diffs > 0] = 1.0
            directions[diffs < 0] = -1.0
            
            # Forward fill zero-diff ticks
            curr_dir = 0.0
            for idx in range(len(directions)):
                if directions[idx] != 0.0:
                    curr_dir = directions[idx]
                else:
                    directions[idx] = curr_dir if curr_dir != 0.0 else 1.0
            
            df_ticks['tick_delta'] = directions
        else:
            flags = df_ticks['flags'].values
            buys = (flags & 1024) > 0
            sells = (flags & 2048) > 0
            df_ticks['tick_delta'] = np.where(buys, vols, np.where(sells, -vols, 0.0))

        # Downsample the transactional tick delta stream straight into 1-minute bins
        df_binned_delta = df_ticks.groupby(pd.Grouper(key='datetime', freq='1min'))['tick_delta'].sum()

        # Reindex to match our M1 structural dataframe exactly, replacing empty minutes with 0.0 delta
        dt_m1 = pd.DatetimeIndex(df_m1.index)
        if dt_m1.tzinfo is None:
            m1_utc_idx = dt_m1.tz_localize(timezone.utc)
        else:
            m1_utc_idx = dt_m1.tz_convert(timezone.utc)
            
        aligned_deltas = df_binned_delta.reindex(m1_utc_idx).fillna(0.0)

        # Cumulative summation segmented by day boundaries to enforce Daily Auto-Reset
        df_grouped = aligned_deltas.groupby(m1_utc_idx.date)  # type: ignore
        cvd_series = df_grouped.cumsum()

        return pd.Series(cvd_series.values, index=df_m1.index, name="cvd")

    def _generate_empty_footprint(self) -> Dict[str, Any]:
        return {
            "profile_matrix": {}, "poc_price": 0.0, "total_delta": 0.0,
            "total_volume": 0.0, "buy_imbalances": [], "sell_imbalances": [],
            "absorption_detected": {"passive_demand_nodes": [], "passive_supply_nodes": []}
        }

    def compute_imbalance_density_vector(self, df_m1: pd.DataFrame, symbol: str) -> pd.Series:
        """
        Computes the stacked imbalances count for each M1 bar in-memory
        by pulling ticks in a single block and grouping by minute.
        """
        if len(df_m1) == 0:
            return pd.Series(0.0, index=df_m1.index, name="imbalance_density")
            
        dt_idx = pd.DatetimeIndex(df_m1.index)
        start_time = pd.to_datetime(dt_idx[0])
        end_time = pd.to_datetime(dt_idx[-1]) + pd.Timedelta(minutes=1)
        
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        
        ticks = mt5.copy_ticks_range(symbol, start_ts, end_ts, mt5.COPY_TICKS_ALL)
        densities = np.zeros(len(df_m1))
        
        if ticks is None or len(ticks) == 0:
            return pd.Series(densities, index=df_m1.index, name="imbalance_density")
            
        df_ticks = pd.DataFrame(ticks)
        df_ticks['datetime'] = pd.to_datetime(df_ticks['time_msc'], unit='ms', utc=True)
        
        # Group ticks by minute
        df_m1_utc = df_m1.copy()
        dt_m1 = pd.DatetimeIndex(df_m1_utc.index)
        if dt_m1.tzinfo is None:
            df_m1_utc.index = dt_m1.tz_localize(timezone.utc)
        else:
            df_m1_utc.index = dt_m1.tz_convert(timezone.utc)
            
        # Get tick size
        tick_size = 0.25
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is not None:
                tick_size = getattr(symbol_info, 'trade_tick_size', 0.25)
                if tick_size <= 0:
                    tick_size = 0.25
        except Exception:
            pass
            
        grouped_ticks = df_ticks.groupby(pd.Grouper(key='datetime', freq='1min'))
        
        for idx, t_val in enumerate(df_m1_utc.index):
            if t_val not in grouped_ticks.groups:
                continue
            try:
                tick_group = grouped_ticks.get_group(t_val)
            except KeyError:
                continue
            if len(tick_group) < 5:
                continue
                
            flags = tick_group['flags'].values
            prices = tick_group['last'].values
            volumes = tick_group['volume'].values
            if np.all(prices == 0) and 'bid' in tick_group.columns:
                prices = tick_group['bid'].values
                
            total_vol_raw = np.sum(volumes)
            if total_vol_raw <= 0:
                volumes = np.ones(len(prices))
                diffs = np.zeros(len(prices))
                diffs[1:] = np.diff(prices)
                is_buy = diffs > 0
                is_sell = diffs < 0
                
                directions = np.zeros(len(prices))
                directions[is_buy] = 1
                directions[is_sell] = -1
                curr_dir = 0
                for i_idx in range(len(directions)):
                    if directions[i_idx] != 0:
                        curr_dir = directions[i_idx]
                    else:
                        directions[i_idx] = curr_dir if curr_dir != 0 else 1
                is_buy = directions == 1
                is_sell = directions == -1
            else:
                is_buy = (flags & 1024) > 0
                is_sell = (flags & 2048) > 0
                unclassified = ~(is_buy | is_sell)
                if np.any(unclassified) and 'ask' in tick_group.columns and 'bid' in tick_group.columns:
                    ask_prices = tick_group['ask'].values
                    bid_prices = tick_group['bid'].values
                    is_buy[unclassified] = prices[unclassified] >= (ask_prices[unclassified] - 1e-6)
                    is_sell[unclassified] = prices[unclassified] <= (bid_prices[unclassified] + 1e-6)
                    
            binned_prices = np.round(prices / tick_size) * tick_size
            df_b = pd.DataFrame({
                'price': binned_prices,
                'buy_vol': np.where(is_buy, volumes, 0.0),
                'sell_vol': np.where(is_sell, volumes, 0.0)
            })
            profile = df_b.groupby('price').agg(
                bid_volume=('sell_vol', 'sum'),
                ask_volume=('buy_vol', 'sum')
            ).sort_index(ascending=False)
            
            p_arr = profile.index.values
            bids = profile['bid_volume'].values
            asks = profile['ask_volume'].values
            
            imb_count = 0
            for k_idx in range(len(p_arr) - 1):
                if asks[k_idx] > 5.0 and bids[k_idx+1] > 0 and (asks[k_idx] / bids[k_idx+1]) >= 3.5:
                    imb_count += 1
                if bids[k_idx+1] > 5.0 and asks[k_idx] > 0 and (bids[k_idx+1] / asks[k_idx]) >= 3.5:
                    imb_count += 1
            densities[idx] = imb_count
            
        return pd.Series(densities, index=df_m1.index, name="imbalance_density")
