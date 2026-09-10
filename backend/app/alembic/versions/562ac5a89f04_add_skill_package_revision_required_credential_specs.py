"""add skill_package_revision required_credential_specs

``skill_package_revision.required_credential_specs`` — the credential slots a
published skill declares in its ``SKILL.md`` ``credentials:`` block, resolved
at publish into the same spec schema as
``agent_bundle_revision.required_credential_specs``: names, types, provisioning
mode; never secret values (template private fields are stripped at publish).
Written once, when the revision row is inserted — revisions are immutable.

WHY THE DEFAULT IS ``[]``. Every revision that exists today was published
before a skill could declare credentials, so "declares nothing" is the true
value for each of them, not a placeholder. A server default of ``'[]'``
backfills them in place with no data step, and keeps the column NOT NULL so no
reader has to branch on NULL.

DOWNGRADE WARNING: dropping the column loses the frozen credential provisioning
of every revision published since this migration. Nothing can re-derive it — it
was resolved against the publisher's credentials as they stood at publish — so
after a downgrade, installing or upgrading to such a revision treats every slot
as absent (no credential provisioning at all).

Revision ID: 562ac5a89f04
Revises: d7b41e0c9a35
Create Date: 2026-09-10 10:27:01.128168

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '562ac5a89f04'
down_revision = 'd7b41e0c9a35'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'skill_package_revision',
        sa.Column(
            'required_credential_specs',
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade():
    op.drop_column('skill_package_revision', 'required_credential_specs')
