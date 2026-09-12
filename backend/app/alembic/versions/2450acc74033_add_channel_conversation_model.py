"""add_channel_conversation_model

Revision ID: 2450acc74033
Revises: 6bdc1a2e709f
Create Date: 2026-09-12 08:21:36.658113

Downgrade is valid only before multiple askers share a native thread. Restoring
the old unique key fails transactionally otherwise; no session is discarded.
reply_target preserves quote timestamps/asker attribution across worker restart.

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = "2450acc74033"
down_revision = "6bdc1a2e709f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "channel_thread_ingest_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("binding_id", sa.Uuid(), nullable=False),
        sa.Column(
            "external_message_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "source", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False
        ),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("attachment_count", sa.Integer(), nullable=False),
        sa.Column("injected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["channel_thread_binding.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "binding_id",
            "external_message_id",
            name="uq_channel_thread_ingest_log_message",
        ),
    )
    op.create_index(
        op.f("ix_channel_thread_ingest_log_binding_id"),
        "channel_thread_ingest_log",
        ["binding_id"],
        unique=False,
    )
    op.add_column(
        "channel_thread_binding",
        sa.Column(
            "scope_key", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True
        ),
    )
    op.add_column(
        "channel_thread_binding",
        sa.Column(
            "conversation_key",
            sqlmodel.sql.sqltypes.AutoString(length=512),
            nullable=True,
        ),
    )
    op.add_column(
        "channel_thread_binding",
        sa.Column(
            "conversation_kind",
            sqlmodel.sql.sqltypes.AutoString(length=16),
            nullable=True,
        ),
    )
    op.add_column(
        "channel_thread_binding",
        sa.Column(
            "last_reply_mode",
            sqlmodel.sql.sqltypes.AutoString(length=24),
            nullable=True,
        ),
    )
    op.add_column(
        "channel_thread_binding",
        sa.Column("history_backfilled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "channel_thread_binding", sa.Column("reply_target", sa.JSON(), nullable=True)
    )
    op.execute("UPDATE channel_thread_binding SET scope_key = thread_key")
    op.alter_column("channel_thread_binding", "scope_key", nullable=False)
    op.drop_constraint(
        op.f("uq_channel_thread_binding_thread"),
        "channel_thread_binding",
        type_="unique",
    )
    op.create_index(
        op.f("ix_channel_thread_binding_conversation_key"),
        "channel_thread_binding",
        ["conversation_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_thread_binding_scope_key"),
        "channel_thread_binding",
        ["scope_key"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_channel_thread_binding_scope",
        "channel_thread_binding",
        ["server_channel_id", "scope_key", "user_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_channel_thread_binding_scope", "channel_thread_binding", type_="unique"
    )
    op.drop_index(
        op.f("ix_channel_thread_binding_scope_key"), table_name="channel_thread_binding"
    )
    op.drop_index(
        op.f("ix_channel_thread_binding_conversation_key"),
        table_name="channel_thread_binding",
    )
    op.create_unique_constraint(
        op.f("uq_channel_thread_binding_thread"),
        "channel_thread_binding",
        ["server_channel_id", "thread_key"],
        postgresql_nulls_not_distinct=False,
    )
    op.drop_column("channel_thread_binding", "reply_target")
    op.drop_column("channel_thread_binding", "history_backfilled_at")
    op.drop_column("channel_thread_binding", "last_reply_mode")
    op.drop_column("channel_thread_binding", "conversation_kind")
    op.drop_column("channel_thread_binding", "conversation_key")
    op.drop_column("channel_thread_binding", "scope_key")
    op.drop_index(
        op.f("ix_channel_thread_ingest_log_binding_id"),
        table_name="channel_thread_ingest_log",
    )
    op.drop_table("channel_thread_ingest_log")
