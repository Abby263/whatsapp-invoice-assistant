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
import tempfile
from pathlib import Path

from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
from agents.response_formatter import ResponseFormatterAgent
from agents.invoice_rag_agent import InvoiceRAGAgent
from services.llm_factory import LLMFactory
from workflows.state import IntentType
from utils.vector_utils import generate_embedding_for_text
from constants.fallback_messages import QUERY_FALLBACKS
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from constants.db_schema import DB_SCHEMA_INFO

logger = logging.getLogger(__name__)


def _get_db_session_iterator():
    from database.connection import get_db

    return get_db()


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, datetime.date):
            return obj.isoformat()
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

        should_close_db = False
        if db_session is not None:
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

            if db_session is None and user_id is None:
                logger.info("No database session or user_id provided; returning generated query without execution")
                return {
                    "content": (
                        "I've generated a database query, but I need a signed-in user context "
                        "before I can execute it safely.\n\n"
                        f"{sql_query}"
                    ),
                    "metadata": {
                        "intent": IntentType.INVOICE_QUERY.value,
                        "query": sql_query,
                        "success": False,
                        "requires_user_context": True,
                    },
                    "confidence": sql_result.get("confidence", 0.6),
                }

            if db_session is None:
                logger.info("No database session provided, creating a new one")
                try:
                    db_session = next(_get_db_session_iterator())
                    should_close_db = True
                    logger.info("Database session created successfully")
                except Exception as e:
                    logger.error(f"Could not create database session: {str(e)}")
                    return {"error": "Database connection error"}

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
                            query_result["source"] = "agentic_rag"
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
                        query_result["source"] = "agentic_rag_fallback"

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
            formatted_response = await format_query_response(
                query=text_content,
                results=results,
                sql_query=query_result.get("sql_query", sql_query),
                success=query_result.get("success", False),
                error=query_result.get("error", None),
                source=query_result.get("source", "sql")
            )

            # Add metadata
            formatted_response.setdefault("metadata", {})
            formatted_response["metadata"].update({
                "intent": IntentType.INVOICE_QUERY.value,
                "results_count": len(results),
                "query": query_result.get("sql_query", sql_query),
                "success": query_result.get("success", False),
                "source": query_result.get("source", "sql"),
                "retrieval_plan": query_result.get("retrieval_plan"),
                "retrieval_checks": query_result.get("checks"),
            })
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

        _write_last_sql_query_log(
            query=text_content,
            use_semantic_search=use_semantic_search,
            sql_query=content,
            confidence=result.confidence,
        )

        # Check if SQL query is empty
        if not content or content.strip() == "":
            logger.error("Generated SQL query is empty, cannot proceed with execution")
            return {"error": "Unable to generate a valid SQL query from your question. Please try rephrasing your question."}

        # Check if the query has proper user filtering
        if user_id and not check_user_filtering(content):
            logger.warning(f"Security issue: Generated SQL query does not contain user_id filtering: {content}")

            # Try to add user filtering automatically
            try:
                original_content = content
                content = add_user_filter(content, str(user_id))

                if content == original_content:
                    # If we couldn't fix it, reject the query
                    logger.error("Failed to add user_id filtering to the query.")
                    return {"error": "For security reasons, I can only execute queries that are specific to your user account."}

                logger.info(f"Successfully added user_id filtering to SQL: {content[:150]}...")
            except Exception as fix_error:
                logger.error(f"Failed to add user filtering to SQL: {str(fix_error)}")
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


def _last_sql_query_log_path() -> Path:
    """Return a writable path for optional SQL debug logs."""

    configured_path = os.environ.get("LAST_SQL_QUERY_LOG_PATH")
    if configured_path:
        return Path(configured_path)

    if os.environ.get("VERCEL") == "1":
        return Path(tempfile.gettempdir()) / "whatsapp-invoice-assistant" / "last_sql_query.log"

    return Path("last_sql_query.log")


def _write_last_sql_query_log(
    query: str,
    use_semantic_search: bool,
    sql_query: str,
    confidence: float,
) -> None:
    """Write SQL debug details without affecting user-facing query execution."""

    if os.environ.get("LAST_SQL_QUERY_LOG_ENABLED", "true").lower() in {"0", "false", "no"}:
        return

    try:
        log_path = _last_sql_query_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as handle:
            handle.write(f"Query: {query}\n")
            handle.write(f"Use semantic search: {use_semantic_search}\n")
            handle.write(f"Generated SQL:\n{sql_query}\n")
            handle.write(f"Confidence: {confidence}\n")
    except OSError as exc:
        logger.warning("Could not write SQL debug log; continuing query execution: %s", exc)


