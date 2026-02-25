"""add agent guest share tables

Revision ID: f53ac2dee553
Revises: i6d5e7f8g9h0
Create Date: 2026-02-24 22:36:11.938500

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'f53ac2dee553'
down_revision = 'i6d5e7f8g9h0'
branch_labels = None
depends_on = None


def upgrade():
    # Create agent_guest_share table
    op.create_table('agent_guest_share',
        sa.Column('label', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('token_prefix', sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column('token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_guest_share_agent_id'), 'agent_guest_share', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agent_guest_share_owner_id'), 'agent_guest_share', ['owner_id'], unique=False)
    op.create_index(op.f('ix_agent_guest_share_token_hash'), 'agent_guest_share', ['token_hash'], unique=False)

    # Create guest_share_grant table
    op.create_table('guest_share_grant',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('guest_share_id', sa.Uuid(), nullable=False),
        sa.Column('activated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['guest_share_id'], ['agent_guest_share.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'guest_share_id', name='uq_guest_share_grant_user_share')
    )

    # Add guest_share_id to session table
    op.add_column('session', sa.Column('guest_share_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_session_guest_share_id',
        'session',
        'agent_guest_share',
        ['guest_share_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    # Drop foreign key and column from session
    op.drop_constraint('fk_session_guest_share_id', 'session', type_='foreignkey')
    op.drop_column('session', 'guest_share_id')

    # Drop guest_share_grant table
    op.drop_table('guest_share_grant')

    # Drop agent_guest_share table
    op.drop_index(op.f('ix_agent_guest_share_token_hash'), table_name='agent_guest_share')
    op.drop_index(op.f('ix_agent_guest_share_owner_id'), table_name='agent_guest_share')
    op.drop_index(op.f('ix_agent_guest_share_agent_id'), table_name='agent_guest_share')
    op.drop_table('agent_guest_share')
