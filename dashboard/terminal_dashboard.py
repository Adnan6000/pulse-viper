# dashboard/terminal_dashboard.py
from dashboard.live_dashboard import LiveDashboard

class TerminalDashboard(LiveDashboard):
    """Subclass of LiveDashboard to maintain backward compatibility with legacy scripts."""
    pass

# Factory function for backward compatibility
def start_dashboard(engine):
    """Start dashboard for a trading engine"""
    dashboard = TerminalDashboard(engine)
    dashboard.start()
    return dashboard