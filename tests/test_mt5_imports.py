# tests/test_mt5_imports.py
import os
import re
import unittest

class TestMT5Imports(unittest.TestCase):
    def test_no_raw_mt5_imports_outside_gateway(self):
        """Assert that no file imports MetaTrader5 directly except the gateway and approved tests."""
        allowed_files = {
            "utils/mt5_gateway.py",
            "core/execution_service.py",
            "core/emergency_exit_controller.py",
            "tests/test_mt5_imports.py",
            "tests/test_dashboard_safety.py",
            "launcher.py",
            "scripts/test_complete_setup.py",
            "scripts/test_live_execution.py",
            "scripts/test_mt5.py",
            "scripts/test_smc_indicators.py"
        }
        
        # We walk the workspace directory and check for raw import lines
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        violations = []
        
        # Patterns to check
        import_pattern = re.compile(r'^\s*(import\s+MetaTrader5|from\s+MetaTrader5\s+import)')
        
        for root, dirs, files in os.walk(workspace_root):
            # Skip virtual environments, cache folders, and hidden folders
            if any(p in root for p in ['venv', '.git', '.vscode', '__pycache__', 'dist', 'build', '.gemini', 'PulseViper.spec', 'launcher.spec']):
                continue
                
            for file in files:
                if not file.endswith('.py'):
                    continue
                    
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, workspace_root).replace('\\', '/')
                
                # Skip some files inside scratch directory if they are original backups
                if rel_path.startswith('scratch/') and rel_path != 'scratch/test_dashboard_safety.py':
                    # Allow old scripts in scratch
                    continue
                if rel_path in allowed_files:
                    continue
                    
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if import_pattern.search(line):
                                violations.append(f"{rel_path}:{line_num} -> {line.strip()}")
                except Exception as e:
                    pass
                    
        self.assertEqual(len(violations), 0, f"Raw MetaTrader5 imports found in restricted files:\n" + "\n".join(violations))

if __name__ == '__main__':
    unittest.main()
