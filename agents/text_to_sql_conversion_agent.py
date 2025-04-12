import logging
import json
from typing import Dict, Any, Optional, List, Union
import time
import re

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from services.llm_factory import LLMFactory
from utils.vector_utils import generate_embedding_for_text

# Configure logger for this module
logger = logging.getLogger(__name__)


class TextToSQLConversionAgent(BaseAgent):
    """
    Agent for converting natural language queries into SQL statements.
    
    This agent takes user text queries about invoices and transforms them
    into valid SQL queries that can be executed against the database.
    """
    
    def __init__(self, llm_factory: LLMFactory, db_schema_info: str):
        """
        Initialize the TextToSQLConversionAgent.
        
        Args:
            llm_factory: LLMFactory instance for LLM operations
            db_schema_info: String containing database schema information
        """
        super().__init__(llm_factory)
        self.db_schema_info = db_schema_info
    
    async def process(self, 
                     agent_input: Union[AgentInput, Dict[str, Any]], 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process the input query and convert it to SQL.
        
        Args:
            agent_input: Input query to convert, either as AgentInput or Dict
            context: Optional context information
            
        Returns:
            AgentOutput with generated SQL
        """
        logger.info("=== TEXT TO SQL CONVERSION STARTED ===")
        start_time = time.time()
        
        try:
            # Ensure context is initialized
            if context is None:
                context = AgentContext()
            
            # Extract content and metadata
            if isinstance(agent_input, dict):
                query_text = agent_input.get("content", "")
                metadata = agent_input.get("metadata", {})
                
                logger.debug(f"Using dictionary input with content: '{query_text[:50]}...' (truncated)")
                logger.debug(f"Dictionary metadata keys: {list(metadata.keys())}")
                
                # Try to get user_id from multiple locations for flexibility
                user_id = agent_input.get("user_id")  # Try top level first
                if user_id is None:
                    # If not at top level, try in metadata
                    user_id = metadata.get("user_id")
                    
                # Try to get conversation_id from multiple locations
                conversation_id = agent_input.get("conversation_id")
                if conversation_id is None:
                    conversation_id = metadata.get("conversation_id")
                
                # Get semantic search flag
                use_semantic_search = metadata.get("use_semantic_search", False)
                if use_semantic_search is None:
                    # Try in extra_context
                    extra_context = metadata.get("extra_context", {})
                    use_semantic_search = extra_context.get("use_semantic_search", False)
                
                intent = metadata.get("intent", "unknown")
                
                # Update context if needed
                if context.user_id is None and user_id is not None:
                    context.user_id = user_id
                if context.conversation_id is None and conversation_id is not None:
                    context.conversation_id = conversation_id
                
                logger.debug(f"Extracted user_id: {user_id} (type: {type(user_id).__name__ if user_id is not None else 'None'})")
                logger.debug(f"Using semantic search: {use_semantic_search}")
            else:
                query_text = agent_input.content
                metadata = agent_input.metadata
                
                logger.debug(f"Using AgentInput with content: '{query_text[:50]}...' (truncated)")
                logger.debug(f"AgentInput metadata keys: {list(metadata.keys())}")
                
                # Try to get user_id from multiple locations for flexibility
                user_id = getattr(agent_input, "user_id", None)  # Try attribute first
                if user_id is None:
                    # If not direct attribute, try in metadata
                    user_id = metadata.get("user_id")
                
                # Try to get conversation_id from multiple locations
                conversation_id = getattr(agent_input, "conversation_id", None)
                if conversation_id is None:
                    conversation_id = metadata.get("conversation_id")
                
                # Get semantic search flag
                use_semantic_search = metadata.get("use_semantic_search", False)
                if use_semantic_search is None:
                    # Try in extra_context
                    extra_context = metadata.get("extra_context", {})
                    use_semantic_search = extra_context.get("use_semantic_search", False)
                    
                intent = metadata.get("intent", "unknown")
                
                # Update context if needed
                if context.user_id is None and user_id is not None:
                    context.user_id = user_id
                if context.conversation_id is None and conversation_id is not None:
                    context.conversation_id = conversation_id
                
                logger.debug(f"Extracted user_id: {user_id} (type: {type(user_id).__name__ if user_id is not None else 'None'})")
                logger.debug(f"Using semantic search: {use_semantic_search}")
            
            logger.info(f"Converting query to SQL | User ID: {user_id} | Intent: {intent} | Conversation ID: {context.conversation_id}")
            logger.debug(f"Full query text: '{query_text}'")
            
            # Enforce user_id presence - critical for data isolation
            if user_id is None:
                logger.error("No user_id provided in metadata, cannot proceed with SQL conversion")
                return AgentOutput(
                    content="Error: No user ID provided for SQL conversion",
                    confidence=0.0,
                    status="error",
                    error="Missing user_id in metadata",
                    metadata=metadata
                )
                
            # Grab database schema
            logger.info("Retrieving database schema for SQL generation")
            db_schema = self._get_database_schema()
            logger.debug(f"Retrieved schema with {len(db_schema.split(';'))} table definitions")
            
            # Get any entities extracted from the query
            entities = metadata.get("entities", {})
            entity_info = ""
            if entities:
                entity_info = "Extracted entities: " + json.dumps(entities)
                logger.debug(f"Using extracted entities: {entity_info}")
            
            # Get conversation history from context or memory system
            recent_messages = []
            if context and context.conversation_id:
                # Try to get history from memory system first
                try:
                    recent_messages = await self.get_conversation_history(context)
                    if recent_messages:
                        logger.info(f"Loaded {len(recent_messages)} messages from memory for conversation {context.conversation_id}")
                    else:
                        logger.debug("No messages found in memory, checking context history")
                except Exception as e:
                    logger.warning(f"Error getting conversation history from memory: {str(e)}")
            
            # Fall back to context conversation history if memory retrieval failed or returned empty
            if not recent_messages:
                # Get history from context or input
                conversation_history = context.conversation_history if context else []
                if not conversation_history and isinstance(agent_input, dict):
                    conversation_history = agent_input.get("conversation_history", [])
                
                recent_messages = conversation_history[-self.max_history_messages:] if conversation_history else []
                if recent_messages:
                    logger.debug(f"Using {len(recent_messages)} messages from context history")
            
            # Prepare history context
            history_context = ""
            if recent_messages:
                logger.debug("Building conversation history context")
                for msg in recent_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    history_context += f"{role}: {content}\n"
                logger.debug(f"Added {len(recent_messages)} messages to history context")
            
            # Check if this is a summary query
            is_summary = self._is_summary_query(query_text)
            if is_summary:
                logger.info("Detected summary query, will ensure proper grouping")
            
            # Generate SQL
            logger.info("Calling LLM to generate SQL")
            logger.info(f"Using semantic search: {use_semantic_search}")
            sql_response = await self.llm_factory.generate_sql_from_query(
                query=query_text,
                db_schema=db_schema,
                user_id=user_id,
                conversation_history=recent_messages if recent_messages else None,
                is_summary_query=is_summary,
                is_semantic_search=use_semantic_search
            )
            
            # Process the SQL response
            logger.debug(f"Raw SQL from LLM: {sql_response}")
            
            # Extract SQL from the response if needed
            cleaned_sql = self._extract_sql(sql_response)
            logger.debug(f"Extracted SQL: {cleaned_sql}")
            
            # Create a result object with the extracted SQL
            sql_result = {
                "sql_query": cleaned_sql
            }
            
            # Validate and clean the SQL (fix PostgreSQL functions, etc.)
            sql_result = self._validate_and_clean_sql(sql_result)
            validated_sql = sql_result["sql_query"]
            
            # Further validate and secure the SQL
            validated_sql = self._validate_sql(validated_sql, user_id)
            
            if validated_sql != cleaned_sql:
                logger.warning("SQL was modified during validation")
                logger.debug(f"Before validation: {cleaned_sql}")
                logger.debug(f"After validation: {validated_sql}")
            
            # Measure completion time
            end_time = time.time()
            processing_time = end_time - start_time
            logger.info(f"SQL generation completed in {processing_time:.2f} seconds")
            
            # Check if SQL contains user filtering
            has_user_filter = self._check_user_filtering(validated_sql, user_id)
            security_level = "secure" if has_user_filter else "requires_verification"
            
            if not has_user_filter:
                logger.warning(f"Generated SQL lacks explicit user filtering for user_id: {user_id}")
                # Force adding user filter if missing
                validated_sql = self._add_user_filter(validated_sql, user_id)
                logger.debug(f"Added user filter, SQL now: {validated_sql}")
                security_level = "secure_after_modification"
            
            # Calculate confidence
            confidence = self._calculate_confidence(validated_sql, query_text)
            
            logger.info(f"Final SQL confidence: {confidence:.2f}")
            logger.info("=== TEXT TO SQL CONVERSION COMPLETED ===")
            
            # Return the SQL query
            sql_metadata = {
                "raw_sql": sql_response,  # Original from LLM
                "cleaned_sql": cleaned_sql,  # After extraction
                "security_level": security_level,
                "processing_time": processing_time,
                "query_complexity": self._calculate_complexity(validated_sql),
                "use_semantic_search": use_semantic_search,
                "postgresql_functions_fixed": validated_sql != cleaned_sql  # Track if PostgreSQL functions were fixed
            }
            
            # Update metadata with SQL specific info
            metadata.update(sql_metadata)
            
            return AgentOutput(
                content=validated_sql,
                confidence=confidence,
                status="success",
                metadata=metadata
            )
            
        except Exception as e:
            end_time = time.time()
            processing_time = end_time - start_time
            
            logger.error(f"Error converting text to SQL: {str(e)}", exc_info=True)
            logger.info("=== TEXT TO SQL CONVERSION FAILED ===")
            
            if 'metadata' not in locals():
                metadata = {}
                
            metadata["error_details"] = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "processing_time": processing_time
            }
            
            return AgentOutput(
                content=f"Error generating SQL: {str(e)}",
                confidence=0.0,
                status="error",
                error=str(e),
                metadata=metadata
            )
            
    def _extract_sql(self, sql_response: str) -> str:
        """
        Extract SQL from the LLM response, removing any explanations.
        
        Args:
            sql_response: LLM response containing SQL
            
        Returns:
            Cleaned SQL query
        """
        logger.debug("Extracting SQL from LLM response")
        
        # Check if the response contains SQL code blocks
        sql_blocks = re.findall(r'```sql\s*(.*?)\s*```', sql_response, re.DOTALL)
        
        if sql_blocks:
            logger.debug(f"Found {len(sql_blocks)} SQL code blocks")
            # Use the first SQL block
            return sql_blocks[0].strip()
        
        # Check for SQL without specific markers
        sql_blocks = re.findall(r'```\s*(SELECT|INSERT|UPDATE|DELETE|WITH).*?```', sql_response, re.DOTALL | re.IGNORECASE)
        
        if sql_blocks:
            logger.debug(f"Found {len(sql_blocks)} unmarked SQL code blocks")
            return sql_blocks[0].strip().strip('`')
        
        # Look for SQL keywords to extract the query
        sql_patterns = [
            r'(SELECT\s+.*?)(;|\Z)',
            r'(INSERT\s+.*?)(;|\Z)',
            r'(UPDATE\s+.*?)(;|\Z)',
            r'(DELETE\s+.*?)(;|\Z)',
            r'(WITH\s+.*?)(;|\Z)'
        ]
        
        for pattern in sql_patterns:
            match = re.search(pattern, sql_response, re.DOTALL | re.IGNORECASE)
            if match:
                logger.debug(f"Extracted SQL using pattern: {pattern[:20]}...")
                return match.group(1).strip()
        
        logger.warning("Could not extract SQL from LLM response, returning full response")
        return sql_response.strip()
    
    def _validate_sql(self, sql: str, user_id: str) -> str:
        """
        Validate and secure the SQL query, ensuring proper user isolation.
        
        Args:
            sql: SQL query to validate
            user_id: User ID for isolation
            
        Returns:
            Validated and possibly modified SQL query
        """
        logger.debug(f"Validating SQL: {sql}")
        
        # Simple validation and cleaning
        if not sql:
            logger.warning("Empty SQL query received")
            return ""
            
        # Remove multiple semicolons, comments, etc.
        sanitized = re.sub(r'--.*?(\n|$)', ' ', sql)  # Remove SQL comments
        sanitized = re.sub(r'/\*.*?\*/', ' ', sanitized, flags=re.DOTALL)  # Remove block comments
        sanitized = re.sub(r'\s+', ' ', sanitized)  # Standardize whitespace
        
        # Prevent multiple queries
        if ';' in sanitized:
            logger.warning("SQL contains multiple statements, keeping only the first")
            sanitized = sanitized.split(';')[0]
        
        # Check for unsafe patterns
        unsafe_patterns = [
            r'\bDROP\b',
            r'\bTRUNCATE\b',
            r'\bALTER\b',
            r'\bDELETE\b\s+(?!FROM)',  # DELETE not followed by FROM
            r'\bGRANT\b',
            r'\bREVOKE\b',
            r'\bEXEC\b'
        ]
        
        for pattern in unsafe_patterns:
            if re.search(pattern, sanitized, re.IGNORECASE):
                logger.error(f"SQL contains unsafe pattern: {pattern}")
                raise ValueError(f"Unsafe SQL pattern detected: {pattern}")
        
        logger.debug("SQL validation successful")
        return sanitized
    
    def _get_database_schema(self) -> str:
        """
        Return the database schema information stored in the agent.
        
        Returns:
            String containing the database schema information
        """
        logger.debug("Retrieving database schema information")
        return self.db_schema_info
        
    def _check_user_filtering(self, sql: str, user_id: str) -> bool:
        """
        Check if the SQL query includes proper user filtering.
        
        Args:
            sql: SQL query to check
            user_id: User ID that should be filtered
            
        Returns:
            True if user filtering is present, False otherwise
        """
        logger.debug("Checking if SQL includes user filtering")
        
        # Look for common user filtering patterns
        # This is a simplified check - in production, consider using a SQL parser
        user_filter_patterns = [
            r'user_id\s*=\s*[\'"]?\d+[\'"]?',  # user_id = 123
            r'user_id\s*=\s*[\'"]?[\w-]+[\'"]?',  # user_id = 'abc-123'
            r'user_id\s*=\s*CAST\s*\([\'"]?[\w-]+[\'"]?\s+AS\s+\w+\)',  # user_id = CAST('abc-123' AS INTEGER)
            r'users\.id\s*=\s*\d+',  # users.id = 123
            r'users\.id\s*=\s*[\'"]?[\w-]+[\'"]?',  # users.id = 'abc-123'
            r'u\.id\s*=\s*\d+',  # u.id = 123 (alias)
            r'u\.id\s*=\s*[\'"]?[\w-]+[\'"]?'  # u.id = 'abc-123' (alias)
        ]
        
        for pattern in user_filter_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                logger.debug(f"Found user filtering pattern: {pattern}")
                return True
        
        # Check if the query is against tables that don't require user filtering
        # like lookup tables or reference data
        non_user_tables = ['categories', 'statuses', 'settings']
        for table in non_user_tables:
            if re.search(fr'\b{table}\b', sql, re.IGNORECASE):
                no_other_tables = True
                for user_table in ['invoices', 'users', 'clients', 'products']:
                    if re.search(fr'\b{user_table}\b', sql, re.IGNORECASE):
                        no_other_tables = False
                        break
                if no_other_tables:
                    logger.debug(f"Query only uses non-user table: {table}")
                    return True
        
        logger.warning("No user filtering detected in SQL query")
        return False
        
    def _add_user_filter(self, sql: str, user_id: str) -> str:
        """
        Add user filtering to SQL if missing.
        
        Args:
            sql: SQL query to modify
            user_id: User ID to filter on
            
        Returns:
            Modified SQL query with user filtering
        """
        logger.debug("Adding user filtering to SQL query")
        
        # Check if user_id filter is already present to avoid duplicates
        user_filter_patterns = [
            r'user_id\s*=\s*:user_id',  # user_id = :user_id
            r'user_id\s*=\s*\d+',  # user_id = 123
            r'user_id\s*=\s*[\'"]?[\w-]+[\'"]?',  # user_id = 'abc-123'
            r'user_id\s*=\s*CAST\s*\([\'"]?[\w-]+[\'"]?\s+AS\s+\w+\)',  # user_id = CAST('abc-123' AS INTEGER)
            r'users\.id\s*=\s*:user_id',  # users.id = :user_id
            r'users\.id\s*=\s*\d+',  # users.id = 123
        ]
        
        for pattern in user_filter_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                logger.debug(f"User filtering already present with pattern: {pattern}")
                return sql  # No need to add the filter
        
        # Convert the query to lowercase for easier parsing
        # but keep the original for final modifications
        sql_lower = sql.lower()
        
        if 'select' in sql_lower:
            if 'where' in sql_lower:
                # Add to existing WHERE clause
                logger.debug("Adding user_id filter to existing WHERE clause")
                sql = re.sub(
                    r'(\bWHERE\b\s+.*?)(\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|\Z)',
                    r'\1 AND user_id = :user_id \2',
                    sql,
                    flags=re.IGNORECASE
                )
            else:
                # Add new WHERE clause before GROUP BY, ORDER BY, LIMIT, or end of string
                logger.debug("Adding new WHERE clause with user_id filter")
                sql = re.sub(
                    r'(\bFROM\b\s+.*?)(\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|\Z)',
                    r'\1 WHERE user_id = :user_id \2',
                    sql,
                    flags=re.IGNORECASE
                )
        
        logger.debug(f"SQL after adding user filter: {sql}")
        return sql
        
    def _calculate_confidence(self, sql: str, query_text: str) -> float:
        """
        Calculate confidence score for the generated SQL.
        
        Args:
            sql: Generated SQL query
            query_text: Original natural language query
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        logger.debug("Calculating confidence for generated SQL")
        
        # Base confidence
        confidence = 0.7  # Start with a reasonable baseline
        
        # If SQL is empty, zero confidence
        if not sql:
            logger.debug("Empty SQL, returning zero confidence")
            return 0.0
            
        # Check SQL has all parts needed for a proper query
        sql_lower = sql.lower()
        
        # Check if basic SQL structure is present
        if 'select' in sql_lower and 'from' in sql_lower:
            confidence += 0.1
            logger.debug("SQL has basic SELECT structure: +0.1 confidence")
            
            # Add more confidence if the query includes filtering 
            if 'where' in sql_lower:
                confidence += 0.05
                logger.debug("SQL has WHERE clause: +0.05 confidence")
                
            # Check for JOINs which might indicate more complex query handling
            if 'join' in sql_lower:
                confidence += 0.05
                logger.debug("SQL uses JOIN: +0.05 confidence")
        
        # Check if SQL seems to answer the query by looking for key terms
        # Extract key nouns from the query
        query_words = set(query_text.lower().split())
        for term in query_words:
            # Skip common stopwords
            if term in ['what', 'who', 'where', 'when', 'how', 'and', 'the', 'is', 'are', 'was']:
                continue
                
            # Check if term is in SQL - could be table/column names
            if term in sql_lower:
                confidence += 0.02  # Small boost for each term found
                logger.debug(f"Found query term '{term}' in SQL: +0.02 confidence")
                
        # Penalize overly simple or complex queries
        if len(sql) < 20:
            confidence -= 0.1
            logger.debug("SQL is very short, possible oversimplification: -0.1 confidence")
            
        if len(sql) > 500:
            confidence -= 0.1
            logger.debug("SQL is very long, possibly overcomplex: -0.1 confidence")
            
        # Cap confidence
        confidence = max(0.0, min(1.0, confidence))
        logger.debug(f"Final calculated confidence: {confidence:.2f}")
        
        return confidence
        
    def _calculate_complexity(self, sql: str) -> str:
        """
        Calculate the complexity level of the SQL query.
        
        Args:
            sql: SQL query to analyze
            
        Returns:
            Complexity level: "simple", "moderate", or "complex"
        """
        sql_lower = sql.lower()
        
        # Count complexity factors
        complexity_score = 0
        
        # Check for query components
        if 'join' in sql_lower:
            complexity_score += 2
            
        if 'where' in sql_lower:
            complexity_score += 1
            
        if 'group by' in sql_lower:
            complexity_score += 2
            
        if 'having' in sql_lower:
            complexity_score += 2
            
        if 'order by' in sql_lower:
            complexity_score += 1
            
        if 'limit' in sql_lower:
            complexity_score += 1
            
        # Check for subqueries
        subqueries = len(re.findall(r'\(\s*SELECT', sql_lower))
        complexity_score += subqueries * 3
        
        # Check for window functions
        if 'over' in sql_lower and ('partition by' in sql_lower or 'order by' in sql_lower):
            complexity_score += 3
            
        # Check for aggregations
        aggregations = len(re.findall(r'\b(count|sum|avg|min|max)\s*\(', sql_lower))
        complexity_score += aggregations
        
        # Determine complexity level
        if complexity_score <= 2:
            complexity = "simple"
        elif complexity_score <= 6:
            complexity = "moderate"
        else:
            complexity = "complex"
            
        logger.debug(f"SQL complexity score: {complexity_score}, level: {complexity}")
        return complexity

    def _is_summary_query(self, query_text: str) -> bool:
        """
        Check if the query is asking for a summary of expenses.
        
        This function passes the query to the LLM factory to determine
        if it's a summary query, avoiding direct keyword matching.
        
        Args:
            query_text: The query text to check
            
        Returns:
            True if it's a summary query, False otherwise
        """
        # Instead of using explicit text matching with keywords, we'll
        # rely on the LLM's classification built into the text-to-SQL prompt.
        # The prompt already contains detailed instructions for handling summary queries.
        
        # We'll pass a query_context parameter to the LLM indicating this might be
        # a summary query, and let the LLM make the final determination based on
        # the semantic understanding of the query.
        
        # No text matching needed - the query context will be passed to the prompt
        return True  # Always pass context to the LLM prompt to handle properly 

    def _might_need_semantic_search(self, query_text: str) -> bool:
        """
        Determine if a query might benefit from semantic search.
        
        Args:
            query_text: The query text to analyze
            
        Returns:
            True if the query might benefit from semantic search, False otherwise
        """
        # Default to not using semantic search unless specifically enabled
        # This ensures semantic search is only used as a fallback
        # when the regular query returns no results
        return False 

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the LLM."""
        try:
            from pathlib import Path
            prompt_path = Path(__file__).parent.parent / "prompts" / "text_to_sql_system_prompt.txt"
            
            if prompt_path.exists():
                with open(prompt_path, "r") as f:
                    template = f.read()
                
                # Replace placeholders in the template
                prompt = template.replace("{db_schema_info}", self.db_schema_info)
                logger.debug("Loaded text_to_sql_system_prompt.txt from prompts directory")
                return prompt
            else:
                logger.warning("text_to_sql_system_prompt.txt not found, using fallback prompt")
                # Fallback to hardcoded prompt if file doesn't exist
        except Exception as e:
            logger.error(f"Error loading system prompt template: {str(e)}")
            logger.warning("Using fallback system prompt")
        
        # Fallback prompt (same as original, only used if file loading fails)
        return f"""You are an expert SQL developer that converts natural language queries about invoices into PostgreSQL SQL.

Use the following PostgreSQL database schema information to craft your queries:
{self.db_schema_info}

Important vector search information:
- The items table has a column 'description_embedding' of type vector(1536) for semantic search
- When doing vector similarity search, use the l2_distance function with proper syntax:
  l2_distance(description_embedding::vector, '[:query_embedding]'::vector)
- DO NOT use to_vector() function as it does not exist in PostgreSQL
- For vector embeddings, use proper vector casting: '[:query_embedding]'::vector
- The invoice_embeddings table stores vector embeddings for invoices - join with the invoices table when needed

Guidelines:
1. Always include "user_id = :user_id" in the WHERE clause for security
2. Use parameterized queries with :param_name syntax for all parameters
3. For semantic search parameters, use '[:param_name]'::vector format
4. Join related tables as needed for complete information
5. Format dates according to PostgreSQL date functions
6. Return only columns required to answer the query
7. Include useful columns like invoice_date, vendor, description, quantity, unit_price and total_price when relevant

Only return valid PostgreSQL SQL. Your query must run on a PostgreSQL database with the pgvector extension.
"""

    def _post_process_sql(self, sql: str) -> str:
        """
        Post-process SQL to fix any syntax issues.
        
        Args:
            sql: Raw SQL string from LLM
            
        Returns:
            Processed SQL with fixes for common issues
        """
        # Fix vector search syntax if needed
        if "to_vector(" in sql.lower():
            # Replace to_vector(:param) with ':param'::vector
            sql = re.sub(r'to_vector\(\s*:(\w+)\s*\)', r"'[:\1]'::vector", sql)
            logger.warning("Fixed to_vector syntax in SQL query")
        
        # Fix vector syntax for query_embedding (most common parameter name)
        sql = re.sub(r'to_vector\s*\(\s*:query_embedding\s*\)', r"'[:query_embedding]'::vector", sql)
        
        # Fix additional vector syntax issues
        if "description_embedding" in sql and "::vector" not in sql:
            # Make sure the description_embedding column is cast to vector
            sql = sql.replace("description_embedding", "description_embedding::vector")
            logger.warning("Added ::vector cast to description_embedding column")
        
        # Fix embedding column in invoice_embeddings table
        if "invoice_embeddings" in sql and "embedding" in sql and "::vector" not in sql:
            # Make sure the embedding column is cast to vector
            sql = sql.replace("embedding", "embedding::vector")
            logger.warning("Added ::vector cast to embedding column")
        
        return sql 

    def _fix_postgresql_round_function(self, sql):
        """
        Fix PostgreSQL ROUND function to ensure proper type casting.
        
        PostgreSQL requires explicit casting to numeric for ROUND to work properly with
        floating point numbers.
        
        Args:
            sql: The SQL query string
            
        Returns:
            The SQL with corrected ROUND function syntax
        """
        import re
        # Find instances of ROUND(AVG(...), N) and replace with ROUND(CAST(AVG(...) AS numeric), N)
        round_avg_pattern = re.compile(r'ROUND\s*\(\s*AVG\s*\(([^)]+)\)\s*,\s*(\d+)\s*\)', re.IGNORECASE)
        fixed_sql = round_avg_pattern.sub(r'ROUND(CAST(AVG(\1) AS numeric), \2)', sql)
        
        # Find other instances of ROUND(..., N) and replace with ROUND(CAST(... AS numeric), N)
        round_pattern = re.compile(r'ROUND\s*\(\s*(?!CAST)([^,)]+)\s*,\s*(\d+)\s*\)', re.IGNORECASE)
        fixed_sql = round_pattern.sub(r'ROUND(CAST(\1 AS numeric), \2)', fixed_sql)
        
        if fixed_sql != sql:
            logger.info("Fixed PostgreSQL ROUND function with proper type casting")
        
        return fixed_sql

    def _validate_and_clean_sql(self, sql_result):
        """Validates and cleans the generated SQL."""
        # Skip validation for empty results
        if not sql_result or not sql_result.get('sql_query'):
            return sql_result
        
        sql = sql_result['sql_query']
        original_sql = sql
        
        # Remove any trailing semicolons
        sql = sql.strip()
        if sql.endswith(';'):
            sql = sql[:-1].strip()
        
        # If SQL contains multiple statements (multiple SELECT or ;), keep only the first one
        if sql.upper().count('SELECT') > 1 or ';' in sql:
            logger.warning("SQL contains multiple statements, keeping only the first")
            # Extract the first statement 
            if ';' in sql:
                sql = sql.split(';')[0].strip()
            else:
                # Attempt to split on SELECT, but only if not within a subquery
                # This is a simplistic approach that might need refinement
                parts = []
                current_part = ""
                in_parens = 0
                
                for char in sql:
                    if char == '(':
                        in_parens += 1
                    elif char == ')':
                        in_parens -= 1
                    
                    current_part += char
                    
                    # If we see SELECT outside of parentheses and already have content, this is a new statement
                    if (current_part.upper().endswith('SELECT') and 
                        in_parens == 0 and 
                        len(current_part.strip()) > 6):
                        parts.append(current_part[:-6].strip())  # Remove the SELECT
                        current_part = "SELECT"
                
                # Add the final part
                if current_part:
                    parts.append(current_part)
                
                # Only keep the first statement
                if len(parts) > 1:
                    sql = parts[0]
        
        # Fix PostgreSQL ROUND function issue
        sql = self._fix_postgresql_round_function(sql)
        
        # Check if SQL was modified during validation
        if sql != original_sql:
            logger.warning("SQL was modified during validation")
        
        # Update the result with the validated SQL
        sql_result['sql_query'] = sql
        return sql_result 