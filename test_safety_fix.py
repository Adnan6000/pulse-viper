
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.safety_engine import SafetyEngine
from configs.config import Config
from utils.settings_manager import settings_manager
from utils.mt5_gateway import mt5_gateway as mt5

if not mt5.initialize():
    print("MT5 initialization failed!")
    exit()

print(f"Checking Safety Engine with Magic Number: {Config.MAGIC_NUMBER}")
se = SafetyEngine()
stats = se.get_stats()
print("Safety stats:", stats)
allowed, reason = se.check_entry_allowed()
print("Entry allowed?", allowed, "Reason:", reason)
mt5.shutdown()
print("Done!")
