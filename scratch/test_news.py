import requests
import xml.etree.ElementTree as ET
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import numpy as np

vader = SentimentIntensityAnalyzer()
urls = [
    "https://finance.yahoo.com/rss/headline?s=GC=F",
    "https://www.dailyfx.com/feeds/market-alerts",
    "https://www.dailyfx.com/feeds/forex-market-news",
    "https://www.cnbc.com/id/10000115/device/rss/rss.html",
    "https://www.fxstreet.com/rss/news"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

for url in urls:
    print(f"Fetching {url}...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            items = root.findall(".//item")
            print(f"Found {len(items)} items")
            for item in items[:3]:
                title = item.find("title")
                title_text = title.text if title is not None else ""
                if title_text:
                    vs = vader.polarity_scores(title_text)
                    print(f"  - {title_text[:60]} | Score: {vs['compound']}")
    except Exception as e:
        print(f"  Error: {e}")
