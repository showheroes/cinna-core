"""add_channel_routing_clarification

Revision ID: 32563e0d9399
Revises: d1721ea327b6
Create Date: 2026-09-14 20:34:59.784330

Adds ``channel_routing_clarification``: the open clarifying question the channel
router asked one sender (channel routing guidance, clarification round-trip).
One row per ``(server_channel_id, scope_key, user_id)``, the binding key, holding
the options offered and the original message in the parked-message entry shape.
Both foreign keys cascade, so deleting the channel or the user removes the
question. ``expires_at`` is indexed for the pending-binding tick's purge.

The rows are short-lived conversational state (TTL
``CHANNEL_ROUTING_CLARIFY_TTL_MINUTES``), so the downgrade simply drops them.

Autogenerate also proposed the three ``cli_device_login_request`` timestamp
``alter_column``s — the known pre-existing drift (timezone-aware in the
database, naive in the model) that ``1367eb81ac66`` and ``e45b436d251f`` also
stripped; applying it would strip the timezone from live rows.
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = '32563e0d9399'
down_revision = 'd1721ea327b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'channel_routing_clarification',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('server_channel_id', sa.Uuid(), nullable=False),
        sa.Column('scope_key', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('thread_key', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column('conversation_key', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column('conversation_kind', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True),
        sa.Column('options', sa.JSON(), nullable=False),
        sa.Column('message', sa.JSON(), nullable=False),
        sa.Column('status_message_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['server_channel_id'],
            ['server_channel.id'],
            name='fk_channel_routing_clarification_server_channel_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['user.id'],
            name='fk_channel_routing_clarification_user_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'server_channel_id',
            'scope_key',
            'user_id',
            name='uq_channel_routing_clarification_scope',
        ),
    )
    op.create_index(
        op.f('ix_channel_routing_clarification_expires_at'),
        'channel_routing_clarification',
        ['expires_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_channel_routing_clarification_user_id'),
        'channel_routing_clarification',
        ['user_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f('ix_channel_routing_clarification_user_id'),
        table_name='channel_routing_clarification',
    )
    op.drop_index(
        op.f('ix_channel_routing_clarification_expires_at'),
        table_name='channel_routing_clarification',
    )
    op.drop_table('channel_routing_clarification')
