#!/usr/bin/env python

"""
Test script for SQL generation functionality.

This script tests that the SQL generation works correctly with the fixed code.
"""

import asyncio
import logging
import os
import sys
from typing import Dict, Any

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.insert(0, project_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger("test_sql_generation")

# Import necessary modules
from services.llm_factory import LLMFactory
from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
from utils.base_agent import AgentInput

# Sample database schema for testing
SAMPLE_SCHEMA = """
Table: invoices
- id (int, primary key)
- user_id (int, foreign key)
- invoice_number (string)
- issue_date (date)
- due_date (date)
- vendor (string)
- total_amount (decimal)
- status (string)
- created_at (timestamp)
- updated_at (timestamp)

Table: items
- id (int, primary key)
- invoice_id (int, foreign key)
- description (string)
- quantity (int)
- unit_price (decimal)
- total_price (decimal)
- created_at (timestamp)
- updated_at (timestamp)
"""

async def test_generate_sql_from_query():
    """Test the SQL generation from a natural language query."""
    llm_factory = LLMFactory()
    
    query = "Show me all invoices from the last month"
    
    logger.info(f"Testing SQL generation for query: '{query}'")
    
    # Test the direct method
    sql_result = await llm_factory.generate_sql_from_query(
        query=query,
        db_schema=SAMPLE_SCHEMA,
        user_id=1,
        is_summary_query=False
    )
    
    logger.info(f"Generated SQL (direct):\n{sql_result}")
    
    # Test via the agent
    sql_agent = TextToSQLConversionAgent(llm_factory, SAMPLE_SCHEMA)
    
    agent_input = AgentInput(
        content=query,
        metadata={
            "user_id": 1,
            "intent": "invoice_query"
        }
    )
    
    agent_output = await sql_agent.process(agent_input)
    
    logger.info(f"Generated SQL (via agent):\n{agent_output.content}")
    logger.info(f"Agent confidence: {agent_output.confidence}")
    logger.info(f"Agent status: {agent_output.status}")
    
    return {
        "direct_sql": sql_result,
        "agent_sql": agent_output.content,
        "confidence": agent_output.confidence,
        "status": agent_output.status
    }

if __name__ == "__main__":
    logger.info("Starting SQL generation test")
    
    try:
        # Run the test
        results = asyncio.run(test_generate_sql_from_query())
        
        # Evaluate results
        if results["status"] == "success" and results["confidence"] > 0.5:
            logger.info("✅ SQL generation test PASSED")
            sys.exit(0)
        else:
            logger.error(f"❌ SQL generation test FAILED - Status: {results['status']}, Confidence: {results['confidence']}")
            logger.error(f"Agent SQL result: {results['agent_sql']}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ SQL generation test FAILED with exception: {str(e)}", exc_info=True)
        sys.exit(1) 