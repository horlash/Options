"""
Paper Trading Database Models
=============================
Point 1: Database Schema & Models (FINALIZED)

These models support ALL 12 points of the paper trading system:
- Point 1:  Core schema (PaperTrade, PriceSnapshot, UserSettings)
- Point 6:  trade_context JSONB (MFE/MAE, strategy, entry/exit snapshots)
- Point 7:  RLS via username column + policies (applied in migrations)
- Point 8:  Optimistic locking via version column
- Point 10: Idempotency via idempotency_key UNIQUE constraint
- Point 11: 7-state lifecycle via StateTransition audit table
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text,
    ForeignKey, CheckConstraint, Index, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

# Import the shared Base from existing models
from backend.database.models import Base


# ---------------------------------------------------------------------------
# Point 11: Trade Status Enum (7-state machine)
# ---------------------------------------------------------------------------
class TradeStatus(enum.Enum):
    PENDING         = "PENDING"
    OPEN            = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CLOSING         = "CLOSING"
    CLOSED          = "CLOSED"
    EXPIRED         = "EXPIRED"
    CANCELED        = "CANCELED"


# ---------------------------------------------------------------------------
# Core Model: PaperTrade
# ---------------------------------------------------------------------------
class PaperTrade(Base):
    __tablename__ = 'paper_trades'

    # --- Identity ---
    id              = Column(Integer, primary_key=True, autoincrement=True)
    username        = Column(String(50), nullable=False, index=True)
    idempotency_key = Column(String(100), unique=True, nullable=True)

    # --- Trade Details ---
    ticker          = Column(String(10), nullable=False)
    option_type     = Column(String(4), nullable=False)       # CALL / PUT
    strike          = Column(Float, nullable=False)
    expiry          = Column(String(10), nullable=False)       # YYYY-MM-DD
    direction       = Column(String(4), default='BUY')         # BUY / SELL
    entry_price     = Column(Float, nullable=False)
    qty             = Column(Integer, default=1)

    # --- Brackets (Point 4) ---
    sl_price        = Column(Float, nullable=True)
    tp_price        = Column(Float, nullable=True)

    # --- Scanner Context Snapshot (at entry time) ---
    strategy        = Column(String(20), nullable=True)        # LEAP / WEEKLY / 0DTE
    card_score      = Column(Float, nullable=True)
    ai_score        = Column(Float, nullable=True)
    ai_verdict      = Column(String(20), nullable=True)
    gate_verdict    = Column(String(20), nullable=True)
    technical_score = Column(Float, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    delta_at_entry  = Column(Float, nullable=True)
    iv_at_entry     = Column(Float, nullable=True)

    # --- Live Monitoring (Point 2) ---
    current_price   = Column(Float, nullable=True)
    unrealized_pnl  = Column(Float, nullable=True)

    # --- Outcome ---
    status          = Column(
        String(20),
        CheckConstraint(
            "status IN ('PENDING','OPEN','PARTIALLY_FILLED','CLOSING','CLOSED','EXPIRED','CANCELED')",
            name='ck_paper_trades_status'
        ),
        default='PENDING',
        nullable=False,
        index=True
    )
    exit_price      = Column(Float, nullable=True)
    realized_pnl    = Column(Float, nullable=True)
    close_reason    = Column(String(30), nullable=True)        # SL_HIT / TP_HIT / MANUAL / EXPIRED / OCC_ASSIGNMENT

    # --- Backtesting Context (Point 6: JSONB) ---
    # Stores: strategy_type, mfe, mae, entry_snapshot, exit_snapshot, etc.
    trade_context   = Column(JSONB, default=dict, nullable=False, server_default='{}')

    # --- Tradier Integration (Point 9) ---
    broker_mode         = Column(String(20), default='TRADIER_SANDBOX')
    tradier_order_id    = Column(String(50), nullable=True)
    tradier_sl_order_id = Column(String(50), nullable=True)
    tradier_tp_order_id = Column(String(50), nullable=True)
    broker_fill_price   = Column(Float, nullable=True)
    broker_fill_time    = Column(DateTime, nullable=True)

    # --- Concurrency & Locking (Points 8 + 10) ---
    version         = Column(Integer, default=1, nullable=False)
    is_locked       = Column(Boolean, default=False)

    # --- Timestamps ---
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at       = Column(DateTime, nullable=True)

    # --- Relationships ---
    state_transitions = relationship(
        "StateTransition",
        back_populates="trade",
        cascade="all, delete-orphan",
        order_by="StateTransition.created_at"
    )
    price_snapshots = relationship(
        "PriceSnapshot",
        back_populates="trade",
        cascade="all, delete-orphan",
        order_by="PriceSnapshot.timestamp"
    )

    # --- Composite Index for common queries ---
    __table_args__ = (
        Index('ix_paper_trades_username_status', 'username', 'status'),
        Index('ix_paper_trades_username_ticker', 'username', 'ticker'),
    )

    def __repr__(self):
        return f"<PaperTrade(id={self.id}, {self.ticker} {self.option_type} {self.strike} status={self.status})>"


# ---------------------------------------------------------------------------
# Audit Trail: StateTransition (Point 11)
# ---------------------------------------------------------------------------
class StateTransition(Base):
    __tablename__ = 'state_transitions'

    id           = Column(Integer, primary_key=True, autoincrement=True)
    trade_id     = Column(
        Integer,
        ForeignKey('paper_trades.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    from_status  = Column(String(20), nullable=True)    # NULL for initial creation
    to_status    = Column(String(20), nullable=False)
    trigger      = Column(String(50), nullable=False)    # cron_fill_check, user_close, sl_hit, etc.
    metadata_json = Column(JSONB, default=dict, server_default='{}')
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    # --- Relationship ---
    trade = relationship("PaperTrade", back_populates="state_transitions")

    def __repr__(self):
        return f"<StateTransition(trade_id={self.trade_id}, {self.from_status}→{self.to_status} via {self.trigger})>"


# ---------------------------------------------------------------------------
# Price History: PriceSnapshot (Point 2 + Point 5 bookends)
# ---------------------------------------------------------------------------
class PriceSnapshot(Base):
    __tablename__ = 'price_snapshots'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    trade_id    = Column(
        Integer,
        ForeignKey('paper_trades.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    timestamp   = Column(DateTime, default=datetime.utcnow, nullable=False)
    mark_price  = Column(Float, nullable=True)
    bid         = Column(Float, nullable=True)
    ask         = Column(Float, nullable=True)
    delta       = Column(Float, nullable=True)
    iv          = Column(Float, nullable=True)
    underlying  = Column(Float, nullable=True)
    snapshot_type = Column(String(20), default='PERIODIC')  # PERIODIC / OPEN_BOOKEND / CLOSE_BOOKEND

    # --- Relationship ---
    trade = relationship("PaperTrade", back_populates="price_snapshots")

    def __repr__(self):
        return f"<PriceSnapshot(trade_id={self.trade_id}, price={self.mark_price}, type={self.snapshot_type})>"


# ---------------------------------------------------------------------------
# User Config: UserSettings (Point 9 tokens + Point 4 defaults)
# ---------------------------------------------------------------------------
class UserSettings(Base):
    __tablename__ = 'user_settings'

    username              = Column(String(50), primary_key=True)
    broker_mode           = Column(String(20), default='TRADIER_SANDBOX')

    # Tradier tokens (encrypted via Point 9 Fernet)
    tradier_sandbox_token = Column(Text, nullable=True)   # Fernet-encrypted
    tradier_live_token    = Column(Text, nullable=True)    # Fernet-encrypted
    tradier_account_id    = Column(String(50), nullable=True)

    # Risk settings
    account_balance       = Column(Float, default=5000.0)
    max_positions         = Column(Integer, default=5)
    daily_loss_limit      = Column(Float, default=150.0)
    heat_limit_pct        = Column(Float, default=6.0)

    # Default bracket settings (Point 4)
    default_sl_pct        = Column(Float, default=20.0)    # 20% stop loss
    default_tp_pct        = Column(Float, default=50.0)    # 50% take profit

    # Preferences
    auto_refresh          = Column(Boolean, default=True)
    sound_enabled         = Column(Boolean, default=True)

    # Timestamps
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UserSettings(username={self.username}, mode={self.broker_mode})>"
