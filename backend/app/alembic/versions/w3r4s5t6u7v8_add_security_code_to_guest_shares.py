"""add security code to guest shares

Revision ID: w3r4s5t6u7v8
Revises: v2q3r4s5t6u7
Create Date: 2026-02-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'w3r4s5t6u7v8'
down_revision = 'f53ac2dee553'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agent_guest_share', sa.Column('security_code_encrypted', sa.String(), nullable=True))
    op.add_column('agent_guest_share', sa.Column('failed_code_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('agent_guest_share', sa.Column('is_code_blocked', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('agent_guest_share', 'is_code_blocked')
    op.drop_column('agent_guest_share', 'failed_code_attempts')
    op.drop_column('agent_guest_share', 'security_code_encrypted')
