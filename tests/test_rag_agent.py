import logging
import sys
import time
import asyncio
from pathlib import Path

# Add the parent directory to sys.path to allow imports
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import utilities and agents
from utils.logging import get_logs_directory
from agents.invoice_rag_agent import InvoiceRAGAgent
from utils.vector_utils import get_embedding_generator

# Configure logging
logs_dir = get_logs_directory()
log_file = str(logs_dir / "rag_agent_test.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("test_rag_agent")

async def test_rag_agent_async():
    """Test the InvoiceRAGAgent with a sample query."""
    logger.info("=== TESTING RAG AGENT ===")
    
    # Start timer
    start_time = time.time()
    
    # Create an instance of the RAG agent
    rag_agent = InvoiceRAGAgent()
    
    # Define a test query
    test_query = "When did I last have coffee?"
    test_user_id = 0  # Test user ID
    
    try:
        # Execute the RAG search
        logger.info(f"Executing RAG search with query: '{test_query}'")
        result = await rag_agent.process(test_query, test_user_id)
        
        # Log execution time
        execution_time = time.time() - start_time
        logger.info(f"RAG search completed in {execution_time:.2f} seconds")
        
        # Check results
        success = result.get("success", False)
        results_list = result.get("results", [])
        result_count = len(results_list)
        
        logger.info(f"Search success: {success}")
        logger.info(f"Results found: {result_count}")
        
        # Print the results
        if success and result_count > 0:
            logger.info("Top results:")
            for i, item in enumerate(results_list[:3]):  # Show top 3 results
                logger.info(f"Result {i+1}:")
                for key, value in item.items():
                    logger.info(f"  {key}: {value}")
        elif not success:
            logger.error(f"Search failed with error: {result.get('error', 'Unknown error')}")
        
        # Return success/failure code
        return 0 if success and result_count > 0 else 1
        
    except Exception as e:
        logger.error(f"Error during RAG test: {str(e)}", exc_info=True)
        return 1

def test_rag_agent():
    """Wrapper function to run the async test using asyncio."""
    exit_code = asyncio.run(test_rag_agent_async())
    logger.info(f"Test completed with exit code: {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    test_rag_agent() 