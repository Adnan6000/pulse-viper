# scripts/final_fix.py
import os

print("🔧 FINAL FIX FOR ENGINE.PY")

# Read engine.py
with open('core/engine.py', 'r') as f:
    content = f.read()

# Remove any MT5_PATH parameters from init_mt5 calls
content = content.replace('init_mt5(self.config.MT5_PATH)', 'init_mt5()')
content = content.replace('init_mt5(config.MT5_PATH)', 'init_mt5()')

# Write back
with open('core/engine.py', 'w') as f:
    f.write(content)

print("✅ Engine.py fixed!")

# Also ensure config has MT5_PATH
config_content = '''
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
    MT5_PATH = None  # Auto-detect MT5
    INITIAL_BALANCE = 10000.0  # Paper trading balance
'''

with open('configs/config.py', 'w') as f:
    f.write(config_content)

print("✅ Config updated!")