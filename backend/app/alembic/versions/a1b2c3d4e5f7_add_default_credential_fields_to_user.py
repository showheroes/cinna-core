"""add_default_credential_fields_to_user

Revision ID: a1b2c3d4e5f7
Revises: f0920ee2eeab
Create Date: 2026-03-21 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = 'f0920ee2eeab'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('default_ai_credential_conversation_id', sa.Uuid(), nullable=True))
    op.add_column('user', sa.Column('default_ai_credential_building_id', sa.Uuid(), nullable=True))
    op.add_column('user', sa.Column('default_model_override_conversation', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('user', sa.Column('default_model_override_building', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_foreign_key(
        'fk_user_default_ai_credential_conversation_id',
        'user', 'ai_credential',
        ['default_ai_credential_conversation_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_user_default_ai_credential_building_id',
        'user', 'ai_credential',
        ['default_ai_credential_building_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    op.drop_constraint('fk_user_default_ai_credential_building_id', 'user', type_='foreignkey')
    op.drop_constraint('fk_user_default_ai_credential_conversation_id', 'user', type_='foreignkey')
    op.drop_column('user', 'default_model_override_building')
    op.drop_column('user', 'default_model_override_conversation')
    op.drop_column('user', 'default_ai_credential_building_id')
    op.drop_column('user', 'default_ai_credential_conversation_id')
