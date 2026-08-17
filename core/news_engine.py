import threading
import time
import requests
import xml.etree.ElementTree as ET
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional
import re

class NewsIntelligenceEngine:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.NewsEngine")
        self.events: List[Dict] = []
        self.news_headlines: List[Dict] = []
        self.current_sentiment = 0.0
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.last_live_success = None
        self.staleness_threshold = timedelta(minutes=30)

        self.bullish_keywords = [
            "growth", "above forecasts", "above expectations", "expansion", 
            "rebound", "surges", "jumps", "rally", "positive", "optimism",
            "beats", "strong", "improves", "upgrades", "higher", "hawkish",
            "support", "gains", "steady", "upgraded"
        ]
        self.bearish_keywords = [
            "slowdown", "recession", "weakening", "contraction", "sink", 
            "rout", "lower", "tensions", "escalating", "concerns", "misses",
            "below forecasts", "below expectations", "falls", "drops", "pessimism",
            "risk-off", "dovish", "deteriorated", "declines", "condemns", "stagflation"
        ]

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_news_scraper, daemon=True)
        self.thread.start()
        self.logger.info("News Intelligence Engine background scraper started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    def _run_news_scraper(self):
        while self.running:
            try:
                self.update_news_events()  # ForexFactory calendar (if it works)
                self.update_news_sentiment() # FXStreet News Sentiment
            except Exception as e:
                self.logger.error(f"Error in news scraper thread: {e}")
                
            for _ in range(300): # Run every 5 mins
                if not self.running:
                    break
                time.sleep(1)

    def update_news_sentiment(self):
        """Scrape FXStreet RSS feed to match MT5 News tab and perform Sentiment Analysis"""
        url = "https://www.fxstreet.com/rss/news"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                headlines = []
                for item in root.findall(".//item")[:20]: # Parse top 20 news
                    title = item.find("title")
                    pubDate = item.find("pubDate")
                    title_text = title.text if title is not None else ""
                    date_text = pubDate.text if pubDate is not None else ""
                    
                    if title_text:
                        headlines.append({"title": title_text, "date": date_text})
                
                with self.lock:
                    self.news_headlines = headlines
                    self.current_sentiment = self.calculate_sentiment(headlines)
                    
                self.logger.info(f"Updated news sentiment: {self.current_sentiment:.2f} based on {len(headlines)} headlines")
            else:
                self.logger.warning(f"Failed to fetch FXStreet RSS: HTTP {response.status_code}")
        except Exception as e:
            self.logger.error(f"Exception during FXStreet RSS update: {e}")

    def calculate_sentiment(self, headlines: List[Dict]) -> float:
        """Calculate market sentiment score from -1.0 to 1.0"""
        score = 0.0
        analyzed_count = 0
        
        for item in headlines:
            title = item['title'].lower()
            headline_score = 0.0
            
            # Simple keyword matching
            for word in self.bullish_keywords:
                if word in title:
                    headline_score += 0.5
            
            for word in self.bearish_keywords:
                if word in title:
                    headline_score -= 0.5
                    
            if headline_score != 0:
                # Clamp per-headline score
                score += max(-1.0, min(1.0, headline_score))
                analyzed_count += 1
                
        if analyzed_count > 0:
            final_score = score / analyzed_count
            return max(-1.0, min(1.0, final_score))
        return 0.0

    def get_market_sentiment(self) -> float:
        """Return the current rolling sentiment score"""
        with self.lock:
            return self.current_sentiment

    def update_news_events(self):
        url = "https://www.forexfactory.com/ffcal_week_this.xml"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                parsed_events = self.parse_xml_feed(response.content)
                if parsed_events:
                    with self.lock:
                        self.events = parsed_events
                        self.last_live_success = datetime.now(timezone.utc)
                else:
                    self.logger.warning("ForexFactory XML feed parsed empty event list. Re-arming static fallbacks.")
                    self._load_fallback_events()
            else:
                self.logger.warning(f"Failed to fetch ForexFactory calendar (HTTP {response.status_code}). Re-arming static fallbacks.")
                self._load_fallback_events()
        except Exception as e:
            self.logger.error(f"Exception during news events update: {e}. Re-arming static fallbacks.")
            self._load_fallback_events()

    def get_eastern_offset_hours(self, dt: datetime) -> int:
        """Calculate US Eastern Time offset (EST=5, EDT=4) dynamically for a given datetime."""
        year = dt.year
        # US DST starts second Sunday in March and ends first Sunday in November
        m1 = datetime(year, 3, 1)
        dst_start = datetime(year, 3, (6 - m1.weekday()) % 7 + 8, 2)  # 2 AM EST
        
        n1 = datetime(year, 11, 1)
        dst_end = datetime(year, 11, (6 - n1.weekday()) % 7 + 1, 2)  # 2 AM EDT
        
        if dst_start <= dt < dst_end:
            return 4  # EDT is UTC-4 (meaning UTC = Eastern + 4 hours)
        else:
            return 5  # EST is UTC-5 (meaning UTC = Eastern + 5 hours)

    def parse_xml_feed(self, xml_content: bytes) -> List[Dict]:
        events_list = []
        try:
            root = ET.fromstring(xml_content)
            for item in root.findall(".//event"):
                title = item.find("title")
                country = item.find("country")
                date = item.find("date")
                time_str = item.find("time")
                impact = item.find("impact")
                
                title_text = title.text if title is not None else ""
                country_text = country.text if country is not None else ""
                date_text = date.text if date is not None else ""
                time_text = time_str.text if time_str is not None else ""
                impact_text = impact.text if impact is not None else "Low"
                
                if not title_text or not date_text or not time_text:
                    continue
                
                try:
                    month, day, year = map(int, date_text.split("-"))
                    if time_text.lower() == "all day":
                        hour, minute = 0, 0
                    else:
                        time_clean = time_text.lower().strip()
                        is_pm = "pm" in time_clean
                        time_digits = time_clean.replace("am", "").replace("pm", "")
                        h_str, m_str = time_digits.split(":")
                        hour = int(h_str)
                        minute = int(m_str)
                        if is_pm and hour < 12: hour += 12
                        if not is_pm and hour == 12: hour = 0
                            
                    event_dt = datetime(year, month, day, hour, minute)
                    offset_hours = self.get_eastern_offset_hours(event_dt)
                    event_dt_utc = event_dt + timedelta(hours=offset_hours)
                    date_iso = event_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    date_iso = datetime.now(timezone.utc).isoformat()
                    
                events_list.append({
                    "event": title_text,
                    "country": country_text,
                    "date_iso": date_iso,
                    "impact": impact_text.upper()
                })
        except Exception:
            pass
        return events_list

    def is_execution_locked(self, current_time_utc: datetime, lockout_mins: int = 30, cooldown_mins: int = 15, symbol: str = None) -> Tuple[bool, Optional[str]]:
        # Determine if this symbol is affected by USD news
        # Crypto, indices without USD exposure, or non-USD forex crosses skip USD news lockout
        is_usd_sensitive = True
        if symbol is not None:
            sym_up = symbol.upper()
            crypto_bases = ["BTC", "ETH", "LTC", "XRP", "SOL", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "BNB", "LINK"]
            is_crypto = any(c in sym_up for c in crypto_bases)
            is_gold = "XAU" in sym_up or "GOLD" in sym_up
            has_usd = "USD" in sym_up
            # Gold is always USD-sensitive. Crypto is NOT. Forex pairs without USD are NOT.
            if is_crypto:
                is_usd_sensitive = False
            elif not is_gold and not has_usd:
                is_usd_sensitive = False

        # 1. First, check the manual weekly news schedule configured via dashboard
        try:
            from core.news_schedule import news_schedule
            blocked, reason = news_schedule.is_blocked(current_time_utc)
            if blocked:
                # If symbol is not USD-sensitive, skip manual USD schedule blocks
                if not is_usd_sensitive:
                    self.logger.debug(f"News schedule block skipped for non-USD symbol {symbol}: {reason}")
                else:
                    return True, f"Manual Schedule: {reason}"
        except Exception as nse:
            self.logger.error(f"Error checking manual news schedule: {nse}")

        # Check if live source is fresh or stale
        live_is_stale = False
        if self.last_live_success is None:
            live_is_stale = True
        else:
            time_since_success = datetime.now(timezone.utc) - self.last_live_success
            if time_since_success > self.staleness_threshold:
                live_is_stale = True

        # 2. Next, check news events
        with self.lock:
            for event in self.events:
                # If the event is static fallback, only lock if live source is stale
                if event.get("is_fallback") and not live_is_stale:
                    continue
                if event.get("impact") not in ["HIGH", "HIGH IMPACT"]:
                    continue
                # Symbol-aware: only block on USD events for USD-sensitive symbols
                event_country = event.get("country", "")
                if event_country == "USD" and not is_usd_sensitive:
                    continue
                if event_country != "USD":
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
                        source_info = "fallback (live source stale)" if event.get("is_fallback") else "live-confirmed"
                        return True, f"{source_info} news event: {event['event']} ({event['country']}) @ {event_time_str}"
                except Exception:
                    continue
        return False, None

    def _load_fallback_events(self):
        today = datetime.now(timezone.utc)
        start_of_week = today - timedelta(days=today.weekday())
        self.events = [
            {
                "event": "US Core CPI YoY (Fallback)",
                "country": "USD",
                "date_iso": (start_of_week + timedelta(days=2, hours=12, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "impact": "HIGH",
                "is_fallback": True
            },
            {
                "event": "FOMC Rate Decision (Fallback)",
                "country": "USD",
                "date_iso": (start_of_week + timedelta(days=3, hours=18, minutes=00)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "impact": "HIGH",
                "is_fallback": True
            },
            {
                "event": "US NFP (Fallback)",
                "country": "USD",
                "date_iso": (start_of_week + timedelta(days=4, hours=12, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "impact": "HIGH",
                "is_fallback": True
            }
        ]
