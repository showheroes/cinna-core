"""add input_task_id to activity

Revision ID: i6d5e7f8g9h0
Revises: h5c3d4e6f7g8
Create Date: 2026-02-23 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i6d5e7f8g9h0'
down_revision = 'h5c3d4e6f7g8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'activity',
        sa.Column('input_task_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_activity_input_task_id',
        'activity',
        'input_task',
        ['input_task_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_activity_input_task_id', 'activity', type_='foreignkey')
    op.drop_column('activity', 'input_task_id')
