"""Add vector embeddings to items table

Revision ID: 8fa9e4d52bc7
Revises: 455b03be74ff
Create Date: 2024-10-06

"""
from alembic import op
import sqlalchemy as sa
import logging

# Try to import VECTOR, use fallback if not available
try:
    from sqlalchemy.dialects.postgresql import VECTOR
    has_pgvector = True
except ImportError:
    # Define a fallback TEXT type for compatibility
    has_pgvector = False
    logging.warning("pgvector not installed, migrations will use TEXT as fallback")

# revision identifiers, used by Alembic.
revision = '8fa9e4d52bc7'
down_revision = '455b03be74ff'
branch_labels = None
depends_on = None


def upgrade():
    # Try to install pgvector extension if it doesn't exist
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
        logging.info("Vector extension installed successfully")
        pgvector_installed = True
    except Exception as e:
        logging.warning(f"Could not install pgvector extension: {str(e)}")
        pgvector_installed = False
    
    # Add embedding column, using appropriate type based on availability
    if pgvector_installed and has_pgvector:
        # Use real VECTOR type
        op.add_column('items', sa.Column('description_embedding', VECTOR(1536), nullable=True))
        
        # Create an index for vector similarity search
        op.execute(
            'CREATE INDEX items_description_embedding_idx ON items USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100)'
        )
        logging.info("Vector column and index created successfully")
    else:
        # Use TEXT as a fallback
        op.add_column('items', sa.Column('description_embedding', sa.Text(), nullable=True))
        logging.warning("Added TEXT column as fallback for vector embeddings")


def downgrade():
    # Try to remove the index if it exists
    try:
        op.execute('DROP INDEX IF EXISTS items_description_embedding_idx')
    except Exception as e:
        logging.warning(f"Could not drop vector index: {str(e)}")
    
    # Remove the column
    op.drop_column('items', 'description_embedding')
    logging.info("Vector column removed successfully") 