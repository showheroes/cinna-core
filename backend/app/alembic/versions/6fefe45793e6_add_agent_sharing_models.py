"""add_agent_sharing_models

Revision ID: 6fefe45793e6
Revises: g7b8c9d0e1f2
Create Date: 2026-01-16 15:43:46.262758

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '6fefe45793e6'
down_revision = 'g7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create agent_share table
    op.create_table('agent_share',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('original_agent_id', sa.Uuid(), nullable=False),
        sa.Column('shared_with_user_id', sa.Uuid(), nullable=False),
        sa.Column('shared_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('share_mode', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='pending'),
        sa.Column('shared_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('declined_at', sa.DateTime(), nullable=True),
        sa.Column('cloned_agent_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['cloned_agent_id'], ['agent.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['original_agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_by_user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['shared_with_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # One share per agent-user pair
        sa.UniqueConstraint('original_agent_id', 'shared_with_user_id', name='uq_agent_share_agent_user')
    )

    # Indexes for efficient agent_share queries
    op.create_index('ix_agent_share_original_agent', 'agent_share', ['original_agent_id'], unique=False)
    op.create_index('ix_agent_share_recipient', 'agent_share', ['shared_with_user_id'], unique=False)
    op.create_index('ix_agent_share_status', 'agent_share', ['status'], unique=False)

    # 2. Add clone fields to agent table
    op.add_column('agent', sa.Column('is_clone', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('agent', sa.Column('parent_agent_id', sa.Uuid(), nullable=True))
    op.add_column('agent', sa.Column('clone_mode', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True))
    op.add_column('agent', sa.Column('last_sync_at', sa.DateTime(), nullable=True))
    op.add_column('agent', sa.Column('update_mode', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='automatic'))
    op.add_column('agent', sa.Column('pending_update', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('agent', sa.Column('pending_update_at', sa.DateTime(), nullable=True))

    # Foreign key for parent agent (self-reference)
    op.create_foreign_key('fk_agent_parent', 'agent', 'agent', ['parent_agent_id'], ['id'], ondelete='SET NULL')

    # Indexes for efficient clone queries
    op.create_index('ix_agent_parent', 'agent', ['parent_agent_id'], unique=False, postgresql_where=sa.text('parent_agent_id IS NOT NULL'))
    op.create_index('ix_agent_is_clone', 'agent', ['is_clone'], unique=False, postgresql_where=sa.text('is_clone = true'))
    op.create_index('ix_agent_pending_update', 'agent', ['pending_update'], unique=False, postgresql_where=sa.text('pending_update = true'))

    # 3. Add placeholder fields to credential table
    op.add_column('credential', sa.Column('is_placeholder', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('credential', sa.Column('placeholder_source_id', sa.Uuid(), nullable=True))

    # Foreign key for placeholder source (self-reference)
    op.create_foreign_key('fk_credential_placeholder_source', 'credential', 'credential', ['placeholder_source_id'], ['id'], ondelete='SET NULL')

    # Index for placeholder credentials
    op.create_index('ix_credential_placeholder', 'credential', ['is_placeholder'], unique=False, postgresql_where=sa.text('is_placeholder = true'))


def downgrade():
    # Drop credential placeholder fields
    op.drop_index('ix_credential_placeholder', table_name='credential')
    op.drop_constraint('fk_credential_placeholder_source', 'credential', type_='foreignkey')
    op.drop_column('credential', 'placeholder_source_id')
    op.drop_column('credential', 'is_placeholder')

    # Drop agent clone fields
    op.drop_index('ix_agent_pending_update', table_name='agent')
    op.drop_index('ix_agent_is_clone', table_name='agent')
    op.drop_index('ix_agent_parent', table_name='agent')
    op.drop_constraint('fk_agent_parent', 'agent', type_='foreignkey')
    op.drop_column('agent', 'pending_update_at')
    op.drop_column('agent', 'pending_update')
    op.drop_column('agent', 'update_mode')
    op.drop_column('agent', 'last_sync_at')
    op.drop_column('agent', 'clone_mode')
    op.drop_column('agent', 'parent_agent_id')
    op.drop_column('agent', 'is_clone')

    # Drop agent_share table
    op.drop_index('ix_agent_share_status', table_name='agent_share')
    op.drop_index('ix_agent_share_recipient', table_name='agent_share')
    op.drop_index('ix_agent_share_original_agent', table_name='agent_share')
    op.drop_table('agent_share')
