# utils/sentiment_analyzer.py
import threading
import time
import requests
import xml.etree.ElementTree as ET
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

class SentimentAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.SentimentAnalyzer")
        self.vader = SentimentIntensityAnalyzer()
        self.news_score = 0.0
        self.news_articles = []
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        
    def start(self):
        """Start the background news scraper thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_news_scraper, daemon=True)
        self.thread.start()
        self.logger.info("News sentiment background worker started.")
        
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

    def update_news_sentiment(self):
        """Scrape Yahoo Finance, CNBC, and FXStreet feeds, running VADER polarity checks"""
        urls = [
            "https://finance.yahoo.com/rss/headline?s=GC=F",
            "https://www.cnbc.com/id/15839069/device/rss/rss.html",
            "https://www.fxstreet.com/rss/news"
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        all_headlines = []
        articles = []
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # Clean/parse XML
                    root = ET.fromstring(response.content)
                    for item in root.findall(".//item"):
                        title = item.find("title")
                        link = item.find("link")
                        pub_date = item.find("pubDate")
                        desc = item.find("description")
                        
                        title_text = title.text if title is not None else ""
                        link_text = link.text if link is not None else ""
                        date_text = pub_date.text if pub_date is not None else ""
                        
                        desc_raw = desc.text if desc is not None else ""
                        # Clean HTML tags from description
                        import re
                        desc_text = re.sub(r'<[^>]*>|&nbsp;|&#\d+;', ' ', desc_raw).strip()
                        desc_text = re.sub(r'\s+', ' ', desc_text)
                        
                        if title_text:
                            # Run VADER on title
                            vs = self.vader.polarity_scores(title_text)
                            score = vs['compound']
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
            if all_headlines:
                self.news_score = float(np.mean(all_headlines))
                # Keep latest 20 articles
                self.news_articles = articles[:20]
                self.logger.info(f"Updated news sentiment: {self.news_score:.2f} based on {len(all_headlines)} headlines")
            else:
                self.news_score = 0.0
                self.news_articles = []

    def get_news_state(self) -> Dict[str, Any]:
        """Thread-safe access to parsed news sentiment state"""
        with self.lock:
            return {
                "score": self.news_score,
                "articles": list(self.news_articles)
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
