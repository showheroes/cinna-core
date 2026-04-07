"""add_task_sequence_counter_to_user_and_task_prefix_to_team

Revision ID: ff3bdb6d86a6
Revises: e8c9e80a2914
Create Date: 2026-04-01 10:47:35.425932

Phase A of task-based-agent-collaboration feature:
- Create task_status_history, task_comment, task_attachment tables
- Add task_prefix to agentic_team
- Add collaboration columns to input_task (short_code, title, priority, hierarchy, team refs)
- Add task_sequence_counter to user
- Data migration: backfill short_code for existing tasks; migrate running→in_progress, pending_input→blocked
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'ff3bdb6d86a6'
down_revision = 'e8c9e80a2914'
branch_labels = None
depends_on = None


def upgrade():
    # Create task_status_history table
    op.create_table(
        'task_status_history',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('from_status', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column('to_status', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column('changed_by_agent_id', sa.Uuid(), nullable=True),
        sa.Column('changed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['changed_by_agent_id'], ['agent.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['input_task.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_task_status_history_task_id', 'task_status_history', ['task_id'], unique=False)

    # Create task_comment table
    op.create_table(
        'task_comment',
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(length=10000), nullable=False),
        sa.Column('comment_type', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('author_node_id', sa.Uuid(), nullable=True),
        sa.Column('author_agent_id', sa.Uuid(), nullable=True),
        sa.Column('author_user_id', sa.Uuid(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['author_agent_id'], ['agent.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['author_node_id'], ['agentic_team_node.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['author_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['input_task.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_task_comment_task_id', 'task_comment', ['task_id'], unique=False)

    # Create task_attachment table
    op.create_table(
        'task_attachment',
        sa.Column('file_name', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('content_type', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('comment_id', sa.Uuid(), nullable=True),
        sa.Column('file_path', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('uploaded_by_agent_id', sa.Uuid(), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('source_agent_id', sa.Uuid(), nullable=True),
        sa.Column('source_workspace_path', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['task_comment.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_agent_id'], ['agent.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['input_task.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_agent_id'], ['agent.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_task_attachment_comment_id', 'task_attachment', ['comment_id'], unique=False)
    op.create_index('ix_task_attachment_task_id', 'task_attachment', ['task_id'], unique=False)

    # Add task_prefix to agentic_team
    op.add_column('agentic_team', sa.Column('task_prefix', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True))

    # Add collaboration columns to input_task (initially nullable for data migration)
    op.add_column('input_task', sa.Column('short_code', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True))
    op.add_column('input_task', sa.Column('sequence_number', sa.Integer(), nullable=True))
    op.add_column('input_task', sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.add_column('input_task', sa.Column('priority', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True))
    op.add_column('input_task', sa.Column('parent_task_id', sa.Uuid(), nullable=True))
    op.add_column('input_task', sa.Column('team_id', sa.Uuid(), nullable=True))
    op.add_column('input_task', sa.Column('assigned_node_id', sa.Uuid(), nullable=True))
    op.add_column('input_task', sa.Column('created_by_node_id', sa.Uuid(), nullable=True))

    # Add new indexes
    op.create_index('ix_input_task_assigned_node_id', 'input_task', ['assigned_node_id'], unique=False)
    op.create_index('ix_input_task_parent_task_id', 'input_task', ['parent_task_id'], unique=False)
    op.create_index('ix_input_task_team_id', 'input_task', ['team_id'], unique=False)

    # Add FK constraints
    op.create_foreign_key(
        'fk_input_task_created_by_node_id', 'input_task', 'agentic_team_node',
        ['created_by_node_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_input_task_assigned_node_id', 'input_task', 'agentic_team_node',
        ['assigned_node_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_input_task_parent_task_id', 'input_task', 'input_task',
        ['parent_task_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_input_task_team_id', 'input_task', 'agentic_team',
        ['team_id'], ['id'], ondelete='SET NULL'
    )

    # Add task_sequence_counter to user (with default 0)
    op.add_column('user', sa.Column('task_sequence_counter', sa.Integer(), nullable=True))
    op.execute("UPDATE \"user\" SET task_sequence_counter = 0 WHERE task_sequence_counter IS NULL")
    op.alter_column('user', 'task_sequence_counter', nullable=False)

    # ── Data migrations ────────────────────────────────────────────────────────

    # 1. Set default priority for existing tasks
    op.execute("UPDATE input_task SET priority = 'normal' WHERE priority IS NULL")
    op.alter_column('input_task', 'priority', nullable=False, server_default='normal')

    # 2. Migrate old statuses: running → in_progress, pending_input → blocked
    op.execute("UPDATE input_task SET status = 'in_progress' WHERE status = 'running'")
    op.execute("UPDATE input_task SET status = 'blocked' WHERE status = 'pending_input'")

    # 3. Backfill short_code and sequence_number for existing tasks
    #    For each user, iterate tasks in created_at order and assign TASK-1, TASK-2, etc.
    #    Then update the user's task_sequence_counter to the count.
    op.execute("""
        WITH ranked_tasks AS (
            SELECT
                id,
                owner_id,
                ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY created_at ASC) AS seq
            FROM input_task
        )
        UPDATE input_task
        SET
            sequence_number = ranked_tasks.seq,
            short_code = 'TASK-' || ranked_tasks.seq::text
        FROM ranked_tasks
        WHERE input_task.id = ranked_tasks.id
    """)

    # 4. Update each user's task_sequence_counter to match number of tasks assigned
    op.execute("""
        UPDATE "user"
        SET task_sequence_counter = COALESCE(task_counts.cnt, 0)
        FROM (
            SELECT owner_id, COUNT(*) AS cnt
            FROM input_task
            GROUP BY owner_id
        ) AS task_counts
        WHERE "user".id = task_counts.owner_id
    """)

    # Note: unique index on short_code intentionally not created - not needed


def downgrade():
    op.drop_constraint('fk_input_task_team_id', 'input_task', type_='foreignkey')
    op.drop_constraint('fk_input_task_parent_task_id', 'input_task', type_='foreignkey')
    op.drop_constraint('fk_input_task_assigned_node_id', 'input_task', type_='foreignkey')
    op.drop_constraint('fk_input_task_created_by_node_id', 'input_task', type_='foreignkey')

    op.drop_index('ix_input_task_team_id', table_name='input_task')
    op.drop_index('ix_input_task_parent_task_id', table_name='input_task')
    op.drop_index('ix_input_task_assigned_node_id', table_name='input_task')

    op.drop_column('input_task', 'created_by_node_id')
    op.drop_column('input_task', 'assigned_node_id')
    op.drop_column('input_task', 'team_id')
    op.drop_column('input_task', 'parent_task_id')
    op.drop_column('input_task', 'priority')
    op.drop_column('input_task', 'title')
    op.drop_column('input_task', 'sequence_number')
    op.drop_column('input_task', 'short_code')

    op.drop_column('agentic_team', 'task_prefix')

    op.drop_index('ix_task_attachment_task_id', table_name='task_attachment')
    op.drop_index('ix_task_attachment_comment_id', table_name='task_attachment')
    op.drop_table('task_attachment')

    op.drop_index('ix_task_comment_task_id', table_name='task_comment')
    op.drop_table('task_comment')

    op.drop_index('ix_task_status_history_task_id', table_name='task_status_history')
    op.drop_table('task_status_history')

    op.drop_column('user', 'task_sequence_counter')
