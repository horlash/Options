"""Force RLS on table owner

Revision ID: 002_force_rls
Revises: 001_initial
Create Date: 2026-02-19

Point 7 Fix: ENABLE ROW LEVEL SECURITY only blocks non-owner users.
Since our app connects as paper_user (the table owner), we must also
FORCE ROW LEVEL SECURITY so that policies apply to the owner too.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '002_force_rls'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Force RLS to apply even to the table owner
    op.execute('ALTER TABLE paper_trades FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE state_transitions FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE price_snapshots FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE user_settings FORCE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.execute('ALTER TABLE paper_trades NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE state_transitions NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE price_snapshots NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE user_settings NO FORCE ROW LEVEL SECURITY')
