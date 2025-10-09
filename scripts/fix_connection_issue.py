# scripts/fix_connection_issue.py
print("🔧 Fixing connection issue in engine.py...")

with open('core/engine.py', 'r') as f:
    content = f.read()

# Fix the reconnect method - remove MT5_PATH parameter
content = content.replace(
    'if not mt5.initialize(self.config.MT5_PATH):',
    'if not mt5.initialize():'
)

with open('core/engine.py', 'w') as f:
    f.write(content)

print("✅ Connection issue fixed!")