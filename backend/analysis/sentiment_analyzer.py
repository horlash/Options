"""
Sentiment Analyzer — G3 Remediation
Uses Finnhub institutional sentiment + Perplexity AI fallback for high-accuracy scoring.

Signal hierarchy:
  1. Finnhub news-sentiment endpoint (premium score, 0-1 scale)
  2. Finnhub company-news headlines + Perplexity AI scoring
  3. Neutral 50 (no data)
"""

import logging
import requests
from datetime import datetime, timedelta
from backend.config import Config

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    def __init__(self):
        self.time_decay_factor = 0.9
        self.perplexity_api_key = Config.PERPLEXITY_API_KEY
        self.perplexity_url = "https://api.perplexity.ai/chat/completions"

    # ------------------------------------------------------------------
    # PRIMARY: Finnhub institutional sentiment (premium or free-tier)
    # ------------------------------------------------------------------
    def score_from_finnhub_premium(self, finnhub_data):
        """
        Convert Finnhub news-sentiment response to 0-100.
        Returns (score, source_label) or (None, None) if unavailable.
        """
        if not finnhub_data or finnhub_data == "FORBIDDEN":
            return None, None
        if 'sentiment' not in finnhub_data:
            return None, None

        # companyNewsScore (0-1): Best single metric
        if 'companyNewsScore' in finnhub_data:
            score = finnhub_data['companyNewsScore'] * 100
            return max(0, min(100, score)), "Finnhub Institutional (companyNewsScore)"

        # Fallback: bullishPercent
        bp = finnhub_data.get('sentiment', {}).get('bullishPercent', None)
        if bp is not None:
            return max(0, min(100, bp * 100)), "Finnhub Institutional (bullishPercent)"

        return None, None

    # ------------------------------------------------------------------
    # SECONDARY: Perplexity AI headline scoring
    # ------------------------------------------------------------------
    def score_headlines_with_perplexity(self, ticker, headlines):
        """
        Use Perplexity sonar-pro to score a batch of headlines 0-100.
        Returns (score, breakdown_list) or (50, []) on failure.
        """
        if not self.perplexity_api_key or not headlines:
            return 50, []

        bullet_list = "\n".join(f"- {h}" for h in headlines[:15])

        prompt = (
            f"You are a quantitative sentiment scorer for options trading.\n"
            f"Rate the overall sentiment of these {ticker} headlines on a 0-100 scale:\n"
            f"0 = extremely bearish, 50 = neutral, 100 = extremely bullish.\n\n"
            f"Headlines:\n{bullet_list}\n\n"
            f"Respond with ONLY a JSON object: {{\"score\": <int>, \"rationale\": \"<1 sentence>\"}}"
        )

        try:
            resp = requests.post(
                self.perplexity_url,
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {"role": "system", "content": "You are a financial sentiment scoring engine. Return only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0
                },
                headers={
                    "Authorization": f"Bearer {self.perplexity_api_key}",
                    "Content-Type": "application/json"
                },
                timeout=15
            )

            if resp.status_code != 200:
                logger.warning("Perplexity sentiment API returned %d", resp.status_code)
                return 50, []

            content = resp.json()['choices'][0]['message']['content']

            # Extract JSON from response
            import json, re
            json_match = re.search(r'\{[^}]*"score"\s*:\s*(\d+)[^}]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group(0))
                score = max(0, min(100, int(parsed.get('score', 50))))
                rationale = parsed.get('rationale', '')
                logger.info("Perplexity sentiment for %s: %d (%s)", ticker, score, rationale)
                return score, [{"source": "Perplexity AI", "score": score, "rationale": rationale}]

        except Exception as e:
            logger.warning("Perplexity sentiment failed for %s: %s", ticker, e)

        return 50, []

    # ------------------------------------------------------------------
    # UNIFIED ENTRY POINT
    # ------------------------------------------------------------------
    def analyze_sentiment(self, ticker, finnhub_premium_data=None, headlines=None):
        """
        Unified sentiment analysis pipeline (G3 fix).

        Priority:
          1. Finnhub premium sentiment → 0-100
          2. Perplexity AI headline scoring → 0-100
          3. Default neutral → 50

        Returns:
            dict with 'score' (0-100), 'source', 'breakdown', 'headlines'
        """
        result = {
            'score': 50,
            'source': 'default_neutral',
            'signal': 'neutral',
            'breakdown': [],
            'headlines': headlines or [],
            'article_count': 0,
        }

        # 1. Try Finnhub premium
        fh_score, fh_source = self.score_from_finnhub_premium(finnhub_premium_data)
        if fh_score is not None:
            result['score'] = fh_score
            result['source'] = fh_source
            result['article_count'] = finnhub_premium_data.get('buzz', {}).get('articlesInLastWeek', 0)
            result['breakdown'].append({
                'method': 'finnhub_premium',
                'score': fh_score,
                'source': fh_source,
            })
        elif headlines:
            # 2. Try Perplexity AI scoring
            px_score, px_breakdown = self.score_headlines_with_perplexity(ticker, headlines)
            result['score'] = px_score
            result['source'] = 'Perplexity AI (headline analysis)'
            result['article_count'] = len(headlines)
            result['breakdown'].extend(px_breakdown)
        # else: stays at neutral 50

        # Derive signal
        result['signal'] = self.get_sentiment_signal(result['score'])

        return result

    # ------------------------------------------------------------------
    # LEGACY COMPATIBILITY — kept for callers that still use old interface
    # ------------------------------------------------------------------
    def analyze_articles(self, articles):
        """Legacy wrapper — extracts headlines and routes through new pipeline."""
        if not articles:
            return {
                'overall_score': 0,
                'article_count': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'weighted_score': 0,
                'headlines': [],
            }

        headlines = [a.get('headline', '') for a in articles if a.get('headline')]
        ticker = ''  # Caller should use analyze_sentiment directly
        px_score, _ = self.score_headlines_with_perplexity(ticker, headlines)

        # Map to legacy format
        return {
            'overall_score': (px_score / 50.0) - 1.0,       # Map 0-100 → -1 to +1
            'weighted_score': (px_score / 50.0) - 1.0,
            'article_count': len(articles),
            'positive_count': 1 if px_score > 55 else 0,
            'negative_count': 1 if px_score < 45 else 0,
            'neutral_count': 1 if 45 <= px_score <= 55 else 0,
            'headlines': headlines,
            'sentiment_breakdown': [
                {
                    'headline': a.get('headline'),
                    'sentiment': (px_score / 50.0) - 1.0,
                    'weight': 1.0,
                    'published_date': a.get('published_date')
                }
                for a in articles
            ]
        }

    def calculate_sentiment_score(self, sentiment_analysis):
        """Legacy: convert analysis dict to 0-100 score."""
        ws = sentiment_analysis.get('weighted_score', 0)
        score = ((ws + 1) / 2) * 100
        return max(0, min(100, score))

    def get_sentiment_signal(self, score):
        """Convert 0-100 score to signal string."""
        if score >= 65:
            return 'bullish'
        elif score <= 35:
            return 'bearish'
        return 'neutral'

    def calculate_time_weight(self, published_date):
        """Calculate time-decay weight (kept for compatibility)."""
        try:
            if isinstance(published_date, str):
                try:
                    pub_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                except Exception:
                    pub_date = datetime.strptime(published_date[:10], '%Y-%m-%d')
            else:
                pub_date = published_date
            days_old = (datetime.now() - pub_date.replace(tzinfo=None)).days
            return max(0.1, self.time_decay_factor ** days_old)
        except Exception:
            return 0.5
