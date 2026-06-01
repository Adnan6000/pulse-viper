# core/news_engine.py
import threading
import time
import requests
import xml.etree.ElementTree as ET
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional

class NewsIntelligenceEngine:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.NewsEngine")
        self.events: List[Dict] = []
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

    def start(self):
        """Start background scraper thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_news_scraper, daemon=True)
        self.thread.start()
        self.logger.info("News Intelligence Engine background scraper started.")

    def stop(self):
        """Stop background scraper thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    def _run_news_scraper(self):
        while self.running:
            try:
                self.update_news_events()
            except Exception as e:
                self.logger.error(f"Error in news scraper thread: {e}")
                
            # Sleep for 15 minutes in 1-second chunks to exit quickly on shutdown
            for _ in range(900):
                if not self.running:
                    break
                time.sleep(1)

    def update_news_events(self):
        """Scrape the weekly economic calendar feed from ForexFactory"""
        url = "https://www.forexfactory.com/ffcal_week_this.xml"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                parsed_events = self.parse_xml_feed(response.content)
                with self.lock:
                    self.events = parsed_events
                self.logger.info(f"Successfully loaded {len(parsed_events)} economic events from ForexFactory.")
            else:
                self.logger.warning(f"Failed to fetch ForexFactory calendar: HTTP {response.status_code}")
                # Fallback to simulated weekly calendar if network error occurs to ensure safety
                self._load_fallback_events()
        except Exception as e:
            self.logger.error(f"Exception during news events update: {e}")
            self._load_fallback_events()

    def parse_xml_feed(self, xml_content: bytes) -> List[Dict]:
        """Parse ForexFactory weekly economic calendar XML"""
        events_list = []
        try:
            root = ET.fromstring(xml_content)
            for item in root.findall(".//event"):
                title = item.find("title")
                country = item.find("country")
                date = item.find("date")
                time_str = item.find("time")
                impact = item.find("impact")
                forecast = item.find("forecast")
                previous = item.find("previous")
                
                title_text = title.text if title is not None else ""
                country_text = country.text if country is not None else ""
                date_text = date.text if date is not None else ""
                time_text = time_str.text if time_str is not None else ""
                impact_text = impact.text if impact is not None else "Low"
                forecast_text = forecast.text if forecast is not None else ""
                previous_text = previous.text if previous is not None else ""
                
                if not title_text or not date_text or not time_text:
                    continue
                
                # Parse date and time into a UTC datetime
                # ForexFactory XML format: date "MM-DD-YYYY", time "h:mmam/pm" in EST/EDT typically, or UTC. 
                # Let's parse it and convert to UTC
                try:
                    # Parse ForexFactory date: e.g. "05-29-2026"
                    month, day, year = map(int, date_text.split("-"))
                    
                    # Parse time: e.g. "8:30am" or "all day"
                    if time_text.lower() == "all day":
                        hour, minute = 0, 0
                    else:
                        # Split hour, minute, am/pm
                        time_clean = time_text.lower().strip()
                        is_pm = "pm" in time_clean
                        time_digits = time_clean.replace("am", "").replace("pm", "")
                        h_str, m_str = time_digits.split(":")
                        hour = int(h_str)
                        minute = int(m_str)
                        if is_pm and hour < 12:
                            hour += 12
                        if not is_pm and hour == 12:
                            hour = 0
                            
                    # ForexFactory XML publishes calendar times in local US Eastern Time
                    # We convert US Eastern Time to UTC
                    # EDT is UTC-4, EST is UTC-5. Let's assume EDT (active in May) or handle dynamically:
                    # In a production system, we shift EST/EDT to UTC. Let's shift by -4 hours to get UTC.
                    event_dt = datetime(year, month, day, hour, minute)
                    # Convert US Eastern to UTC (approximate EDT for May)
                    event_dt_utc = event_dt + timedelta(hours=4)
                    date_iso = event_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    # Fallback date conversion
                    date_iso = datetime.now(timezone.utc).isoformat()
                    
                events_list.append({
                    "event": title_text,
                    "country": country_text,
                    "date_iso": date_iso,
                    "impact": impact_text.upper(),
                    "forecast": forecast_text,
                    "previous": previous_text
                })
        except Exception as e:
            self.logger.error(f"Failed to parse XML calendar: {e}")
        return events_list

    def is_execution_locked(self, current_time_utc: datetime, 
                            lockout_mins: int = 30, 
                            cooldown_mins: int = 15) -> Tuple[bool, Optional[str]]:
        """
        Check if we are in a news lockout or cooldown window for high-impact USD/XAU events.
        Returns: (is_locked, locking_event_description)
        """
        with self.lock:
            for event in self.events:
                # We only lock execution on HIGH impact news matching USD or EUR (key volatility drivers)
                if event.get("impact") not in ["HIGH", "HIGH IMPACT"]:
                    continue
                if event.get("country") not in ["USD", "EUR", "ALL"]:
                    continue
                
                try:
                    event_time_str = event["date_iso"]
                    if event_time_str.endswith("Z"):
                        event_time = datetime.strptime(event_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    else:
                        event_time = datetime.fromisoformat(event_time_str).replace(tzinfo=timezone.utc)
                        
                    pre_lock = event_time - timedelta(minutes=lockout_mins)
                    post_cool = event_time + timedelta(minutes=cooldown_mins)
                    
                    if pre_lock <= current_time_utc <= post_cool:
                        return True, f"{event['event']} ({event['country']}) @ {event_time_str}"
                except Exception as e:
                    self.logger.error(f"Error checking lockout window for event {event}: {e}")
                    
        return False, None

    def _load_fallback_events(self):
        """Load simulated events as safety fallback if network queries fail"""
        # Create standard weekly high-impact events for USD
        today = datetime.now(timezone.utc)
        start_of_week = today - timedelta(days=today.weekday())
        
        self.events = [
            {
                "event": "US Core CPI YoY",
                "country": "USD",
                "date_iso": (start_of_week + timedelta(days=2, hours=12, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), # Wed 12:30 UTC
                "impact": "HIGH",
                "forecast": "3.4%",
                "previous": "3.5%"
            },
            {
                "event": "FOMC Rate Decision",
                "country": "USD",
                "date_iso": (start_of_week + timedelta(days=3, hours=18, minutes=00)).strftime("%Y-%m-%dT%H:%M:%SZ"), # Thu 18:00 UTC
                "impact": "HIGH",
                "forecast": "5.50%",
                "previous": "5.50%"
            },
            {
                "event": "US Nonfarm Payrolls & Unemployment",
                "country": "USD",
                "date_iso": (start_of_week + timedelta(days=4, hours=12, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), # Fri 12:30 UTC
                "impact": "HIGH",
                "forecast": "180K",
                "previous": "175K"
            }
        ]
        self.logger.info("Loaded safety fallback economic calendar events.")
