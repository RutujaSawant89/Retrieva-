"""citation passage offsets

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23 21:58:08.550835
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('message_citations', sa.Column('page_end', sa.Integer(), nullable=True))
    op.add_column('message_citations', sa.Column('start_char', sa.Integer(), nullable=True))
    op.add_column('message_citations', sa.Column('end_char', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('message_citations', 'end_char')
    op.drop_column('message_citations', 'start_char')
    op.drop_column('message_citations', 'page_end')
