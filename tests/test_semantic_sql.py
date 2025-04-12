import logging
import sys
import json
import time
import asyncio
from pathlib import Path

# Add the parent directory to sys.path to allow imports
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils.logging import get_logs_directory
from services.llm_factory import LLMFactory
from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
from utils.vector_utils import generate_embedding_for_text

# Configure logging
logs_dir = get_logs_directory()
log_file = str(logs_dir / "semantic_sql_test.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("test_semantic_sql")

def get_db_schema():
    """Get the database schema from fixtures or directly."""
    try:
        from tests.fixtures.db_schema import DB_SCHEMA
        return DB_SCHEMA
    except ImportError:
        try:
            # Try to load from a file
            schema_path = Path(__file__).parent / "fixtures" / "db_schema.py"
            if schema_path.exists():
                with open(schema_path, "r") as f:
                    content = f.read()
                    # Extract DB_SCHEMA
                    start = content.find("DB_SCHEMA = \"\"\"")
                    end = content.find("\"\"\"", start + 15)
                    if start > 0 and end > 0:
                        return content[start+15:end]
        except Exception as e:
            logger.warning(f"Could not load schema from file: {e}")
            
        # Return a minimal schema if all else fails
        return """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    whatsapp_number VARCHAR(20) UNIQUE,
    name VARCHAR(100),
    email VARCHAR(100)
);

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    invoice_number VARCHAR(50),
    vendor VARCHAR(100),
    invoice_date DATE,
    total_amount DECIMAL(10, 2)
);

CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    description TEXT,
    quantity DECIMAL(10, 2),
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2),
    description_embedding VECTOR(1536)
);

CREATE TABLE invoice_embeddings (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    user_id INTEGER REFERENCES users(id),
    content_text TEXT,
    embedding VECTOR(1536)
);
"""

async def test_semantic_sql_generation():
    """Test SQL generation with semantic search enabled."""
    logger.info("Starting semantic SQL generation test")

    # Initialize LLM factory
    llm_factory = LLMFactory()

    # Get database schema
    db_schema = get_db_schema()

    # Initialize the text to SQL conversion agent
    sql_agent = TextToSQLConversionAgent(llm_factory, db_schema)

    # Test queries
    queries = [
        "What coffee or latte have I bought recently?",
        "Find invoices about beverages"
    ]

    passed = True

    for query in queries:
        logger.info(f"Testing semantic SQL generation for query: '{query}'")

        # First, test direct SQL generation with semantic search
        start_time = time.time()
        
        # Generate SQL directly with semantic search enabled
        direct_sql = await llm_factory.generate_sql_from_query(
            query=query,
            db_schema=db_schema,
            user_id="1",
            is_semantic_search=True
        )
        
        # Check if the SQL contains correct pgvector syntax
        if "'[:query_embedding]'::vector" in direct_sql:
            pgvector_syntax_correct = True
            logger.info("✅ Direct SQL generation uses correct pgvector syntax")
        else:
            pgvector_syntax_correct = False
            passed = False
            logger.error("❌ Direct SQL generation does not use correct pgvector syntax")
            
        direct_time = time.time() - start_time
        logger.info(f"Direct SQL generation time: {direct_time:.2f} seconds")
        logger.info(f"Generated SQL (direct):\n```sql\n{direct_sql}\n```")

        # Now test the SQL agent
        start_time = time.time()
        
        # Create test input for the agent
        test_input = {
            "content": query,
            "metadata": {
                "user_id": "1",
                "intent": "invoice_query",
                "use_semantic_search": True
            }
        }
        
        # Process the query using the agent
        agent_result = await sql_agent.process(test_input)
        agent_time = time.time() - start_time
        
        # Print the agent's SQL and confidence
        agent_sql = agent_result.content if agent_result else "Failed to generate SQL"
        agent_confidence = agent_result.confidence if agent_result else 0
        agent_status = agent_result.status if agent_result else "error"
        
        logger.info(f"Agent SQL generation time: {agent_time:.2f} seconds")
        logger.info(f"Generated SQL (via agent):\n{agent_sql}")
        logger.info(f"Agent confidence: {agent_confidence}")
        logger.info(f"Agent status: {agent_status}")
        
        # Validate that the SQL contains the correct vector search syntax
        if "'[:query_embedding]'::vector" in agent_sql:
            logger.info("✅ Agent SQL generation uses correct pgvector syntax")
        else:
            passed = False
            logger.error("❌ Agent SQL generation does not use correct pgvector syntax")
            
        # Check for to_vector function (shouldn't be present)
        if "to_vector" in agent_sql.lower():
            passed = False
            logger.error("❌ SQL still contains incorrect to_vector function")
        else:
            logger.info("✅ SQL does not contain incorrect to_vector function")
            
        logger.info("-----------------------------------------------------------")

    # Final result
    if passed:
        logger.info("✅ Semantic SQL generation test PASSED")
        return 0
    else:
        logger.error("❌ Semantic SQL generation test FAILED")
        return 1

if __name__ == "__main__":
    # Run the async test function
    result = asyncio.run(test_semantic_sql_generation())
    sys.exit(result) 