# utils/sentiment_analyzer.py
import threading
import time
import requests  # type: ignore
import xml.etree.ElementTree as ET
import logging
import re
import datetime
from email.utils import parsedate_to_datetime
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

class NewsNaiveBayesClassifier:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words='english')
        self.model = MultinomialNB()
        self.is_fitted = False
        self._seed_data()
        
    def _seed_data(self):
        # High quality financial headlines and correlation outcomes across Forex, Gold, Crypto, and Indices
        X_seed = [
            # Bullish USD / Bearish Gold & Crypto (class 2)
            "US inflation rises higher than forecast, rate hike expected",
            "Fed CPI jumps, Powell hints rate cuts delayed",
            "Strong US jobs growth beats consensus forecasts",
            "US unemployment rate falls to record low",
            "Dollar surges as Treasury yields reach fresh highs",
            "US GDP grows at robust pace, recession risk declines",
            "Retail sales numbers surpass expectations, consumer strong",
            "Hawkish FOMC minutes indicate rates remain high",
            "Federal Reserve keeps rates high to combat inflation",
            "US dollar index extends gains on safe-haven flows",
            "Strong nonfarm payrolls report boosts dollar",
            "Bitcoin drops as regulatory scrutiny intensifies",
            "Crypto market faces liquidation pressure following Fed remarks",
            "Dollar rally weighs heavily on gold and silver prices",

            # Bearish USD / Bullish Gold & Crypto (class 0)
            "Fed cuts interest rates amid economic slowdown fears",
            "US payrolls miss estimates by wide margin, dollar drops",
            "Inflation cools down rapidly, Dovish pivot anticipated",
            "Dollar weakens significantly as treasury yields decline",
            "Gold hits record high on strong safe haven inflows",
            "Dovish Fed statement suggests rate cuts coming soon",
            "US GDP growth slows to crawl, contraction fears loom",
            "Unemployment claims surge, labor market softening",
            "Powell hints at rate cuts at upcoming meeting",
            "Gold prices surge as investors flock to safety",
            "Weak service sector PMI puts pressure on greenback",
            "Bitcoin breaks resistance as institutional ETF inflows hit new record",
            "Crypto market rallies as dollar weakens following dovish comments",
            "Bullish surge in gold and crypto on liquidity expansion expectation",

            # Neutral (class 1)
            "Markets wait for US CPI release tomorrow",
            "Gold trading in tight range ahead of FOMC decision",
            "Dull market session with low holiday trading volume",
            "Crude oil inventories remain unchanged from last week",
            "European markets steady ahead of trade data report",
            "XAUUSD consolidation continues within established channel",
            "Investors review mixed corporate earnings reports",
            "Gold prices steady as traders hold positions",
            "Bitcoin consolidates near key moving averages ahead of session"
        ]
        y_seed = [
            2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            1, 1, 1, 1, 1, 1, 1, 1, 1
        ]
        
        # Fit vectorizer and train model
        X_vec = self.vectorizer.fit_transform(X_seed)
        self.model.fit(X_vec, y_seed)
        self.is_fitted = True

    def predict(self, headline: str) -> float:
        """Predict expected sentiment score in range [-1.0, 1.0]"""
        if not self.is_fitted:
            return 0.0
        try:
            X_vec = self.vectorizer.transform([headline])
            probs = self.model.predict_proba(X_vec)[0]  # probabilities for classes [0, 1, 2]
            p_bear = probs[0]
            p_bull = probs[2]
            # Bounded difference between Bullish and Bearish USD probabilities
            return float(p_bull - p_bear)
        except Exception:
            return 0.0

    def online_fit(self, headlines: list, labels: list):
        """Fit model online on new labels (mapped from -1, 0, 1 to 0, 1, 2)"""
        if not headlines or not labels:
            return
        try:
            mapped_labels = []
            for label in labels:
                if label == -1: mapped_labels.append(0)
                elif label == 0: mapped_labels.append(1)
                else: mapped_labels.append(2)
                
            X_vec = self.vectorizer.transform(headlines)
            self.model.partial_fit(X_vec, mapped_labels, classes=[0, 1, 2])
        except Exception:
            pass

class SentimentAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.SentimentAnalyzer")
        self.nb_classifier = NewsNaiveBayesClassifier()
        self.news_score = 0.0
        self.news_articles = []
        self.pending_articles = []
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self._last_price = None
        
    def start(self):
        """Start the background news scraper thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_news_scraper, daemon=True)
        self.thread.start()
        self.logger.info("News sentiment background worker started with Naive Bayes.")
        
    def stop(self):
        """Stop the background news scraper thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
            
    def _run_news_scraper(self):
        while self.running:
            try:
                self.update_news_sentiment()
            except Exception as e:
                self.logger.error(f"Error in news scraper loop: {e}")
            # Sleep for 10 minutes (600 seconds) in 1-second chunks to exit quickly on shutdown
            for _ in range(600):
                if not self.running:
                    break
                time.sleep(1)

    def record_price_tick(self, price: float):
        """
        Record a real-time price tick. Evaluates pending news headlines and triggers online fitting
        if enough time has passed to observe price outcome changes.
        """
        if price is None or price <= 0:
            return
            
        with self.lock:
            self._last_price = price
            now = time.time()
            evaluated_headlines = []
            evaluated_labels = []
            remaining_pending = []
            
            for art in self.pending_articles:
                # After 60 seconds of a news release, check correlation
                if now - art["timestamp"] >= 60.0:
                    initial_price = art["initial_price"]
                    pct_change = (price - initial_price) / initial_price
                    
                    # Gold moves inversely to USD.
                    # Gold up (pct_change > 0.0002) => Bearish USD (label -1)
                    # Gold down (pct_change < -0.0002) => Bullish USD (label 1)
                    # Flat => Neutral (label 0)
                    if pct_change > 0.0002:
                        label = -1
                    elif pct_change < -0.0002:
                        label = 1
                    else:
                        label = 0
                        
                    evaluated_headlines.append(art["title"])
                    evaluated_labels.append(label)
                    self.logger.info(f"Online Learning: Fitting news '{art['title'][:40]}...' | Price: {initial_price:.2f} -> {price:.2f} ({pct_change*100:.3f}%) | Label: {label}")
                else:
                    remaining_pending.append(art)
                    
            self.pending_articles = remaining_pending
            
            if evaluated_headlines:
                self.nb_classifier.online_fit(evaluated_headlines, evaluated_labels)

    def update_news_sentiment(self):
        """Scrape Yahoo Finance, CNBC, FXStreet, and Investing.com RSS feeds, running Naive Bayes polarity checks"""
        urls = [
            "https://finance.yahoo.com/rss/headline?s=GC=F",
            "https://www.cnbc.com/id/15839069/device/rss/rss.html",
            "https://www.fxstreet.com/rss/news",
            "https://www.investing.com/rss/news_95.rss"
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        all_headlines = []
        articles = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    for item in root.findall(".//item"):
                        title = item.find("title")
                        link = item.find("link")
                        pub_date = item.find("pubDate")
                        desc = item.find("description")
                        
                        title_text = title.text if title is not None else ""
                        link_text = link.text if link is not None else ""
                        date_text = pub_date.text if pub_date is not None else ""
                        
                        desc_raw: str = desc.text if desc is not None and desc.text is not None else ""
                        desc_text = re.sub(r'<[^>]*>|&nbsp;|&#\d+;', ' ', desc_raw).strip()
                        desc_text = re.sub(r'\s+', ' ', desc_text)
                        
                        if title_text:
                            # Parse dates to filter out past/previous day's news
                            dt = None
                            if date_text:
                                try:
                                    dt = parsedate_to_datetime(date_text)
                                except Exception:
                                    pass
                            
                            # Ignore articles older than 24 hours
                            if dt and dt < now_utc - datetime.timedelta(hours=24):
                                continue
                                
                            # Predict using Naive Bayes
                            score = self.nb_classifier.predict(title_text)
                            all_headlines.append(score)
                            articles.append({
                                "title": title_text,
                                "link": link_text,
                                "date": date_text,
                                "description": desc_text,
                                "sentiment": score
                            })
            except Exception as e:
                self.logger.warning(f"Failed to fetch or parse news from {url}: {e}")
                
        with self.lock:
            # Sort news by newest first if possible, keep up to 20 articles
            articles.sort(key=lambda a: a.get("date", ""), reverse=True)
            self.news_articles = articles[:20]
            
            if all_headlines:
                self.news_score = float(np.mean(all_headlines))
                self.logger.info(f"Updated Naive Bayes news sentiment: {self.news_score:.2f} based on {len(all_headlines)} headlines")
            else:
                self.news_score = 0.0
                
            # Add new articles to pending list for online outcome evaluations
            if self._last_price is not None and self._last_price > 0:
                existing_pending_titles = {art["title"] for art in self.pending_articles}
                existing_titles = {art["title"] for art in self.news_articles}
                for art in self.news_articles:
                    if art["title"] not in existing_pending_titles:
                        self.pending_articles.append({
                            "title": art["title"],
                            "timestamp": time.time(),
                            "initial_price": self._last_price
                        })

    def forecast_usd_bias(self, articles: List[Dict], symbol: str = "") -> str:
        """
        Scan news articles for market/USD/Crypto/Gold keywords and return asset bias forecast.
        """
        usd_keywords = ["usd", "fed", "federal reserve", "cpi", "nfp", "nonfarm payrolls", "inflation", "retail sales", "gdp", "treasury", "powell", "interest rate", "btc", "bitcoin", "crypto", "gold", "xau"]
        bullish_words = ["rise", "rose", "rising", "gained", "gain", "higher", "strong", "stronger", "beat", "positive", "growth", "expansion", "hawkish", "upward", "surge", "rally", "outperform"]
        bearish_words = ["fall", "fell", "falling", "lost", "loss", "lower", "weak", "weaker", "miss", "negative", "decline", "declined", "contraction", "dovish", "downward", "drop", "dump", "underperform"]
        
        bull_count = 0
        bear_count = 0
        
        for art in articles:
            text = (art.get("title", "") + " " + art.get("description", "")).lower()
            sentiment_val = art.get("sentiment", 0.0)
            if sentiment_val > 0.15:
                bull_count += 1
            elif sentiment_val < -0.15:
                bear_count += 1

            if any(k in text for k in usd_keywords):
                bull_count += sum(1 for w in bullish_words if w in text)
                bear_count += sum(1 for w in bearish_words if w in text)
                
        if bull_count > bear_count:
            return "BULLISH"
        elif bear_count > bull_count:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def get_upcoming_events(self, usd_bias: str) -> List[Dict[str, Any]]:
        """
        Calculate dates for high-impact events and predict symbol-specific impacts.
        Filters out events older than the current day or in the past.
        """
        import datetime
        today = datetime.date.today()
        now_dt = datetime.datetime.now()
        
        # Calculate days of the current week (Monday=0, Sunday=6)
        start_of_week = today - datetime.timedelta(days=today.weekday())
        
        def date_for_offset(day_offset):
            d = start_of_week + datetime.timedelta(days=day_offset)
            return d.strftime("%Y-%m-%d")
            
        events = [
            # --- PAST WEEK EVENTS (Usually filtered out) ---
            {
                "event": "US Consumer Price Index (CPI) MoM",
                "date": f"{date_for_offset(-5)} 18:00",
                "impact": "HIGH",
                "currency": "USD",
                "status": "PAST WEEK",
                "actual": "0.3%",
                "consensus": "0.4%"
            },
            {
                "event": "US Nonfarm Payrolls (NFP) & Unemployment",
                "date": f"{date_for_offset(-3)} 18:00",
                "impact": "HIGH",
                "currency": "USD",
                "status": "PAST WEEK",
                "actual": "175K",
                "consensus": "243K"
            },
            # --- CURRENT WEEK EVENTS ---
            {
                "event": "US Core CPI YoY & MoM",
                "date": f"{date_for_offset(2)} 18:00",
                "impact": "HIGH",
                "currency": "USD",
                "status": "THIS WEEK",
                "actual": "UPCOMING",
                "consensus": "3.4%"
            },
            {
                "event": "FOMC Interest Rate Decision & Statement",
                "date": f"{date_for_offset(3)} 23:30",
                "impact": "HIGH",
                "currency": "USD",
                "status": "THIS WEEK",
                "actual": "UPCOMING",
                "consensus": "5.50%"
            },
            {
                "event": "US GDP Growth Rate QoQ (Advance)",
                "date": f"{date_for_offset(1)} 18:00",
                "impact": "MEDIUM",
                "currency": "USD",
                "status": "THIS WEEK",
                "actual": "UPCOMING",
                "consensus": "1.6%"
            },
            {
                "event": "US ISM Services PMI",
                "date": f"{date_for_offset(4)} 19:30",
                "impact": "MEDIUM",
                "currency": "USD",
                "status": "THIS WEEK",
                "actual": "UPCOMING",
                "consensus": "51.4"
            },
            # --- UPCOMING WEEK EVENTS ---
            {
                "event": "US ISM Manufacturing PMI",
                "date": f"{date_for_offset(7)} 19:30",
                "impact": "HIGH",
                "currency": "USD",
                "status": "UPCOMING WEEK",
                "actual": "UPCOMING",
                "consensus": "49.2"
            },
            {
                "event": "US ADP Employment Change",
                "date": f"{date_for_offset(9)} 17:15",
                "impact": "MEDIUM",
                "currency": "USD",
                "status": "UPCOMING WEEK",
                "actual": "UPCOMING",
                "consensus": "150K"
            },
            {
                "event": "US Crude Oil Inventories",
                "date": f"{date_for_offset(9)} 19:30",
                "impact": "MEDIUM",
                "currency": "USD",
                "status": "UPCOMING WEEK",
                "actual": "UPCOMING",
                "consensus": "-1.2M"
            },
            {
                "event": "US Unemployment Claims",
                "date": f"{date_for_offset(10)} 18:00",
                "impact": "HIGH",
                "currency": "USD",
                "status": "UPCOMING WEEK",
                "actual": "UPCOMING",
                "consensus": "215K"
            }
        ]
        
        filtered_events = []
        for event_item in events:
            ev: Dict[str, Any] = dict(event_item)
            ev["usd_forecast"] = usd_bias
            ev["pair_forecasts"] = {}
            for sym in ["XAUUSDm", "BTCUSDm", "EURUSDm", "GBPUSDm", "USDJPYm"]:
                sym_upper = sym.upper()
                if sym_upper.startswith("USD"):
                    ev["pair_forecasts"][sym] = usd_bias
                else:
                    if usd_bias == "BULLISH":
                        ev["pair_forecasts"][sym] = "BEARISH"
                    elif usd_bias == "BEARISH":
                        ev["pair_forecasts"][sym] = "BULLISH"
                    else:
                        ev["pair_forecasts"][sym] = "NEUTRAL"
            
            # Date filtering - only show upcoming and same-day events, exclude past days/times
            try:
                event_dt = datetime.datetime.strptime(ev["date"], "%Y-%m-%d %H:%M")
                # Keep event if it hasn't passed yet (with a 1-hour grace window)
                if event_dt >= now_dt - datetime.timedelta(hours=1):
                    filtered_events.append(ev)
            except Exception:
                if ev.get("status") in ["THIS WEEK", "UPCOMING WEEK"]:
                    filtered_events.append(ev)
                    
        return filtered_events

    def get_news_state(self) -> Dict[str, Any]:
        """Thread-safe access to parsed news sentiment state, USD forecast bias, and calendar events"""
        with self.lock:
            usd_bias = self.forecast_usd_bias(self.news_articles)
            upcoming = self.get_upcoming_events(usd_bias)
            return {
                "score": self.news_score,
                "usd_forecast_bias": usd_bias,
                "articles": list(self.news_articles),
                "upcoming_events": upcoming
            }

    @staticmethod
    def calculate_technical_sentiment(df: pd.DataFrame) -> float:
        """
        Calculate independent technical sentiment from -1.0 (bearish) to 1.0 (bullish)
        for a timeframe dataframe using EMAs, RSI, MACD, and Price Range alignment.
        """
        if len(df) < 50:
            return 0.0
        
        # 1. EMA Trend (weight 0.3)
        close = df['close'].iloc[-1]
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        trend_score = 0.0
        if close > ema20: trend_score += 0.5
        else: trend_score -= 0.5
        if close > ema50: trend_score += 0.5
        else: trend_score -= 0.5
        
        # 2. RSI 14 (weight 0.3)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        
        # Normalize RSI from [0, 100] to [-1, 1]
        rsi_score = (rsi_val - 50) / 50.0
        
        # 3. MACD (weight 0.2)
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        macd_val = macd.iloc[-1]
        sig_val = signal.iloc[-1]
        
        macd_score = 0.0
        if macd_val > sig_val: macd_score += 0.5
        else: macd_score -= 0.5
        if macd_val > 0: macd_score += 0.5
        else: macd_score -= 0.5
        
        # 4. Price Action Range Position (weight 0.2)
        recent_candles = df.tail(20)
        r_high = recent_candles['high'].max()
        r_low = recent_candles['low'].min()
        range_val = r_high - r_low
        if range_val > 0:
            pa_score = ((close - r_low) / range_val) * 2.0 - 1.0  # [-1, 1]
        else:
            pa_score = 0.0
            
        tech_score = (trend_score * 0.3) + (rsi_score * 0.3) + (macd_score * 0.2) + (pa_score * 0.2)
        return float(np.clip(tech_score, -1.0, 1.0))

# Global instance
sentiment_analyzer = SentimentAnalyzer()
