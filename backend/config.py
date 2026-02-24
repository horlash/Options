import os
from dotenv import load_dotenv

# Load .env from project root
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
env_path = os.path.join(basedir, '.env')
load_dotenv(env_path, override=True)

class Config:
    # API Keys — Primary
    ORATS_API_KEY = os.getenv('ORATS_API_KEY')
    FMP_API_KEY = os.getenv('FMP_API_KEY')
    FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
    NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')
    
    # API Keys — Optional
    TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
    TRADIER_USE_SANDBOX = os.getenv('TRADIER_USE_SANDBOX', 'False') == 'True'
    PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
    
    # Application Settings
    MAX_INVESTMENT_PER_POSITION = int(os.getenv('MAX_INVESTMENT_PER_POSITION', 2000))
    MIN_LEAP_DAYS = int(os.getenv('MIN_LEAP_DAYS', 150))  # 5 months minimum for LEAPs
    MIN_PROFIT_POTENTIAL = float(os.getenv('MIN_PROFIT_POTENTIAL', 15))
    
    # Technical Indicator Thresholds
    RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', 30))
    RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', 70))
    MIN_VOLUME_MULTIPLIER = float(os.getenv('MIN_VOLUME_MULTIPLIER', 1.5))
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./leap_scanner.db')
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    
    # Server
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    PORT = int(os.getenv('PORT', 5050))
    
    # Rate Limiting
    NEWS_CACHE_HOURS = 6  # cache news for 6 hours

