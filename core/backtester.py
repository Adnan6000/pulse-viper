# core/backtester.py
"""
PulseViper Adaptive Backtester
- Re-runs SMC entry logic on recent historical OHLCV data from MT5
- Compares backtest performance vs actual live performance
- Self-optimizes min_rr_ratio and other parameters automatically
"""
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import MetaTrader5 as mt5
import numpy as np
import pandas as pd


class AdaptiveBacktester:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.Backtester")
        self.results_path = "logs/backtest_results.json"
        self.last_results: Dict = {}

    def _fetch_data(self, symbol: str, days: int, timeframe) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from MT5 for backtesting."""
        try:
            bars = days * 24 * 60  # Conservative: 1-min bars enough for any TF
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, min(bars, 50000))
            if rates is None or len(rates) < 100:
                self.logger.warning(f"Insufficient data for {symbol} backtest")
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Backtest data fetch failed: {e}")
            return None

    def run_backtest(self, symbol: str, days: int = 30,
                     rr_ratio: float = 2.0, trading_mode: str = "scalping",
                     swing_window: int = 2, lookback_sweep: int = 20,
                     lookback_mss: int = 10, lookback_fvg: int = 5) -> Dict:
        """
        Run a full simulation of the SMC strategy on recent historical data.
        Returns comprehensive backtest statistics.
        """
        self.logger.info(f"🔬 Backtester: Running {days}-day backtest on {symbol} | Mode={trading_mode}, RR={rr_ratio}, SW={swing_window}, SWP={lookback_sweep}, MSS={lookback_mss}")

        from utils.smc_indicators import SMCIndicators
        from utils.mt5_data import fetch_ohlcv

        # Select timeframes based on mode
        if trading_mode == "scalping":
            tf_htf = mt5.TIMEFRAME_H1
            tf_context = mt5.TIMEFRAME_M5
            tf_ltf = mt5.TIMEFRAME_M1
        elif trading_mode == "swing":
            tf_htf = mt5.TIMEFRAME_D1
            tf_context = mt5.TIMEFRAME_H1
            tf_ltf = mt5.TIMEFRAME_M15
        else:  # intraday
            tf_htf = mt5.TIMEFRAME_H1
            tf_context = mt5.TIMEFRAME_M15
            tf_ltf = mt5.TIMEFRAME_M5

        bars_needed = days * 24 * 12  # M5 bars per day
        df_htf = fetch_ohlcv(symbol, tf_htf, n=bars_needed)
        df_context = fetch_ohlcv(symbol, tf_context, n=bars_needed)
        df_ltf = fetch_ohlcv(symbol, tf_ltf, n=min(bars_needed * 5, 50000))

        if df_htf is None or df_context is None or df_ltf is None:
            return {"error": "Failed to fetch backtest data", "symbol": symbol}

        if len(df_htf) < 50 or len(df_ltf) < 50:
            return {"error": "Not enough historical bars", "symbol": symbol}

        # Compute SMC features
        try:
            htf_smc = SMCIndicators.compute_smc_features(df_htf, window=swing_window)
            context_smc = SMCIndicators.compute_smc_features(df_context, window=swing_window)
            ltf_smc = SMCIndicators.compute_smc_features(df_ltf, window=swing_window)
        except Exception as e:
            return {"error": f"SMC compute failed: {e}", "symbol": symbol}

        # Run simulation
        trades = []
        n = len(ltf_smc)
        htf_indices = htf_smc.index
        ctx_indices = context_smc.index
        trade_exit_bar = -1

        for i in range(100, n - 100):
            if i <= trade_exit_bar:
                continue  # Only 1 trade at a time

            t = ltf_smc.index[i]
            ltf_row = ltf_smc.iloc[i]

            # Get aligned HTF and context rows using fast binary search
            idx_htf = htf_indices.searchsorted(t, side='right')
            idx_ctx = ctx_indices.searchsorted(t, side='right')
            if idx_htf == 0 or idx_ctx == 0:
                continue

            htf_row = htf_smc.iloc[idx_htf - 1]
            ctx_row = context_smc.iloc[idx_ctx - 1]

            h1_bias = htf_row.get('active_bias', 0)
            
            # Check last lookback_sweep context candles for any sweep (scan backward)
            ctx_sweep = 0
            for k in range(idx_ctx - 1, max(-1, idx_ctx - (lookback_sweep + 1)), -1):
                sweep_val = context_smc.iloc[k].get('liq_sweep_type', 0)
                if sweep_val != 0:
                    ctx_sweep = int(sweep_val)
                    break
                    
            # Check last lookback_mss LTF candles for any MSS (scan backward)
            ltf_mss = 0
            for k in range(i, max(-1, i - lookback_mss), -1):
                mss_val = ltf_smc.iloc[k].get('mss_signal', 0)
                if mss_val != 0:
                    ltf_mss = int(mss_val)
                    break
                    
            # Check last lookback_fvg candles for FVG
            fvg_class = 'none'
            for k in range(i, max(-1, i - lookback_fvg), -1):
                cls_val = ltf_smc.iloc[k].get('fvg_class', 'none')
                if cls_val != 'none' and cls_val != 'rfvg':
                    fvg_class = cls_val
                    break
            if fvg_class == 'none':
                fvg_class = ltf_row.get('fvg_class', 'none')
                
            atr = ltf_row.get('atr', 1.0)
            entry = ltf_row.get('close', 0)
            support = ltf_row.get('support', entry - atr)
            resistance = ltf_row.get('resistance', entry + atr)

            action = None
            sl = 0.0
            tp = 0.0

            # Bullish setup (strict bias)
            is_bullish = (h1_bias == 1) and (ctx_sweep == 1) and (ltf_mss == 1)
            # Bearish setup (strict bias)
            is_bearish = (h1_bias == -1) and (ctx_sweep == -1) and (ltf_mss == -1)

            if is_bullish:
                action = "BUY"
                sl = min(support - (0.2 * atr), entry - (1.5 * atr))
                tp = entry + (rr_ratio * (entry - sl))
                if resistance > entry:
                    tp = max(tp, resistance)
            elif is_bearish:
                action = "SELL"
                sl = max(resistance + (0.2 * atr), entry + (1.5 * atr))
                tp = entry - (rr_ratio * (sl - entry))
                if support < entry:
                    tp = min(tp, support)

            if action is None:
                continue

            # Resolve outcome
            sl_dist = abs(entry - sl)
            resolved = False
            outcome = 0.0
            bars_held = 0
            close_price = entry

            for j in range(i + 1, min(i + 200, n)):
                future = ltf_smc.iloc[j]
                bars_held += 1
                if action == "BUY":
                    if future.get('low', entry) <= sl:
                        outcome = -sl_dist
                        close_price = sl
                        resolved = True
                        trade_exit_bar = j
                        break
                    elif future.get('high', entry) >= tp:
                        outcome = rr_ratio * sl_dist
                        close_price = tp
                        resolved = True
                        trade_exit_bar = j
                        break
                else:
                    if future.get('high', entry) >= sl:
                        outcome = -sl_dist
                        close_price = sl
                        resolved = True
                        trade_exit_bar = j
                        break
                    elif future.get('low', entry) <= tp:
                        outcome = rr_ratio * sl_dist
                        close_price = tp
                        resolved = True
                        trade_exit_bar = j
                        break

            if resolved:
                rr_achieved = outcome / (sl_dist + 1e-9)
                trades.append({
                    "action": action,
                    "entry": round(float(entry), 2),
                    "close": round(float(close_price), 2),
                    "sl": round(float(sl), 2),
                    "tp": round(float(tp), 2),
                    "outcome": round(float(outcome), 4),
                    "rr": round(float(rr_achieved), 2),
                    "bars_held": int(bars_held),
                    "win": bool(outcome > 0),
                    "setup": "SHARP_TURN" if (ctx_sweep != 0 and ltf_mss != 0) else "MSS_ONLY",
                    "time": str(t)
                })
            else:
                trade_exit_bar = min(i + 200, n) - 1

        # Compute stats
        if not trades:
            return {
                "symbol": symbol, "days": days, "rr_ratio": rr_ratio,
                "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "profit_factor": 0.0, "message": "No qualifying setups found in backtest window"
            }

        wins = [t for t in trades if t["win"]]
        losses = [t for t in trades if not t["win"]]
        win_rate = (len(wins) / len(trades)) * 100
        gross_profit = sum(t["outcome"] for t in wins)
        gross_loss = abs(sum(t["outcome"] for t in losses))
        profit_factor = gross_profit / (gross_loss + 1e-9)
        avg_rr = sum(t["rr"] for t in trades) / len(trades)
        avg_bars = sum(t["bars_held"] for t in trades) / len(trades)

        # Max drawdown (running cumulative sum)
        cumulative = np.cumsum([t["outcome"] for t in trades])
        max_cumulative = np.maximum.accumulate(cumulative)
        drawdowns = max_cumulative - cumulative
        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        results = {
            "symbol": symbol,
            "days": days,
            "rr_ratio": rr_ratio,
            "trading_mode": trading_mode,
            "timestamp": datetime.now().isoformat(),
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 3),
            "avg_rr_achieved": round(avg_rr, 2),
            "avg_bars_held": round(avg_bars, 1),
            "max_drawdown_pts": round(max_drawdown, 4),
            "trades_sample": trades[-10:]  # Last 10 trades as sample
        }

        self.last_results = results
        self._save_results(results)
        self.logger.info(
            f"✅ Backtest done: {symbol} | {len(trades)} trades | WR={win_rate:.1f}% | "
            f"PF={profit_factor:.2f} | AvgRR={avg_rr:.2f}R"
        )
        return results

    def self_optimize(self, symbol: str, trading_mode: str = "scalping") -> Dict:
        """
        Evaluate multiple indicator parameters (swing window, sweep lookback, MSS lookback, RR ratio)
        using historical backtesting. Chooses the configuration with highest fitness score and
        saves it to settings_manager.
        """
        from utils.settings_manager import settings_manager

        self.logger.info(f"🧠 Backtester: Commencing grid self-optimization for {symbol}...")
        
        # Current settings
        curr_swing_window = settings_manager.get("smc_swing_window", 2)
        curr_lookback_sweep = settings_manager.get("smc_lookback_sweep", 20)
        curr_lookback_mss = settings_manager.get("smc_lookback_mss", 10)
        curr_lookback_fvg = settings_manager.get("smc_fvg_lookback", 5)
        curr_rr = settings_manager.get("min_rr_ratio", 2.0)

        # Generate candidates to evaluate
        candidates = []
        swing_options = [2, 3]
        sweep_options = [15, 20, 30]
        mss_options = [8, 10, 15]
        rr_options = [1.5, 2.0, 2.5]
        
        for sw in swing_options:
            for sweep in sweep_options:
                for mss in mss_options:
                    for rr in rr_options:
                        candidates.append({
                            "swing_window": sw,
                            "lookback_sweep": sweep,
                            "lookback_mss": mss,
                            "lookback_fvg": 5,
                            "rr": rr
                        })

        best_score = -1.0
        best_cfg = None
        results_log = {}

        # Fetch data once to optimize performance
        # We backtest last 14 days
        self.logger.info(f"📊 Grid optimizing {len(candidates)} configurations over last 14 days...")
        
        for idx, cfg in enumerate(candidates):
            try:
                res = self.run_backtest(
                    symbol=symbol,
                    days=14,
                    rr_ratio=cfg["rr"],
                    trading_mode=trading_mode,
                    swing_window=cfg["swing_window"],
                    lookback_sweep=cfg["lookback_sweep"],
                    lookback_mss=cfg["lookback_mss"],
                    lookback_fvg=cfg["lookback_fvg"]
                )
                
                total_trades = res.get("total_trades", 0)
                pf = res.get("profit_factor", 0.0)
                wr = res.get("win_rate", 0.0)
                
                # Fitness scoring: rewards good profit factor & sensible trade count
                score = pf * (1.0 + min(total_trades, 5) * 0.1)
                
                cfg_key = f"sw{cfg['swing_window']}_swp{cfg['lookback_sweep']}_mss{cfg['lookback_mss']}_rr{cfg['rr']}"
                results_log[cfg_key] = {
                    "trades": total_trades,
                    "pf": pf,
                    "wr": wr,
                    "score": score
                }
                
                if score > best_score and total_trades >= 2:
                    best_score = score
                    best_cfg = cfg
            except Exception as e:
                self.logger.error(f"Failed to evaluate candidate {cfg}: {e}")

        optimization = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "previous_settings": {
                "swing_window": curr_swing_window,
                "lookback_sweep": curr_lookback_sweep,
                "lookback_mss": curr_lookback_mss,
                "lookback_fvg": curr_lookback_fvg,
                "min_rr_ratio": curr_rr
            },
            "best_settings": best_cfg,
            "best_score": round(best_score, 3),
            "applied": False
        }

        # Apply settings if a valid config with trades was found and it is better than current
        if best_cfg:
            curr_key = f"sw{curr_swing_window}_swp{curr_lookback_sweep}_mss{curr_lookback_mss}_rr{curr_rr}"
            curr_score = results_log.get(curr_key, {}).get("score", 0.0)
            
            if best_score > curr_score or (curr_score == 0 and best_score > 0):
                settings_manager.set("smc_swing_window", best_cfg["swing_window"])
                settings_manager.set("smc_lookback_sweep", best_cfg["lookback_sweep"])
                settings_manager.set("smc_lookback_mss", best_cfg["lookback_mss"])
                settings_manager.set("smc_fvg_lookback", best_cfg["lookback_fvg"])
                settings_manager.set("min_rr_ratio", best_cfg["rr"])
                optimization["applied"] = True
                self.logger.info(
                    f"🎯 Grid Optimizer applied new settings for {symbol}: "
                    f"swing_window={best_cfg['swing_window']}, sweep={best_cfg['lookback_sweep']}, "
                    f"mss={best_cfg['lookback_mss']}, rr={best_cfg['rr']} (Score: {curr_score:.2f} -> {best_score:.2f})"
                )
            else:
                self.logger.info(f"📊 Grid Optimizer: Current settings are still optimal (Score: {curr_score:.2f} vs best candidate: {best_score:.2f})")
        else:
            # Fallback: if all configurations returned 0 trades, let's loosen settings to force swing/trade detection
            self.logger.warning(f"⚠️ Grid Optimizer: All candidates yielded 0 trades. Applying sensitive settings to capture swing points.")
            settings_manager.set("smc_swing_window", 2)
            settings_manager.set("smc_lookback_sweep", 35)
            settings_manager.set("smc_lookback_mss", 15)
            settings_manager.set("smc_fvg_lookback", 8)
            settings_manager.set("min_rr_ratio", 1.5)
            optimization["applied"] = True
            optimization["fallback_applied"] = True

        # Save optimization log
        opt_path = "logs/optimization_log.json"
        try:
            existing = []
            if os.path.exists(opt_path):
                with open(opt_path, "r") as f:
                    existing = json.load(f)
            existing.append(optimization)
            with open(opt_path, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save optimization log: {e}")

        return optimization

    def get_last_results(self) -> Dict:
        """Return the last backtest results."""
        if self.last_results:
            return self.last_results
        return self._load_results()

    def _save_results(self, results: Dict):
        try:
            with open(self.results_path, "w") as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save backtest results: {e}")

    def _load_results(self) -> Dict:
        if os.path.exists(self.results_path):
            try:
                with open(self.results_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
