# train_base_model.py
"""
Offline Heavy Pre-Training Pipeline for PulseViper's PyTorch Neural Network.
Loads historical XAUUSD data from MT5, calculates SMC confluences, 
constructs an 8-dimensional feature matrix, and trains the model on GPU/CPU.
Saves weights to models/pulse_viper_base.pth.
"""
import os
import sys
import time
import logging
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from datetime import datetime, timedelta

# Adjust path to find core files
sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PulseViper.OfflineTrainer")

def init_mt5_connection():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        logger.error("Failed to initialize MetaTrader 5 terminal.")
        sys.exit(1)
    logger.info("Connected to MT5 successfully.")

def fetch_historical_dataset(symbol: str, timeframe, n_bars: int) -> pd.DataFrame:
    import MetaTrader5 as mt5
    from utils.mt5_data import fetch_ohlcv
    logger.info(f"Fetching last {n_bars} bars for {symbol} on timeframe {timeframe}...")
    df = fetch_ohlcv(symbol, timeframe, n=n_bars)
    if df is None or len(df) < 100:
        logger.error(f"Failed to fetch sufficient historical data for {symbol} on timeframe {timeframe}.")
        sys.exit(1)
    logger.info(f"Fetched {len(df)} bars successfully.")
    return df

def generate_training_samples(df_ltf: pd.DataFrame, df_h1: pd.DataFrame, swing_window: int = 3):
    from utils.smc_indicators import SMCIndicators
    from core.pattern_learner import PatternLearner
    
    logger.info("Calculating SMC indicators and creating training dataset...")
    df_ltf_feat = SMCIndicators.compute_smc_features(df_ltf, window=swing_window)
    
    n = len(df_ltf_feat)
    highs = df_ltf_feat['high'].values
    lows = df_ltf_feat['low'].values
    closes = df_ltf_feat['close'].values
    atrs = df_ltf_feat['atr'].values
    
    h1_indices = df_h1.index
    h1_closes = df_h1['close'].values
    h1_highs = df_h1['high'].values
    h1_lows = df_h1['low'].values
    
    inputs = []
    targets = []
    
    # Pre-generate features and synthetic win/loss targets
    for i in range(50, n - 200):
        t = df_ltf_feat.index[i]
        
        # Get HTF bias from H1
        idx_h1 = h1_indices.searchsorted(t, side='right')
        if idx_h1 == 0:
            continue
        
        h1_close = h1_closes[idx_h1 - 1]
        h1_high = h1_highs[idx_h1 - 1]
        h1_low = h1_lows[idx_h1 - 1]
        h1_bias = 1.0 if h1_close > 0.5 * (h1_high + h1_low) else -1.0
        
        # Current LTF state features
        row = df_ltf_feat.iloc[i]
        
        features_dict = {
            'active_bias': h1_bias,
            'liq_sweep_type': float(row.get('liq_sweep_type', 0.0)),
            'mss_signal': float(row.get('mss_signal', 0.0)),
            'fvg_class': str(row.get('fvg_class', 'none')),
            'volatility': float(row.get('volatility', 0.0)),
            'atr_pct': float(row.get('atr_pct', 0.0)),
            'rvol': 1.0 + np.random.rand() * 0.5, # RVOL fallback for offline
            'buy_pressure': 55.0 if h1_bias > 0 else 45.0,
            'sell_pressure': 45.0 if h1_bias > 0 else 55.0
        }
        
        # Extract to 8-dim array
        feat_vector = PatternLearner.extract_nn_features(features_dict)
        
        # Synthetic target: evaluate if a trade opened here wins (1.0) or loses (0.0)
        # Using a simple 1:2 Risk-Reward ratio check over the next 200 candles
        atr_val = atrs[i]
        if atr_val <= 0:
            continue
            
        entry_price = closes[i]
        
        # Determine trade action from bias/sweep/mss
        action = None
        if h1_bias > 0 and (row.get('liq_sweep_type', 0) == 1 or row.get('mss_signal', 0) == 1):
            action = "BUY"
        elif h1_bias < 0 and (row.get('liq_sweep_type', 0) == -1 or row.get('mss_signal', 0) == -1):
            action = "SELL"
            
        if not action:
            continue
            
        sl = entry_price - (1.5 * atr_val) if action == "BUY" else entry_price + (1.5 * atr_val)
        tp = entry_price + (3.0 * atr_val) if action == "BUY" else entry_price - (3.0 * atr_val)
        
        outcome = 0.0
        for j in range(i + 1, min(i + 200, n)):
            curr_low = lows[j]
            curr_high = highs[j]
            
            if action == "BUY":
                if curr_low <= sl:
                    outcome = 0.0
                    break
                if curr_high >= tp:
                    outcome = 1.0
                    break
            else:
                if curr_high >= sl:
                    outcome = 0.0
                    break
                if curr_low <= tp:
                    outcome = 1.0
                    break
                    
        inputs.append(feat_vector)
        targets.append([outcome])
        
    return np.array(inputs, dtype=np.float32), np.array(targets, dtype=np.float32)

