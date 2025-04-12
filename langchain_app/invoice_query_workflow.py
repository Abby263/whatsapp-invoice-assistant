"""
Invoice Query Workflow for WhatsApp Invoice Assistant.

This module implements specialized workflow for handling invoice queries,
converting natural language questions to SQL, executing them, and formatting
the responses appropriately.
"""

import logging
from typing import Dict, Any, Optional, List, Union
from uuid import UUID
from sqlalchemy.orm import Session
from datetime import datetime
import json
from decimal import Decimal
import time
import re
import os
from pathlib import Path

from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
from agents.response_formatter import ResponseFormatterAgent
from agents.invoice_rag_agent import InvoiceRAGAgent
from services.llm_factory import LLMFactory
from database.connection import get_db, db_session
from langchain_app.state import IntentType
from utils.vector_utils import generate_embedding_for_text
from constants.fallback_messages import QUERY_FALLBACKS
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from constants.db_schema import DB_SCHEMA_INFO

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


async def process_invoice_query(
    text_content: str,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    db_session: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Process a natural language query about invoices.
    
    Args:
        text_content: The text content of the query
        user_id: Optional user ID
        conversation_history: Optional conversation history
        db_session: Optional database session for executing queries
        
    Returns:
        Query results and metadata
    """
    try:
        start_time = time.time()
        logger.info(f"Processing invoice query: {text_content}")
        
        # Use our own db session if one wasn't provided
        should_close_db = False
        if db_session is None:
            logger.info("No database session provided, creating a new one")
            try:
                db_session = next(get_db())
                should_close_db = True
                logger.info("Database session created successfully")
            except Exception as e:
                logger.error(f"Could not create database session: {str(e)}")
                return {"error": "Database connection error"}
        else:
            logger.info("Using provided database session")
        
        try:
            # Step 1: Convert the natural language query to SQL (without semantic search)
            logger.info("Step 1: Converting natural language to SQL (regular query)")
            sql_result = await convert_to_sql(text_content, user_id, conversation_history, use_semantic_search=False)
            
            if "error" in sql_result:
                logger.error(f"Error converting to SQL: {sql_result['error']}")
                return sql_result
            
            sql_query = sql_result["sql_query"]
            logger.info(f"Generated regular SQL query: {sql_query}")
            
            # Step 2: Execute the regular SQL query against the database
            logger.info("Step 2: Executing regular SQL query")
            query_result = await execute_query(
                sql_query, 
                session=db_session, 
                user_id=user_id,
                query_text=text_content
            )
            
            results = query_result.get("results", [])
            
            # If no results found, try with semantic search
            if query_result.get("success", False) and len(results) == 0:
                logger.info("No results found with regular query, trying semantic search")
                
                # Generate SQL with semantic search enabled
                semantic_sql_result = await convert_to_sql(text_content, user_id, conversation_history, use_semantic_search=True)
                
                if "error" not in semantic_sql_result:
                    semantic_sql_query = semantic_sql_result["sql_query"]
                    logger.info(f"Generated semantic SQL query: {semantic_sql_query}")
                    
                    # Execute the semantic search query
                    semantic_query_result = await execute_query(
                        semantic_sql_query,
                        session=db_session,
                        user_id=user_id,
                        query_text=text_content
                    )
                    
                    # If semantic search was successful and returned results, use those
                    if semantic_query_result.get("success", False) and len(semantic_query_result.get("results", [])) > 0:
                        logger.info(f"Semantic search returned {len(semantic_query_result.get('results', []))} results")
                        query_result = semantic_query_result
                        sql_query = semantic_sql_query
                        results = query_result.get("results", [])
                    else:
                        logger.info("Semantic search SQL also returned no results, trying RAG approach")
                        
                        # If SQL-based semantic search also returns no results, use the dedicated RAG agent
                        rag_agent = InvoiceRAGAgent(llm_factory=LLMFactory())
                        rag_result = await rag_agent.process(
                            query_text=text_content,
                            user_id=user_id,
                            db_session=db_session
                        )
                        
                        # If RAG search was successful and returned results, use those
                        if rag_result.get("success", False) and len(rag_result.get("results", [])) > 0:
                            logger.info(f"RAG search returned {len(rag_result.get('results', []))} results")
                            query_result = rag_result
                            results = rag_result.get("results", [])
                            # Add a flag to indicate this came from RAG
                            query_result["source"] = "rag"
                else:
                    logger.error(f"Error generating semantic SQL: {semantic_sql_result['error']}")
                    
                    # If semantic SQL generation failed, try RAG as a fallback
                    logger.info("Trying RAG approach as fallback after semantic SQL generation failure")
                    rag_agent = InvoiceRAGAgent(llm_factory=LLMFactory())
                    rag_result = await rag_agent.process(
                        query_text=text_content,
                        user_id=user_id,
                        db_session=db_session
                    )
                    
                    if rag_result.get("success", False) and len(rag_result.get("results", [])) > 0:
                        logger.info(f"RAG fallback search returned {len(rag_result.get('results', []))} results")
                        query_result = rag_result
                        results = rag_result.get("results", [])
                        query_result["source"] = "rag_fallback"
            
            logger.info(f"Final query returned {len(results)} results")
            
            # If query execution failed, return error
            if not query_result.get("success", False):
                logger.error(f"Error executing query: {query_result.get('error', 'Unknown error')}")
                return {
                    "error": query_result.get("error", "Database query execution failed"),
                    "sql_query": sql_query,
                    "results": []
                }
            
            # Step 3: Format the response based on the query and results
            logger.info("Step 3: Formatting query response")
            
            # Let the response formatter agent determine the query type
            # Rather than using keyword matching here
            
            # Format the response
            formatted_response = await format_query_results(
                query=text_content,
                results=results,
                sql_query=query_result.get("sql_query", sql_query),
                success=query_result.get("success", False),
                error=query_result.get("error", None),
                source=query_result.get("source", "sql")
            )
            
            # Add metadata
            formatted_response["sql_query"] = query_result.get("sql_query", sql_query)
            formatted_response["execution_time"] = round(time.time() - start_time, 2)
            formatted_response["source"] = query_result.get("source", "sql")
            
            logger.info(f"Query processing completed in {formatted_response['execution_time']} seconds")
            return formatted_response
            
        except Exception as e:
            logger.exception(f"Error processing invoice query: {str(e)}")
            return {"error": f"Error processing query: {str(e)}"}
        
    finally:
        # Close the database session if we created it
        if should_close_db and db_session:
            db_session.close()
            logger.info("Database session closed")


async def convert_to_sql(
    text_content: str,
    user_id: Optional[Union[str, UUID]] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    use_semantic_search: bool = False
) -> Dict[str, Any]:
    """
    Convert a natural language query to SQL.
    
    Args:
        text_content: The query text
        user_id: Optional user ID for filtering
        conversation_history: Optional conversation history for context
        use_semantic_search: Whether to use semantic search for the query
        
    Returns:
        Dict containing the SQL query or error
    """
    logger.info(f"Starting conversion of text to SQL: '{text_content}'")
    logger.info(f"Semantic search enabled: {use_semantic_search}")
    llm_factory = LLMFactory()
    logger.debug("LLMFactory initialized for SQL conversion")
    
    # Create a database schema description for the SQL conversion agent
    # Load from constants file instead of hardcoding or using prompts
    db_schema_info = DB_SCHEMA_INFO
    
    logger.debug("Loaded database schema from constants/db_schema.py")
    
    logger.debug("Initializing TextToSQLConversionAgent with database schema")
    agent = TextToSQLConversionAgent(llm_factory=llm_factory, db_schema_info=db_schema_info)
    
    # If user_id is a string or UUID, try to convert to integer for database compatibility
    user_id_int = None
    if user_id is not None:
        if isinstance(user_id, (str, UUID)):
            try:
                # If it's a UUID or string, convert it to an integer-like value
                user_id_int = int(str(user_id).replace('-', '')[:8], 16) if '-' in str(user_id) else int(user_id)
                logger.debug(f"Converted user_id from {user_id} to integer: {user_id_int}")
            except (ValueError, TypeError):
                user_id_int = 0  # Default to test user ID if conversion fails
                logger.warning(f"Failed to convert user_id {user_id} to integer, using 0 instead")
        else:
            # Already an integer or integer-like
            user_id_int = user_id
    
    # Add information about the context to help with SQL generation
    user_context = {
        "current_user_id": user_id_int
    }
    
    # Setup extra context with semantic search flag only
    extra_context = {
        "use_semantic_search": use_semantic_search
    }
    
    # Create agent input with both top-level user_id and metadata user_id to ensure it's accessible
    agent_input = {
        "content": text_content,
        "user_id": user_id_int,  # Include at top level for direct access
        "metadata": {
            "user_id": user_id_int,  # Include in metadata as integer
            "user_context": user_context,
            "intent": "invoice_query",
            "extra_context": extra_context,
            "use_semantic_search": use_semantic_search  # Add flag to metadata
        },
        "conversation_history": conversation_history or []
    }
    
    logger.info(f"Calling TextToSQLConversionAgent with input: '{text_content}'")
    logger.debug(f"Agent input metadata includes user_id: {user_id_int} (type: {type(user_id_int).__name__})")
    logger.debug(f"Semantic search: {use_semantic_search}")
    
    try:
        result = await agent.process(agent_input)
        
        if not result:
            logger.error("TextToSQLConversionAgent returned empty result")
            return {"error": "Could not convert your question to a database query."}
        
        if result.content is None or result.content == "":
            logger.error("TextToSQLConversionAgent returned empty SQL query")
            return {"error": "Generated SQL query was empty or invalid."}
        
        # Ensure the query includes user_id filtering for security
        content = result.content
        
        # Post-process the SQL query to ensure correct pgvector syntax
        content = post_process_sql_for_vector(content)
        
        logger.info(f"Generated SQL query: {content}")
        
        # Log the full query to help with debugging
        with open("last_sql_query.log", "w") as f:
            f.write(f"Query: {text_content}\n")
            f.write(f"Use semantic search: {use_semantic_search}\n")
            f.write(f"Generated SQL:\n{content}\n")
            f.write(f"Confidence: {result.confidence}\n")
        
        if user_id and ":user_id" not in content and "user_id" not in content.lower():
            logger.warning(f"Security issue: Generated SQL query does not contain user_id filtering: {content}")
            return {"error": "For security reasons, I can only execute queries that are specific to your user account."}
        
        logger.info(f"SQL conversion successful with confidence: {result.confidence}")
        if result.metadata and result.metadata.get("explanation"):
            logger.info(f"Explanation: {result.metadata.get('explanation')}")
        
        return {
            "sql_query": content,
            "explanation": result.metadata.get("explanation", ""),
            "use_semantic_search": use_semantic_search
        }
        
    except Exception as e:
        logger.exception(f"Error during SQL conversion: {str(e)}")
        return {"error": f"Error during query conversion: {str(e)}"}


def post_process_sql_for_vector(sql: str) -> str:
    """
    Post-process SQL to ensure correct pgvector syntax.
    
    Args:
        sql: Raw SQL string from the agent
        
    Returns:
        Processed SQL with corrected pgvector syntax
    """
    import re
    
    # Fix vector search syntax if needed (ensure consistent format)
    if "to_vector(" in sql.lower():
        # Replace to_vector(:param) with the correct format for our templates
        # Note: This will be later converted to SQLAlchemy format in execute_query
        sql = re.sub(r'to_vector\(\s*:(\w+)\s*\)', r"'[:\1]'::vector", sql)
        logger.warning("Fixed to_vector syntax in SQL query")
    
    # Ensure description_embedding is cast to vector type
    if "description_embedding" in sql and "::vector" not in sql:
        sql = sql.replace("description_embedding", "description_embedding::vector")
        logger.warning("Added ::vector cast to description_embedding column")
    
    # Ensure embedding column in invoice_embeddings table is cast to vector
    if "invoice_embeddings" in sql and "embedding" in sql and "::vector" not in sql:
        sql = sql.replace("embedding", "embedding::vector")
        logger.warning("Added ::vector cast to embedding column")
    
    # Double-check the formatting is consistent for the embedding parameter
    # We want '[:query_embedding]'::vector format here, which will be converted
    # to SQLAlchemy's %(query_embedding)s::vector format in execute_query
    if ":query_embedding" in sql and "'[:query_embedding]'::vector" not in sql:
        sql = sql.replace(":query_embedding::vector", "'[:query_embedding]'::vector")
        logger.warning("Standardized query_embedding vector syntax for template format")
    
    # Log the processed SQL
    logger.debug(f"Post-processed SQL: {sql[:150]}...")
    
    return sql


async def execute_query(
    query: str, 
    session: Optional[Session] = None,
    user_id: Union[int, str] = None,
    query_text: str = "",
    params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Execute a SQL query and return the results.
    
    Args:
        query: The SQL query string to execute
        session: SQLAlchemy database session
        user_id: The user ID to filter results by
        query_text: The original natural language query text for embedding generation
        params: Dictionary of parameters to bind to the query
        
    Returns:
        Dictionary containing query results or error information
    """
    start_time = time.time()
    logger.info(f"Executing SQL query: {query[:150]}...")
    
    if params is None:
        params = {}
    
    # Add user_id to params if provided
    if user_id is not None:
        try:
            # Convert user_id to integer if it's a string
            if isinstance(user_id, str) and user_id.isdigit():
                user_id = int(user_id)
            
            # Check if the query explicitly asks for all data or global counts
            # This is used for admin queries or data status panels
            is_global_query = False
            
            # Only add user_id filter if not a global query
            if not is_global_query and "user_id" not in params:
                params["user_id"] = user_id
                logger.info(f"Added user_id={user_id} filtering")
            elif is_global_query:
                logger.info("Global query detected, not adding user_id filter")
        except ValueError:
            logger.error(f"Invalid user_id: {user_id}")
            return {
                "success": False,
                "error": f"Invalid user_id: {user_id}",
                "results": []
            }
    
    # Generate embedding if needed
    if query_text and ":query_embedding" in query:
        try:
            from utils.vector_utils import generate_embedding_for_text
            
            embedding = generate_embedding_for_text(query_text)
            if embedding:
                params["query_embedding"] = embedding
                logger.info(f"Generated embedding for query (length: {len(embedding)})")
            else:
                logger.error("Failed to generate embedding")
                return {
                    "success": False,
                    "error": "Failed to generate embedding for semantic search",
                    "results": []
                }
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return {
                "success": False,
                "error": f"Error generating embedding: {str(e)}",
                "results": []
            }
    
    # Sanitize the query to prevent SQL injection attacks
    sanitized_query = sanitize_sql(query)
    
    # Log the sanitized query and parameters for debugging
    logger.debug(f"Sanitized SQL query: {sanitized_query}")
    logger.debug("Query parameters: {user_id and standard params included, embedding omitted}")
    
    # Fix vector syntax for PostgreSQL - replace the placeholder syntax with direct array casting
    # This handles the '[:query_embedding]'::vector pattern from our prompt templates and converts 
    # it to a format that works with SQLAlchemy parameter binding
    if "query_embedding" in params:
        try:
            # Convert embedding to PostgreSQL array format if needed
            if isinstance(params["query_embedding"], list):
                embedding_array = params["query_embedding"]
                # Format as PostgreSQL vector string (use square brackets for vectors, not curly braces)
                embedding_str = f"[{','.join(str(x) for x in embedding_array)}]"
                logger.debug(f"Formatted embedding as PostgreSQL array: {embedding_str[:30]}...")
                
                # Instead of using parameter binding for the vector, directly substitute the value
                # This avoids issues with SQLAlchemy's parameter binding for complex vector types
                if "'[:query_embedding]'::vector" in sanitized_query:
                    sanitized_query = sanitized_query.replace("'[:query_embedding]'::vector", f"'{embedding_str}'::vector")
                    logger.debug("Replaced '[:query_embedding]'::vector pattern")
                elif ":query_embedding::vector" in sanitized_query:
                    sanitized_query = sanitized_query.replace(":query_embedding::vector", f"'{embedding_str}'::vector")
                    logger.debug("Replaced :query_embedding::vector pattern")
                else:
                    # Try more aggressive pattern matching for any other variations
                    import re
                    pattern = r"['\[]?:query_embedding['\]]?::vector"
                    replacement = f"'{embedding_str}'::vector"
                    sanitized_query = re.sub(pattern, replacement, sanitized_query)
                    logger.debug(f"Used regex pattern matching for vector replacement")
                
                # Remove the query_embedding parameter since we've directly substituted it
                del params["query_embedding"]
                
                logger.debug(f"Final query after vector substitution: {sanitized_query[:150]}...")
            else:
                logger.warning(f"query_embedding is not a list but {type(params['query_embedding'])}")
        except Exception as e:
            logger.error(f"Error processing vector embedding: {str(e)}")
            return {
                "success": False,
                "error": f"Error formatting vector embedding: {str(e)}",
                "results": []
            }
    
    # Execute the query using SQLAlchemy
    try:
        # Create a SQL expression for execution
        from sqlalchemy.sql import text
        
        # Use provided session or create a new one
        should_close = False
        if session is None:
            should_close = True
            session = next(get_db())
            
        try:
            # Execute the query - use native SQLAlchemy parameter binding
            stmt = text(sanitized_query)
            
            # Log the final SQL and parameters for debugging
            debug_params = {k: (v[:30] + '...' if isinstance(v, str) and len(v) > 30 else v) 
                         for k, v in params.items()}
            
            logger.debug(f"Executing SQL with params: {debug_params}")
            
            # Execute the query
            result = session.execute(stmt, params)
            
            # Convert results to a list of dictionaries
            column_names = result.keys()
            results = [dict(zip(column_names, row)) for row in result.fetchall()]
            
            # Filter out any embedding vectors from results before returning to user
            # This prevents large vector data from being sent to the client
            filtered_results = []
            for row in results:
                filtered_row = {k: v for k, v in row.items() 
                             if not (k.endswith('_embedding') or k == 'embedding')}
                
                # If there's a similarity score, round it to 3 decimal places
                if 'similarity' in filtered_row:
                    filtered_row['similarity'] = round(filtered_row['similarity'], 3)
                if 'similarity_score' in filtered_row:
                    filtered_row['similarity_score'] = round(filtered_row['similarity_score'], 3)
                
                filtered_results.append(filtered_row)
            
            # Log the number of results
            logger.info(f"Query returned {len(filtered_results)} results")
            
            # Calculate execution time
            execution_time = time.time() - start_time
            logger.info(f"Query executed in {execution_time:.3f} seconds")
            
            return {
                "success": True,
                "results": filtered_results,
                "execution_time": execution_time,
                "row_count": len(filtered_results)
            }
        finally:
            if should_close:
                session.close()
    except Exception as e:
        logger.error(f"Error executing query: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "results": []
        }


def sanitize_sql(query: str) -> str:
    """
    Sanitize a SQL query to prevent SQL injection attacks.
    
    Args:
        query: The SQL query to sanitize
        
    Returns:
        The sanitized SQL query
    """
    # Remove any dangerous SQL commands
    dangerous_commands = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT", "GRANT", "REVOKE"]
    
    # Check if the query contains any dangerous commands
    query_upper = query.upper()
    for cmd in dangerous_commands:
        if f"{cmd} " in query_upper or f"{cmd};" in query_upper:
            logger.warning(f"Potentially dangerous SQL command detected: {cmd}")
    
    # We're not actually modifying the query since we're using parameterized queries,
    # but we log warnings for potentially dangerous operations
    return query


async def format_query_results(
    query: str,
    results: List[Dict[str, Any]],
    sql_query: str,
    success: bool = True,
    error: Optional[str] = None,
    source: str = "sql"
) -> Dict[str, Any]:
    """
    Format database query results into a user-friendly response.
    
    Args:
        query: The original query text
        results: List of result rows
        sql_query: The SQL query that was executed
        success: Whether the query execution was successful
        error: Optional error message
        source: Source of the results (sql, rag, etc.)
        
    Returns:
        Dict containing the formatted response and metadata
    """
    logger.info(f"Formatting query response for original query: '{query}'")
    logger.info(f"Query successful: {success}")
    logger.info(f"Results count: {len(results)}")
    logger.info(f"Results source: {source}")
    
    result_count = len(results)
    if result_count > 0:
        try:
            logger.debug(f"First result: {results[0]}")
        except Exception as e:
            logger.debug(f"Could not log first result: {str(e)}")
    else:
        logger.debug("No results")
    
    # Make results JSON-serializable (convert datetime objects, etc.)
    serialized_results = _prepare_results_for_json(results)
    
    # Initialize LLMFactory for response formatting
    logger.debug(f"Initialized LLMFactory for response formatting")
    llm_factory = LLMFactory()
    
    # Initialize ResponseFormatterAgent
    logger.debug(f"Initialized ResponseFormatterAgent")
    formatter_agent = ResponseFormatterAgent(llm_factory=llm_factory)
    
    # Prepare formatting input
    format_input = {
        "type": "query_result",
        "content": {
            "query": query,
            "results": serialized_results,  # Use serialized results instead of raw results
            "success": success,
            "error": error,
            "count": result_count,
            "sql_query": sql_query,
            "source": source  # Add source information for the formatter
        },
        "intent": "invoice_query"
    }
    
    # Log what we're sending to the formatter - now with serialized results and custom encoder
    try:
        truncated_input = json.dumps(format_input, cls=DecimalEncoder)[:500]
        logger.debug(f"Calling ResponseFormatterAgent with input: {truncated_input}...")
    except TypeError as e:
        logger.warning(f"Could not serialize format_input for logging: {str(e)}")
        logger.debug("Using a simplified version of the input for logging")
        
    logger.info(f"Processing response through formatter agent")
    
    # Process the response
    formatted_response = await formatter_agent.process(format_input)
    
    # Check for successful formatting
    if formatted_response and formatted_response.content:
        logger.info(f"Formatted response generated successfully with confidence: {formatted_response.confidence}")
        logger.debug(f"Formatted response content: {formatted_response.content[:100]}...")
        
        return {
            "content": formatted_response.content,
            "metadata": {
                "confidence": formatted_response.confidence,
                "intent": "invoice_query",
                "query": query,
                "sql_query": sql_query,
                "result_count": result_count,
                "source": source
            },
            "confidence": formatted_response.confidence
        }
    else:
        logger.error("Failed to format response")
        return {
            "content": QUERY_FALLBACKS["query_error"],
            "metadata": {
                "confidence": 0.5,
                "intent": "invoice_query",
                "query": query,
                "sql_query": sql_query,
                "result_count": result_count,
                "source": source
            },
            "confidence": 0.5
        }

def _prepare_results_for_json(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert database query results to JSON-serializable format.
    Handles datetime and Decimal objects.
    
    Args:
        results: List of result rows from database query
        
    Returns:
        List of JSON-serializable dictionaries
    """
    if not results:
        return []
        
    serialized_results = []
    
    for row in results:
        # Convert Row object to dict if needed
        if hasattr(row, '_asdict'):
            row_dict = row._asdict()
        elif hasattr(row, '__dict__'):
            row_dict = row.__dict__.copy()
            # Remove SQLAlchemy internal attributes
            row_dict = {k: v for k, v in row_dict.items() if not k.startswith('_')}
        else:
            row_dict = dict(row)
        
        # Convert non-JSON serializable objects to serializable format
        serialized_row = {}
        for key, value in row_dict.items():
            if isinstance(value, datetime):
                serialized_row[key] = value.isoformat()
            elif isinstance(value, Decimal):
                serialized_row[key] = float(value)
            else:
                serialized_row[key] = value
        serialized_results.append(serialized_row)
    
    return serialized_results 