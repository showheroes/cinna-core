"""Add ACP connectors and hashed bearer tokens.

Revision ID: 6bdc1a2e709f
Revises: fc99da75645c
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "6bdc1a2e709f"
down_revision = "fc99da75645c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acp_connector",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("mode", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("max_connections", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('conversation', 'building')", name="ck_acp_connector_mode"
        ),
        sa.CheckConstraint(
            "max_connections BETWEEN 1 AND 100", name="ck_acp_connector_max_connections"
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agent.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_acp_connector_agent_id", "acp_connector", ["agent_id"])
    op.create_index("ix_acp_connector_owner_id", "acp_connector", ["owner_id"])
    op.create_table(
        "acp_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column(
            "token_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column(
            "prefix", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False
        ),
        sa.Column(
            "label", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["acp_connector.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_acp_token_connector_id", "acp_token", ["connector_id"])
    op.create_index("ix_acp_token_token_hash", "acp_token", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("acp_token")
    op.drop_table("acp_connector")
