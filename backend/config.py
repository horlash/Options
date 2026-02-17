import os
from dotenv import load_dotenv

# Explicitly load .env from project root
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
env_path = os.path.join(basedir, '.env')
# print(f"DEBUG: Loading .env from {env_path}")
status = load_dotenv(env_path, override=True) # Force override
# print(f"DEBUG: load_dotenv status: {status}")
# print(f"DEBUG: SCHWAB keys in env: {[k for k in os.environ.keys() if 'SCHWAB' in k]}")

class Config:
    # API Keys
    TD_AMERITRADE_API_KEY = os.getenv('TD_AMERITRADE_API_KEY')
    TD_AMERITRADE_REDIRECT_URI = os.getenv('TD_AMERITRADE_REDIRECT_URI', 'https://localhost')
    TD_AMERITRADE_TOKEN_PATH = os.getenv('TD_AMERITRADE_TOKEN_PATH', './td_token.json')
    
    SCHWAB_API_KEY = os.getenv('SCHWAB_API_KEY')
    SCHWAB_API_SECRET = os.getenv('SCHWAB_API_SECRET')
    SCHWAB_TOKEN_PATH = os.getenv('SCHWAB_TOKEN_PATH', 'token.json')
    FMP_API_KEY = os.environ.get('FMP_API_KEY')
    
    print(f"DEBUG: Config loaded. SCHWAB_KEY length: {len(SCHWAB_API_KEY) if SCHWAB_API_KEY else 0}")
    print(f"DEBUG: FMP_KEY length: {len(FMP_API_KEY) if FMP_API_KEY else 0}")
    
    NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')
    FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
    ALPHAVANTAGE_API_KEY = os.getenv('ALPHAVANTAGE_API_KEY')
    PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
    ORATS_API_KEY = os.getenv('ORATS_API_KEY')
    
    # Tradier API (for options chains with Greeks)
    TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
    TRADIER_USE_SANDBOX = os.getenv('TRADIER_USE_SANDBOX', 'False') == 'True'
    
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
    PORT = int(os.getenv('PORT', 5000))
    
    # Rate Limiting
    TD_RATE_LIMIT = 120  # requests per minute
    NEWS_CACHE_HOURS = 6  # cache news for 6 hours
