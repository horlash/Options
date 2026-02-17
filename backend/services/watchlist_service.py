from backend.database.models import Watchlist, SessionLocal
import yfinance as yf

class WatchlistService:
    def __init__(self):
        self.db = SessionLocal()
        
    def add_ticker(self, ticker, username):
        """
        Add ticker to watchlist
        
        Args:
            ticker: Stock ticker symbol
            username: User ID/Name
        
        Returns:
            Success boolean and message
        """
        try:
            # Check if ticker already exists for this user
            existing = self.db.query(Watchlist).filter(
                Watchlist.ticker == ticker.upper(),
                Watchlist.username == username
            ).first()
            
            if existing:
                return False, f"{ticker} already in watchlist"
            
            # Get sector information using yfinance
            sector = self._get_sector(ticker)
            
            # Add to watchlist
            new_ticker = Watchlist(
                ticker=ticker.upper(),
                username=username,
                sector=sector
            )
            
            self.db.add(new_ticker)
            self.db.commit()
            
            return True, f"{ticker} added to watchlist"
            
        except Exception as e:
            self.db.rollback()
            return False, f"Error adding ticker: {str(e)}"
    
    def remove_ticker(self, ticker, username):
        """
        Remove ticker from watchlist
        
        Args:
            ticker: Stock ticker symbol
            username: User ID/Name
        
        Returns:
            Success boolean and message
        """
        try:
            ticker_obj = self.db.query(Watchlist).filter(
                Watchlist.ticker == ticker.upper(),
                Watchlist.username == username
            ).first()
            
            if not ticker_obj:
                return False, f"{ticker} not found in watchlist"
            
            self.db.delete(ticker_obj)
            self.db.commit()
            
            return True, f"{ticker} removed from watchlist"
            
        except Exception as e:
            self.db.rollback()
            return False, f"Error removing ticker: {str(e)}"
    
    def get_watchlist(self, username):
        """
        Get all tickers in watchlist for a user
        
        Args:
            username: User ID/Name

        Returns:
            List of ticker dictionaries
        """
        try:
            tickers = self.db.query(Watchlist).filter(
                Watchlist.username == username
            ).all()
            
            return [
                {
                    'ticker': t.ticker,
                    'sector': t.sector,
                    'added_date': t.added_date.isoformat() if t.added_date else None
                }
                for t in tickers
            ]
            
        except Exception as e:
            print(f"Error getting watchlist: {str(e)}")
            return []
    
    def get_tickers_by_sector(self, sector, username):
        """
        Get all tickers in a specific sector for a user
        
        Args:
            sector: Sector name
            username: User ID/Name
        
        Returns:
            List of tickers
        """
        try:
            tickers = self.db.query(Watchlist).filter(
                Watchlist.sector == sector,
                Watchlist.username == username
            ).all()
            
            return [t.ticker for t in tickers]
            
        except Exception as e:
            print(f"Error getting tickers by sector: {str(e)}")
            return []
    
    def _get_sector(self, ticker):
        """
        Get sector for a ticker using yfinance
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            Sector name or None
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return info.get('sector', 'Unknown')
        except Exception as e:
            print(f"Error getting sector for {ticker}: {str(e)}")
            return 'Unknown'
    
    def get_related_tickers(self, ticker, username, limit=5):
        """
        Get related tickers in the same sector for a user
        
        Args:
            ticker: Stock ticker symbol
            username: User ID/Name
            limit: Maximum number of related tickers
        
        Returns:
            List of related ticker symbols
        """
        try:
            # Get sector of the ticker
            ticker_obj = self.db.query(Watchlist).filter(
                Watchlist.ticker == ticker.upper(),
                Watchlist.username == username
            ).first()
            
            if not ticker_obj or not ticker_obj.sector:
                return []
            
            # Get other tickers in same sector
            related = self.db.query(Watchlist).filter(
                Watchlist.sector == ticker_obj.sector,
                Watchlist.username == username,
                Watchlist.ticker != ticker.upper()
            ).limit(limit).all()
            
            return [t.ticker for t in related]
            
        except Exception as e:
            print(f"Error getting related tickers: {str(e)}")
            return []
    
    def close(self):
        """Close database session"""
        self.db.close()
