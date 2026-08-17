# core/genetic_evolver.py
import os
import json
import random
import logging
import numpy as np
import pandas as pd
from utils.mt5_gateway import mt5_gateway as mt5
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

GENETIC_PARAMS_FILE = "configs/genetic_params.json"

class GeneticEvolver:
    """
    Autoregressive Genetic Optimization loop. Runs offline/weekends to evolve
    structural lookbacks, FVG thresholds, and Setup Validation Gate parameters.
    Optimizes for the Recovery Factor (Absolute Net Profit / Max Drawdown).
    """
    def __init__(self, engine_instance=None):
        self.logger = logging.getLogger("PulseViper.GeneticEvolver")
        self.engine = engine_instance

    def run_optimization(self, symbol: str, population_size: int = 12, generations: int = 4) -> Dict:
        """
        Run the genetic evolution loop over historical data and save the winning chromosome.
        """
        self.logger.info("🧬 Starting Genetic Optimization Loop...")
        
        # 1. Fetch historical data for backtesting (last 10 days of M15 rates)
        if not mt5.initialize():
            self.logger.error("Failed to initialize MT5 for Genetic Evolver.")
            return {}

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 800)
        if rates is None or len(rates) < 100:
            self.logger.error("Failed to fetch historical rates for backtesting.")
            return {}
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Calculate a simple ATR feature for mock calculations
        high_low = df['high'] - df['low']
        close_prev = df['close'].shift(1)
        high_close = (df['high'] - close_prev).abs()
        low_close = (df['low'] - close_prev).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14, min_periods=1).mean().ffill()

        # 2. Initialize Population
        population = self._initialize_population(population_size)
        
        best_chromosome = None
        best_fitness = -np.inf

        for gen in range(generations):
            self.logger.info(f"🧬 Generation {gen + 1}/{generations}...")
            fitnesses = []
            
            for chrom in population:
                fit = self._evaluate_fitness(chrom, df)
                fitnesses.append(fit)
                
                if fit > best_fitness:
                    best_fitness = fit
                    best_chromosome = chrom
            
            self.logger.info(f"Best fitness in generation {gen + 1}: {best_fitness:.4f}")
            
            # Select parents and generate next generation
            population = self._reproduce(population, fitnesses)

        if best_chromosome:
            self.logger.info(f"🏆 Evolved optimal parameters: {best_chromosome} (Fitness: {best_fitness:.4f})")
            self._save_winning_chromosome(best_chromosome)
            return best_chromosome

        return {}

    def _initialize_population(self, size: int) -> List[Dict]:
        population = []
        for _ in range(size):
            chrom = {
                "smc_swing_window": random.randint(2, 6),
                "smc_lookback_sweep": random.randint(10, 25),
                "smc_lookback_mss": random.randint(10, 25),
                "smc_fvg_lookback": random.randint(3, 8),
                # Setup gate clamped strictly between 10.5 (30% of T2) and 15.75 (45% of T2)
                "setup_validation_gate": round(random.uniform(10.5, 15.75), 2)
            }
            population.append(chrom)
        return population

    def _evaluate_fitness(self, chrom: Dict, df: pd.DataFrame) -> float:
        """
        Fast vectorized simulation to evaluate parameters.
        Simulates buy/sell triggers based on lookback windows and computes the Recovery Factor.
        """
        try:
            closes = df['close'].values
            atrs = df['atr'].values
            T = len(closes)
            
            swing = chrom["smc_swing_window"]
            sweep_lb = chrom["smc_lookback_sweep"]
            mss_lb = chrom["smc_lookback_mss"]
            gate = chrom["setup_validation_gate"]

            # Simulate simple signals using chromosome parameters
            pnl = 0.0
            equity = 10000.0
            peak = equity
            max_dd = 0.0
            
            # Fast mock simulation of trades
            for t in range(50, T - 10):
                # Buying setup indicator (proxy): local low sweep
                low_recent = np.min(closes[t-sweep_lb:t])
                high_recent = np.max(closes[t-mss_lb:t])
                
                # Check setup score proxy (simulating Tier 2 behavior)
                t2_score_proxy = 0.0
                if closes[t] > low_recent + atrs[t] * 0.2:
                    t2_score_proxy += 8.0  # Structure setup score
                if df['atr'].iloc[t] > df['atr'].iloc[t-1]:
                    t2_score_proxy += 5.0  # Volatility/Momentum confirmation
                t2_score_proxy += random.uniform(0, 5.0)  # Noise

                # Setup Validation Gate check
                if t2_score_proxy < gate:
                    continue  # Blocked by Setup Gate

                # Signal trigger
                if closes[t] < low_recent + atrs[t] * 0.5:
                    # Buy trade
                    entry = closes[t]
                    sl = entry - atrs[t] * 1.5
                    tp = entry + atrs[t] * 3.0
                    
                    # Track trade outcome over next 8 bars
                    for forward in range(1, 9):
                        fut_price = closes[t + forward]
                        if fut_price <= sl:
                            # Loss
                            trade_pnl = -150.0  # $150 loss
                            pnl += trade_pnl
                            equity += trade_pnl
                            break
                        elif fut_price >= tp:
                            # Win
                            trade_pnl = 300.0   # $300 profit
                            pnl += trade_pnl
                            equity += trade_pnl
                            break
                    else:
                        # Time exit
                        trade_pnl = (closes[t+8] - entry) / atrs[t] * 100.0
                        pnl += trade_pnl
                        equity += trade_pnl
                    
                    # Update drawdown
                    peak = max(peak, equity)
                    dd = (peak - equity) / peak * 100.0
                    max_dd = max(max_dd, dd)

            recovery_factor = pnl / (max_dd + 1.0)
            return float(recovery_factor)
        except Exception:
            return -9999.0

    def _reproduce(self, population: List[Dict], fitnesses: List[float]) -> List[Dict]:
        """Selection, Crossover, Mutation to generate next generation."""
        pop_size = len(population)
        
        # Sort population by fitness
        sorted_pop = [population[i] for i in np.argsort(fitnesses)[::-1]]
        
        # Keep top 4 as elites
        next_gen = list(sorted_pop[:4])
        
        # Generate rest by crossover and mutation
        while len(next_gen) < pop_size:
            # Selection (weighted random from top half)
            p1 = random.choice(sorted_pop[:pop_size//2])
            p2 = random.choice(sorted_pop[:pop_size//2])
            
            # Crossover
            child = {}
            for k in p1.keys():
                child[k] = p1[k] if random.random() > 0.5 else p2[k]
                
            # Mutation (15% chance per gene)
            if random.random() < 0.15:
                child["smc_swing_window"] = max(2, min(10, child["smc_swing_window"] + random.choice([-1, 1])))
            if random.random() < 0.15:
                child["smc_lookback_sweep"] = max(5, min(40, child["smc_lookback_sweep"] + random.choice([-2, 2])))
            if random.random() < 0.15:
                child["smc_lookback_mss"] = max(5, min(40, child["smc_lookback_mss"] + random.choice([-2, 2])))
            if random.random() < 0.15:
                child["smc_fvg_lookback"] = max(2, min(15, child["smc_fvg_lookback"] + random.choice([-1, 1])))
            if random.random() < 0.15:
                child["setup_validation_gate"] = float(np.clip(
                    child["setup_validation_gate"] + random.choice([-0.5, 0.5]), 10.5, 15.75
                ))
                child["setup_validation_gate"] = round(child["setup_validation_gate"], 2)
                
            next_gen.append(child)
            
        return next_gen

    def _save_winning_chromosome(self, chrom: Dict):
        try:
            os.makedirs("configs", exist_ok=True)
            with open(GENETIC_PARAMS_FILE, "w") as f:
                json.dump(chrom, f, indent=4)
            self.logger.info(f"Saved optimal genetic parameters to {GENETIC_PARAMS_FILE}")
        except Exception as e:
            self.logger.error(f"Failed to save genetic parameters: {e}")

    @staticmethod
    def load_genetic_parameters() -> Optional[Dict]:
        """Static helper to load evolved parameter chromosomes from configuration."""
        if os.path.exists(GENETIC_PARAMS_FILE):
            try:
                with open(GENETIC_PARAMS_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None
