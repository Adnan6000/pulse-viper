# launcher.py
"""
PulseViper Core Launcher with Subprocess Pre-Flight Checks.
Ensures dependencies are met and MT5 broker connection is active via virtual environment Python.
This launcher itself does not import external libraries directly, keeping the executable compiled by PyInstaller fast and lightweight.
"""
import sys
import os
import subprocess
import time
import webbrowser
import socket
import logging

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/startup.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("PulseViper.Launcher")

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def run_preflight_checks() -> bool:
    logger.info("🔍 Starting PulseViper Pre-Flight Checks...")
    os.makedirs("logs", exist_ok=True)
    
    python_exe = os.path.join("venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = "python"

    # Tiny verification script to run in the virtual environment Python
    checker_script = """
import sys
import os
try:
    import MetaTrader5 as mt5
    import pandas as pd
    import numpy as np
    import sklearn
    import torch
    import scipy
except ImportError as e:
    print(f"IMPORT_ERROR:{e}")
    sys.exit(1)

if not mt5.initialize():
    print("MT5_INIT_ERROR:MetaTrader 5 failed to initialize. Make sure MT5 is installed and running.")
    sys.exit(2)

account_info = mt5.account_info()
if account_info is None:
    print("MT5_CONN_ERROR:Broker Account connection failed. Check your login status inside MT5.")
    mt5.shutdown()
    sys.exit(3)

# Check active symbol from settings
settings_file = "configs/settings.json"
symbol = "XAUUSDm"
try:
    import json
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            settings = json.load(f)
            symbol = settings.get("active_symbol", "XAUUSDm")
except Exception:
    pass

sym_info = mt5.symbol_info(symbol)
if sym_info is None:
    # Try alternative symbol name without suffix
    alt_symbol = "XAUUSD"
    sym_info = mt5.symbol_info(alt_symbol)
    if sym_info is None:
        print(f"SYMBOL_ERROR:Gold trading symbols ({symbol} / {alt_symbol}) are unavailable in MarketWatch.")
        mt5.shutdown()
        sys.exit(4)
    symbol = alt_symbol

print(f"SUCCESS:{account_info.company}:{account_info.login}:{symbol}")
mt5.shutdown()
sys.exit(0)
"""
    try:
        # Run checker script as a subprocess
        res = subprocess.run([python_exe, "-c", checker_script], capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            output = res.stdout.strip()
            if output.startswith("SUCCESS:"):
                parts = output.split(":")
                logger.info(f"✅ Connected to Broker: {parts[1]} | Account: {parts[2]}")
                logger.info(f"✅ Verified Target Symbol: {parts[3]}")
                logger.info("🚀 All pre-flight checks passed successfully!")
                return True
            else:
                logger.error(f"❌ Preflight check returned unexpected format: {output}")
                return False
        else:
            err_output = res.stdout.strip() or res.stderr.strip()
            # Parse checker errors
            if "IMPORT_ERROR" in err_output:
                logger.error(f"❌ Missing dependency check failed: {err_output}")
            elif "MT5_INIT_ERROR" in err_output:
                logger.error(f"❌ MetaTrader 5 initialization failed: {err_output}")
            elif "MT5_CONN_ERROR" in err_output:
                logger.error(f"❌ Broker connection failed: {err_output}")
            elif "SYMBOL_ERROR" in err_output:
                logger.error(f"❌ Symbol check failed: {err_output}")
            else:
                logger.error(f"❌ Pre-flight checks failed: {err_output}")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to execute pre-flight checks: {e}")
        return False

def start_engine():
    port = 8000
    if is_port_in_use(port):
        logger.warning(f"⚠️ Warning: Port {port} is already in use. Is the engine already running?")
        
    python_exe = os.path.join("venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = "python"
        
    logger.info(f"⚡ Launching Advanced Trading Engine subprocess using {python_exe}...")
    
    cmd = [python_exe, "run.py", "--port", str(port)]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")

    # Thread to stream subprocess output to launcher output stream
    import threading
    def log_stream():
        for line in iter(process.stdout.readline, ''):
            sys.stdout.write(line)
            sys.stdout.flush()
    t = threading.Thread(target=log_stream, daemon=True)
    t.start()

    time.sleep(1.5)
    url = f"http://localhost:{port}"
    logger.info(f"🌐 Opening Web Dashboard at: {url}")
    webbrowser.open(url)
    
    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("🛑 Received termination signal. Stopping trading engine...")
        process.terminate()

if __name__ == "__main__":
    if run_preflight_checks():
        start_engine()
    else:
        logger.error("❌ Startup aborted due to pre-flight check failure.")
        sys.exit(1)
