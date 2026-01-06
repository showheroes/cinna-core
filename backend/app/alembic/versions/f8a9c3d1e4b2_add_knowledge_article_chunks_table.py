"""add knowledge article chunks table

Revision ID: f8a9c3d1e4b2
Revises: a52c4af4a9e5
Create Date: 2026-01-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'f8a9c3d1e4b2'
down_revision = 'a52c4af4a9e5'
branch_labels = None
depends_on = None


def upgrade():
    # Create knowledge_article_chunks table
    op.create_table('knowledge_article_chunks',
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('embedding_model', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('article_id', sa.Uuid(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['knowledge_articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_chunk_article_idx_unique', 'knowledge_article_chunks', ['article_id', 'chunk_index'], unique=True)
    op.create_index('idx_chunks_article', 'knowledge_article_chunks', ['article_id'], unique=False)
    op.create_index('idx_chunks_model', 'knowledge_article_chunks', ['embedding_model'], unique=False)
    op.create_index(op.f('ix_knowledge_article_chunks_article_id'), 'knowledge_article_chunks', ['article_id'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_knowledge_article_chunks_article_id'), table_name='knowledge_article_chunks')
    op.drop_index('idx_chunks_model', table_name='knowledge_article_chunks')
    op.drop_index('idx_chunks_article', table_name='knowledge_article_chunks')
    op.drop_index('idx_chunk_article_idx_unique', table_name='knowledge_article_chunks')

    # Drop table
    op.drop_table('knowledge_article_chunks')
