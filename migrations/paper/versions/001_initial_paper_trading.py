"""Add paper trading tables

Revision ID: 001_initial
Revises: None
Create Date: 2026-02-19

Point 1: Database Schema — Creates all paper trading tables:
  - paper_trades     (core trade data, JSONB context, version, idempotency)
  - state_transitions (Point 11 audit trail)
  - price_snapshots  (Point 2/5 price history + bookends)
  - user_settings    (Point 9 broker tokens + Point 4 defaults)

Point 7: Row Level Security policies applied here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===================================================================
    # 1. paper_trades
    # ===================================================================
    op.create_table(
        'paper_trades',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('idempotency_key', sa.String(100), unique=True, nullable=True),

        # Trade details
        sa.Column('ticker', sa.String(10), nullable=False),
        sa.Column('option_type', sa.String(4), nullable=False),
        sa.Column('strike', sa.Float(), nullable=False),
        sa.Column('expiry', sa.String(10), nullable=False),
        sa.Column('direction', sa.String(4), server_default='BUY'),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('qty', sa.Integer(), server_default='1'),

        # Brackets
        sa.Column('sl_price', sa.Float(), nullable=True),
        sa.Column('tp_price', sa.Float(), nullable=True),

        # Scanner context snapshot
        sa.Column('strategy', sa.String(20), nullable=True),
        sa.Column('card_score', sa.Float(), nullable=True),
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('ai_verdict', sa.String(20), nullable=True),
        sa.Column('gate_verdict', sa.String(20), nullable=True),
        sa.Column('technical_score', sa.Float(), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('delta_at_entry', sa.Float(), nullable=True),
        sa.Column('iv_at_entry', sa.Float(), nullable=True),

        # Live monitoring
        sa.Column('current_price', sa.Float(), nullable=True),
        sa.Column('unrealized_pnl', sa.Float(), nullable=True),

        # Status + outcome
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('close_reason', sa.String(30), nullable=True),

        # JSONB context (Point 6)
        sa.Column('trade_context', postgresql.JSONB(), server_default='{}', nullable=False),

        # Tradier integration (Point 9)
        sa.Column('broker_mode', sa.String(20), server_default='TRADIER_SANDBOX'),
        sa.Column('tradier_order_id', sa.String(50), nullable=True),
        sa.Column('tradier_sl_order_id', sa.String(50), nullable=True),
        sa.Column('tradier_tp_order_id', sa.String(50), nullable=True),
        sa.Column('broker_fill_price', sa.Float(), nullable=True),
        sa.Column('broker_fill_time', sa.DateTime(), nullable=True),

        # Concurrency (Points 8 + 10)
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_locked', sa.Boolean(), server_default='false'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(), nullable=True),

        # CHECK constraint on status (Point 11)
        sa.CheckConstraint(
            "status IN ('PENDING','OPEN','PARTIALLY_FILLED','CLOSING','CLOSED','EXPIRED','CANCELED')",
            name='ck_paper_trades_status'
        ),
    )

    # Indexes
    op.create_index('ix_paper_trades_username', 'paper_trades', ['username'])
    op.create_index('ix_paper_trades_status', 'paper_trades', ['status'])
    op.create_index('ix_paper_trades_username_status', 'paper_trades', ['username', 'status'])
    op.create_index('ix_paper_trades_username_ticker', 'paper_trades', ['username', 'ticker'])

    # GIN index on trade_context JSONB (Point 6)
    op.execute('CREATE INDEX ix_paper_trades_context_gin ON paper_trades USING GIN (trade_context)')

    # ===================================================================
    # 2. state_transitions (Point 11: Audit Trail)
    # ===================================================================
    op.create_table(
        'state_transitions',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('trade_id', sa.Integer(), sa.ForeignKey('paper_trades.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_status', sa.String(20), nullable=True),
        sa.Column('to_status', sa.String(20), nullable=False),
        sa.Column('trigger', sa.String(50), nullable=False),
        sa.Column('metadata_json', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_state_transitions_trade_id', 'state_transitions', ['trade_id'])

    # ===================================================================
    # 3. price_snapshots (Point 2 + Point 5: Bookends)
    # ===================================================================
    op.create_table(
        'price_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('trade_id', sa.Integer(), sa.ForeignKey('paper_trades.id', ondelete='CASCADE'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('mark_price', sa.Float(), nullable=True),
        sa.Column('bid', sa.Float(), nullable=True),
        sa.Column('ask', sa.Float(), nullable=True),
        sa.Column('delta', sa.Float(), nullable=True),
        sa.Column('iv', sa.Float(), nullable=True),
        sa.Column('underlying', sa.Float(), nullable=True),
        sa.Column('snapshot_type', sa.String(20), server_default='PERIODIC'),
    )
    op.create_index('ix_price_snapshots_trade_id', 'price_snapshots', ['trade_id'])

    # ===================================================================
    # 4. user_settings (Point 9: Broker Config)
    # ===================================================================
    op.create_table(
        'user_settings',
        sa.Column('username', sa.String(50), primary_key=True),
        sa.Column('broker_mode', sa.String(20), server_default='TRADIER_SANDBOX'),

        # Tradier tokens (Fernet-encrypted)
        sa.Column('tradier_sandbox_token', sa.Text(), nullable=True),
        sa.Column('tradier_live_token', sa.Text(), nullable=True),
        sa.Column('tradier_account_id', sa.String(50), nullable=True),

        # Risk settings
        sa.Column('account_balance', sa.Float(), server_default='5000.0'),
        sa.Column('max_positions', sa.Integer(), server_default='5'),
        sa.Column('daily_loss_limit', sa.Float(), server_default='150.0'),
        sa.Column('heat_limit_pct', sa.Float(), server_default='6.0'),

        # Default bracket settings
        sa.Column('default_sl_pct', sa.Float(), server_default='20.0'),
        sa.Column('default_tp_pct', sa.Float(), server_default='50.0'),

        # Preferences
        sa.Column('auto_refresh', sa.Boolean(), server_default='true'),
        sa.Column('sound_enabled', sa.Boolean(), server_default='true'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # ===================================================================
    # 5. Row Level Security (Point 7)
    # ===================================================================
    # Enable RLS on paper_trades
    op.execute('ALTER TABLE paper_trades ENABLE ROW LEVEL SECURITY')
    op.execute("""
        CREATE POLICY paper_trades_user_isolation ON paper_trades
        USING (username = current_setting('app.current_user', true))
        WITH CHECK (username = current_setting('app.current_user', true))
    """)

    # Enable RLS on state_transitions (via join to paper_trades)
    op.execute('ALTER TABLE state_transitions ENABLE ROW LEVEL SECURITY')
    op.execute("""
        CREATE POLICY state_transitions_user_isolation ON state_transitions
        USING (trade_id IN (
            SELECT id FROM paper_trades
            WHERE username = current_setting('app.current_user', true)
        ))
    """)

    # Enable RLS on price_snapshots
    op.execute('ALTER TABLE price_snapshots ENABLE ROW LEVEL SECURITY')
    op.execute("""
        CREATE POLICY price_snapshots_user_isolation ON price_snapshots
        USING (trade_id IN (
            SELECT id FROM paper_trades
            WHERE username = current_setting('app.current_user', true)
        ))
    """)

    # Enable RLS on user_settings
    op.execute('ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY')
    op.execute("""
        CREATE POLICY user_settings_user_isolation ON user_settings
        USING (username = current_setting('app.current_user', true))
        WITH CHECK (username = current_setting('app.current_user', true))
    """)


def downgrade() -> None:
    # Drop RLS policies first
    op.execute('DROP POLICY IF EXISTS paper_trades_user_isolation ON paper_trades')
    op.execute('DROP POLICY IF EXISTS state_transitions_user_isolation ON state_transitions')
    op.execute('DROP POLICY IF EXISTS price_snapshots_user_isolation ON price_snapshots')
    op.execute('DROP POLICY IF EXISTS user_settings_user_isolation ON user_settings')

    # Drop tables (reverse order)
    op.drop_table('user_settings')
    op.drop_table('price_snapshots')
    op.drop_table('state_transitions')
    op.drop_table('paper_trades')
