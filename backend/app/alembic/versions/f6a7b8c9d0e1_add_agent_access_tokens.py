"""add agent access tokens

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-01-16

Adds agent_access_tokens table for A2A token-based authentication:
- Tokens provide scoped access to agents for external A2A clients
- Tokens have mode (conversation/building) and scope (limited/general)
- Sessions track which access token created them

Also adds access_token_id to session table for scope enforcement.
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    # Create agent_access_tokens table
    op.create_table('agent_access_tokens',
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('mode', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('scope', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('token_prefix', sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_access_tokens_token_hash'), 'agent_access_tokens', ['token_hash'], unique=False)

    # Add access_token_id to session table
    op.add_column('session', sa.Column('access_token_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_session_access_token_id',
        'session',
        'agent_access_tokens',
        ['access_token_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    # Drop foreign key and column from session
    op.drop_constraint('fk_session_access_token_id', 'session', type_='foreignkey')
    op.drop_column('session', 'access_token_id')

    # Drop agent_access_tokens table
    op.drop_index(op.f('ix_agent_access_tokens_token_hash'), table_name='agent_access_tokens')
    op.drop_table('agent_access_tokens')
