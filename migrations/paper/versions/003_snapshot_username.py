"""Add username column to price_snapshots + direct RLS policy

Revision ID: 003_snapshot_username
Revises: 002_force_rls
Create Date: 2026-02-24

Adds a `username` column directly to price_snapshots so RLS can use
a direct column match instead of a subquery join to paper_trades.
This improves query performance at scale.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '003_snapshot_username'
down_revision: Union[str, None] = '002_force_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add username column to price_snapshots
    op.add_column(
        'price_snapshots',
        sa.Column('username', sa.String(50), nullable=False, server_default='')
    )

    # 2. Create index for RLS performance
    op.create_index(
        'ix_price_snapshots_username',
        'price_snapshots',
        ['username']
    )

    # 3. Drop old subquery-based RLS policy
    op.execute('DROP POLICY IF EXISTS price_snapshots_user_isolation ON price_snapshots')

    # 4. Create new direct-match RLS policy
    op.execute("""
        CREATE POLICY price_snapshots_user_isolation ON price_snapshots
        USING (username = current_setting('app.current_user', true))
        WITH CHECK (username = current_setting('app.current_user', true))
    """)

    # 5. Remove the server_default (only needed for migration of existing rows)
    op.alter_column('price_snapshots', 'username', server_default=None)


def downgrade() -> None:
    # Revert to subquery-based RLS policy
    op.execute('DROP POLICY IF EXISTS price_snapshots_user_isolation ON price_snapshots')
    op.execute("""
        CREATE POLICY price_snapshots_user_isolation ON price_snapshots
        USING (trade_id IN (
            SELECT id FROM paper_trades
            WHERE username = current_setting('app.current_user', true)
        ))
    """)

    # Drop index and column
    op.drop_index('ix_price_snapshots_username', table_name='price_snapshots')
    op.drop_column('price_snapshots', 'username')
