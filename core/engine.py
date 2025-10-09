# core/engine.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
from collections import deque
import traceback

from utils.mt5_data import fetch_ohlcv, init_mt5, shutdown_mt5
from utils.features import feature_engine
from configs.config import Config


class AdvancedTradingEngine:
    def __init__(self, symbols=None, strategy_mode='adaptive'):
        self.strategy_mode = strategy_mode
        self.config = Config()

        # State & performance tracking
        self.market_state = {}
        self.performance_history = deque(maxlen=1000)
        self.risk_exposure = 0.0
        self.consecutive_losses = 0
        self.win_streak = 0
        self.connected = False
        self.cycle_count = 0

        # Multi-timeframe definitions
        self.timeframes = {
            'scalping': mt5.TIMEFRAME_M5,
            'intraday': mt5.TIMEFRAME_M15,
            'swing': mt5.TIMEFRAME_H1
        }

        # 🔌 Initialize MetaTrader connection FIRST
        self._initialize_connection()

        # 🎯 SMART SYMBOL DETECTION - after connection is established
        if symbols is None:
            self.symbols = self._auto_detect_symbols()
        else:
            self.symbols = self._validate_symbols(symbols)

        print(f"🚀 Advanced PulseViper Engine Initialized")
        print(f"📊 Symbols: {self.symbols}")
        print(f"🎯 Mode: {self.strategy_mode}")
        print(f"⏰ Timeframes: {list(self.timeframes.keys())}")

    # -----------------------------
    # 🔹 SMART SYMBOL DETECTION
    # -----------------------------
    def _auto_detect_symbols(self):
        """Automatically detect available and enabled symbols"""
        print("🔍 Auto-detecting trading symbols...")
        
        try:
            # Get all symbols from MT5
            all_symbols = mt5.symbols_get()
            if not all_symbols:
                print("❌ No symbols found in MT5")
                return ['XAUUSDm']  # Fallback
                
            available_symbols = [s.name for s in all_symbols]
            enabled_symbols = [s.name for s in all_symbols if s.visible]
            
            print(f"📊 Found {len(available_symbols)} total symbols")
            print(f"🎯 {len(enabled_symbols)} symbols enabled in Market Watch")
            
            # Test enabled symbols first
            working_symbols = []
            for symbol in enabled_symbols[:8]:  # Test first 8 enabled symbols
                if self._test_symbol_data(symbol):
                    working_symbols.append(symbol)
                    print(f"   ✅ {symbol}: Data available")
                else:
                    print(f"   ❌ {symbol}: No data")
            
            if working_symbols:
                return working_symbols[:5]  # Use max 5 working symbols
            
            # If no enabled symbols work, try popular symbols
            print("🔄 Testing popular symbols...")
            popular_symbols = ['XAUUSDm', 'EURUSD', 'GBPUSD', 'USDJPY', 'US30', 'GER40']
            
            for symbol in popular_symbols:
                if symbol in available_symbols:
                    print(f"   🔄 Enabling {symbol}...")
                    if mt5.symbol_select(symbol, True):
                        if self._test_symbol_data(symbol):
                            working_symbols.append(symbol)
                            print(f"   ✅ {symbol}: Enabled and working")
                        else:
                            print(f"   ❌ {symbol}: Enabled but no data")
                    else:
                        print(f"   ❌ {symbol}: Failed to enable")
            
            return working_symbols if working_symbols else ['XAUUSDm']
            
        except Exception as e:
            print(f"❌ Symbol detection error: {e}")
            return ['XAUUSDm']  # Ultimate fallback

    def _validate_symbols(self, requested_symbols):
        """Validate that requested symbols are available and have data"""
        print("🔍 Validating requested symbols...")
        valid_symbols = []
        
        try:
            all_symbols = mt5.symbols_get()
            available_symbols = [s.name for s in all_symbols] if all_symbols else []
            
            for symbol in requested_symbols:
                # Check if symbol exists
                if symbol not in available_symbols:
                    print(f"   ❌ {symbol}: Not available in MT5")
                    continue
                
                # Check if enabled, enable if not
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info and not symbol_info.visible:
                    print(f"   🔄 {symbol}: Enabling in Market Watch...")
                    if not mt5.symbol_select(symbol, True):
                        print(f"   ❌ {symbol}: Failed to enable")
                        continue
                
                # Test data availability
                if self._test_symbol_data(symbol):
                    valid_symbols.append(symbol)
                    print(f"   ✅ {symbol}: Validated and ready")
                else:
                    print(f"   ❌ {symbol}: No data available")
            
            if not valid_symbols:
                print("⚠️ No valid symbols found, using auto-detection...")
                return self._auto_detect_symbols()
            
            return valid_symbols
            
        except Exception as e:
            print(f"❌ Symbol validation error: {e}")
            return self._auto_detect_symbols()

    def _test_symbol_data(self, symbol, timeframe=mt5.TIMEFRAME_M15, bars=10):
        """Test if we can get data for a symbol"""
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
            return rates is not None and len(rates) >= 5  # At least 5 bars
        except:
            return False

    # -----------------------------
    # 🔹 ENHANCED CONNECTION MANAGEMENT
    # -----------------------------
    def _initialize_connection(self):
        """Initialize MT5 connection with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if init_mt5():
                    self.connected = True
                    # Verify connection works
                    account_info = mt5.account_info()
                    if account_info:
                        print(f"✅ Connected to MT5 (Account: {account_info.login})")
                        return
                    else:
                        print("⚠️ Connected but cannot get account info")
                else:
                    print(f"❌ MT5 connection failed (attempt {attempt + 1}/{max_retries})")
            except Exception as e:
                print(f"❌ Connection error: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(2)
        
        raise ConnectionError("❌ Failed to connect to MetaTrader 5 after multiple attempts")

    def _reconnect_if_needed(self):
        """Smart reconnection with health check"""
        try:
            # Simple health check - try to get account info
            account_info = mt5.account_info()
            if account_info is None:
                self.connected = False
                print("⚠️ Connection lost - attempting to reconnect...")
                time.sleep(1)
                self._initialize_connection()
        except Exception as e:
            self.connected = False
            print(f"⚠️ Connection check failed: {e}")
            time.sleep(1)
            self._initialize_connection()

    def _shutdown_connection(self):
        """Graceful MT5 shutdown"""
        if self.connected:
            try:
                shutdown_mt5()
                print("🔒 MT5 connection closed safely.")
                self.connected = False
            except Exception as e:
                print(f"⚠️ Error during shutdown: {e}")

    # -----------------------------
    # 🔹 ENHANCED ANALYSIS MODULE
    # -----------------------------
    def multi_timeframe_analysis(self, symbol):
        """Analyze symbol on multiple timeframes with fallbacks"""
        tf_analysis = {}
        successful_timeframes = 0

        for tf_name, tf_value in self.timeframes.items():
            try:
                df = fetch_ohlcv(symbol, tf_value, n=100)  # Reduced for speed
                if df is None or len(df) < 20:  # Reduced minimum
                    continue

                features = feature_engine.compute_advanced_features(df)
                if features.empty:
                    continue

                latest = features.iloc[-1]
                signal_strength = self.calculate_signal_strength(latest, tf_name)
                
                tf_analysis[tf_name] = {
                    'signal': signal_strength['signal'],
                    'confidence': signal_strength['confidence'],
                    'rsi': latest.get('rsi', 50),
                    'trend': latest.get('ema_trend', 0),
                    'regime': latest.get('market_regime', 'unknown'),
                    'price': latest.get('close', 0)
                }
                successful_timeframes += 1
                
            except Exception as e:
                print(f"   ⚠️ {symbol} {tf_name} analysis failed: {str(e)}")
                continue

        return tf_analysis if successful_timeframes > 0 else None

    def calculate_signal_strength(self, data, timeframe):
        """Enhanced signal generation with fallbacks"""
        signals, weights = [], []

        try:
            # RSI logic (with fallback)
            rsi = data.get('rsi', 50)
            rsi_slope = data.get('rsi_slope', 0)
            if rsi < 30 and rsi_slope > 0:
                signals.append(1); weights.append(0.25)
            elif rsi > 70 and rsi_slope < 0:
                signals.append(-1); weights.append(0.25)

            # Trend logic (with fallback)
            ema_trend = data.get('ema_trend', 0)
            macd_hist = data.get('macd_hist', 0)
            if ema_trend == 1 and macd_hist > 0:
                signals.append(1); weights.append(0.30)
            elif ema_trend == 0 and macd_hist < 0:
                signals.append(-1); weights.append(0.30)

            # Mean reversion (with fallback)
            bb_position = data.get('bb_position', 0.5)
            if bb_position < 0.1 and rsi < 40:
                signals.append(1); weights.append(0.20)
            elif bb_position > 0.9 and rsi > 60:
                signals.append(-1); weights.append(0.20)

            # Breakout (with fallback)
            bb_squeeze = data.get('bb_squeeze', 0)
            volume_ratio = data.get('volume_ratio', 1.0)
            ema_21 = data.get('ema_21', data.get('close', 0))
            close = data.get('close', 0)
            
            if bb_squeeze == 1 and volume_ratio > 1.5:
                direction = 1 if close > ema_21 else -1
                signals.append(direction); weights.append(0.25)

        except Exception as e:
            print(f"   ⚠️ Signal calculation error: {e}")

        if not signals:
            return {'signal': 0, 'confidence': 0.0}

        try:
            weighted_signal = sum(s * w for s, w in zip(signals, weights)) / sum(weights)
            confidence = min(abs(weighted_signal) * 2, 1.0)
            final_signal = 1 if weighted_signal > 0.1 else -1 if weighted_signal < -0.1 else 0
            return {'signal': final_signal, 'confidence': round(confidence, 3)}
        except:
            return {'signal': 0, 'confidence': 0.0}

    # -----------------------------
    # 🔹 ENHANCED RISK MANAGEMENT
    # -----------------------------
    def risk_management_check(self, symbol, signal, confidence):
        """Enhanced position sizing with volatility adjustment"""
        try:
            base_size = 0.01
            
            # Streak-based adjustment
            if self.consecutive_losses > 2:
                base_size *= 0.5
                print(f"   📉 Reduced size due to {self.consecutive_losses} losses")
            elif self.win_streak > 3:
                base_size *= min(1.2 + (self.win_streak * 0.1), 2.0)  # Cap at 2x
                print(f"   📈 Increased size due to {self.win_streak} wins")

            # Confidence-based sizing
            position_size = base_size * max(confidence, 0.1)  # Minimum 10% of base
            
            # Risk limits
            max_risk = getattr(self.config, 'INITIAL_BALANCE', 10000) * 0.02
            estimated_risk = position_size * 1000
            
            if estimated_risk > max_risk:
                position_size = max_risk / 1000
                print(f"   ⚠️ Capped size due to risk limits")

            return max(position_size, 0.01)  # Minimum 0.01 lots
            
        except Exception as e:
            print(f"   ⚠️ Risk management error: {e}")
            return 0.01

    # -----------------------------
    # 🔹 ENHANCED TRADE EXECUTION
    # -----------------------------
    def execute_paper_trade(self, symbol, decision, position_size):
        """Enhanced trade execution with detailed logging"""
        action_map = {1: "BUY", -1: "SELL", 0: "HOLD"}
        action = action_map[decision['signal']]

        trade_record = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'action': action,
            'confidence': decision['confidence'],
            'size': position_size,
            'price': decision.get('price', 0),
            'rsi': decision.get('rsi', 0),
            'reasoning': self.generate_trade_reasoning(decision)
        }

        self.performance_history.append(trade_record)
        self._update_streak(action)

        # Enhanced output with more details
        emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
        details = f"Size: {position_size:.3f} | Conf: {decision['confidence']}"
        if action != "HOLD":
            details += f" | RSI: {decision.get('rsi', 0):.1f}"
            details += f" | Price: {decision.get('price', 0):.5f}"
        
        print(f"{emoji} [{symbol}] {action} | {details}")
        
        if action != "HOLD":
            print(f"   📋 Reasoning: {trade_record['reasoning']}")

        return trade_record

    def _update_streak(self, action):
        """Improved streak tracking"""
        if action in ["BUY", "SELL"]:
            if len(self.performance_history) > 1:
                prev_trade = self.performance_history[-2]
                # Simple logic: if same action type, consider it a "win" for streak
                if prev_trade['action'] == action:
                    self.win_streak += 1
                    self.consecutive_losses = 0
                else:
                    self.consecutive_losses += 1
                    self.win_streak = 0
            else:
                # First trade
                self.win_streak = 1
                self.consecutive_losses = 0

    def generate_trade_reasoning(self, decision):
        """Enhanced reasoning with more indicators"""
        reasons = []
        
        rsi = decision.get('rsi', 50)
        if rsi < 35: 
            reasons.append(f"Oversold RSI ({rsi:.1f})")
        elif rsi > 65: 
            reasons.append(f"Overbought RSI ({rsi:.1f})")
            
        trend = decision.get('trend', 0)
        if trend == 1: 
            reasons.append("Uptrend")
        elif trend == 0: 
            reasons.append("Downtrend")
            
        regime = decision.get('regime', 'unknown')
        if regime == 'trending': 
            reasons.append("Trending market")
        elif regime == 'ranging': 
            reasons.append("Ranging market")
            
        confidence = decision.get('confidence', 0)
        if confidence > 0.7:
            reasons.append("High confidence")
        elif confidence < 0.3:
            reasons.append("Low confidence")
            
        return ", ".join(reasons) if reasons else "Market monitoring"

    # -----------------------------
    # 🔹 ENHANCED MAIN ENGINE LOOP
    # -----------------------------
    def run_engine(self, sleep_seconds=15):
        """Enhanced main loop with better error handling"""
        print(f"\n🎯 Starting Advanced Trading Engine...")
        print(f"⏰ Analysis interval: {sleep_seconds} seconds")
        print(f"📈 Multi-timeframe analysis: {list(self.timeframes.keys())}")
        print(f"🎯 Trading symbols: {self.symbols}")
        print("=" * 60)

        self.cycle_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 5

        try:
            while True:
                self.cycle_count += 1
                print(f"\n🔄 Cycle {self.cycle_count} | {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 50)

                # Connection health check
                self._reconnect_if_needed()
                if not self.connected:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        print("❌ Too many consecutive failures, stopping engine")
                        break
                    time.sleep(sleep_seconds)
                    continue
                
                consecutive_failures = 0  # Reset on successful cycle

                # Analyze each symbol
                successful_analyses = 0
                for symbol in self.symbols:
                    try:
                        tf_analysis = self.multi_timeframe_analysis(symbol)
                        if not tf_analysis:
                            print(f"⚠️ No analysis data for {symbol}")
                            continue

                        aggregated_signal = self.aggregate_timeframe_signals(tf_analysis)
                        position_size = self.risk_management_check(
                            symbol, aggregated_signal, aggregated_signal['confidence']
                        )
                        
                        # Add price to decision for better logging
                        aggregated_signal['price'] = tf_analysis.get('intraday', {}).get('price', 0)
                        aggregated_signal['rsi'] = tf_analysis.get('intraday', {}).get('rsi', 50)
                        
                        trade_record = self.execute_paper_trade(symbol, aggregated_signal, position_size)

                        self.market_state[symbol] = {
                            'last_analysis': tf_analysis,
                            'last_trade': trade_record,
                            'timestamp': datetime.now()
                        }
                        
                        successful_analyses += 1

                    except Exception as e:
                        print(f"❌ Error analyzing {symbol}: {str(e)}")
                        continue

                if successful_analyses == 0:
                    print("💤 No successful analyses this cycle")

                # Performance summary
                if self.cycle_count % 5 == 0:
                    self.print_performance_summary()

                time.sleep(sleep_seconds)

        except KeyboardInterrupt:
            print(f"\n🛑 Engine stopped by user after {self.cycle_count} cycles")
        except Exception as e:
            print(f"\n💥 Unexpected engine error: {e}")
            traceback.print_exc()
        finally:
            self.print_final_summary()

    # -----------------------------
    # 🔹 ENHANCED REPORTING
    # -----------------------------
    def aggregate_timeframe_signals(self, tf_analysis):
        """Enhanced signal aggregation"""
        signals, confidences = [], []

        for tf, analysis in tf_analysis.items():
            signals.append(analysis['signal'])
            confidences.append(analysis['confidence'])

        if not signals:
            return {'signal': 0, 'confidence': 0.0}

        # Dynamic weighting based on available timeframes
        weights = [0.2, 0.3, 0.5][:len(signals)]
        if len(weights) < len(signals):
            weights.extend([0.5] * (len(signals) - len(weights)))
        
        # Normalize weights
        total_weight = sum(weights)
        weights = [w/total_weight for w in weights]
        
        weighted_signal = sum(s * w for s, w in zip(signals, weights))
        final_signal = 1 if weighted_signal > 0.15 else -1 if weighted_signal < -0.15 else 0
        avg_confidence = sum(confidences) / len(confidences)

        return {
            'signal': final_signal,
            'confidence': round(avg_confidence, 3),
            'rsi': tf_analysis.get('intraday', {}).get('rsi', 50),
            'trend': tf_analysis.get('swing', {}).get('trend', 0),
            'regime': tf_analysis.get('swing', {}).get('regime', 'unknown')
        }

    def print_performance_summary(self):
        """Enhanced performance reporting"""
        if not self.performance_history:
            print("📊 No trades yet")
            return
            
        trades = list(self.performance_history)
        buy_trades = [t for t in trades if t['action'] == 'BUY']
        sell_trades = [t for t in trades if t['action'] == 'SELL']
        active_trades = [t for t in trades if t['action'] in ['BUY', 'SELL']]
        
        print(f"\n📊 PERFORMANCE SUMMARY (Cycle {self.cycle_count})")
        print(f"   Total Analyses: {self.cycle_count}")
        print(f"   BUY Signals: {len(buy_trades)} | SELL Signals: {len(sell_trades)}")
        print(f"   Active Trades: {len(active_trades)}")
        print(f"   Win Streak: {self.win_streak} | Loss Streak: {self.consecutive_losses}")
        if active_trades:
            avg_confidence = np.mean([t['confidence'] for t in active_trades])
            print(f"   Avg Confidence: {avg_confidence:.3f}")

    def print_final_summary(self):
        """Comprehensive final summary"""
        print(f"\n🎯 FINAL ENGINE SUMMARY")
        print(f"   Total Cycles: {self.cycle_count}")
        print(f"   Symbols Tracked: {len(self.market_state)}")
        print(f"   Total Analyses: {len(self.performance_history)}")
        print(f"   Final Win Streak: {self.win_streak}")
        print(f"   Final Loss Streak: {self.consecutive_losses}")
        print("   Engine shutdown complete.")
        self._shutdown_connection()


# -----------------------------
# Simplified Wrapper for Testing
# -----------------------------
class PulseViperEngine(AdvancedTradingEngine):
    def __init__(self, symbol='XAUUSDm', mode='intraday'):
        super().__init__(symbols=[symbol] if symbol else None, strategy_mode=mode)

    def run(self, sleep_seconds=15):
        self.run_engine(sleep_seconds)