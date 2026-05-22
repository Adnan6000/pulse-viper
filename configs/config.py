# configs/config.py
class Config:
    # MT5 Settings
    MT5_PATH = None  # Auto-detect MT5 installation path
    PAPER_MODE = True  # Set to False for real live trading
    
    # Portfolio & Sizing
    INITIAL_BALANCE = 10000.0  # Simulated paper trading account balance
    RISK_PERCENT = 1.0  # Risk 1.0% of account equity per trade
    MAGIC_NUMBER = 123456
    
    # Session Times (UTC)
    # Gold is most active during London and NY sessions.
    # Format: (Start Hour, End Hour)
    LONDON_SESSION = (7, 11)
    NY_SESSION = (12, 16)
    
    # Risk Limits
    MAX_SPREAD_POINTS = 60  # Max spread in broker points to allow entry (e.g. 6.0 USD for Gold)
    MIN_RR_RATIO = 2.0  # Minimum Risk-to-Reward ratio for trade entry
    
    # Data fetch settings
    HISTORY_BARS = 2000
    LOG_PATH = "logs/signals.csv"