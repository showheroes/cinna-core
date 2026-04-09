"""add cli tokens

Revision ID: a1b2c3d4e5f6
Revises: z6u7v8w9x0y1
Create Date: 2026-04-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '51014db83e57'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    # Create cli_setup_token table
    op.create_table(
        'cli_setup_token',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('environment_id', sa.Uuid(), nullable=True),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['environment_id'], ['agent_environment.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_cli_setup_token_token',
        'cli_setup_token',
        ['token'],
        unique=True,
    )
    op.create_index(
        'ix_cli_setup_token_owner_agent',
        'cli_setup_token',
        ['owner_id', 'agent_id'],
        unique=False,
    )

    # Create cli_token table
    op.create_table(
        'cli_token',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('prefix', sa.String(length=12), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('machine_info', sa.String(length=200), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_cli_token_token_hash',
        'cli_token',
        ['token_hash'],
        unique=True,
    )
    op.create_index(
        'ix_cli_token_owner_agent',
        'cli_token',
        ['owner_id', 'agent_id'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_cli_token_owner_agent', table_name='cli_token')
    op.drop_index('ix_cli_token_token_hash', table_name='cli_token')
    op.drop_table('cli_token')

    op.drop_index('ix_cli_setup_token_owner_agent', table_name='cli_setup_token')
    op.drop_index('ix_cli_setup_token_token', table_name='cli_setup_token')
    op.drop_table('cli_setup_token')
