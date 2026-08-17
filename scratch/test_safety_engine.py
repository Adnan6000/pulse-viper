# scratch/test_safety_engine.py
"""
Unit tests for PulseViper SafetyEngine.
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone, timedelta

sys.path.insert(0, 'd:/pulse-viper')

import core.safety_engine as se
from utils.settings_manager import settings_manager

# Override DB path for safety during testing
TEST_DB = "data/test_safety_history.db"
se.JOURNAL_DB = TEST_DB

# Helper to clean/init test DB
def init_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            symbol TEXT,
            action TEXT,
            entry_price REAL,
            close_price REAL,
            sl REAL,
            tp REAL,
            lot_size REAL,
            pnl REAL,
            rr_achieved REAL,
            close_reason TEXT,
            duration_mins REAL,
            setup_type TEXT,
            fvg_class TEXT,
            bias INTEGER,
            volatility_regime TEXT,
            spread_at_entry REAL,
            classification TEXT,
            classification_reason TEXT,
            brain_score REAL,
            brain_tier1 REAL,
            brain_tier2 REAL,
            brain_tier3 REAL,
            brain_direction TEXT,
            brain_block_reason TEXT,
            session TEXT,
            vsa_signals TEXT
        )
    """)
    conn.commit()
    conn.close()

trade_counter = 0
def insert_test_trade(pnl: float, date_str: str):
    global trade_counter
    trade_counter += 1
    # 2 minutes apart per trade to prevent sibling grouping
    time_str = f"12:{trade_counter*2:02d}:00"
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trades (date, time, symbol, action, pnl)
        VALUES (?, ?, 'XAUUSDm', ?, ?)
    """, (date_str, time_str, f"SELL_{trade_counter}", pnl))
    conn.commit()
    conn.close()

def run_tests():
    print("=" * 60)
    print("  Testing SafetyEngine Protections")
    print("=" * 60)

    # Initialize configuration
    settings_manager.set("safety_engine_enabled", True)
    settings_manager.set("max_consecutive_losses", 3)
    settings_manager.set("max_daily_drawdown_pct", 3.0)
    settings_manager.set("max_weekly_drawdown_pct", 8.0)

    engine = se.SafetyEngine()

    # ─── TEST 1: Clean State ──────────────────────────────────────────────────
    init_test_db()
    allowed, reason = engine.check_entry_allowed()
    assert allowed, f"Should be allowed on clean DB, got: {reason}"
    print("  PASS  Test 1: Clean state allowed")

    # ─── TEST 2: Consecutive Losses ──────────────────────────────────────────
    init_test_db()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # 2 losses
    insert_test_trade(-100.0, today_str)
    insert_test_trade(-50.0, today_str)
    stats = engine.get_stats()
    assert stats["consecutive_losses"] == 2, f"Losses: {stats['consecutive_losses']}"
    allowed, reason = engine.check_entry_allowed()
    assert allowed, f"Should be allowed with 2 losses: {reason}"
    
    # 3 losses (violates max_consecutive_losses=3)
    insert_test_trade(-20.0, today_str)
    stats = engine.get_stats()
    assert stats["consecutive_losses"] == 3, f"Losses: {stats['consecutive_losses']}"
    allowed, reason = engine.check_entry_allowed()
    assert not allowed, "Should be blocked with 3 consecutive losses"
    assert "consecutive losses" in reason.lower(), f"Reason: {reason}"
    print("  PASS  Test 2: Consecutive losses block")

    # ─── TEST 3: Daily Drawdown Violation ─────────────────────────────────────
    init_test_db()
    # Insert 1 trade with large loss (e.g. $400, on $10000 balance it is 4.0% drawdown, max daily is 3.0%)
    insert_test_trade(-400.0, today_str)
    stats = engine.get_stats()
    assert stats["daily_pnl"] == -400.0
    allowed, reason = engine.check_entry_allowed()
    assert not allowed, "Should be blocked by daily drawdown"
    assert "daily drawdown" in reason.lower(), f"Reason: {reason}"
    print("  PASS  Test 3: Daily drawdown block")

    # ─── TEST 4: Weekly Drawdown Violation ────────────────────────────────────
    init_test_db()
    # Temporarily raise daily drawdown limit to test weekly drawdown independently on Monday
    settings_manager.set("max_daily_drawdown_pct", 20.0)
    # Insert a loss on a previous day of the current week (e.g. 3 days ago)
    past_date = datetime.now(timezone.utc) - timedelta(days=2)
    # Ensure it's in the current week (if today is Monday or Tuesday, 2 days ago is still in the week or last week.
    # To be safe, let's force the date string to be the same week Monday)
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    monday_str = monday.strftime("%Y-%m-%d")
    
    insert_test_trade(-900.0, monday_str) # $900 loss = 9.0% drawdown, weekly max is 8.0%
    stats = engine.get_stats()
    assert stats["weekly_pnl"] == -900.0
    allowed, reason = engine.check_entry_allowed()
    assert not allowed, "Should be blocked by weekly drawdown"
    assert "weekly drawdown" in reason.lower(), f"Reason: {reason}"
    # Restore daily limit
    settings_manager.set("max_daily_drawdown_pct", 3.0)
    print("  PASS  Test 4: Weekly drawdown block")

    # ─── TEST 5: Recovery with Win ───────────────────────────────────────────
    init_test_db()
    insert_test_trade(-100.0, today_str)
    insert_test_trade(-100.0, today_str)
    insert_test_trade(50.0, today_str) # win resets consecutive losses
    stats = engine.get_stats()
    assert stats["consecutive_losses"] == 0, f"Expected 0 consecutive losses after win, got: {stats['consecutive_losses']}"
    allowed, reason = engine.check_entry_allowed()
    # Total P&L is -150.0, which is 1.5% drawdown (less than 3%)
    assert allowed, f"Should be allowed after win reset: {reason}"
    print("  PASS  Test 5: Recovery and win reset")

    print("\nAll 5 SafetyEngine tests passed successfully!")
    
    # Cleanup test DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

if __name__ == "__main__":
    run_tests()
