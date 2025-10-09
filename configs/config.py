# configs/config.py
class Config:
    SUPPORTED_SYMBOLS = None  # None => read from MT5
    MT5_TIMEFRAME = 1  # replace with mt5.TIMEFRAME_H1 in code
    HISTORY_BARS = 2000
    REPLAY_CAPACITY = 100000
    BATCH_SIZE = 128
    LEARNING_RATE = 3e-4
    PAPER_MODE = True
    LOG_PATH = "logs/signals.csv"
    MT5_PATH = None  # Auto-detect MT5 path
    INITIAL_BALANCE = 10000.0  # For paper trading