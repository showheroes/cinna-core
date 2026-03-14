"""add_dashboard_block_prompt_actions

Revision ID: 361c33705d15
Revises: b8c9d0e1f2g3
Create Date: 2026-03-13 23:18:15.171912

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '361c33705d15'
down_revision = 'b8c9d0e1f2g3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_dashboard_block_prompt_action',
        sa.Column('prompt_text', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False),
        sa.Column('label', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('block_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['user_dashboard_block.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_user_dashboard_block_prompt_action_block_id',
        'user_dashboard_block_prompt_action',
        ['block_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_user_dashboard_block_prompt_action_block_id',
        table_name='user_dashboard_block_prompt_action',
    )
    op.drop_table('user_dashboard_block_prompt_action')
