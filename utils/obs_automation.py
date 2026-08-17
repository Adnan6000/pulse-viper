# utils/obs_automation.py
"""
Quantum Viper 3.0 — OBS Studio Automation Engine
Provides real-time WebSocket IPC connection to OBS Studio (v28+) for automatic scene switching,
stream alert triggering, and visual overlay updates during live YouTube educational streams.
"""

import json
import logging
import threading
import time
from typing import Optional, Dict, Any

try:
    import websocket  # type: ignore
except ImportError:
    websocket = None


class ObsAutomationEngine:
    """Automates OBS Studio scene transitions and broadcast stream alerts."""
    
    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self.ws_url = f"ws://{host}:{port}"
        self.logger = logging.getLogger("PulseViper.ObsAutomation")
        self.connected = False
        self.ws = None
        self._lock = threading.Lock()
        
    def connect(self) -> bool:
        """Establish connection to OBS Studio WebSocket Server."""
        if not websocket:
            self.logger.warning("websocket-client module not installed. Install with: pip install websocket-client")
            return False
            
        try:
            self.ws = websocket.create_connection(self.ws_url, timeout=3.0)
            self.connected = True
            self.logger.info(f"🎥 Connected to OBS Studio WebSocket Server at {self.ws_url}")
            return True
        except Exception as e:
            self.logger.warning(f"Could not connect to OBS Studio WebSocket ({e}). Stream automation running in offline standby.")
            self.connected = False
            return False

    def switch_scene(self, scene_name: str) -> bool:
        """Switch active OBS scene (e.g. 'Alert Scene', 'Chart Overlay', 'Co-Pilot Breakdown')."""
        if not self.connected or not self.ws:
            return False
            
        payload = {
            "op": 6,
            "d": {
                "requestType": "SetCurrentProgramScene",
                "requestId": f"pv-obs-{int(time.time())}",
                "requestData": {
                    "sceneName": scene_name
                }
            }
        }
        try:
            with self._lock:
                self.ws.send(json.dumps(payload))
            self.logger.info(f"🎬 OBS Scene Switched to: '{scene_name}'")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to send OBS scene switch command: {e}")
            self.connected = False
            return False

    def trigger_setup_alert(self, symbol: str, action: str, p_win: float):
        """Trigger visual stream alert when a high probability trade setup is identified."""
        self.logger.info(f"📢 STREAM ALERT: {action} setup detected on {symbol} (Pwin: {p_win*100:.1f}%)")
        if self.connected:
            # Attempt switching to 'Trade Alert' scene if available in OBS
            self.switch_scene("Trade Alert")


# Global singleton instance
obs_engine = ObsAutomationEngine()
