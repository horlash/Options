from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from backend.config import Config

Base = declarative_base()
engine = create_engine(Config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Watchlist(Base):
    __tablename__ = 'watchlist'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, index=True)
    ticker = Column(String(10), nullable=False)
    sector = Column(String(100))
    added_date = Column(DateTime, default=datetime.utcnow)
    
class ScanResult(Base):
    __tablename__ = 'scan_results'
    
    id = Column(Integer, primary_key=True)
    scan_date = Column(DateTime, default=datetime.utcnow)
    ticker = Column(String(10), nullable=False)
    opportunity_score = Column(Float)
    technical_score = Column(Float)
    sentiment_score = Column(Float)
    profit_potential = Column(Float)
    
class Opportunity(Base):
    __tablename__ = 'opportunities'
    
    id = Column(Integer, primary_key=True)
    scan_result_id = Column(Integer)
    ticker = Column(String(10), nullable=False)
    option_type = Column(String(4))  # CALL or PUT
    strike_price = Column(Float)
    expiration_date = Column(DateTime)
    premium = Column(Float)
    profit_potential = Column(Float)
    days_to_expiry = Column(Integer)
    volume = Column(Integer)
    open_interest = Column(Integer)
    implied_volatility = Column(Float)
    delta = Column(Float)
    gamma = Column(Float)
    theta = Column(Float)
    vega = Column(Float)
    opportunity_score = Column(Float)
    created_date = Column(DateTime, default=datetime.utcnow)
    
class NewsCache(Base):
    __tablename__ = 'news_cache'
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    headline = Column(String(500))
    summary = Column(Text)
    source = Column(String(100))
    url = Column(String(500))
    published_date = Column(DateTime)
    sentiment_score = Column(Float)
    cached_date = Column(DateTime, default=datetime.utcnow)

class SearchHistory(Base):
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, index=True)
    ticker = Column(String(10), nullable=False)
    last_searched = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Initialize the scanner database (SQLite) by creating scanner-only tables.
    
    Paper trading tables (PaperTrade, PriceSnapshot, etc.) use PostgreSQL-specific
    JSONB columns and are managed by Alembic migrations — not created here.
    """
    scanner_tables = [
        t for t in Base.metadata.sorted_tables
        if t.name in ('watchlist', 'scan_results', 'opportunities', 'news_cache', 'search_history')
    ]
    Base.metadata.create_all(engine, tables=scanner_tables)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()
