import sys
import os

# Reconfigure stdout/stderr encoding to UTF-8 to prevent CP1252/UnicodeEncodeError on Windows
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        try:
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        except Exception:
            pass

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("🔍 Testing imports...")
print("=" * 50)

try:
    from configs.config import Config
    print("✅ configs.config imported")
except Exception as e:
    print(f"❌ configs.config failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from utils.mt5_data import fetch_ohlcv, init_mt5, shutdown_mt5
    print("✅ utils.mt5_data imported")
except Exception as e:
    print(f"❌ utils.mt5_data failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from utils.smc_indicators import SMCIndicators
    print("✅ utils.smc_indicators imported")
except Exception as e:
    print(f"❌ utils.smc_indicators failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.experience_memory import ExperienceMemory
    print("✅ core.experience_memory imported")
except Exception as e:
    print(f"❌ core.experience_memory failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.pattern_learner import PatternLearner
    print("✅ core.pattern_learner imported")
except Exception as e:
    print(f"❌ core.pattern_learner failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.trade_manager import PaperTradeManager, LiveTradeManager
    print("✅ core.trade_manager imported")
except Exception as e:
    print(f"❌ core.trade_manager failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.trade_journal import trade_journal
    print("✅ core.trade_journal imported")
except Exception as e:
    print(f"❌ core.trade_journal failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.daily_analyzer import DailyAnalyzer
    print("✅ core.daily_analyzer imported")
except Exception as e:
    print(f"❌ core.daily_analyzer failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.backtester import AdaptiveBacktester
    print("✅ core.backtester imported")
except Exception as e:
    print(f"❌ core.backtester failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from utils.settings_manager import settings_manager
    print("✅ utils.settings_manager imported")
except Exception as e:
    print(f"❌ utils.settings_manager failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from utils.volume_analyzer import VolumeAnalyzer
    print("✅ utils.volume_analyzer imported")
except Exception as e:
    print(f"❌ utils.volume_analyzer failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from utils.sentiment_analyzer import sentiment_analyzer
    print("✅ utils.sentiment_analyzer imported")
except Exception as e:
    print(f"❌ utils.sentiment_analyzer failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.crt_tbs import CrtTbsStrategy
    print("✅ strategies.crt_tbs imported")
except Exception as e:
    print(f"❌ strategies.crt_tbs failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.raja_strategy import RajaStrategy
    print("✅ strategies.raja_strategy imported")
except Exception as e:
    print(f"❌ strategies.raja_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.ict_strategy import IctStrategy
    print("✅ strategies.ict_strategy imported")
except Exception as e:
    print(f"❌ strategies.ict_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.bank_strategy import BankStrategy
    print("✅ strategies.bank_strategy imported")
except Exception as e:
    print(f"❌ strategies.bank_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.vsa_strategy import VsaStrategy
    print("✅ strategies.vsa_strategy imported")
except Exception as e:
    print(f"❌ strategies.vsa_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.avc_strategy import AvcStrategy
    print("✅ strategies.avc_strategy imported")
except Exception as e:
    print(f"❌ strategies.avc_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.m1_scalping_strategy import M1ScalpingStrategy
    print("✅ strategies.m1_scalping_strategy imported")
except Exception as e:
    print(f"❌ strategies.m1_scalping_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.vwap_strategy import VwapStrategy
    print("✅ strategies.vwap_strategy imported")
except Exception as e:
    print(f"❌ strategies.vwap_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.smc_concepts_strategy import SmcConceptsStrategy
    print("✅ strategies.smc_concepts_strategy imported")
except Exception as e:
    print(f"❌ strategies.smc_concepts_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from strategies.quantum_viper_strategy import QuantumViperStrategy
    print("✅ strategies.quantum_viper_strategy imported")
except Exception as e:
    print(f"❌ strategies.quantum_viper_strategy failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from dashboard.web_dashboard import WebDashboardServer
    print("✅ dashboard.web_dashboard imported")
except Exception as e:
    print(f"❌ dashboard.web_dashboard failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.safety_engine import SafetyEngine
    print("✅ core.safety_engine imported")
except Exception as e:
    print(f"❌ core.safety_engine failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.session_engine import SessionEngine
    print("✅ core.session_engine imported")
except Exception as e:
    print(f"❌ core.session_engine failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.brain_calibrator import BrainCalibrator
    print("✅ core.brain_calibrator imported")
except Exception as e:
    print(f"❌ core.brain_calibrator failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.prediction_auditor import prediction_auditor
    print("✅ core.prediction_auditor imported")
except Exception as e:
    print(f"❌ core.prediction_auditor failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.starvation_analyzer import StarvationAnalyzer
    print("✅ core.starvation_analyzer imported")
except Exception as e:
    print(f"❌ core.starvation_analyzer failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.market_regime import MarketRegimeDetector
    print("✅ core.market_regime imported")
except Exception as e:
    print(f"❌ core.market_regime failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.liquidity_map import LiquidityMap
    print("✅ core.liquidity_map imported")
except Exception as e:
    print(f"❌ core.liquidity_map failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.risk_engine import DynamicRiskEngine
    print("✅ core.risk_engine imported")
except Exception as e:
    print(f"❌ core.risk_engine failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.news_engine import NewsIntelligenceEngine
    print("✅ core.news_engine imported")
except Exception as e:
    print(f"❌ core.news_engine failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from core.trade_brain import TradeBrain
    print("✅ core.trade_brain imported")
except Exception as e:
    print(f"❌ core.trade_brain failed: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ All imports tested!")
