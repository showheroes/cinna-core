"""add default_ai_functions_credential_id and is_oauth_token to user

Revision ID: g2h3i4j5k6l7
Revises: f1g2h3i4j5k6
Create Date: 2026-03-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g2h3i4j5k6l7'
down_revision = 'f1g2h3i4j5k6'
branch_labels = None
depends_on = None


def upgrade():
    # Add optional credential_id field to user table.
    # When set, AI functions will use this specific credential instead of the default for type.
    # NULL = use the default credential for the selected SDK type.
    op.add_column(
        'user',
        sa.Column(
            'default_ai_functions_credential_id',
            sa.Uuid(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column('user', 'default_ai_functions_credential_id')
