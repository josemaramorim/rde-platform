"""add is_demo to plans

Revision ID: a1b2c3d4e5f6
Revises: f5f894a3114f
Create Date: 2026-07-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f5f894a3114f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default='1'))
    op.execute("UPDATE plans SET is_demo = 1 WHERE name = 'Free'")
    op.execute("UPDATE plans SET is_demo = 0 WHERE name IN ('Pro', 'VIP')")


def downgrade() -> None:
    op.drop_column('plans', 'is_demo')
