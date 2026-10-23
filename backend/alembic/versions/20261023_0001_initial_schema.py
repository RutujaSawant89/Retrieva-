"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-23 20:44:40.922091
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import pgvector.sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

# The embedding dimension is fixed per deployment; changing models with a different
# dimension requires a new migration (see docs/ARCHITECTURE.md, "Embedding model changes").
EMBEDDING_DIM = get_settings().embedding_dim

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_extensions_and_types()
    op.create_table('organizations',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizations')),
    sa.UniqueConstraint('slug', name=op.f('uq_organizations_slug'))
    )
    op.create_table('roles',
    sa.Column('id', sa.SmallInteger(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('permissions', postgresql.ARRAY(sa.String(length=64)), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('name', name=op.f('uq_roles_name'))
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('api_usage',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('method', sa.String(length=8), nullable=False),
    sa.Column('route', sa.String(length=255), nullable=False),
    sa.Column('status_code', sa.SmallInteger(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_api_usage_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_api_usage_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_usage'))
    )
    op.create_index('ix_api_usage_org_created', 'api_usage', ['organization_id', 'created_at'], unique=False)
    op.create_table('audit_logs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('resource_type', sa.String(length=64), nullable=True),
    sa.Column('resource_id', sa.String(length=64), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_audit_logs_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_logs_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_org_created', 'audit_logs', ['organization_id', 'created_at'], unique=False)
    op.create_table('conversations',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('scope', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('summary_message_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_conversations_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index('ix_conversations_org_user_updated', 'conversations', ['organization_id', 'user_id', 'updated_at'], unique=False)
    op.create_table('document_collections',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('visibility', postgresql.ENUM(name='visibility', create_type=False), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_document_collections_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_document_collections_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_collections'))
    )
    op.create_index(op.f('ix_document_collections_organization_id'), 'document_collections', ['organization_id'], unique=False)
    op.create_index('uq_document_collections_org_name_active', 'document_collections', ['organization_id', sa.literal_column('lower(name)')], unique=True, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_table('documents',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('original_filename', sa.String(length=500), nullable=False),
    sa.Column('file_type', sa.String(length=16), nullable=False),
    sa.Column('mime_type', sa.String(length=128), nullable=False),
    sa.Column('file_size', sa.BigInteger(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('storage_path', sa.String(length=1024), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('visibility', postgresql.ENUM(name='visibility', create_type=False), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('status', postgresql.ENUM(name='document_status', create_type=False), nullable=False),
    sa.Column('progress', sa.SmallInteger(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('embedding_model', sa.String(length=200), nullable=True),
    sa.Column('chunking_strategy', sa.String(length=32), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_documents_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_documents_owner_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    op.create_index('ix_documents_org_created', 'documents', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_documents_org_status', 'documents', ['organization_id', 'status'], unique=False)
    op.create_index('uq_documents_org_hash_active', 'documents', ['organization_id', 'content_hash'], unique=True, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_table('evaluation_datasets',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('item_count', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_evaluation_datasets_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_evaluation_datasets_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_datasets')),
    sa.UniqueConstraint('organization_id', 'name', 'version', name=op.f('uq_evaluation_datasets_organization_id_name_version'))
    )
    op.create_index(op.f('ix_evaluation_datasets_organization_id'), 'evaluation_datasets', ['organization_id'], unique=False)
    op.create_table('organization_invitations',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('role_id', sa.SmallInteger(), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_organization_invitations_invited_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_organization_invitations_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_organization_invitations_role_id_roles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organization_invitations')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_organization_invitations_token_hash'))
    )
    op.create_index(op.f('ix_organization_invitations_organization_id'), 'organization_invitations', ['organization_id'], unique=False)
    op.create_table('organization_members',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.SmallInteger(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_organization_members_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_organization_members_role_id_roles')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_organization_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organization_members')),
    sa.UniqueConstraint('organization_id', 'user_id', name=op.f('uq_organization_members_organization_id_user_id'))
    )
    op.create_index(op.f('ix_organization_members_organization_id'), 'organization_members', ['organization_id'], unique=False)
    op.create_index(op.f('ix_organization_members_user_id'), 'organization_members', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by_id', sa.UUID(), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_refresh_tokens_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('search_queries',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('rewritten_queries', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('strategy', sa.String(length=32), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result_count', sa.Integer(), nullable=False),
    sa.Column('top_score', sa.Float(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('timings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('retrieval_ms', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_search_queries_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_search_queries_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_search_queries'))
    )
    op.create_index('ix_search_queries_org_created', 'search_queries', ['organization_id', 'created_at'], unique=False)
    op.create_table('collection_documents',
    sa.Column('collection_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('added_by', sa.UUID(), nullable=True),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_collection_documents_added_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['collection_id'], ['document_collections.id'], name=op.f('fk_collection_documents_collection_id_document_collections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_collection_documents_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_collection_documents_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('collection_id', 'document_id', name=op.f('pk_collection_documents'))
    )
    op.create_index(op.f('ix_collection_documents_document_id'), 'collection_documents', ['document_id'], unique=False)
    op.create_table('document_chunks',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('page_end', sa.Integer(), nullable=True),
    sa.Column('section', sa.String(length=500), nullable=True),
    sa.Column('heading_path', postgresql.ARRAY(sa.String(length=500)), nullable=False),
    sa.Column('start_char', sa.Integer(), nullable=False),
    sa.Column('end_char', sa.Integer(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=EMBEDDING_DIM), nullable=True),
    sa.Column('embedding_model', sa.String(length=200), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_document_chunks_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks')),
    sa.UniqueConstraint('document_id', 'chunk_index', name=op.f('uq_document_chunks_document_id_chunk_index'))
    )
    op.create_index('ix_document_chunks_content_hash', 'document_chunks', ['organization_id', 'content_hash'], unique=False)
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index('ix_document_chunks_embedding_hnsw', 'document_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_document_chunks_org_model', 'document_chunks', ['organization_id', 'embedding_model'], unique=False)
    op.create_table('evaluation_runs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('dataset_id', sa.UUID(), nullable=False),
    sa.Column('dataset_version', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('status', postgresql.ENUM(name='run_status', create_type=False), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('embedding_model', sa.String(length=200), nullable=False),
    sa.Column('reranker_model', sa.String(length=200), nullable=True),
    sa.Column('llm_provider', sa.String(length=64), nullable=True),
    sa.Column('llm_model', sa.String(length=200), nullable=True),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_evaluation_runs_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['dataset_id'], ['evaluation_datasets.id'], name=op.f('fk_evaluation_runs_dataset_id_evaluation_datasets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_evaluation_runs_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_runs'))
    )
    op.create_index(op.f('ix_evaluation_runs_dataset_id'), 'evaluation_runs', ['dataset_id'], unique=False)
    op.create_index('ix_evaluation_runs_org_created', 'evaluation_runs', ['organization_id', 'created_at'], unique=False)
    op.create_table('ingestion_jobs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('task_id', sa.String(length=255), nullable=True),
    sa.Column('status', postgresql.ENUM(name='document_status', create_type=False), nullable=False),
    sa.Column('progress', sa.SmallInteger(), nullable=False),
    sa.Column('attempts', sa.SmallInteger(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('stage_timings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_ingestion_jobs_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ingestion_jobs_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingestion_jobs'))
    )
    op.create_index(op.f('ix_ingestion_jobs_document_id'), 'ingestion_jobs', ['document_id'], unique=False)
    op.create_index('ix_ingestion_jobs_org_status', 'ingestion_jobs', ['organization_id', 'status'], unique=False)
    op.create_table('messages',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', postgresql.ENUM(name='message_role', create_type=False), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('retrieval', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('verification', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('llm_provider', sa.String(length=64), nullable=True),
    sa.Column('llm_model', sa.String(length=200), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('retrieval_ms', sa.Float(), nullable=True),
    sa.Column('generation_ms', sa.Float(), nullable=True),
    sa.Column('total_ms', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_messages_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_messages_organization_id'), 'messages', ['organization_id'], unique=False)
    op.create_table('evaluation_results',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('item_index', sa.Integer(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('retrieved', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('answer', sa.Text(), nullable=True),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_evaluation_results_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['evaluation_runs.id'], name=op.f('fk_evaluation_results_run_id_evaluation_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_results'))
    )
    op.create_index(op.f('ix_evaluation_results_run_id'), 'evaluation_results', ['run_id'], unique=False)
    op.create_table('message_citations',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('message_id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=16), nullable=False),
    sa.Column('label_index', sa.SmallInteger(), nullable=False),
    sa.Column('chunk_id', sa.UUID(), nullable=True),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('document_title', sa.String(length=500), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('section', sa.String(length=500), nullable=True),
    sa.Column('passage', sa.Text(), nullable=False),
    sa.Column('retrieval_score', sa.Float(), nullable=True),
    sa.Column('rerank_score', sa.Float(), nullable=True),
    sa.Column('cited_in_answer', sa.Boolean(), nullable=False),
    sa.Column('validation_status', sa.String(length=16), nullable=False),
    sa.Column('support_score', sa.Float(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], name=op.f('fk_message_citations_chunk_id_document_chunks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_message_citations_document_id_documents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_message_citations_message_id_messages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_message_citations_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_message_citations'))
    )
    op.create_index(op.f('ix_message_citations_chunk_id'), 'message_citations', ['chunk_id'], unique=False)
    op.create_index(op.f('ix_message_citations_message_id'), 'message_citations', ['message_id'], unique=False)
    _seed_roles()
    _enable_row_level_security()
    _grant_app_role()


def downgrade() -> None:
    op.drop_index(op.f('ix_message_citations_message_id'), table_name='message_citations')
    op.drop_index(op.f('ix_message_citations_chunk_id'), table_name='message_citations')
    op.drop_table('message_citations')
    op.drop_index(op.f('ix_evaluation_results_run_id'), table_name='evaluation_results')
    op.drop_table('evaluation_results')
    op.drop_index(op.f('ix_messages_organization_id'), table_name='messages')
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_ingestion_jobs_org_status', table_name='ingestion_jobs')
    op.drop_index(op.f('ix_ingestion_jobs_document_id'), table_name='ingestion_jobs')
    op.drop_table('ingestion_jobs')
    op.drop_index('ix_evaluation_runs_org_created', table_name='evaluation_runs')
    op.drop_index(op.f('ix_evaluation_runs_dataset_id'), table_name='evaluation_runs')
    op.drop_table('evaluation_runs')
    op.drop_index('ix_document_chunks_org_model', table_name='document_chunks')
    op.drop_index('ix_document_chunks_embedding_hnsw', table_name='document_chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_index('ix_document_chunks_content_hash', table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_index(op.f('ix_collection_documents_document_id'), table_name='collection_documents')
    op.drop_table('collection_documents')
    op.drop_index('ix_search_queries_org_created', table_name='search_queries')
    op.drop_table('search_queries')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_organization_members_user_id'), table_name='organization_members')
    op.drop_index(op.f('ix_organization_members_organization_id'), table_name='organization_members')
    op.drop_table('organization_members')
    op.drop_index(op.f('ix_organization_invitations_organization_id'), table_name='organization_invitations')
    op.drop_table('organization_invitations')
    op.drop_index(op.f('ix_evaluation_datasets_organization_id'), table_name='evaluation_datasets')
    op.drop_table('evaluation_datasets')
    op.drop_index('uq_documents_org_hash_active', table_name='documents', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_documents_org_status', table_name='documents')
    op.drop_index('ix_documents_org_created', table_name='documents')
    op.drop_table('documents')
    op.drop_index('uq_document_collections_org_name_active', table_name='document_collections', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index(op.f('ix_document_collections_organization_id'), table_name='document_collections')
    op.drop_table('document_collections')
    op.drop_index('ix_conversations_org_user_updated', table_name='conversations')
    op.drop_table('conversations')
    op.drop_index('ix_audit_logs_org_created', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('ix_api_usage_org_created', table_name='api_usage')
    op.drop_table('api_usage')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('organizations')
    for enum_name in ENUMS:
        op.execute(f'DROP TYPE IF EXISTS {enum_name}')


ENUMS = {
    "visibility": ("organization", "private"),
    "document_status": (
        "uploaded", "queued", "extracting", "chunking", "embedding", "indexing", "completed", "failed",
    ),
    "run_status": ("pending", "running", "completed", "failed"),
    "message_role": ("user", "assistant"),
}

# Tables whose rows belong to exactly one organization. Mirrors app.db.models.TENANT_TABLES,
# duplicated on purpose: migrations must not change when application code changes.
TENANT_TABLES = (
    "documents", "document_chunks", "document_collections", "collection_documents", "conversations",
    "messages", "message_citations", "ingestion_jobs", "search_queries", "evaluation_datasets",
    "evaluation_runs", "evaluation_results", "audit_logs", "api_usage",
)

APP_ROLE = "retrieva_app"

ROLES = (
    (1, "admin", "Full control of the organization, its members, documents and audit logs."),
    (2, "analyst", "Uploads documents, runs evaluations and reads analytics."),
    (3, "researcher", "Uploads documents, builds collections, chats and runs research."),
    (4, "viewer", "Searches and chats over documents shared with the organization."),
)


def _create_extensions_and_types() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)


def _seed_roles() -> None:
    from app.core.permissions import ROLE_PERMISSIONS, RoleName

    roles = sa.table(
        "roles",
        sa.column("id", sa.SmallInteger),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("permissions", postgresql.ARRAY(sa.String)),
    )
    op.bulk_insert(
        roles,
        [
            {
                "id": role_id,
                "name": name,
                "description": description,
                "permissions": sorted(p.value for p in ROLE_PERMISSIONS[RoleName(name)]),
            }
            for role_id, name, description in ROLES
        ],
    )


def _enable_row_level_security() -> None:
    """Restrict every tenant table to rows of ``current_setting('app.current_org')``.

    ``FORCE`` makes the policy apply to the table owner too. When the setting is absent,
    ``current_setting(..., true)`` returns NULL and the policy matches no rows.
    """
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid) "
            "WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid)"
        )


def _grant_app_role() -> None:
    """Grant DML to the runtime role when it exists (created by infra scripts, not migrations)."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                EXECUTE 'GRANT USAGE ON SCHEMA public TO {APP_ROLE}';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}';
                EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}';
                EXECUTE 'REVOKE ALL ON TABLE alembic_version FROM {APP_ROLE}';
                EXECUTE 'GRANT SELECT ON TABLE alembic_version TO {APP_ROLE}';
                EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}';
            END IF;
        END $$;
        """
    )
