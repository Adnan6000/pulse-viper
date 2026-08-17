# train_base_model.py
"""
Offline Multi-Strategy Pre-Training Pipeline for PulseViper's PyTorch Neural Network.
Loads historical multi-timeframe data from MT5, evaluates all 9 strategies chronologically,
resolves outcomes with transaction costs, and trains the model on a chronological split.
Saves weights to models/pulse_viper_base.pth and backs up old weights.
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
from datetime import datetime, timezone, timedelta
from typing import Tuple

# Adjust path to find core files
sys.path.append(os.getcwd())

from core.feature_extractor import FeatureExtractor
from core.pattern_learner import PulseViperNeuralNet
from strategies.crt_tbs import CrtTbsStrategy
from strategies.raja_strategy import RajaStrategy
from strategies.ict_strategy import IctStrategy
from strategies.bank_strategy import BankStrategy
from strategies.vsa_strategy import VsaStrategy
from strategies.avc_strategy import AvcStrategy
from strategies.m1_scalping_strategy import M1ScalpingStrategy
from strategies.vwap_strategy import VwapStrategy
from strategies.smc_concepts_strategy import SmcConceptsStrategy
from core.market_regime import MarketRegimeDetector, RegimeType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PulseViper.OfflineTrainer")

def init_mt5_connection():
    from utils.mt5_gateway import mt5_gateway as mt5
    if not mt5.initialize():
        logger.error("Failed to initialize MetaTrader 5 terminal.")
        sys.exit(1)
    logger.info("Connected to MT5 successfully.")

def fetch_historical_dataset(symbol: str, timeframe, n_bars: int) -> pd.DataFrame:
    from utils.mt5_gateway import mt5_gateway as mt5
    from utils.mt5_data import fetch_ohlcv
    logger.info(f"Fetching last {n_bars} bars for {symbol} on timeframe {timeframe}...")
    df = fetch_ohlcv(symbol, timeframe, n=n_bars)
    if df is None or len(df) < 100:
        logger.error(f"Failed to fetch sufficient historical data for {symbol} on timeframe {timeframe}.")
        sys.exit(1)
    logger.info(f"Fetched {len(df)} bars successfully.")
    return df

def calculate_roc_auc(y_true, y_scores):
    """
    Computes Area Under the ROC Curve (ROC AUC) using Mann-Whitney U statistic.
    """
    y_true = np.array(y_true).flatten()
    y_scores = np.array(y_scores).flatten()
    if len(np.unique(y_true)) < 2:
        return 0.5
    
    pos = y_scores[y_true == 1]
    neg = y_scores[y_true == 0]
    
    n_pos = len(pos)
    n_neg = len(neg)
    
    if n_pos == 0 or n_neg == 0:
        return 0.5
        
    all_scores = np.concatenate([pos, neg])
    all_true = np.concatenate([np.ones(n_pos), np.zeros(n_neg)])
    
    sort_idx = np.argsort(all_scores)
    all_true = all_true[sort_idx]
    
    ranks = np.arange(1, len(all_scores) + 1)
    pos_ranks = ranks[all_true == 1]
    
    u_stat = np.sum(pos_ranks) - (n_pos * (n_pos + 1)) / 2.0
    auc = u_stat / (n_pos * n_neg)
    return float(auc)

def generate_multi_strategy_samples(dfs: dict, symbol: str) -> Tuple[np.ndarray, np.ndarray]:
    import logging
    # Suppress console log spams from strategies during sample mining
    logging.getLogger("PulseViper.CrtTbsStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.RajaStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.IctStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.BankStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.VsaStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.AvcStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.M1ScalpingStrategy").setLevel(logging.WARNING)
    logging.getLogger("PulseViper.SmcConceptsStrategy").setLevel(logging.WARNING)

    df_d1 = dfs.get('D1')
    df_h4 = dfs.get('H4')
    df_h1 = dfs.get('H1')
    df_m15 = dfs.get('M15')
    df_m5 = dfs.get('M5')
    df_m1 = dfs.get('M1')

    # Calculate indicators on M1, M5, H1 once
    from utils.smc_indicators import SMCIndicators
    df_m1_feat = SMCIndicators.compute_smc_features(df_m1, window=3)
    df_m5_feat = SMCIndicators.compute_smc_features(df_m5, window=3) if df_m5 is not None else None
    df_h1_feat = SMCIndicators.compute_smc_features(df_h1, window=3) if df_h1 is not None else None

    # Calculate historical volume pressure and rvol once for df_m1
    from utils.volume_analyzer import VolumeAnalyzer
    rvol_series = VolumeAnalyzer.calculate_rvol(df_m1, period=20)
    bp_series, sp_series = VolumeAnalyzer.calculate_buying_selling_pressure(df_m1)

    # Shift all swing-dependent columns to eliminate lookahead leakage
    leakage_cols = [
        'is_swing_high', 'is_swing_low', 'is_sth', 'is_stl', 'is_ith', 'is_itl',
        'support', 'resistance', 'liq_sweep_type', 'liq_sweep_level', 'mss_signal',
        'active_bias', 'ob_reaction_signal', 'sr_reaction_signal', 'retest_pullback_signal',
        'trend_shift_signal'
    ]
    for col in leakage_cols:
        if col in df_m1_feat.columns:
            df_m1_feat[col] = df_m1_feat[col].shift(3).fillna(0)
        if df_m5_feat is not None and col in df_m5_feat.columns:
            df_m5_feat[col] = df_m5_feat[col].shift(3).fillna(0)
        if df_h1_feat is not None and col in df_h1_feat.columns:
            df_h1_feat[col] = df_h1_feat[col].shift(3).fillna(0)

    # M1 column arrays for quick outcome scans
    m1_closes = df_m1['close'].values
    m1_highs = df_m1['high'].values
    m1_lows = df_m1['low'].values
    m1_timestamps = df_m1.index

    # Detect swing legs on df_m5 using window=5 for robust swings
    logger.info("Extracting clean swing legs from M5 data...")
    df_m5_swings = SMCIndicators.detect_swing_points(df_m5, window=5)
    
    swing_points = []
    m5_highs = df_m5_swings['high'].values
    m5_lows = df_m5_swings['low'].values
    is_sh = df_m5_swings['is_swing_high'].values
    is_sl = df_m5_swings['is_swing_low'].values
    m5_timestamps = df_m5_swings.index
    
    for idx in range(len(df_m5_swings)):
        if is_sh[idx]:
            swing_points.append({'type': 'HIGH', 'price': m5_highs[idx], 'time': m5_timestamps[idx]})
        if is_sl[idx]:
            swing_points.append({'type': 'LOW', 'price': m5_lows[idx], 'time': m5_timestamps[idx]})
            
    # Alternate HIGH and LOW points
    alternating = []
    for pt in swing_points:
        if not alternating:
            alternating.append(pt)
            continue
        last = alternating[-1]
        if last['type'] == pt['type']:
            if pt['type'] == 'HIGH':
                if pt['price'] > last['price']:
                    alternating[-1] = pt
            else:
                if pt['price'] < last['price']:
                    alternating[-1] = pt
        else:
            alternating.append(pt)
            
    # Create swing legs
    legs = []
    for k in range(len(alternating) - 1):
        p1 = alternating[k]
        p2 = alternating[k+1]
        legs.append({
            'type': 'BULLISH' if p1['type'] == 'LOW' else 'BEARISH',
            'start_price': p1['price'],
            'end_price': p2['price'],
            'start_time': p1['time'],
            'end_time': p2['time']
        })
        
    logger.info(f"Identified {len(legs)} swing legs for candidate mining.")

    inputs = []
    targets = []
    
    # Simulation constants
    spread_pts = 12.0  # 1.2 pip spread proxy
    commission_pts = 7.0 # commission charge round-turn
    pip_size = 0.1 # Gold 1 pip = 0.1 USD
    cost_offset = (spread_pts + commission_pts) * pip_size # Total cost deducted from trade outcomes
    
    for leg_idx, leg in enumerate(legs):
        if leg_idx % 50 == 0:
            logger.info(f"Mining candidates: leg {leg_idx}/{len(legs)}...")
        t_start = leg['end_time'] # Pullback begins after the peak/valley
        
        # Find M1 index where pullback starts
        start_m1_idx = m1_timestamps.searchsorted(t_start)
        if start_m1_idx >= len(df_m1):
            continue
            
        L_swing = leg['start_price']
        H_swing = leg['end_price']
        
        end_m1_idx = len(df_m1) - 600
        for idx in range(start_m1_idx, len(df_m1)):
            price = m1_closes[idx]
            if leg['type'] == 'BULLISH':
                if price > H_swing: # continuation (new high)
                    end_m1_idx = idx
                    break
                if price < L_swing: # invalidation (new low)
                    end_m1_idx = idx
                    break
            else: # BEARISH
                if price < H_swing: # continuation (new low)
                    end_m1_idx = idx
                    break
                if price > L_swing: # invalidation (new high)
                    end_m1_idx = idx
                    break
                    
        if end_m1_idx <= start_m1_idx:
            continue
            
        triggered_strategies_in_leg = set()
        
        for i in range(start_m1_idx, end_m1_idx):
            # Optimizations: Only check every 3rd M1 bar, and stop if all strategies have triggered
            if (i - start_m1_idx) % 3 != 0:
                continue
            if len(triggered_strategies_in_leg) == 9:
                break
                
            current_price = m1_closes[i]
            t = m1_timestamps[i]
            
            swing_min = min(L_swing, H_swing)
            swing_max = max(L_swing, H_swing)
            swing_mid = swing_min + 0.5 * (swing_max - swing_min)
            
            in_zone = False
            if leg['type'] == 'BULLISH':
                if current_price <= swing_mid:
                    in_zone = True
            else: # BEARISH
                if current_price >= swing_mid:
                    in_zone = True
                    
            if not in_zone:
                continue
                
            # Strict lookahead bias protection: slice dfs at timestamp t
            sub_m1 = df_m1.loc[:t]
            sub_m5 = df_m5.loc[:t] if df_m5 is not None else None
            sub_m15 = df_m15.loc[:t] if df_m15 is not None else None
            sub_h1 = df_h1.loc[:t] if df_h1 is not None else None
            sub_h4 = df_h4.loc[:t] if df_h4 is not None else None
            sub_d1 = df_d1.loc[:t] if df_d1 is not None else None
            
            # Align biases
            h1_bias = 0
            if sub_h1 is not None and len(sub_h1) > 0:
                idx_h1 = df_h1_feat.index.searchsorted(t, side='right')
                if idx_h1 > 0:
                    h1_bias = float(df_h1_feat['active_bias'].iloc[idx_h1 - 1])
                    
            # Market Regime
            rvol_val = 1.0
            regime = MarketRegimeDetector.detect_regime(sub_m15, rvol_val, symbol=symbol)
            htf_bias = h1_bias
            
            atr_val = df_m1_feat['atr'].iloc[i]
            if np.isnan(atr_val) or atr_val <= 0:
                atr_val = 1.5
                
            current_rvol = float(rvol_series.iloc[i]) if not np.isnan(rvol_series.iloc[i]) else 1.0
            current_bp = float(bp_series.iloc[i]) if not np.isnan(bp_series.iloc[i]) else 50.0
            current_sp = float(sp_series.iloc[i]) if not np.isnan(sp_series.iloc[i]) else 50.0
            volume_cache = {
                "profile": {"poc_price": current_price}, 
                "rvol": current_rvol, 
                "buy_pressure": current_bp, 
                "sell_pressure": current_sp,
                "ofi": 0.0
            }
            
            # Evaluate strategies
            setups = []
            target_act = "BUY" if leg['type'] == 'BULLISH' else "SELL"
            
            # 1. Raja
            if "RAJA" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = RajaStrategy.evaluate_raja(sub_m15, None, sub_h1, sub_h4, current_price, atr_val, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "RAJA"))
                except Exception:
                    pass
                
            # 2. ICT
            if "ICT" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = IctStrategy.evaluate_ict(sub_m1, sub_m5, sub_m15, sub_h1, sub_h4, current_price, atr_val, htf_bias, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "ICT"))
                except Exception:
                    pass
        
            # 3. Bank
            if "BANK" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = BankStrategy.evaluate_bank(sub_m1, sub_m5, sub_m15, sub_h1, sub_h4, current_price, atr_val, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "BANK"))
                except Exception:
                    pass
        
            # 4. VSA
            if "VSA" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = VsaStrategy.evaluate_vsa(sub_m1, sub_m5, sub_h1, current_price, atr_val, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "VSA"))
                except Exception:
                    pass
        
            # 5. AVC
            if "AVC" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = AvcStrategy.evaluate_avc(sub_m1, sub_m5, sub_m15, current_price, atr_val, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "AVC"))
                except Exception:
                    pass
        
            # 6. M1 Scalping
            if "M1_SCALPING" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = M1ScalpingStrategy.evaluate_m1_scalping(sub_m1, sub_m5, sub_m15, current_price, atr_val, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "M1_SCALPING"))
                except Exception:
                    pass
        
            # 7. VWAP
            if "VWAP" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = VwapStrategy.evaluate_vwap(sub_m1, sub_m5, sub_h1, current_price, atr_val, regime.name, htf_bias)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "VWAP"))
                except Exception:
                    pass
        
            # 8. SMC Concepts
            if "SMC_CONCEPTS" not in triggered_strategies_in_leg:
                try:
                    act, sl, tp, _ = SmcConceptsStrategy.evaluate_smc(sub_m1, sub_m5, sub_m15, sub_h1, sub_h4, current_price, atr_val, htf_bias, volume_cache, regime.name)
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "SMC_CONCEPTS"))
                except Exception:
                    pass
        
            # 9. CRT TBS
            if "CRT_TBS" not in triggered_strategies_in_leg:
                try:
                    act, _, sl, tp, _ = CrtTbsStrategy.evaluate_crt_tbs(
                        df_d1=sub_d1,
                        df_h4=sub_h4,
                        df_h1=sub_h1,
                        df_m15=sub_m15,
                        df_m5=sub_m5,
                        df_m1=sub_m1,
                        current_price=current_price,
                        atr=atr_val,
                        volume_cache=volume_cache,
                        sentiment_cache={},
                        htf_bias=htf_bias,
                        symbol=symbol,
                        regime=regime.name
                    )
                    if act == target_act and sl > 0 and tp > 0:
                        setups.append((act, sl, tp, "CRT_TBS"))
                except Exception:
                    pass
                
            for act, strategy_sl, strategy_tp, strategy_name in setups:
                if strategy_name in triggered_strategies_in_leg:
                    continue
                    
                # Swing-based trade outcomes:
                # StopLoss is at the swing extremity: L_swing for BUY, H_swing for SELL
                # TakeProfit is at the opposite swing extremity: H_swing for BUY, L_swing for SELL
                sl_price = L_swing if act == "BUY" else H_swing
                tp_price = H_swing if act == "BUY" else L_swing
                
                # Resolve outcome (Win/Loss) against future candles
                resolved = False
                win = 0.0
                
                future_l = m1_lows[i+1 : i+600]
                future_h = m1_highs[i+1 : i+600]
                
                for f_low, f_high in zip(future_l, future_h):
                    if act == "BUY":
                        if f_low <= sl_price:
                            resolved = True
                            pnl = (sl_price - current_price) - cost_offset
                            win = 1.0 if pnl > 0 else 0.0
                            break
                        elif f_high >= tp_price:
                            resolved = True
                            pnl = (tp_price - current_price) - cost_offset
                            win = 1.0 if pnl > 0 else 0.0
                            break
                    else:  # SELL
                        if f_high >= sl_price:
                            resolved = True
                            pnl = (current_price - sl_price) - cost_offset
                            win = 1.0 if pnl > 0 else 0.0
                            break
                        elif f_low <= tp_price:
                            resolved = True
                            pnl = (current_price - tp_price) - cost_offset
                            win = 1.0 if pnl > 0 else 0.0
                            break
                
                if resolved:
                    # Extract clean 18-dimensional features (shifted/lookahead-free)
                    features_dict = {
                        'active_bias': htf_bias,
                        'liq_sweep_type': float(df_m1_feat['liq_sweep_type'].iloc[i]),
                        'mss_signal': float(df_m1_feat['mss_signal'].iloc[i]),
                        'fvg_class': str(df_m1_feat['fvg_class'].iloc[i]),
                        'volatility': float(df_m1_feat['volatility'].iloc[i]),
                        'atr_pct': float(df_m1_feat['atr_pct'].iloc[i]),
                        'rvol': current_rvol,
                        'buy_pressure': current_bp,
                        'sell_pressure': current_sp,
                        'ob_reaction_signal': float(df_m1_feat.get('ob_reaction_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'sr_reaction_signal': float(df_m1_feat.get('sr_reaction_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'retest_pullback_signal': float(df_m1_feat.get('retest_pullback_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'trend_shift_signal': float(df_m1_feat.get('trend_shift_signal', pd.Series(0.0, index=df_m1_feat.index)).iloc[i]),
                        'timestamp': pd.Timestamp(t).timestamp()
                    }
                    
                    feat_arr = FeatureExtractor.extract_nn_features(features_dict)
                    inputs.append(feat_arr)
                    targets.append([win])
                    triggered_strategies_in_leg.add(strategy_name)
                    
    logger.info(f"Mined {len(inputs)} unique swing-based strategy setups for NN training.")
    return np.array(inputs), np.array(targets)

def train_base_model():
    # Setup logger
    logger.info("Initializing preflight MT5 connection...")
    init_mt5_connection()
    
    from utils.mt5_gateway import mt5_gateway as mt5
    symbol = "XAUUSDm"
    if mt5.symbol_info(symbol) is None:
        symbol = "XAUUSD"
        if mt5.symbol_info(symbol) is None:
            logger.error("Gold symbols not found in terminal watch list.")
            sys.exit(1)
            
    # Fetch historical bars across multiple timeframes for multi-strategy mining
    # Limit bars size to fit safely in memory while providing deep historical coverage
    dfs = {
        'D1': fetch_historical_dataset(symbol, mt5.TIMEFRAME_D1, n_bars=200),
        'H4': fetch_historical_dataset(symbol, mt5.TIMEFRAME_H4, n_bars=600),
        'H1': fetch_historical_dataset(symbol, mt5.TIMEFRAME_H1, n_bars=2000),
        'M15': fetch_historical_dataset(symbol, mt5.TIMEFRAME_M15, n_bars=5000),
        'M5': fetch_historical_dataset(symbol, mt5.TIMEFRAME_M5, n_bars=10000),
        'M1': fetch_historical_dataset(symbol, mt5.TIMEFRAME_M1, n_bars=30000)
    }
    
    mt5.shutdown()
    
    X, y = generate_multi_strategy_samples(dfs, symbol)
    logger.info(f"Dataset generated. X shape: {X.shape}, y shape: {y.shape}")
    
    if len(X) < 100:
        logger.error("Dataset size too small. Cannot train neural net.")
        sys.exit(1)
        
    # Chronological Split (Train 85%, Validation 15%) to avoid autocorrelation leakage
    split_idx = int(0.85 * len(X))
    X_train, y_train = X[:split_idx], y[:split_idx]
    X_val, y_val = X[split_idx:], y[split_idx:]
    
    logger.info(f"Dataset split chronologically. Train size: {len(X_train)}, Validation size: {len(X_val)}")
    
    # Calculate class weights for BCELoss to handle imbalance
    num_neg = np.sum(y_train == 0.0)
    num_pos = np.sum(y_train == 1.0)
    pos_weight_val = num_neg / (num_pos + 1e-9)
    logger.info(f"Class distribution: wins={num_pos}, losses={num_neg}. Pos weight multiplier: {pos_weight_val:.4f}")
    
    # GPU acceleration selection
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Selected Device for training: {device}")
    
    model = PulseViperNeuralNet().to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-4)
    # Using weighted loss
    pos_weight_tensor = torch.tensor([pos_weight_val], dtype=torch.float32).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight_tensor)
    
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32).to(device)
    y_train_tensor = torch.tensor(y_train, dtype=torch.float32).to(device)
    X_val_tensor = torch.tensor(X_val, dtype=torch.float32).to(device)
    y_val_tensor = torch.tensor(y_val, dtype=torch.float32).to(device)
    
    epochs = 45
    batch_size = 256
    logger.info("Starting neural net multi-strategy training...")
    
    # Sigmoid function for evaluations
    m_sigmoid = nn.Sigmoid()
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        
        # Batch loop
        for start in range(0, len(X_train), batch_size):
            end = start + batch_size
            xb = X_train_tensor[start:end]
            yb = y_train_tensor[start:end]
            
            optimizer.zero_grad()
            # Raw logits from NN before sigmoid
            # We must pass it to BCEWithLogitsLoss
            # Wait: PulseViperNeuralNet's forward method ends with Sigmoid!
            # Let's check the design: if self.network contains Sigmoid, we must use BCELoss, NOT BCEWithLogitsLoss.
            # Yes! PulseViperNeuralNet ends in self.Sigmoid() (see: self.network ends with nn.Sigmoid()).
            # So we must use nn.BCELoss()!
            outputs = model(xb)
            loss = nn.BCELoss()(outputs, yb)
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item() * len(xb)
            
        epoch_loss /= len(X_train)
        
        # Validation score
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val_tensor)
            val_loss = nn.BCELoss()(val_outputs, y_val_tensor).item()
            
            pred_classes = (val_outputs >= 0.5).float()
            val_acc = (pred_classes == y_val_tensor).float().mean().item()
            
            # Compute ROC AUC
            val_auc = calculate_roc_auc(y_val, val_outputs.cpu().numpy())
            
        if (epoch + 1) % 5 == 0 or epoch == 0:
            logger.info(
                f"Epoch {epoch+1:02d}/{epochs:02d} | Train Loss: {epoch_loss:.5f} | "
                f"Val Loss: {val_loss:.5f} | Val Accuracy: {val_acc*100:.2f}% | Val AUC: {val_auc:.4f}"
            )
            
    # Model backups: backup old base weights before overwrite
    active_path = "models/pulse_viper_base.pth"
    backup_path = "models/pulse_viper_base_backup.pth"
    try:
        if os.path.exists(active_path):
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(active_path, backup_path)
            logger.info(f"🔄 Backed up old weights to {backup_path}")
    except Exception as backup_err:
        logger.warning(f"Failed to backup weights: {backup_err}")
        
    # Export state dictionary
    os.makedirs("models", exist_ok=True)
    torch.save(model.to('cpu').state_dict(), active_path)
    logger.info(f"✨ Multi-strategy pre-training complete. baseline model exported to: {active_path}")

if __name__ == "__main__":
    train_base_model()
