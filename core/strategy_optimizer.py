# core/strategy_optimizer.py
import os
import json
import logging
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Any
from utils.mt5_gateway import mt5_gateway as mt5

from utils.smc_indicators import SMCIndicators
from utils.mt5_data import fetch_ohlcv
from core.session_engine import SessionEngine
from core.market_regime import MarketRegimeDetector, RegimeType

# Strategy Imports
from strategies.crt_tbs import CrtTbsStrategy
from strategies.raja_strategy import RajaStrategy
from strategies.ict_strategy import IctStrategy
from strategies.bank_strategy import BankStrategy
from strategies.vsa_strategy import VsaStrategy
from strategies.avc_strategy import AvcStrategy
from strategies.m1_scalping_strategy import M1ScalpingStrategy
from strategies.vwap_strategy import VwapStrategy
from strategies.smc_concepts_strategy import SmcConceptsStrategy
from strategies.amd import AmdStrategy
from strategies.src import SrcStrategy

class StrategyOptimizer:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.StrategyOptimizer")
        self.session_engine = SessionEngine()
        self.matrix_path = "data/performance_matrix.json"

    def run_global_optimization(self, symbol: str, days: int = 14) -> Dict:
        """
        Runs historical simulation on all 11 strategies across all 3 modes
        (scalping, intraday, swing), evaluates their performance by Day of Week,
        Session, and Market Regime, and saves the condition-ranked Performance Matrix.
        """
        try:
            self.logger.info(f"🔬 Starting global strategy optimization for {symbol} over last {days} days...")
            os.makedirs("data", exist_ok=True)

            # Ensure MT5 is connected
            if not mt5.initialize():
                self.logger.error("MT5 failed to initialize for global optimization.")
                return {"error": "MT5 initialization failed"}

            # Fetch rates for all timeframes
            # To test swing mode, we need D1, H4, H1, M15.
            # To test intraday, we need H1, M15, M5.
            # To test scalping, we need H1, M5, M1.
            # We fetch a generous amount of bars to cover the backtest duration
            self.logger.info("📊 Fetching historical candles from MT5...")
            timeframes = {
                "D1": (mt5.TIMEFRAME_D1, max(100, days * 2)),
                "H4": (mt5.TIMEFRAME_H4, max(100, days * 8)),
                "H1": (mt5.TIMEFRAME_H1, max(150, days * 26)),
                "M30": (mt5.TIMEFRAME_M30, max(200, days * 50)),
                "M15": (mt5.TIMEFRAME_M15, max(200, days * 100)),
                "M5": (mt5.TIMEFRAME_M5, max(300, days * 300)),
                "M1": (mt5.TIMEFRAME_M1, max(1000, min(days * 1440, 45000)))
            }

            dfs = {}
            for tf_name, (tf_const, num_bars) in timeframes.items():
                df = fetch_ohlcv(symbol, tf_const, n=num_bars)
                if df is not None and len(df) >= 30:
                    # Precompute SMC indicators
                    dfs[tf_name] = SMCIndicators.compute_smc_features(df, window=3)
                else:
                    self.logger.warning(f"Insufficient historical data for timeframe {tf_name}")
                    dfs[tf_name] = None  # type: ignore[assignment]

            # Verify core dataframes exist
            if not dfs.get("M1") is not None or not dfs.get("M5") is not None or not dfs.get("H1") is not None:
                self.logger.error("Core timeframes (M1, M5, H1) are unavailable. Aborting optimization.")
                return {"error": "Core timeframes missing"}

            modes = ["scalping", "intraday", "swing"]
            all_trades = []

            for mode in modes:
                self.logger.info(f"⚡ Backtesting all strategies for trading mode: {mode.upper()}...")
                mode_trades = self._backtest_mode(symbol, dfs, mode)
                all_trades.extend(mode_trades)

            # Analyze trades and build performance matrix
            matrix = self._build_performance_matrix(all_trades)
            
            # Save matrix
            with open(self.matrix_path, "w") as f:
                json.dump(matrix, f, indent=2)

            self.logger.info(f"✅ Global strategy optimization complete! Performance Matrix saved to {self.matrix_path}")
            return matrix

        except Exception as e:
            self.logger.error(f"Global optimization error: {e}")
            self.logger.error(traceback.format_exc())
            return {"error": str(e)}

    def _backtest_mode(self, symbol: str, dfs: Dict[str, pd.DataFrame], mode: str) -> List[Dict]:
        """
        Backtests all strategies in the context of the given trading mode.
        """
        # Determine execution (LTF) timeframe, Context timeframe, and HTF timeframe
        if mode == "scalping":
            ltf_name = "M1"
            context_name = "M5"
            htf_name = "H1"
        elif mode == "swing":
            ltf_name = "M15"
            context_name = "H1"
            htf_name = "D1"
        else: # intraday
            ltf_name = "M5"
            context_name = "M15"
            htf_name = "H1"

        df_ltf = dfs.get(ltf_name)
        df_context = dfs.get(context_name)
        df_htf = dfs.get(htf_name)
        df_d1 = dfs.get("D1")
        df_h4 = dfs.get("H4")
        df_h1 = dfs.get("H1")
        df_m15 = dfs.get("M15")
        df_m5 = dfs.get("M5")
        df_m1 = dfs.get("M1")

        if df_ltf is None or df_context is None or df_htf is None:
            self.logger.warning(f"Skipping backtest for mode {mode} due to missing dataframes.")
            return []

        # Ensure df indices are pd.DatetimeIndex before backtest loop, so they can be cast to datetime64[ns] properly
        for k in dfs:
            if dfs[k] is not None:
                dfs[k].index = pd.to_datetime(dfs[k].index)

        # Convert index datetimes to numpy array of timestamps for fast lookup
        ltf_times = df_ltf.index.values
        ltf_close = df_ltf['close'].values
        ltf_high = df_ltf['high'].values
        ltf_low = df_ltf['low'].values
        ltf_atr = df_ltf['atr'].values

        # Precompute searchsorted indices to speed up slicing (O(N) searchsorted instead of O(N^2))
        # Shift search indices to guarantee lookahead-proof slicing
        search_d1 = np.searchsorted(df_d1.index.values, ltf_times - np.timedelta64(1, 'D'), side='right') if df_d1 is not None else None
        search_h4 = np.searchsorted(df_h4.index.values, ltf_times - np.timedelta64(4, 'h'), side='right') if df_h4 is not None else None
        search_h1 = np.searchsorted(df_h1.index.values, ltf_times - np.timedelta64(1, 'h'), side='right') if df_h1 is not None else None
        search_m30 = np.searchsorted(dfs.get("M30").index.values, ltf_times - np.timedelta64(30, 'm'), side='right') if dfs.get("M30") is not None else None
        search_m15 = np.searchsorted(df_m15.index.values, ltf_times - np.timedelta64(15, 'm'), side='right') if df_m15 is not None else None
        search_m5 = np.searchsorted(df_m5.index.values, ltf_times - np.timedelta64(5, 'm'), side='right') if df_m5 is not None else None
        search_m1 = np.searchsorted(df_m1.index.values, ltf_times - np.timedelta64(1, 'm'), side='right') if df_m1 is not None else None

        strategies = ["crt", "raja", "ict", "bank", "vsa", "avc", "m1_scalping", "vwap", "smc", "amd", "src"]
        
        # Risk-reward ratio by mode
        if mode == "scalping":
            rr_ratio = 1.5
        elif mode == "swing":
            rr_ratio = 3.0
        else:
            rr_ratio = 2.0

        # We step through the LTF bars. To optimize speed, we evaluate every 5 bars on M1, every bar on M5/M15.
        step = 5 if ltf_name == "M1" else 1
        n = len(df_ltf)
        
        trades = []
        # Keep track of cooldown per strategy: timestamp when next trade can be taken
        strategy_cooldown = {s: pd.Timestamp.min for s in strategies}

        for i in range(100, n - 200, step):
            t = df_ltf.index[i]
            dt_t = pd.Timestamp(t).to_pydatetime()
            weekday = dt_t.weekday()
            
            # Map Session
            session_ctx = self.session_engine.get_session_context(dt_t, symbol)
            session_name = session_ctx['session_name'].replace("GOLD_", "")
            
            # Skip weekends
            if weekday in (5, 6):
                continue

            # Determine aligned indices
            idx_d1 = search_d1[i] if search_d1 is not None else 0
            idx_h4 = search_h4[i] if search_h4 is not None else 0
            idx_h1 = search_h1[i] if search_h1 is not None else 0
            idx_m30 = search_m30[i] if search_m30 is not None else 0
            idx_m15 = search_m15[i] if search_m15 is not None else 0
            idx_m5 = search_m5[i] if search_m5 is not None else 0
            idx_m1 = search_m1[i] if search_m1 is not None else 0

            # Skip if we don't have enough history in any required timeframe
            if idx_h1 < 30 or idx_m5 < 30:
                continue

            # Slice dataframes to represent historical state at time t
            df_d1_s = df_d1.iloc[max(0, idx_d1-200) : idx_d1] if df_d1 is not None else None
            df_h4_s = df_h4.iloc[max(0, idx_h4-200) : idx_h4] if df_h4 is not None else None
            df_h1_s = df_h1.iloc[max(0, idx_h1-200) : idx_h1] if df_h1 is not None else None
            df_m30_s = dfs.get("M30").iloc[max(0, idx_m30-200) : idx_m30] if dfs.get("M30") is not None else None
            df_m15_s = df_m15.iloc[max(0, idx_m15-200) : idx_m15] if df_m15 is not None else None
            df_m5_s = df_m5.iloc[max(0, idx_m5-200) : idx_m5] if df_m5 is not None else None
            df_m1_s = df_m1.iloc[max(0, idx_m1-200) : idx_m1] if df_m1 is not None else None

            # Get master HTF bias
            h1_bias = int(df_h1_s['active_bias'].iloc[-1]) if df_h1_s is not None else 0
            h4_bias = int(df_h4_s['active_bias'].iloc[-1]) if df_h4_s is not None else 0
            d1_bias = int(df_d1_s['active_bias'].iloc[-1]) if df_d1_s is not None else 0
            
            if d1_bias == h4_bias and d1_bias != 0:
                htf_bias = d1_bias
            elif d1_bias != 0:
                htf_bias = d1_bias
            else:
                htf_bias = h1_bias

            # Get current volatility/regime
            rvol = 1.0
            regime = MarketRegimeDetector.detect_regime(df_m15_s, rvol, symbol).name  # type: ignore[arg-type]

            curr_price = ltf_close[i]
            atr = ltf_atr[i]

            # Evaluate each strategy
            for s in strategies:
                if t < strategy_cooldown[s]:
                    continue

                action, sl, tp, metadata = None, 0.0, 0.0, {}

                try:
                    if s == "crt":
                        action, _, sl, tp, metadata = CrtTbsStrategy.evaluate_crt_tbs(
                            df_d1=df_d1_s, df_h4=df_h4_s, df_h1=df_h1_s,  # type: ignore[arg-type]
                            df_m15=df_m15_s, df_m5=df_m5_s, df_m1=df_m1_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, volume_cache={},
                            sentiment_cache={}, htf_bias=htf_bias, symbol=symbol, regime=regime
                        )
                    elif s == "raja":
                        action, sl, tp, metadata = RajaStrategy.evaluate_raja(
                            df_m15=df_m15_s, df_m30=df_m30_s, df_h1=df_h1_s, df_h4=df_h4_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, volume_cache={}, regime=regime
                        )
                    elif s == "ict":
                        action, sl, tp, metadata = IctStrategy.evaluate_ict(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, df_h1=df_h1_s, df_h4=df_h4_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, htf_bias=htf_bias, volume_cache={}, regime=regime,
                            sim_time=dt_t
                        )
                    elif s == "bank":
                        action, sl, tp, metadata = BankStrategy.evaluate_bank(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, df_h1=df_h1_s, df_h4=df_h4_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, volume_cache={}, regime=regime
                        )
                    elif s == "vsa":
                        action, sl, tp, metadata = VsaStrategy.evaluate_vsa(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_h1=df_h1_s, current_price=curr_price,  # type: ignore[arg-type]
                            atr=atr, volume_cache={}, regime=regime
                        )
                    elif s == "avc":
                        action, sl, tp, metadata = AvcStrategy.evaluate_avc(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, current_price=curr_price,  # type: ignore[arg-type]
                            atr=atr, volume_cache={}, regime=regime
                        )
                    elif s == "m1_scalping":
                        action, sl, tp, metadata = M1ScalpingStrategy.evaluate_m1_scalping(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, current_price=curr_price,  # type: ignore[arg-type]
                            atr=atr, volume_cache={}, regime=regime
                        )
                    elif s == "vwap":
                        action, sl, tp, metadata = VwapStrategy.evaluate_vwap(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_h1=df_h1_s, current_price=curr_price,  # type: ignore[arg-type]
                            atr=atr, regime=regime, htf_bias=htf_bias
                        )
                    elif s == "smc":
                        action, sl, tp, metadata = SmcConceptsStrategy.evaluate_smc(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, df_h1=df_h1_s, df_h4=df_h4_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, htf_bias=htf_bias, volume_cache={}, regime=regime
                        )
                    elif s == "amd":
                        action, _, sl, tp, metadata = AmdStrategy.evaluate_amd(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, df_h1=df_h1_s, df_h4=df_h4_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, htf_bias=htf_bias, volume_cache={}, regime=regime
                        )
                    elif s == "src":
                        action, _, sl, tp, metadata = SrcStrategy.evaluate_src(
                            df_m1=df_m1_s, df_m5=df_m5_s, df_m15=df_m15_s, df_h1=df_h1_s, df_h4=df_h4_s,  # type: ignore[arg-type]
                            current_price=curr_price, atr=atr, htf_bias=htf_bias, volume_cache={}, regime=regime
                        )
                except Exception:
                    # Silent skip evaluation errors during simulation to prevent log flooding
                    continue

                if action in ["BUY", "SELL"] and sl > 0.0 and tp > 0.0:
                    # Simulate trade outcome walking forward in LTF df
                    outcome, bars_held, resolved = self._simulate_trade(
                        action, sl, tp, df_ltf, i, rr_ratio
                    )
                    if resolved:
                        trades.append({
                            "strategy": s,
                            "mode": mode,
                            "weekday": weekday,
                            "session": session_name,
                            "regime": regime,
                            "action": action,
                            "outcome": outcome,
                            "win": outcome > 0,
                            "time": str(t)
                        })
                        # Apply cooldown of 40 candles in LTF
                        strategy_cooldown[s] = df_ltf.index[min(i + 40, n - 1)]  # type: ignore[assignment]

        return trades

    def _simulate_trade(
        self, action: str, sl: float, tp: float, df_ltf: pd.DataFrame, entry_idx: int, rr_ratio: float
    ) -> Tuple[float, int, bool]:
        """Simulates walk forward to resolve trade outcome."""
        if entry_idx + 1 >= len(df_ltf):
            return 0.0, 0, False  # Discard signal if it occurs on the trailing edge of historical data
        entry_price = df_ltf['open'].values[entry_idx + 1]
        highs = df_ltf['high'].values
        lows = df_ltf['low'].values
        n = len(df_ltf)

        sl_dist = abs(entry_price - sl)
        if sl_dist <= 0:
            return 0.0, 0, False

        bars_held = 0
        max_bars = 200

        for j in range(entry_idx + 1, min(entry_idx + max_bars, n)):
            bars_held += 1
            future_high = highs[j]
            future_low = lows[j]

            if action == "BUY":
                if future_low <= sl:
                    # Hit SL
                    return -sl_dist, bars_held, True
                elif future_high >= tp:
                    # Hit TP
                    return rr_ratio * sl_dist, bars_held, True
            else: # SELL
                if future_high >= sl:
                    # Hit SL
                    return -sl_dist, bars_held, True
                elif future_low <= tp:
                    # Hit TP
                    return rr_ratio * sl_dist, bars_held, True

        return 0.0, bars_held, False

    def _wilson_lower_bound(self, wins: int, n: int, z: float = 1.64) -> float:
        """95%-ish one-sided lower bound on win rate (z=1.64 ~ 90% CI, conservative)."""
        import math
        if n == 0:
            return 0.0
        p_hat = wins / n
        denom = 1 + z**2 / n
        center = p_hat + z**2 / (2 * n)
        margin = z * math.sqrt(max(0.0, (p_hat * (1 - p_hat) + z**2 / (4 * n)) / n))
        return max(0.0, (center - margin) / denom)

    def _build_performance_matrix(self, trades: List[Dict]) -> Dict:
        """
        Processes simulated trades to construct the Performance Matrix.
        Groups and ranks strategies for each condition set.
        """
        # Convert trades to DataFrame
        if not trades:
            return {"meta": {"updated_at": datetime.now(timezone.utc).isoformat(), "total_trades": 0}, "matrix": {}}

        df = pd.DataFrame(trades)
        
        # We group by Mode, Weekday, Session, Regime, and Strategy
        group_cols = ["mode", "weekday", "session", "regime", "strategy"]
        grouped = df.groupby(group_cols).agg(
            total_trades=('outcome', 'count'),
            wins=('win', 'sum'),
            net_pnl=('outcome', 'sum'),
        ).reset_index()

        grouped['win_rate'] = (grouped['wins'] / grouped['total_trades']) * 100
        
        # Calculate shrunk win-rate
        shrunk_wrs = []
        for idx, row in grouped.iterrows():
            sw = self._wilson_lower_bound(int(row['wins']), int(row['total_trades']))
            shrunk_wrs.append(sw * 100.0)
        grouped['shrunk_win_rate'] = shrunk_wrs
        
        # Calculate gross profit / gross loss for profit factor
        pf_list = []
        for idx, row in grouped.iterrows():
            sub = df[
                (df['mode'] == row['mode']) & 
                (df['weekday'] == row['weekday']) & 
                (df['session'] == row['session']) & 
                (df['regime'] == row['regime']) & 
                (df['strategy'] == row['strategy'])
            ]
            gross_prof = sub[sub['outcome'] > 0]['outcome'].sum()
            gross_loss = abs(sub[sub['outcome'] < 0]['outcome'].sum())
            pf = gross_prof / (gross_loss + 1e-9)
            pf_list.append(round(pf, 2))
        
        grouped['profit_factor'] = pf_list

        # Rank strategies per combination using fitness score: shrunk_win_rate * 0.4 + profit_factor * 10
        grouped['fitness'] = (grouped['shrunk_win_rate'] * 0.4) + (grouped['profit_factor'] * 10)

        # Build nested matrix dictionary
        matrix_data = {}

        # Loop through combinations of conditions
        combos = df.groupby(["mode", "weekday", "session", "regime"]).size().reset_index()
        
        for _, c_row in combos.iterrows():
            m_val = c_row['mode']
            w_val = int(c_row['weekday'])
            s_val = c_row['session']
            r_val = c_row['regime']

            # Filter strategies for this combo
            cond_df = grouped[
                (grouped['mode'] == m_val) &
                (grouped['weekday'] == w_val) &
                (grouped['session'] == s_val) &
                (grouped['regime'] == r_val)
            ].sort_values(by='fitness', ascending=False)  # type: ignore[call-overload]

            if cond_df.empty:
                continue

            # Ranked list of strategies
            ranked_strategies = []
            for _, r in cond_df.iterrows():
                ranked_strategies.append({
                    "strategy": r['strategy'],
                    "total_trades": int(r['total_trades']),
                    "win_rate": round(float(r['win_rate']), 1),
                    "shrunk_win_rate": round(float(r['shrunk_win_rate']), 1),
                    "profit_factor": float(r['profit_factor']),
                    "net_pnl_R": round(float(r['net_pnl']), 2),
                    "fitness": round(float(r['fitness']), 1)
                })

            # Store in nested keys: mode -> weekday -> session -> regime
            if m_val not in matrix_data:
                matrix_data[m_val] = {}
            if str(w_val) not in matrix_data[m_val]:
                matrix_data[m_val][str(w_val)] = {}
            if s_val not in matrix_data[m_val][str(w_val)]:
                matrix_data[m_val][str(w_val)][s_val] = {}
            
            matrix_data[m_val][str(w_val)][s_val][r_val] = ranked_strategies

        # Build fallback rankings (overall strategy rankings per mode) for cases where specific combo has no data
        fallback_rankings = {}
        for mode in grouped['mode'].unique():
            mode_df = df[df['mode'] == mode]
            mode_grouped = mode_df.groupby("strategy").agg(
                total_trades=('outcome', 'count'),
                wins=('win', 'sum'),
                net_pnl=('outcome', 'sum'),
            ).reset_index()
            mode_grouped['win_rate'] = (mode_grouped['wins'] / mode_grouped['total_trades']) * 100
            
            mode_shrunk = []
            for _, r in mode_grouped.iterrows():
                mode_shrunk.append(self._wilson_lower_bound(int(r['wins']), int(r['total_trades'])) * 100.0)
            mode_grouped['shrunk_win_rate'] = mode_shrunk
            
            pf_list_mode = []
            for _, r in mode_grouped.iterrows():
                sub = mode_df[mode_df['strategy'] == r['strategy']]
                g_p = sub[sub['outcome'] > 0]['outcome'].sum()
                g_l = abs(sub[sub['outcome'] < 0]['outcome'].sum())
                pf_list_mode.append(round(g_p / (g_l + 1e-9), 2))
            mode_grouped['profit_factor'] = pf_list_mode
            mode_grouped['fitness'] = (mode_grouped['shrunk_win_rate'] * 0.4) + (mode_grouped['profit_factor'] * 10)
            
            mode_ranked = mode_grouped.sort_values(by='fitness', ascending=False)
            fallback_rankings[mode] = [
                {
                    "strategy": r['strategy'],
                    "total_trades": int(r['total_trades']),
                    "win_rate": round(float(r['win_rate']), 1),
                    "shrunk_win_rate": round(float(r['shrunk_win_rate']), 1),
                    "profit_factor": float(r['profit_factor']),
                    "net_pnl_R": round(float(r['net_pnl']), 2)
                } for _, r in mode_ranked.iterrows()
            ]

        return {
            "meta": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_trades_analyzed": len(trades),
                "symbols_optimized": [df.get("symbol", "XAUUSDm") for df in [df] if 'symbol' in df.columns]
            },
            "fallback_rankings": fallback_rankings,
            "matrix": matrix_data
        }
