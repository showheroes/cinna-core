"""add_quoted_context_to_routing_decision

Revision ID: d1721ea327b6
Revises: e45b436d251f
Create Date: 2026-09-14 15:26:33.346296

Stores the message a channel sender replied to on the routing trace, so a trace
shows what the classifier was given and a replay can reproduce it:

- ``quoted_message_text`` / ``quoted_message_author`` — a third party's words
  and display label, written and served only under
  ``ROUTING_TRACE_STORE_MESSAGE_TEXT`` (the ``message_text`` rule);
- ``quoted_agent_id`` — the agent whose reply was quoted, as resolved from the
  delivery ledger. An id, not gated; ``SET NULL`` like ``selected_agent_id``.

Existing rows read NULL everywhere, which is accurate: no quote was read when
they were written. No backfill. The data is disposable diagnostics, so the
downgrade simply drops it.

The foreign key is named explicitly (autogenerate emits ``None``), so the
downgrade can drop it by name.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd1721ea327b6'
down_revision = 'e45b436d251f'
branch_labels = None
depends_on = None

_QUOTED_AGENT_FK = 'routing_decision_quoted_agent_id_fkey'


def upgrade():
    op.add_column(
        'routing_decision',
        sa.Column('quoted_message_text', sa.Text(), nullable=True),
    )
    op.add_column(
        'routing_decision',
        sa.Column('quoted_message_author', sa.String(length=120), nullable=True),
    )
    op.add_column(
        'routing_decision',
        sa.Column('quoted_agent_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        _QUOTED_AGENT_FK,
        'routing_decision',
        'agent',
        ['quoted_agent_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint(_QUOTED_AGENT_FK, 'routing_decision', type_='foreignkey')
    op.drop_column('routing_decision', 'quoted_agent_id')
    op.drop_column('routing_decision', 'quoted_message_author')
    op.drop_column('routing_decision', 'quoted_message_text')