def train_base_model():
    # Setup logger
    logger.info("Initializing preflight MT5 connection...")
    init_mt5_connection()
    
    import MetaTrader5 as mt5
    symbol = "XAUUSDm"
    # Fallback checking
    if mt5.symbol_info(symbol) is None:
        symbol = "XAUUSD"
        if mt5.symbol_info(symbol) is None:
            logger.error("Gold symbols not found in terminal watch list.")
            sys.exit(1)
            
    # Fetch historical bars: 100,000 LTF (M5) and 10,000 HTF (H1)
    df_ltf = fetch_historical_dataset(symbol, mt5.TIMEFRAME_M5, n_bars=80000)
    df_h1 = fetch_historical_dataset(symbol, mt5.TIMEFRAME_H1, n_bars=10000)
    
    mt5.shutdown()
    
    X, y = generate_training_samples(df_ltf, df_h1)
    logger.info(f"Dataset generated. X shape: {X.shape}, y shape: {y.shape}")
    
    if len(X) < 100:
        logger.error("Dataset size too small. Cannot train neural net.")
        sys.exit(1)
        
    # GPU acceleration selection
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Selected Device for training: {device}")
    
    from core.pattern_learner import PulseViperNeuralNet
    model = PulseViperNeuralNet().to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.005)
    criterion = nn.BCELoss()
    
    # Shuffle and split train/validation
    indices = np.arange(len(X))
    np.random.shuffle(indices)
    split = int(0.85 * len(X))
    
    train_idx, val_idx = indices[:split], indices[split:]
    X_train, y_train = torch.tensor(X[train_idx]).to(device), torch.tensor(y[train_idx]).to(device)
    X_val, y_val = torch.tensor(X[val_idx]).to(device), torch.tensor(y[val_idx]).to(device)
    
    epochs = 40
    batch_size = 256
    logger.info("Starting neural net base model training...")
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        
        # Batch loop
        for start in range(0, len(X_train), batch_size):
            end = start + batch_size
            xb = X_train[start:end]
            yb = y_train[start:end]
            
            optimizer.zero_grad()
            outputs = model(xb)
            loss = criterion(outputs, yb)
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item() * len(xb)
            
        epoch_loss /= len(X_train)
        
        # Validation score
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val)
            val_loss = criterion(val_outputs, y_val).item()
            pred_classes = (val_outputs >= 0.5).float()
            val_acc = (pred_classes == y_val).float().mean().item()
            
        if (epoch + 1) % 5 == 0 or epoch == 0:
            logger.info(f"Epoch {epoch+1:02d}/{epochs:02d} | Train Loss: {epoch_loss:.5f} | Val Loss: {val_loss:.5f} | Val Accuracy: {val_acc*100:.2f}%")
            
    # Export state dictionary
    os.makedirs("models", exist_ok=True)
    export_path = "models/pulse_viper_base.pth"
    torch.save(model.to('cpu').state_dict(), export_path)
    logger.info(f"✨ Training complete. Baseline model exported to: {export_path}")

if __name__ == "__main__":
    train_base_model()
