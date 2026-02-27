"""
Paper Trading Database Session Manager
=======================================
Separate engine/session for the paper trading Postgres database.
The existing scanner uses SQLite — this keeps them isolated.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, scoped_session

from backend.config import Config


def _get_engine():
    """Create the paper trading database engine with Point 10 pool settings."""
    url = Config.get_paper_db_url()

    engine = create_engine(
        url,
        pool_size=10,           # Point 10: Connection pool config
        max_overflow=5,         # Point 10: Max 15 total connections
        pool_timeout=30,        # Point 10: 30s timeout on pool exhaustion
        pool_pre_ping=True,     # Point 10: Auto-recover stale connections
        isolation_level='REPEATABLE_READ',  # Point 10: Prevent phantom reads
    )
    return engine


paper_engine = _get_engine()
PaperSessionLocal = sessionmaker(bind=paper_engine)
PaperScopedSession = scoped_session(PaperSessionLocal)


def get_paper_db():
    """Get a paper trading database session.

    Usage:
        db = get_paper_db()
        try:
            # ... do work ...
            db.commit()
        except:
            db.rollback()
            raise
        finally:
            db.close()
    """
    return PaperScopedSession()


def get_paper_db_with_user(username: str):
    """Get a paper trading database session with RLS user context set.

    This sets the PostgreSQL session variable `app.current_user`
    which is used by Row Level Security policies (Point 7).

    Usage:
        db = get_paper_db_with_user('alice')
        # All queries now filtered by RLS to only see alice's data
    """
    import re
    # F30 FIX: Sanitize username to prevent SQL injection.
    # Only allow alphanumeric, underscore, hyphen, dot, @ (for email-style usernames).
    if not re.match(r'^[a-zA-Z0-9_@.\-]+$', username):
        raise ValueError(f"Invalid username format: {username}")
    session = PaperScopedSession()
    # F30 FIX: Use parameterized query instead of f-string interpolation.
    # PostgreSQL SET does not support $1 bind params, so we use format()
    # AFTER validating the username with the regex above.
    session.execute(text("SET \"app.current_user\" = :uname"), {"uname": username})
    return session


# F38 FIX: Module-level singleton engine for system sessions.
# Previously, get_paper_db_system() created a new engine on every call,
# wasting connections and bypassing pool management.
_system_engine = None
_SystemSessionLocal = None


def _get_system_engine():
    """Lazy-initialize the system engine singleton."""
    global _system_engine, _SystemSessionLocal
    if _system_engine is None:
        url = Config.get_paper_db_url()
        system_url = url.replace('app_user:app_pass', 'paper_user:paper_pass')
        _system_engine = create_engine(
            system_url,
            pool_size=3,
            max_overflow=2,
            pool_pre_ping=True,
        )
        _SystemSessionLocal = sessionmaker(bind=_system_engine)
    return _SystemSessionLocal


def get_paper_db_system():
    """Get a paper trading database session that can see ALL users' trades.

    Used by background jobs (monitor service, lifecycle sync) that
    need to query trades across ALL users.

    Uses the superuser (paper_user) engine directly to bypass RLS.
    F38 FIX: Reuses a singleton engine instead of creating one per call.
    """
    SessionFactory = _get_system_engine()
    return SessionFactory()
