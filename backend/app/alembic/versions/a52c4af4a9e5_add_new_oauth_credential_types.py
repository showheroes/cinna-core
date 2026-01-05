"""add_new_oauth_credential_types

Revision ID: a52c4af4a9e5
Revises: 240176144d01
Create Date: 2026-01-05 16:12:08.943715

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'a52c4af4a9e5'
down_revision = '240176144d01'
branch_labels = None
depends_on = None


def upgrade():
    # Add new OAuth credential type values to the credentialtype enum
    # These support Google OAuth for Gmail, Drive, and Calendar with read-only variants
    op.execute("ALTER TYPE credentialtype ADD VALUE IF NOT EXISTS 'GMAIL_OAUTH_READONLY'")
    op.execute("ALTER TYPE credentialtype ADD VALUE IF NOT EXISTS 'GDRIVE_OAUTH'")
    op.execute("ALTER TYPE credentialtype ADD VALUE IF NOT EXISTS 'GDRIVE_OAUTH_READONLY'")
    op.execute("ALTER TYPE credentialtype ADD VALUE IF NOT EXISTS 'GCALENDAR_OAUTH'")
    op.execute("ALTER TYPE credentialtype ADD VALUE IF NOT EXISTS 'GCALENDAR_OAUTH_READONLY'")


def downgrade():
    # Note: PostgreSQL does not support removing enum values directly
    # You would need to recreate the enum type to remove values
    # For safety, we'll leave this as a no-op
    # If you need to rollback, you'll need to manually handle it or recreate the enum
    pass
