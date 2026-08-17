
import sqlite3

JOURNAL_DB = "data/trade_history.db"

conn = sqlite3.connect(JOURNAL_DB)
cursor = conn.cursor()

print("Table schema:")
cursor.execute("PRAGMA table_info(trades)")
for col in cursor.fetchall():
    print(col)

print("\nLast 10 trades:")
cursor.execute("SELECT id, date, time, symbol, action, pnl, close_reason FROM trades ORDER BY id DESC LIMIT 20")
for row in cursor.fetchall():
    print(row)

conn.close()
