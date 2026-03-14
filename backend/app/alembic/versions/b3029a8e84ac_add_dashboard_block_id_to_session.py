"""add_dashboard_block_id_to_session

Revision ID: b3029a8e84ac
Revises: 361c33705d15
Create Date: 2026-03-14 08:56:37.608410

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'b3029a8e84ac'
down_revision = '361c33705d15'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('session', sa.Column('dashboard_block_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_session_dashboard_block_id',
        'session', 'user_dashboard_block',
        ['dashboard_block_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_session_dashboard_block_id',
        'session', ['dashboard_block_id'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_session_dashboard_block_id', table_name='session')
    op.drop_constraint('fk_session_dashboard_block_id', 'session', type_='foreignkey')
    op.drop_column('session', 'dashboard_block_id')
