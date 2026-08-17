# launcher.py
r"""
PulseViper Core Launcher with Subprocess Pre-Flight Checks.
Ensures dependencies are met and MT5 broker connection is active via virtual environment Python.
This launcher itself does not import external libraries directly, keeping the executable compiled by PyInstaller fast and lightweight.

IMPORTANT (Windows):
    Do NOT double-click this .py file directly. On many systems .py files are opened by the IDE/editor
    instead of being executed by Python. Instead, run ONE of these entry points:

        - DOUBLE_CLICK_ME.bat            (recommended for normal users)
        - QuickStart_PulseViper.bat      (scalping defaults, skips MT5 pre-flight, no auto browser)
        - start_pulse_viper.bat          (full control, forwards all CLI args)
        - In a terminal:
              venv\Scripts\python.exe launcher.py --help
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

os.makedirs("logs", exist_ok=True)

_env_added = False
if "PYTHONIOENCODING" not in os.environ or not os.environ["PYTHONIOENCODING"]:
    os.environ["PYTHONIOENCODING"] = "utf-8:ignore"
    _env_added = True
if "PYTHONUTF8" not in os.environ or os.environ["PYTHONUTF8"] not in ("0", "1"):
    os.environ["PYTHONUTF8"] = "1"
    _env_added = True
if _env_added:
    os.environ["PYTHONLEGACYWINDOWSSTDIO"] = ""

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

def resolve_python() -> str:
    venv_exe = os.path.abspath(os.path.join("venv", "Scripts", "python.exe"))
    candidates = []
    if os.path.exists(venv_exe):
        candidates.append(venv_exe)
    candidates.extend([
        "python",
        "python3",
        "py -3",
    ])
    last_error = None
    for candidate in candidates:
        try:
            parts = candidate.split()
            # Lightweight probe: --version. In restricted shells this is more reliable.
            res = subprocess.run(
                parts + ["--version"],
                capture_output=True, text=True, encoding="utf-8", errors="ignore",
                timeout=10,
            )
            if res.returncode == 0:
                return candidate
            last_error = f"probe rc={res.returncode}: {(res.stderr or res.stdout or '').strip()}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            continue
    # As a last resort, if venv exe exists accept it even if probe failed under restrictive shell
    if os.path.exists(venv_exe):
        return venv_exe
    raise RuntimeError(
        "No working Python interpreter found. Tried venv\\Scripts\\python.exe, python, python3, py -3. "
        f"Last error: {last_error or 'n/a'}"
    )


def run_preflight_checks(skip_mt5: bool = False) -> bool:
    logger.info("🔍 Starting PulseViper Pre-Flight Checks...")
    os.makedirs("logs", exist_ok=True)

    try:
        python_exe = resolve_python()
        logger.info(f"🐍 Using Python: {python_exe}")
    except Exception as e:
        logger.error(f"❌ Python resolution failed: {e}")
        return False

    skip_flag = "1" if skip_mt5 else "0"

    # Tiny verification script to run in the virtual environment Python
    checker_script = r"""
import sys
import os
skip_mt5 = os.environ.get("PV_SKIP_MT5", "0") == "1"
try:
    import pandas as pd
    import numpy as np
    import sklearn
    import torch
    import scipy
except ImportError as e:
    print(f"IMPORT_ERROR:{e}")
    sys.exit(1)

if skip_mt5:
    print("SUCCESS:SKIPPED:0:XAUUSD")
    sys.exit(0)

try:
    import MetaTrader5 as mt5
except ImportError as e:
    print(f"MT5_IMPORT_ERROR:{e}")
    sys.exit(5)

if not mt5.initialize(timeout=5000):
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
        with open(settings_file, "r", encoding="utf-8") as f:
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

company = (getattr(account_info, "company", "") or "").replace(":", "_") or "Unknown"
login = getattr(account_info, "login", 0) or 0
print(f"SUCCESS:{company}:{login}:{symbol}")
mt5.shutdown()
sys.exit(0)
"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:ignore"
    env["PYTHONUTF8"] = "1"
    env["PV_SKIP_MT5"] = skip_flag

    try:
        # Run checker script as a subprocess
        parts = python_exe.split()
        res = subprocess.run(
            parts + ["-c", checker_script],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
            env=env, timeout=60,
        )
        if res.returncode == 0:
            output = res.stdout.strip()
            if output.startswith("SUCCESS:"):
                parts_out = output.split(":")
                if len(parts_out) >= 4:
                    logger.info(f"✅ Connected to Broker: {parts_out[1]} | Account: {parts_out[2]}")
                    logger.info(f"✅ Verified Target Symbol: {parts_out[3]}")
                logger.info("🚀 All pre-flight checks passed successfully!")
                return True
            else:
                logger.error(f"❌ Preflight check returned unexpected format: {output}")
                return False
        else:
            err_output = (res.stdout or "").strip() + " | " + (res.stderr or "").strip()
            # Parse checker errors
            if "IMPORT_ERROR" in err_output:
                logger.error(f"❌ Missing dependency check failed: {err_output}")
            elif "MT5_IMPORT_ERROR" in err_output:
                logger.error(f"❌ MetaTrader5 package not installed: {err_output}")
            elif "MT5_INIT_ERROR" in err_output:
                logger.error(f"❌ MetaTrader 5 initialization failed: {err_output}")
            elif "MT5_CONN_ERROR" in err_output:
                logger.error(f"❌ Broker connection failed: {err_output}")
            elif "SYMBOL_ERROR" in err_output:
                logger.error(f"❌ Symbol check failed: {err_output}")
            else:
                logger.error(f"❌ Pre-flight checks failed: {err_output}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("❌ Pre-flight checks timed out after 60s.")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to execute pre-flight checks: {e}")
        return False

