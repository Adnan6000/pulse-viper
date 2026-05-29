# scripts/train_gold_patterns.py
import os
import sys
import logging
import pandas as pd
import numpy as np
import requests

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pattern_learner import PatternLearner
from core.experience_memory import ExperienceMemory

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("TrainGoldPatterns")

def main():
    # Force stdout encoding to UTF-8 on Windows to prevent UnicodeEncodeError
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    logger.info("Starting Gold Pattern Training Program...")
    
    symbol = "XAUUSDm"
    csv_url = "https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/XAUUSD/XAUUSDh1.csv"
    
    # 1. Fetch deep historical Gold data from internet
    logger.info(f"Downloading 10-year hourly XAUUSD historical dataset from: {csv_url}")
    try:
        response = requests.get(csv_url, timeout=30)
        if response.status_code != 200:
            logger.error(f"Failed to download data. HTTP Status: {response.status_code}")
            sys.exit(1)
            
        from io import StringIO
        csv_data = StringIO(response.text)
        df = pd.read_csv(csv_data)
        logger.info(f"Successfully downloaded {len(df)} historical bars.")
    except Exception as e:
        logger.error(f"Failed to fetch historical data: {e}")
        sys.exit(1)
        
    # 2. Clean and format the dataset
    # Rename columns to lowercase standard
    df = df.rename(columns={
        'Date': 'datetime',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'tick_volume': 'volume'
    })
    
    # Parse dates and set index
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')
    df = df.sort_index()
    
    # Verify price scaling: ejtraderLabs prices are multiplied by 100 (e.g. 154000 instead of 1540)
    first_close = df['close'].iloc[0]
    if first_close > 10000:
        logger.info(f"Detected scaled price values (first close: {first_close}). Applying price division by 100...")
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col] / 100.0
        logger.info(f"Rescaled prices. New first close: {df['close'].iloc[0]:.2f}")
        
    # Drop rows with NaN or zero prices
    df = df.dropna()
    df = df[(df[['open', 'high', 'low', 'close']] > 0).all(axis=1)]
    
    logger.info(f"Cleaned dataset: {len(df)} bars. Start: {df.index[0]} | End: {df.index[-1]}")
    
    # 3. Initialize AI Pattern Learner
    memory = ExperienceMemory(capacity=5000)
    learner = PatternLearner(memory)
    
    # Log initial stats
    prev_winning = len(learner.patterns.get(f"{symbol}_winning", []))
    prev_losing = len(learner.patterns.get(f"{symbol}_losing", []))
    logger.info(f"Pre-training pattern count for {symbol}: Winning={prev_winning}, Losing={prev_losing}")
    
    # 4. Run Single-Timeframe Training on 10-year Gold history
    logger.info("Executing training on downloaded 10-year historical dataset...")
    try:
        # Train on the last 15,000 hourly bars (about 2.5 years of hourly data) for fast execution
        # Hourly data is deep enough for trend and swing analysis.
        df_train = df.tail(15000)
        learner.train_on_single_timeframe(symbol, df_train)
    except Exception as e:
        logger.error(f"Error during single-timeframe training: {e}")
        import traceback
        traceback.print_exc()
        
    # 5. Run Synthetic Idealized ("Imaginary") Pattern Training
    logger.info("Executing training on synthetic idealized ('imaginary') pattern templates...")
    try:
        learner.train_on_synthetic_idealized_patterns(symbol, n_samples_per_pattern=500)
    except Exception as e:
        logger.error(f"Error during synthetic pattern training: {e}")
        import traceback
        traceback.print_exc()
        
    # 6. Verify training results
    stats = learner.training_stats.get(symbol, {})
    new_winning = len(learner.patterns.get(f"{symbol}_winning", []))
    new_losing = len(learner.patterns.get(f"{symbol}_losing", []))
    
    logger.info("====================================")
    logger.info("      TRAINING RUN COMPLETED        ")
    logger.info("====================================")
    logger.info(f"Total ML Samples: {stats.get('total_samples', 0)}")
    logger.info(f"AI Model Win Rate: {stats.get('win_rate', 0.0)}%")
    logger.info(f"Post-training pattern count: Winning={new_winning}, Losing={new_losing}")
    
    # Explicitly save patterns database
    learner.save_patterns()
    logger.info("Patterns saved successfully to data/smc_patterns.json")
    logger.info("Gold Pattern Training finished successfully!")

if __name__ == "__main__":
    main()
