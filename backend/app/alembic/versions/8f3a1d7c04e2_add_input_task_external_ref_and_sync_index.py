"""add input_task.external_ref and the owner/updated_at sync index

Two columns' worth of support for external clients that mirror cinna tasks
(the desktop app is the first).

``external_ref`` is a caller-supplied idempotency key — the client's own id for
its local task. The partial unique index on ``(owner_id, external_ref) WHERE
external_ref IS NOT NULL`` is what makes the guarantee real: a create retried
after a lost response returns the first task instead of making a second one,
and two owners may independently use the same ref. It is partial because the
overwhelming majority of tasks (everything created on the web) have no ref, and
those must not collide with each other.

``ix_input_task_owner_updated`` backs the ``updated_since`` cursor on
``GET /tasks/``: an incremental pull filters ``updated_at >`` and orders by it
ascending, which is an index scan only if the index exists. Without it every
polling device sequentially scans that owner's tasks.

DOWNGRADE: dropping ``external_ref`` loses the binding between local client
tasks and their cinna counterparts. Clients fall back to re-binding by title,
and a retried create can duplicate again.

Revision ID: 8f3a1d7c04e2
Revises: 562ac5a89f04
Create Date: 2026-09-11 10:12:44.109233

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = '8f3a1d7c04e2'
down_revision = '562ac5a89f04'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'input_task',
        sa.Column(
            'external_ref',
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_input_task_owner_external_ref',
        'input_task',
        ['owner_id', 'external_ref'],
        unique=True,
        postgresql_where=sa.text('external_ref IS NOT NULL'),
    )
    op.create_index(
        'ix_input_task_owner_updated',
        'input_task',
        ['owner_id', 'updated_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_input_task_owner_updated', table_name='input_task')
    op.drop_index(
        'ix_input_task_owner_external_ref',
        table_name='input_task',
        postgresql_where=sa.text('external_ref IS NOT NULL'),
    )
    op.drop_column('input_task', 'external_ref')