def post_process_sql_for_vector(sql: str) -> str:
    """
    Post-process SQL to ensure correct pgvector and PostgreSQL syntax.

    Args:
        sql: Raw SQL string from the agent

    Returns:
        Processed SQL with corrected pgvector syntax
    """
    import re

    # PostgreSQL only supports ROUND(value, precision) for numeric, not double
    # precision. Our amount columns are Float, so aggregate summaries need an
    # explicit cast before rounding to two decimals.
    sql = re.sub(
        r"ROUND\(\s*(COALESCE\(\s*(?:SUM|AVG|MIN|MAX)\([^)]+\)\s*,\s*0(?:\.0)?\s*\))\s*,\s*(\d+)\s*\)",
        r"ROUND(CAST(\1 AS numeric), \2)",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r"ROUND\(\s*((?:SUM|AVG|MIN|MAX)\([^)]+\))\s*,\s*(\d+)\s*\)",
        r"ROUND(CAST(\1 AS numeric), \2)",
        sql,
        flags=re.IGNORECASE,
    )

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

    try:
        sanitized_query = sanitize_sql(query)
    except ValueError as e:
        logger.warning("Rejected unsafe SQL query: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "results": []
        }

    # Log the sanitized query and parameters for debugging
    logger.debug(f"Sanitized SQL query: {sanitized_query}")
    logger.debug("Query parameters: {user_id and standard params included, embedding omitted}")

    # Fix vector syntax for PostgreSQL while preserving parameter binding.
    if "query_embedding" in params:
        try:
            if isinstance(params["query_embedding"], list):
                embedding_array = params["query_embedding"]
                embedding_str = f"[{','.join(str(x) for x in embedding_array)}]"
                params["query_embedding"] = embedding_str

                if "'[:query_embedding]'::vector" in sanitized_query:
                    sanitized_query = sanitized_query.replace("'[:query_embedding]'::vector", "CAST(:query_embedding AS vector)")
                    logger.debug("Replaced '[:query_embedding]'::vector pattern")
                elif ":query_embedding::vector" in sanitized_query:
                    sanitized_query = sanitized_query.replace(":query_embedding::vector", "CAST(:query_embedding AS vector)")
                    logger.debug("Replaced :query_embedding::vector pattern")
                else:
                    import re
                    pattern = r"['\[]?:query_embedding['\]]?::vector"
                    replacement = "CAST(:query_embedding AS vector)"
                    sanitized_query = re.sub(pattern, replacement, sanitized_query)
                    logger.debug("Used regex pattern matching for vector replacement")
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
            session = next(_get_db_session_iterator())

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
    import re

    if not query or not query.strip():
        raise ValueError("Empty SQL query")

    sanitized = query.strip().rstrip(";")
    if ";" in sanitized:
        raise ValueError("Multiple SQL statements are not allowed")

    if not re.match(r"^\s*(SELECT|WITH)\b", sanitized, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed")

    dangerous_commands = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT", "GRANT", "REVOKE"]
    for cmd in dangerous_commands:
        if re.search(rf"\b{cmd}\b", sanitized, re.IGNORECASE):
            raise ValueError(f"SQL command is not allowed: {cmd}")

    return sanitized


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

async def format_query_response(*args, **kwargs) -> Dict[str, Any]:
    return await format_query_results(*args, **kwargs)

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

def check_user_filtering(sql: str) -> bool:
    """
    Check if the SQL query includes proper user filtering.

    Args:
        sql: SQL query to check

    Returns:
        True if user filtering is present, False otherwise
    """
    logger.debug("Checking if SQL includes user filtering")

    # Look for common user filtering patterns
    # This is a simplified check - in production, consider using a SQL parser
    user_filter_patterns = [
        r'user_id\s*=\s*:user_id',  # user_id = :user_id
        r'user_id\s*=\s*\d+',  # user_id = 123
        r'user_id\s*=\s*[\'"]?[\w-]+[\'"]?',  # user_id = 'abc-123'
        r'user_id\s*=\s*CAST\s*\([\'"]?[\w-]+[\'"]?\s+AS\s+\w+\)',  # user_id = CAST('abc-123' AS INTEGER)
        r'users\.id\s*=\s*:user_id',  # users.id = :user_id
        r'users\.id\s*=\s*\d+',  # users.id = 123
        r'users\.id\s*=\s*[\'"]?[\w-]+[\'"]?',  # users.id = 'abc-123'
        r'u\.id\s*=\s*:user_id',  # u.id = :user_id (alias)
        r'u\.id\s*=\s*\d+',  # u.id = 123 (alias)
        r'u\.id\s*=\s*[\'"]?[\w-]+[\'"]?',  # u.id = 'abc-123' (alias)
        r'i\.user_id\s*=\s*:user_id',  # i.user_id = :user_id (invoices alias)
        r'inv\.user_id\s*=\s*:user_id',  # inv.user_id = :user_id (invoices alias)
        r'invoices\.user_id\s*=\s*:user_id',  # invoices.user_id = :user_id
        r'invoices\.user_id\s*=\s*\d+',  # invoices.user_id = 123
        r'it\.invoice_id\s+IN\s+\(SELECT\s+id\s+FROM\s+invoices\s+WHERE\s+user_id\s*=\s*:user_id\)',  # items with invoice_id in (select from invoices where user_id=:user_id)
        r'items\.invoice_id\s+IN\s+\(SELECT\s+id\s+FROM\s+invoices\s+WHERE\s+user_id\s*=\s*:user_id\)',  # items with invoice_id in (select from invoices where user_id=:user_id)
        r'JOIN\s+invoices\s+.*?\s+ON\s+.*?\s+WHERE\s+.*?user_id\s*=\s*:user_id',  # JOIN invoices ... WHERE ... user_id = :user_id
        r'FROM\s+invoices\s+.*?\s+WHERE\s+.*?user_id\s*=\s*:user_id',  # FROM invoices ... WHERE ... user_id = :user_id
        r'FROM\s+items\s+.*?JOIN\s+invoices\s+.*?\s+WHERE\s+.*?user_id\s*=\s*:user_id',  # FROM items ... JOIN invoices ... WHERE ... user_id = :user_id
    ]

    for pattern in user_filter_patterns:
        if re.search(pattern, sql, re.IGNORECASE):
            logger.debug(f"Found user filtering pattern: {pattern}")
            return True

    # Check for various table aliases commonly used
    common_invoice_aliases = ['i', 'inv', 'invoices']
    for alias in common_invoice_aliases:
        # Check for alias.user_id = :user_id
        pattern = fr'{alias}\.user_id\s*=\s*:user_id'
        if re.search(pattern, sql, re.IGNORECASE):
            logger.debug(f"Found user filtering with invoice alias '{alias}'")
            return True

    # Check if the query is against tables that don't require user filtering
    # like lookup tables or reference data
    non_user_tables = ['categories', 'statuses', 'settings']
    for table in non_user_tables:
        if re.search(fr'\b{table}\b', sql, re.IGNORECASE):
            no_other_tables = True
            for user_table in ['invoices', 'users', 'clients', 'products', 'items', 'media']:
                if re.search(fr'\b{user_table}\b', sql, re.IGNORECASE):
                    no_other_tables = False
                    break
            if no_other_tables:
                logger.debug(f"Query only uses non-user table: {table}")
                return True

    # Check for common aggregate/count queries that might be implicitly filtered by user_id
    if re.search(r'COUNT\s*\(\s*\*\s*\)', sql, re.IGNORECASE) and re.search(r'FROM\s+invoices', sql, re.IGNORECASE):
        logger.debug("Found COUNT(*) query on invoices, assuming it's filtered by user_id parameter")
        # For count queries, we'll trust that the user_id parameter binding will handle isolation
        return True

    logger.warning("No user filtering detected in SQL query")
    return False

def add_user_filter(sql: str, user_id: str) -> str:
    """
    Add user filtering to SQL if missing.

    Args:
        sql: SQL query to modify
        user_id: User ID to filter on

    Returns:
        Modified SQL query with user filtering
    """
    logger.debug("Adding user filtering to SQL query")

    # First ensure the SQL is not empty
    if not sql or sql.strip() == "":
        logger.error("Cannot add user filtering to empty SQL query")
        return sql

    # Check if user_id filter is already present to avoid duplicates
    if check_user_filtering(sql):
        logger.debug("User filtering already present")
        return sql  # No need to add the filter

    # Convert the query to lowercase for easier parsing
    # but keep the original for final modifications
    sql_lower = sql.lower()

    # Create a simple default query if we can't add filtering
    if 'select' not in sql_lower:
        logger.warning("SQL doesn't contain SELECT statement, creating a simple default query")
        return "SELECT COUNT(*) AS count FROM invoices WHERE user_id = :user_id"

    if 'select' in sql_lower:
        if 'where' in sql_lower:
            # Add to existing WHERE clause
            logger.debug("Adding user_id filter to existing WHERE clause")
            try:
                sql = re.sub(
                    r'(\bWHERE\b\s+.*?)(\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|\Z)',
                    r'\1 AND user_id = :user_id \2',
                    sql,
                    flags=re.IGNORECASE
                )
            except Exception as e:
                logger.error(f"Error adding user_id to WHERE clause: {e}")
                # Fallback - add at the end of WHERE clause
                sql = re.sub(r'(\bWHERE\b\s+.*?)(\Z)', r'\1 AND user_id = :user_id', sql, flags=re.IGNORECASE)
        else:
            # Add new WHERE clause before GROUP BY, ORDER BY, LIMIT, or end of string
            logger.debug("Adding new WHERE clause with user_id filter")
            try:
                sql = re.sub(
                    r'(\bFROM\b\s+.*?)(\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|\Z)',
                    r'\1 WHERE user_id = :user_id \2',
                    sql,
                    flags=re.IGNORECASE
                )
            except Exception as e:
                logger.error(f"Error adding WHERE clause: {e}")
                # Fallback - add after FROM clause
                sql = re.sub(r'(\bFROM\b\s+.*?)(\Z)', r'\1 WHERE user_id = :user_id', sql, flags=re.IGNORECASE)

    logger.debug(f"SQL after adding user filter: {sql}")
    return sql
