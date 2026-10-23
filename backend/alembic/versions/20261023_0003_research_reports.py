"""research reports

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23 22:35:57.537246
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('research_reports',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('scope', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('subqueries', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('report', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('conflicts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('verification', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('llm_provider', sa.String(length=64), nullable=True),
    sa.Column('llm_model', sa.String(length=200), nullable=True),
    sa.Column('total_ms', sa.Float(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_research_reports_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_research_reports_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_research_reports'))
    )
    op.create_index('ix_research_reports_org_user_created', 'research_reports', ['organization_id', 'user_id', 'created_at'], unique=False)
    op.execute("ALTER TABLE research_reports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE research_reports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON research_reports "
        "USING (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid) "
        "WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retrieva_app') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE research_reports TO retrieva_app';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index('ix_research_reports_org_user_created', table_name='research_reports')
    op.drop_table('research_reports')