def kill_process_by_port(port: int):
    try:
        cmd = f"netstat -ano | findstr :{port}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res.stdout:
            for line in res.stdout.strip().split('\n'):
                if 'LISTENING' in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid and pid != '0':
                        logger.info(f"Killing existing process (PID: {pid}) on port {port}...")
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                        time.sleep(1)
    except Exception as e:
        logger.warning(f"Could not kill process on port {port}: {e}")

def start_engine(port: int = 8000, extra_run_args: list | None = None, open_browser: bool = True):
    if is_port_in_use(port):
        logger.warning(f"⚠️ Warning: Port {port} is already in use. Attempting to kill old engine process...")
        kill_process_by_port(port)
        if is_port_in_use(port):
            logger.error(f"❌ Failed to free port {port}. Please close the old process manually.")

    try:
        python_exe = resolve_python()
    except Exception as e:
        logger.error(f"❌ Python resolution failed in start_engine: {e}")
        raise

    if not os.path.exists("run.py"):
        logger.error("❌ run.py not found in project root. Cannot launch engine.")
        raise FileNotFoundError("run.py missing from project root")

    logger.info(f"⚡ Launching Advanced Trading Engine subprocess using {python_exe}...")

    engine_log = os.path.join("logs", "engine_subprocess.log")
    os.makedirs("logs", exist_ok=True)

    py_parts = python_exe.split()
    cmd = py_parts + ["run.py", "--port", str(port)] + list(extra_run_args or [])

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:ignore"
    env["PYTHONUTF8"] = "1"

    try:
        log_fh = open(engine_log, "a", encoding="utf-8")
    except Exception:
        log_fh = None

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        env=env,
        bufsize=1,
    )

    import threading

    def log_stream():
        try:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except Exception:
                    pass
                if log_fh is not None:
                    try:
                        log_fh.write(line)
                        log_fh.flush()
                    except Exception:
                        pass
        finally:
            if log_fh is not None:
                try:
                    log_fh.close()
                except Exception:
                    pass

    t = threading.Thread(target=log_stream, daemon=True)
    t.start()

    def wait_for_port(timeout: float = 30.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if process.poll() is not None:
                return False
            if is_port_in_use(port):
                return True
            time.sleep(0.4)
        return is_port_in_use(port)

    dashboard_ready = wait_for_port(timeout=30.0)
    url = f"http://localhost:{port}"
    if dashboard_ready:
        logger.info(f"🌐 Dashboard ready at: {url}")
        if open_browser:
            try:
                webbrowser.open(url, new=2, autoraise=False)
            except Exception as e:
                logger.warning(f"Could not open browser automatically: {e}. Open {url} manually.")
    else:
        logger.warning(f"⏳ Dashboard not ready within 30s. You can open {url} manually. Full log: {os.path.abspath(engine_log)}")

    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("🛑 Received termination signal. Stopping trading engine...")
        try:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate gracefully; killing it.")
                process.kill()
        except Exception:
            pass


def _parse_launcher_args(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="PulseViper Launcher")
    parser.add_argument("--port", type=int, default=8000, help="Dashboard port (default: 8000)")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip pre-flight checks entirely")
    parser.add_argument("--skip-mt5", action="store_true", help="Skip MT5/broker pre-flight checks (keep deps check)")
    parser.add_argument("--no-dashboard", action="store_true", help="Pass --no-dashboard to run.py")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the dashboard URL in a browser")
    parser.add_argument("--symbols", nargs="+", default=None, help="Trading symbols passed to run.py")
    parser.add_argument("--mode", choices=["scalping", "intraday", "swing"], default=None, help="Trading mode")
    parser.add_argument("--interval", type=int, default=None, help="Analysis interval in seconds")
    known, extra = parser.parse_known_args(argv)
    return known, extra


if __name__ == "__main__":
    import argparse

    try:
        args, extra_run_args = _parse_launcher_args()
    except SystemExit as e:
        sys.exit(e.code)

    extra_for_run = extra_run_args[:]
    if args.no_dashboard:
        extra_for_run.append("--no-dashboard")
    if args.symbols:
        extra_for_run.extend(["--symbols", *args.symbols])
    if args.mode:
        extra_for_run.extend(["--mode", args.mode])
    if args.interval:
        extra_for_run.extend(["--interval", str(args.interval)])

    preflight_ok = True
    if not args.skip_preflight:
        preflight_ok = run_preflight_checks(skip_mt5=args.skip_mt5)

    if preflight_ok:
        try:
            start_engine(
                port=args.port,
                extra_run_args=extra_for_run,
                open_browser=not args.no_browser,
            )
        except Exception as e:
            logger.error(f"❌ Engine failed to start: {e}")
            sys.exit(2)
    else:
        logger.error("❌ Startup aborted due to pre-flight check failure.")
        sys.exit(1)
