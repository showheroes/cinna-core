"""add ai credentials table

Revision ID: h8c9d0e1f2g3
Revises: 6fefe45793e6
Create Date: 2026-01-16

Adds ai_credential table for named AI credentials:
- Stores encrypted API keys for AI providers (Anthropic, MiniMax, OpenAI Compatible)
- Users can have multiple credentials per type
- One credential per type can be marked as default
- Default credentials sync to user's ai_credentials_encrypted for backward compatibility
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'h8c9d0e1f2g3'
down_revision = '6fefe45793e6'
branch_labels = None
depends_on = None


def upgrade():
    # Create ai_credential table
    op.create_table('ai_credential',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('encrypted_data', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Index for efficient lookups by owner and type
    op.create_index('ix_ai_credential_owner_type', 'ai_credential', ['owner_id', 'type'], unique=False)
    # Index for finding defaults
    op.create_index('ix_ai_credential_owner_default', 'ai_credential', ['owner_id', 'is_default'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('ix_ai_credential_owner_default', table_name='ai_credential')
    op.drop_index('ix_ai_credential_owner_type', table_name='ai_credential')
    # Drop table
    op.drop_table('ai_credential')
