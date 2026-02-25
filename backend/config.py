import os
from dotenv import load_dotenv

# Load .env from project root (prioritize .env.feature for testing)
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
feature_env = os.path.join(basedir, '.env.feature')
prod_env = os.path.join(basedir, '.env')
env_path = feature_env if os.path.exists(feature_env) else prod_env
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
    
    # Tradier URLs (Point 9)
    TRADIER_SANDBOX_URL = 'https://sandbox.tradier.com/v1'
    TRADIER_LIVE_URL    = 'https://api.tradier.com/v1'
    
    # Application Settings
    MAX_INVESTMENT_PER_POSITION = int(os.getenv('MAX_INVESTMENT_PER_POSITION', 2000))
    MIN_LEAP_DAYS = int(os.getenv('MIN_LEAP_DAYS', 150))  # 5 months minimum for LEAPs
    MIN_PROFIT_POTENTIAL = float(os.getenv('MIN_PROFIT_POTENTIAL', 15))
    
    # Technical Indicator Thresholds
    RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', 30))
    RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', 70))
    MIN_VOLUME_MULTIPLIER = float(os.getenv('MIN_VOLUME_MULTIPLIER', 1.5))
    
    # Database — Scanner (existing SQLite)
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./leap_scanner.db')
    
    # Database — Paper Trading (App connects as app_user for RLS enforcement)
    # Dev: port 5433 (paper_trading_dev_db), Prod: port 5432 (paper_trading_db)
    # Migrations use paper_user (superuser) via alembic_paper.ini
    PAPER_TRADE_DB_URL = os.getenv(
        'PAPER_TRADE_DB_URL',
        'postgresql://app_user:app_pass@localhost:5433/paper_trading'
    )
    
    # Encryption (Point 9: Fernet key for Tradier tokens)
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    
    # Server
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    PORT = int(os.getenv('PORT', 5000))
    
    # Rate Limiting
    NEWS_CACHE_HOURS = 6  # cache news for 6 hours

    @staticmethod
    def get_paper_db_url():
        """Get the paper trading database URL.
        Uses PAPER_TRADE_DB_URL env var, which should point to:
        - Docker Postgres in dev
        - Neon Postgres in prod
        """
        return Config.PAPER_TRADE_DB_URL
