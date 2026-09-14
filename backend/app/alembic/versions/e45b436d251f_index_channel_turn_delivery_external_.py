"""index_channel_turn_delivery_external_message_id

Revision ID: e45b436d251f
Revises: 8ca241bf9d12
Create Date: 2026-09-14 15:26:14.371753

Indexes ``channel_turn_delivery.external_message_id``. Quote-aware channel
routing now looks a quoted message up by this id
(``ChannelTurnDeliveryLedger.platform_agent_for_message``) for every new thread
whose first message quotes something, on top of the conversation context
builder's existing join. Btree, non-unique: one external message can belong to
more than one delivery row.

Autogenerate also proposed:

- three ``cli_device_login_request`` timestamp ``alter_column``s — the known
  pre-existing drift (timezone-aware in the database, naive in the model) that
  ``1367eb81ac66`` also stripped; applying it would strip the timezone from
  live rows;
- the three ``routing_decision`` quoted-context columns, which belong to the
  next revision (``d1721ea327b6``) so each phase's schema change stands alone.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e45b436d251f'
down_revision = '8ca241bf9d12'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        op.f('ix_channel_turn_delivery_external_message_id'),
        'channel_turn_delivery',
        ['external_message_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f('ix_channel_turn_delivery_external_message_id'),
        table_name='channel_turn_delivery',
    )
