import requests
from datetime import datetime, timedelta
from backend.config import Config

class NewsAPIs:
    def __init__(self):
        self.newsapi_key = Config.NEWSAPI_KEY
        self.finnhub_key = Config.FINNHUB_API_KEY
        self.alphavantage_key = Config.ALPHAVANTAGE_API_KEY
        
    def get_newsapi_articles(self, ticker, days_back=7):
        """
        Get news articles from NewsAPI
        
        Args:
            ticker: Stock ticker symbol
            days_back: Number of days to look back
        
        Returns:
            List of news articles
        """
        if not self.newsapi_key:
            return []
        
        try:
            from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': ticker,
                'from': from_date,
                'sortBy': 'publishedAt',
                'language': 'en',
                'apiKey': self.newsapi_key
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                articles = []
                
                for article in data.get('articles', []):
                    articles.append({
                        'headline': article.get('title'),
                        'summary': article.get('description'),
                        'source': article.get('source', {}).get('name'),
                        'url': article.get('url'),
                        'published_date': article.get('publishedAt')
                    })
                
                return articles
            else:
                print(f"NewsAPI error: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Exception in get_newsapi_articles: {str(e)}")
            return []
    
    def get_finnhub_news(self, ticker, days_back=7):
        """
        Get company news from Finnhub
        
        Args:
            ticker: Stock ticker symbol
            days_back: Number of days to look back
        
        Returns:
            List of news articles
        """
        if not self.finnhub_key:
            return []
        
        try:
            import finnhub
            
            finnhub_client = finnhub.Client(api_key=self.finnhub_key)
            
            from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            
            news = finnhub_client.company_news(ticker, _from=from_date, to=to_date)
            
            articles = []
            for item in news:
                articles.append({
                    'headline': item.get('headline'),
                    'summary': item.get('summary'),
                    'source': item.get('source'),
                    'url': item.get('url'),
                    'published_date': datetime.fromtimestamp(item.get('datetime')).isoformat()
                })
            
            return articles
            
        except Exception as e:
            print(f"Exception in get_finnhub_news: {str(e)}")
            return []
    
    def get_alphavantage_sentiment(self, ticker):
        """
        Get news sentiment from Alpha Vantage
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            News articles with sentiment scores
        """
        if not self.alphavantage_key:
            return []
        
        try:
            url = 'https://www.alphavantage.co/query'
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': ticker,
                'apikey': self.alphavantage_key
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                articles = []
                
                for item in data.get('feed', []):
                    # Find sentiment for this specific ticker
                    ticker_sentiment = None
                    for sentiment in item.get('ticker_sentiment', []):
                        if sentiment.get('ticker') == ticker:
                            ticker_sentiment = float(sentiment.get('ticker_sentiment_score', 0))
                            break
                    
                    articles.append({
                        'headline': item.get('title'),
                        'summary': item.get('summary'),
                        'source': item.get('source'),
                        'url': item.get('url'),
                        'published_date': item.get('time_published'),
                        'sentiment_score': ticker_sentiment
                    })
                
                return articles
            else:
                print(f"Alpha Vantage error: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Exception in get_alphavantage_sentiment: {str(e)}")
            return []
    
    def get_all_news(self, ticker, days_back=7):
        """
        Aggregate news from all sources
        
        Args:
            ticker: Stock ticker symbol
            days_back: Number of days to look back
        
        Returns:
            Combined list of news articles from all sources
        """
        all_articles = []
        
        # Get from all sources
        all_articles.extend(self.get_newsapi_articles(ticker, days_back))
        all_articles.extend(self.get_finnhub_news(ticker, days_back))
        all_articles.extend(self.get_alphavantage_sentiment(ticker))
        
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
