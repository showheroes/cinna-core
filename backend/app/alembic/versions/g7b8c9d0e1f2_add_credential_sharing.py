"""add credential sharing

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-01-16

Adds credential sharing functionality:
- allow_sharing column to credential table
- credential_shares table for tracking shares between users
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'g7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # Add allow_sharing column to credential table
    op.add_column('credential', sa.Column('allow_sharing', sa.Boolean(), nullable=False, server_default='false'))

    # Create index for allow_sharing (partial index for shareable credentials)
    op.create_index(
        'ix_credential_allow_sharing',
        'credential',
        ['allow_sharing'],
        postgresql_where=sa.text('allow_sharing = true')
    )

    # Create credential_shares table
    op.create_table('credential_shares',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('credential_id', sa.Uuid(), nullable=False),
        sa.Column('shared_with_user_id', sa.Uuid(), nullable=False),
        sa.Column('shared_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('shared_at', sa.DateTime(), nullable=False),
        sa.Column('access_level', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='read'),
        sa.ForeignKeyConstraint(['credential_id'], ['credential.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_with_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_by_user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('credential_id', 'shared_with_user_id', name='uq_credential_shares_credential_user')
    )

    # Create indexes for credential_shares
    op.create_index(op.f('ix_credential_shares_credential_id'), 'credential_shares', ['credential_id'], unique=False)
    op.create_index(op.f('ix_credential_shares_shared_with_user_id'), 'credential_shares', ['shared_with_user_id'], unique=False)


def downgrade():
    # Drop credential_shares table and indexes
    op.drop_index(op.f('ix_credential_shares_shared_with_user_id'), table_name='credential_shares')
    op.drop_index(op.f('ix_credential_shares_credential_id'), table_name='credential_shares')
    op.drop_table('credential_shares')

    # Drop allow_sharing column and index from credential
    op.drop_index('ix_credential_allow_sharing', table_name='credential')
    op.drop_column('credential', 'allow_sharing')
