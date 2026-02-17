from textblob import TextBlob
from datetime import datetime, timedelta
import numpy as np

class SentimentAnalyzer:
    def __init__(self):
        self.time_decay_factor = 0.9  # Weight recent news more heavily
        
    def analyze_text_sentiment(self, text):
        """
        Analyze sentiment of text using TextBlob
        
        Args:
            text: Text to analyze
        
        Returns:
            Sentiment score (-1 to 1)
        """
        if not text:
            return 0
        
        try:
            blob = TextBlob(text)
            # Polarity ranges from -1 (negative) to 1 (positive)
            return blob.sentiment.polarity
        except Exception as e:
            print(f"Error analyzing sentiment: {str(e)}")
            return 0
    
    def calculate_time_weight(self, published_date):
        """
        Calculate weight based on how recent the news is
        More recent news gets higher weight
        
        Args:
            published_date: Publication date string or datetime
        
        Returns:
            Weight factor (0-1)
        """
        try:
            if isinstance(published_date, str):
                # Try parsing different date formats
                try:
                    pub_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                except:
                    pub_date = datetime.strptime(published_date[:10], '%Y-%m-%d')
            else:
                pub_date = published_date
            
            days_old = (datetime.now() - pub_date.replace(tzinfo=None)).days
            
            # Exponential decay - news older than 7 days gets significantly less weight
            weight = self.time_decay_factor ** days_old
            
            return max(0.1, weight)  # Minimum weight of 0.1
            
        except Exception as e:
            print(f"Error calculating time weight: {str(e)}")
            return 0.5  # Default weight
    
    def analyze_articles(self, articles):
        """
        Analyze sentiment across multiple news articles
        
        Args:
            articles: List of article dictionaries with headline, summary, published_date
        
        Returns:
            Dictionary with overall sentiment score and breakdown
        """
        if not articles:
            return {
                'overall_score': 0,
                'article_count': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'weighted_score': 0
            }
        
        sentiments = []
        weights = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        
        for article in articles:
            # Combine headline and summary for analysis
            text = f"{article.get('headline', '')} {article.get('summary', '')}"
            
            # Get sentiment score
            if 'sentiment_score' in article and article['sentiment_score'] is not None:
                # Use pre-calculated sentiment if available (from Alpha Vantage)
                sentiment = article['sentiment_score']
            else:
                # Calculate sentiment using TextBlob
                sentiment = self.analyze_text_sentiment(text)
            
            # Calculate time weight
            published_date = article.get('published_date')
            weight = self.calculate_time_weight(published_date) if published_date else 0.5
            
            sentiments.append(sentiment)
            weights.append(weight)
            
            # Count sentiment types
            if sentiment > 0.1:
                positive_count += 1
            elif sentiment < -0.1:
                negative_count += 1
            else:
                neutral_count += 1
        
        # Calculate weighted average sentiment
        if sentiments:
            weighted_score = float(np.average(sentiments, weights=weights))
            overall_score = float(np.mean(sentiments))
        else:
            weighted_score = 0
            overall_score = 0
        
        return {
            'overall_score': overall_score,
            'weighted_score': weighted_score,
            'article_count': len(articles),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'sentiment_breakdown': [
                {
                    'headline': article.get('headline'),
                    'sentiment': float(sentiments[i]),
                    'weight': float(weights[i]),
                    'published_date': article.get('published_date')
                }
                for i, article in enumerate(articles)
            ]
        }
    
    def get_sentiment_signal(self, sentiment_score):
        """
        Convert sentiment score to signal
        
        Args:
            sentiment_score: Sentiment score (-1 to 1)
        
        Returns:
            Signal string: 'bullish', 'bearish', or 'neutral'
        """
        if sentiment_score > 0.2:
            return 'bullish'
        elif sentiment_score < -0.2:
            return 'bearish'
        else:
            return 'neutral'
    
    def calculate_sentiment_score(self, sentiment_analysis):
        """
        Convert sentiment analysis to 0-100 score
        
        Args:
            sentiment_analysis: Dictionary from analyze_articles
        
        Returns:
            Score from 0-100
        """
        # Use weighted score for better accuracy
        weighted_score = sentiment_analysis.get('weighted_score', 0)
        
        # Convert from -1 to 1 range to 0 to 100 range
        score = ((weighted_score + 1) / 2) * 100
        
        return max(0, min(100, score))
