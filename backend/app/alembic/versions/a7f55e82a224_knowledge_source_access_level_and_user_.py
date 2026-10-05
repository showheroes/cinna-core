"""knowledge source access level and user shares

Knowledge sources become server-wide, admin-managed resources:
- ``public_discovery`` (bool) is replaced by ``access_level``
  (private | public | shared); backfill True -> public, False -> private.
- New ``ai_knowledge_git_repo_user_shares`` link table (source <-> user) for
  the ``shared`` level.
- Workspace scoping (``workspace_access_type`` + ``ai_knowledge_git_repo_workspaces``)
  is dropped: it scoped a source to the creating admin's own workspaces, which
  has no meaning for server-wide sources.
- ``user_id`` (creator) becomes nullable with ON DELETE SET NULL, so deleting
  the creating admin no longer deletes server-wide sources.
- Dead ``user_enabled_discoverable_sources`` table is dropped.
- ``ssh_key_id`` FK gets ON DELETE SET NULL, DEFERRABLE INITIALLY DEFERRED,
  so deleting an admin (which cascades their SSH keys) does not fail on sources
  using their key. Deferred because an admin who is both creator and key owner
  reaches the source row via two cascade paths, and an immediate check on the
  intermediate row version fails.

Downgrade is lossy:
- Knowledge sources whose creator was deleted (``user_id IS NULL``) are
  deleted, because ``user_id`` returns to NOT NULL + CASCADE.
- Shared-user grants (``ai_knowledge_git_repo_user_shares``) are dropped;
  ``shared`` sources come back as ``public_discovery = false``.
- Workspace grants dropped by the upgrade are not restored; every source comes
  back with ``workspace_access_type = 'all'``.

Revision ID: a7f55e82a224
Revises: dc920creds01
Create Date: 2026-09-28 09:19:59.221444

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a7f55e82a224'
down_revision = 'dc920creds01'
branch_labels = None
depends_on = None


access_level_enum = postgresql.ENUM(
    'private', 'public', 'shared', name='knowledgesourceaccesslevel'
)
workspace_access_enum = postgresql.ENUM('all', 'specific', name='workspaceaccesstype')


def upgrade():
    # 1. Share link table
    op.create_table(
        'ai_knowledge_git_repo_user_shares',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('git_repo_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['git_repo_id'], ['ai_knowledge_git_repo.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('git_repo_id', 'user_id', name='uq_knowledge_repo_user_share'),
    )
    op.create_index(op.f('ix_ai_knowledge_git_repo_user_shares_git_repo_id'), 'ai_knowledge_git_repo_user_shares', ['git_repo_id'], unique=False)
    op.create_index(op.f('ix_ai_knowledge_git_repo_user_shares_user_id'), 'ai_knowledge_git_repo_user_shares', ['user_id'], unique=False)

    # 2. access_level replaces public_discovery (with backfill)
    access_level_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'ai_knowledge_git_repo',
        sa.Column('access_level', access_level_enum, nullable=False, server_default='private'),
    )
    op.execute(
        "UPDATE ai_knowledge_git_repo SET access_level = 'public' WHERE public_discovery IS TRUE"
    )
    op.alter_column('ai_knowledge_git_repo', 'access_level', server_default=None)
    op.create_index(op.f('ix_ai_knowledge_git_repo_access_level'), 'ai_knowledge_git_repo', ['access_level'], unique=False)
    op.drop_index(op.f('ix_ai_knowledge_git_repo_public_discovery'), table_name='ai_knowledge_git_repo')
    op.drop_column('ai_knowledge_git_repo', 'public_discovery')

    # 3. Drop workspace scoping
    op.drop_index(op.f('idx_git_repo_workspace_unique'), table_name='ai_knowledge_git_repo_workspaces')
    op.drop_index(op.f('ix_ai_knowledge_git_repo_workspaces_git_repo_id'), table_name='ai_knowledge_git_repo_workspaces')
    op.drop_index(op.f('ix_ai_knowledge_git_repo_workspaces_user_workspace_id'), table_name='ai_knowledge_git_repo_workspaces')
    op.drop_table('ai_knowledge_git_repo_workspaces')
    op.drop_column('ai_knowledge_git_repo', 'workspace_access_type')
    workspace_access_enum.drop(op.get_bind(), checkfirst=True)

    # 4. Creator FK: CASCADE -> SET NULL, nullable
    op.drop_constraint('ai_knowledge_git_repo_user_id_fkey', 'ai_knowledge_git_repo', type_='foreignkey')
    op.alter_column('ai_knowledge_git_repo', 'user_id', existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key(
        'ai_knowledge_git_repo_user_id_fkey', 'ai_knowledge_git_repo', 'user',
        ['user_id'], ['id'], ondelete='SET NULL',
    )
    op.drop_constraint('ai_knowledge_git_repo_ssh_key_id_fkey', 'ai_knowledge_git_repo', type_='foreignkey')
    op.create_foreign_key(
        'ai_knowledge_git_repo_ssh_key_id_fkey', 'ai_knowledge_git_repo', 'user_ssh_keys',
        ['ssh_key_id'], ['id'], ondelete='SET NULL',
        deferrable=True, initially='DEFERRED',
    )

    # 5. Drop dead discoverable-sources link table
    op.drop_index(op.f('ix_user_enabled_discoverable_sources_git_repo_id'), table_name='user_enabled_discoverable_sources')
    op.drop_index(op.f('ix_user_enabled_discoverable_sources_user_id'), table_name='user_enabled_discoverable_sources')
    op.drop_index('idx_user_source_unique', table_name='user_enabled_discoverable_sources')
    op.drop_table('user_enabled_discoverable_sources')


def downgrade():
    # 5. Recreate discoverable-sources link table (empty)
    op.create_table(
        'user_enabled_discoverable_sources',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('git_repo_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['git_repo_id'], ['ai_knowledge_git_repo.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_user_source_unique', 'user_enabled_discoverable_sources', ['user_id', 'git_repo_id'], unique=True)
    op.create_index(op.f('ix_user_enabled_discoverable_sources_user_id'), 'user_enabled_discoverable_sources', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_enabled_discoverable_sources_git_repo_id'), 'user_enabled_discoverable_sources', ['git_repo_id'], unique=False)

    # 4. Creator FK back to NOT NULL + CASCADE. Orphaned sources (creator
    #    deleted) cannot satisfy NOT NULL and are removed, matching the old
    #    cascade semantics.
    op.execute("DELETE FROM ai_knowledge_git_repo WHERE user_id IS NULL")
    op.drop_constraint('ai_knowledge_git_repo_user_id_fkey', 'ai_knowledge_git_repo', type_='foreignkey')
    op.alter_column('ai_knowledge_git_repo', 'user_id', existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key(
        'ai_knowledge_git_repo_user_id_fkey', 'ai_knowledge_git_repo', 'user',
        ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.drop_constraint('ai_knowledge_git_repo_ssh_key_id_fkey', 'ai_knowledge_git_repo', type_='foreignkey')
    op.create_foreign_key(
        'ai_knowledge_git_repo_ssh_key_id_fkey', 'ai_knowledge_git_repo', 'user_ssh_keys',
        ['ssh_key_id'], ['id'],
    )

    # 3. Restore workspace scoping (all sources back to "all"; specific grants are lost)
    workspace_access_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'ai_knowledge_git_repo',
        sa.Column('workspace_access_type', workspace_access_enum, nullable=False, server_default='all'),
    )
    op.alter_column('ai_knowledge_git_repo', 'workspace_access_type', server_default=None)
    op.create_table(
        'ai_knowledge_git_repo_workspaces',
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('git_repo_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('user_workspace_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['git_repo_id'], ['ai_knowledge_git_repo.id'], name=op.f('ai_knowledge_git_repo_workspaces_git_repo_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_workspace_id'], ['user_workspace.id'], name=op.f('ai_knowledge_git_repo_workspaces_user_workspace_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('ai_knowledge_git_repo_workspaces_pkey')),
    )
    op.create_index(op.f('ix_ai_knowledge_git_repo_workspaces_user_workspace_id'), 'ai_knowledge_git_repo_workspaces', ['user_workspace_id'], unique=False)
    op.create_index(op.f('ix_ai_knowledge_git_repo_workspaces_git_repo_id'), 'ai_knowledge_git_repo_workspaces', ['git_repo_id'], unique=False)
    op.create_index(op.f('idx_git_repo_workspace_unique'), 'ai_knowledge_git_repo_workspaces', ['git_repo_id', 'user_workspace_id'], unique=True)

    # 2. Restore public_discovery (public -> True; private and shared -> False)
    op.add_column(
        'ai_knowledge_git_repo',
        sa.Column('public_discovery', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    )
    op.execute(
        "UPDATE ai_knowledge_git_repo SET public_discovery = TRUE WHERE access_level = 'public'"
    )
    op.create_index(op.f('ix_ai_knowledge_git_repo_public_discovery'), 'ai_knowledge_git_repo', ['public_discovery'], unique=False)
    op.drop_index(op.f('ix_ai_knowledge_git_repo_access_level'), table_name='ai_knowledge_git_repo')
    op.drop_column('ai_knowledge_git_repo', 'access_level')
    access_level_enum.drop(op.get_bind(), checkfirst=True)

    # 1. Drop share link table
    op.drop_index(op.f('ix_ai_knowledge_git_repo_user_shares_user_id'), table_name='ai_knowledge_git_repo_user_shares')
    op.drop_index(op.f('ix_ai_knowledge_git_repo_user_shares_git_repo_id'), table_name='ai_knowledge_git_repo_user_shares')
    op.drop_table('ai_knowledge_git_repo_user_shares')
