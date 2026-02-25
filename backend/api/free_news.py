import feedparser
import requests
from datetime import datetime, timedelta

class FreeNewsAPIs:
    """Free news sources without API keys"""
    
    def __init__(self):
        pass
    
    def get_google_news(self, ticker, days_back=7):
        """
        Get news from Google News RSS feed (free, no API key)
        """
        try:
            # Google News RSS feed for stock ticker
            url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
            
            feed = feedparser.parse(url)
            
            articles = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            for entry in feed.entries[:20]:  # Limit to 20 articles
                try:
                    # Parse published date
                    pub_date = datetime(*entry.published_parsed[:6])
                    
                    if pub_date < cutoff_date:
                        continue
                    
                    articles.append({
                        'headline': entry.title,
                        'summary': entry.get('summary', ''),
                        'source': entry.get('source', {}).get('title', 'Google News'),
                        'url': entry.link,
                        'published_date': pub_date.isoformat()
                    })
                except Exception as e:
                    continue
            
            return articles
            
        except Exception as e:
            print(f"Error fetching Google News: {str(e)}")
            return []
    
    def get_yahoo_finance_news(self, ticker):
        """
        Get news from Yahoo Finance (free, no API key)
        """
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            news = stock.news
            
            articles = []
            
            for item in news[:15]:  # Limit to 15 articles
                try:
                    pub_date = datetime.fromtimestamp(item.get('providerPublishTime', 0))
                    
                    articles.append({
                        'headline': item.get('title', ''),
                        'summary': item.get('summary', ''),
                        'source': item.get('publisher', 'Yahoo Finance'),
                        'url': item.get('link', ''),
                        'published_date': pub_date.isoformat()
                    })
                except Exception as e:
                    continue
            
            return articles
            
        except Exception as e:
            print(f"Error fetching Yahoo Finance news: {str(e)}")
            return []
    
    def get_all_news(self, ticker, days_back=7):
        """
        Aggregate news from all free sources
        """
        all_articles = []
        
        # Get from Google News
        all_articles.extend(self.get_google_news(ticker, days_back))
        
        # Get from Yahoo Finance
        all_articles.extend(self.get_yahoo_finance_news(ticker))
        
        # Remove duplicates based on headline
        seen_headlines = set()
        unique_articles = []
        
        for article in all_articles:
            headline = article.get('headline', '')
            if headline and headline not in seen_headlines:
                seen_headlines.add(headline)
                unique_articles.append(article)
        
        # Sort by published date (most recent first)
        unique_articles.sort(
            key=lambda x: x.get('published_date', ''),
            reverse=True
        )
        
        return unique_articles
