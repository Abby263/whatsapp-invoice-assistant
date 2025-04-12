import time
from typing import Dict, Optional, Any
from log import logger
from agent_output import AgentOutput
from agent_context import AgentContext
from constants.fallback_messages import QUERY_FALLBACKS, DB_FALLBACKS, GENERAL_FALLBACKS

class InvoiceQueryWorkflow:
    async def run(self, 
                 user_input: str, 
                 metadata: Dict[str, Any], 
                 context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Run the invoice query workflow.
        
        Args:
            user_input: User's query about invoices
            metadata: Additional information about the request
            context: Optional context for the workflow
            
        Returns:
            AgentOutput with the response to the user's query
        """
        logger.info("=== INVOICE QUERY WORKFLOW STARTED ===")
        start_time = time.time()
        
        try:
            # Extract user ID from metadata
            user_id = metadata.get("user_id")
            if not user_id:
                logger.error("No user_id provided in metadata, cannot proceed with invoice query")
                return AgentOutput(
                    content=DB_FALLBACKS["connection_error"],
                    confidence=0.0,
                    status="error",
                    error="Missing user_id in metadata",
                    metadata=metadata
                )
            
            logger.info(f"Processing invoice query for user: {user_id}")
            logger.debug(f"User query: '{user_input}'")
            logger.debug(f"Metadata keys: {list(metadata.keys())}")
            
            # Step 1: Determine user's intent more specifically
            intent = metadata.get("intent", {})
            intent_type = intent.get("intent_type", "unknown")
            intent_details = intent.get("details", {})
            
            logger.info(f"Query intent type: {intent_type}")
            logger.debug(f"Intent details: {intent_details}")
            
            # Check if we need to extract entities
            entities = metadata.get("entities", {})
            if not entities and hasattr(self, 'entity_extractor'):
                logger.info("Extracting entities from query")
                
                # Extract entities like dates, amounts, etc.
                entity_input = {
                    "content": user_input,
                    "metadata": {
                        "intent": intent
                    }
                }
                
                entity_result = await self.entity_extractor.process(entity_input, context)
                
                if entity_result and hasattr(entity_result, 'metadata'):
                    entities = entity_result.metadata.get("entities", {})
                    logger.info(f"Extracted {len(entities)} entities")
                    logger.debug(f"Entities: {entities}")
                    metadata["entities"] = entities
            
            # Step 2: Convert to SQL
            logger.info("Converting natural language query to SQL")
            
            # Prepare input for SQL conversion
            sql_input = {
                "content": user_input,
                "metadata": metadata
            }
            
            # Generate SQL query
            sql_result = await self.sql_converter.process(sql_input, context)
            
            if not sql_result or not hasattr(sql_result, 'content') or not sql_result.content:
                logger.error("SQL conversion failed or returned empty result")
                return AgentOutput(
                    content=QUERY_FALLBACKS["sql_conversion_failed"],
                    confidence=0.3,
                    status="error",
                    error="SQL conversion failed",
                    metadata=metadata
                )
            
            sql_query = sql_result.content
            sql_confidence = sql_result.confidence
            
            logger.info(f"Generated SQL query with confidence: {sql_confidence:.2f}")
            logger.debug(f"SQL query: {sql_query}")
            
            # Step 3: Execute SQL query
            logger.info("Executing SQL query against database")
            
            try:
                # Time the database query execution
                db_start_time = time.time()
                query_result = await self.execute_query(sql_query, user_id)
                db_end_time = time.time()
                db_time = db_end_time - db_start_time
                
                logger.info(f"Database query executed in {db_time:.2f} seconds")
                
                if isinstance(query_result, Exception):
                    logger.error(f"Database query error: {str(query_result)}", exc_info=True)
                    # Try to create a user-friendly error message
                    error_details = self._analyze_db_error(query_result)
                    logger.info(f"Analyzed error type: {error_details['type']}")
                    
                    return AgentOutput(
                        content=f"I encountered an error while querying your invoice data: {error_details['message']}",
                        confidence=0.2,
                        status="error",
                        error=str(query_result),
                        metadata={
                            **metadata,
                            "sql_query": sql_query,
                            "error_type": error_details["type"],
                            "error_details": error_details
                        }
                    )
                
                if query_result is None or (isinstance(query_result, list) and len(query_result) == 0):
                    logger.info("Query returned no results")
                    
                    # Provide a helpful message for no results
                    no_results_message = QUERY_FALLBACKS["no_results"]
                    
                    # Add context based on the specific query
                    if "invoice" in user_input.lower() and any(term in user_input.lower() for term in ["recent", "latest", "last"]):
                        no_results_message += " You don't have any invoices uploaded yet."
                    elif "total" in user_input.lower() or "sum" in user_input.lower():
                        no_results_message += " There may not be any data matching those criteria."
                    else:
                        no_results_message += " Please try a different query or check if you have uploaded any invoices."
                    
                    return AgentOutput(
                        content=no_results_message,
                        confidence=0.7,
                        status="success",
                        metadata={
                            **metadata,
                            "sql_query": sql_query,
                            "result_count": 0
                        }
                    )
                
                # Log results summary
                if isinstance(query_result, list):
                    result_count = len(query_result)
                    result_types = set(type(item).__name__ for item in query_result)
                    logger.info(f"Query returned {result_count} results of types: {result_types}")
                    
                    # Log a sample of results for debugging
                    if result_count > 0:
                        sample = query_result[0]
                        if isinstance(sample, dict):
                            logger.debug(f"First result keys: {list(sample.keys())}")
                            logger.debug(f"Sample result: {sample}")
                        else:
                            logger.debug(f"First result: {sample}")
                else:
                    logger.info(f"Query returned scalar result: {query_result}")
                
                # Update metadata with query stats
                query_metadata = {
                    "sql_query": sql_query,
                    "db_query_time": db_time,
                    "result_count": len(query_result) if isinstance(query_result, list) else 1
                }
                metadata.update(query_metadata)
                
            except Exception as db_error:
                logger.error(f"Error executing database query: {str(db_error)}", exc_info=True)
                return AgentOutput(
                    content=DB_FALLBACKS["retrieval_error"],
                    confidence=0.2,
                    status="error",
                    error=str(db_error),
                    metadata={
                        **metadata,
                        "sql_query": sql_query,
                        "error_type": "database_execution_error"
                    }
                )
            
            # Step 4: Format the results into a natural language response
            logger.info("Formatting query results into natural language response")
            
            # Prepare input for the formatter
            formatter_input = {
                "content": query_result,
                "metadata": {
                    "original_query": user_input,
                    "sql_query": sql_query,
                    "intent": intent,
                    "entities": entities,
                    "format_type": "invoice_query_result"
                }
            }
            
            # Format results into natural language
            formatter_start_time = time.time()
            formatted_result = await self.response_formatter.process(formatter_input, context)
            formatter_end_time = time.time()
            formatter_time = formatter_end_time - formatter_start_time
            
            logger.info(f"Response formatting completed in {formatter_time:.2f} seconds")
            
            # Measure total processing time
            end_time = time.time()
            total_time = end_time - start_time
            
            # Prepare final response
            if isinstance(formatted_result, AgentOutput):
                # Add workflow metadata
                workflow_metadata = {
                    **metadata,
                    "workflow": "invoice_query",
                    "total_processing_time": total_time,
                    "formatting_time": formatter_time,
                    "sql_query": sql_query,
                    "sql_confidence": sql_confidence
                }
                
                # Update formatted result metadata
                combined_metadata = {**formatted_result.metadata, **workflow_metadata}
                
                response = AgentOutput(
                    content=formatted_result.content,
                    confidence=formatted_result.confidence,
                    status=formatted_result.status,
                    metadata=combined_metadata
                )
            else:
                logger.warning(f"Formatter returned unexpected type: {type(formatted_result)}")
                # Handle case where formatter didn't return AgentOutput
                response = AgentOutput(
                    content=str(formatted_result),
                    confidence=0.5,
                    status="success",
                    metadata={
                        **metadata,
                        "workflow": "invoice_query",
                        "total_processing_time": total_time,
                        "formatter_error": "Formatter did not return AgentOutput"
                    }
                )
            
            logger.info(f"Invoice query workflow completed in {total_time:.2f} seconds")
            logger.info("=== INVOICE QUERY WORKFLOW COMPLETED ===")
            
            return response
            
        except Exception as e:
            # Calculate time if we have start_time
            end_time = time.time()
            total_time = end_time - start_time if 'start_time' in locals() else 0
            
            logger.error(f"Error in invoice query workflow: {str(e)}", exc_info=True)
            logger.info(f"=== INVOICE QUERY WORKFLOW FAILED === Time: {total_time:.2f}s")
            
            # Provide a helpful error message
            error_message = GENERAL_FALLBACKS["error"]
            
            # Add context if we can determine the error type
            if "database" in str(e).lower() or "sql" in str(e).lower():
                error_message = DB_FALLBACKS["retrieval_error"]
            elif "format" in str(e).lower():
                error_message = GENERAL_FALLBACKS["error"]
            elif "memory" in str(e).lower() or "context" in str(e).lower():
                error_message = GENERAL_FALLBACKS["no_response"]
            
            error_message += " Please try a different query or contact support if the problem persists."
            
            return AgentOutput(
                content=error_message,
                confidence=0.0,
                status="error",
                error=str(e),
                metadata={
                    **(metadata if 'metadata' in locals() else {}),
                    "error_type": type(e).__name__,
                    "processing_time": total_time
                }
            )
            
    def _analyze_db_error(self, error: Exception) -> Dict[str, str]:
        """
        Analyze database errors and create user-friendly messages.
        
        Args:
            error: The database error
            
        Returns:
            Dict with error type and message
        """
        error_str = str(error).lower()
        error_type = "unknown"
        message = DB_FALLBACKS["retrieval_error"]
        
        logger.debug(f"Analyzing database error: {error_str}")
        
        # Check for common error types
        if "no such column" in error_str:
            error_type = "invalid_column"
            message = DB_FALLBACKS["retrieval_error"]
        elif "syntax error" in error_str:
            error_type = "syntax_error"
            message = DB_FALLBACKS["retrieval_error"]
        elif "permission" in error_str or "access" in error_str:
            error_type = "permission_error"
            message = DB_FALLBACKS["connection_error"]
        elif "timeout" in error_str or "timed out" in error_str:
            error_type = "timeout"
            message = GENERAL_FALLBACKS["timeout"]
        elif "unique constraint" in error_str:
            error_type = "duplicate_entry"
            message = DB_FALLBACKS["storage_error"]
        elif "foreign key constraint" in error_str:
            error_type = "reference_error"
            message = DB_FALLBACKS["storage_error"]
        elif "type error" in error_str or "cannot cast" in error_str or "invalid input syntax" in error_str:
            error_type = "type_mismatch"
            message = DB_FALLBACKS["retrieval_error"]
        
        logger.info(f"Classified database error as: {error_type}")
        return {
            "type": error_type,
            "message": message,
            "original": str(error)
        } 