"""mark existing command messages as forwarded

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-04-19 12:30:00.000000

Bulk-marks all pre-deploy command system messages with forwarded_to_llm_at
to prevent them from flooding the next LLM turn after this feature is deployed.

Any existing role='system' message with message_metadata['command']=true and
no 'forwarded_to_llm_at' key is considered a legacy message and is marked with
the migration sentinel timestamp '2026-04-19T00:00:00Z'.

The downgrade removes exactly those sentinel values so the migration is
cleanly reversible.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    # message_metadata is a `json` column, so cast to jsonb for key existence
    # check and mutation, then cast back.
    op.execute("""
        UPDATE message
        SET message_metadata = jsonb_set(
            COALESCE(message_metadata::jsonb, '{}'::jsonb),
            '{forwarded_to_llm_at}',
            to_jsonb('2026-04-19T00:00:00Z'::text),
            true
        )::json
        WHERE role = 'system'
          AND (message_metadata->>'command') = 'true'
          AND (message_metadata->>'forwarded_to_llm_at') IS NULL
    """)


def downgrade():
    op.execute("""
        UPDATE message
        SET message_metadata = (message_metadata::jsonb - 'forwarded_to_llm_at')::json
        WHERE role = 'system'
          AND (message_metadata->>'command') = 'true'
          AND message_metadata->>'forwarded_to_llm_at' = '2026-04-19T00:00:00Z'
    """)
