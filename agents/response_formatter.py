import logging
import json
import re
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from decimal import Decimal

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from services.llm_factory import LLMFactory
from constants.fallback_messages import GENERAL_FALLBACKS, QUERY_FALLBACKS

# Configure logger for this module
logger = logging.getLogger(__name__)


class ResponseFormatterAgent(BaseAgent):
    """
    Agent for formatting responses for WhatsApp messages.
    
    This agent takes processed results from other agents and formats them
    in a way that is suitable for delivery as WhatsApp messages, ensuring
    proper formatting, emojis, and length constraints.
    """
    
    def __init__(self, llm_factory: LLMFactory):
        """
        Initialize the ResponseFormatterAgent.
        
        Args:
            llm_factory: LLMFactory instance for LLM operations
        """
        super().__init__(llm_factory)
    
    def _serialize_for_json(self, obj):
        """
        Convert an object to a JSON-serializable format, handling special cases like datetime.
        
        Args:
            obj: The object to serialize
            
        Returns:
            JSON-serializable version of the object
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        
        # Handle Decimal objects (commonly returned by database queries)
        if hasattr(obj, '__class__') and obj.__class__.__name__ == 'Decimal':
            return float(obj)
        
        if isinstance(obj, dict):
            return {k: self._serialize_for_json(v) for k, v in obj.items()}
        
        if isinstance(obj, list):
            return [self._serialize_for_json(item) for item in obj]
        
        if hasattr(obj, '__dict__'):
            return self._serialize_for_json(obj.__dict__)
        
        return obj
    
    async def process(self, 
                     agent_input: Union[AgentInput, Dict[str, Any]], 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Format the input content for WhatsApp delivery.
        
        Args:
            agent_input: Content to format and message type, either as AgentInput or Dict
            context: Optional context information
            
        Returns:
            AgentOutput with formatted WhatsApp message
        """
        logger.info("=== RESPONSE FORMATTER STARTED ===")
        
        try:
            # Convert dict to AgentInput if needed
            if isinstance(agent_input, dict):
                # Extract content from the dict or use the whole dict if no content key
                content = agent_input.get("content", agent_input)
                metadata = agent_input.get("metadata", {})
                
                format_type = agent_input.get('type', 'default')
                if "type" in agent_input:
                    logger.debug(f"Extracted format type '{format_type}' from input")
                
                logger.debug(f"Using dictionary input with keys: {list(agent_input.keys())}")
                if "metadata" not in agent_input:
                    # Add remaining dict items as metadata if not already there
                    for key, value in agent_input.items():
                        if key != "content" and key != "type":
                            metadata[key] = value
                    logger.debug(f"Added additional keys to metadata: {[k for k in agent_input.keys() if k != 'content' and k != 'type']}")
            else:
                # Extract content and metadata from AgentInput
                content = agent_input.content
                metadata = agent_input.metadata
                format_type = metadata.get('format_type', 'default')
                logger.debug(f"Using AgentInput object with metadata keys: {list(metadata.keys())}")
            
            logger.info(f"Formatting response of type '{format_type}'")
            
            # If content is a dict or list, convert to JSON string
            if isinstance(content, (dict, list)):
                import json
                logger.debug(f"Converting complex content to JSON string (type: {type(content).__name__})")
                
                # If format_type is query_result, keep the content as is for the LLM formatter
                if format_type == 'query_result':
                    # Serialize content for JSON compatibility
                    content_for_llm = self._serialize_for_json(content)
                    logger.debug(f"Using structured content for query_result formatting")
                else:
                    # For other types, convert to JSON string
                    # Use custom serialization for datetime objects
                    try:
                        # First make sure all objects are serializable
                        serialized_content = self._serialize_for_json(content)
                        
                        class DateTimeEncoder(json.JSONEncoder):
                            def default(self, obj):
                                if isinstance(obj, datetime):
                                    return obj.isoformat()
                                return super().default(obj)
                        
                        content_for_llm = json.dumps(serialized_content, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                        logger.debug(f"JSON content length: {len(content_for_llm)}")
                    except TypeError as e:
                        logger.warning(f"Error serializing content to JSON: {str(e)}")
                        # Fallback to string representation if JSON serialization fails
                        content_for_llm = str(content)
            else:
                content_for_llm = str(content)
                logger.debug(f"String content length: {len(content_for_llm)}")
            
            # Call LLM to format the response
            logger.info(f"Calling LLM for response formatting")
            try:
                formatted_response = await self.llm_factory.format_response(
                    content=content_for_llm,
                    format_type=format_type
                )
                
                logger.debug(f"Raw formatted response length: {len(formatted_response)}")
                
                # Apply additional WhatsApp-specific formatting if needed
                logger.info("Applying WhatsApp-specific formatting")
                whatsapp_formatted = self._apply_whatsapp_formatting(formatted_response)
                
                logger.info(f"Final formatted response length: {len(whatsapp_formatted)}")
                logger.debug(f"Formatted response preview: {whatsapp_formatted[:100]}...")
                
                # Check for emojis and formatting markers
                emoji_count = self._count_emojis(whatsapp_formatted)
                formatting_markers = self._detect_formatting_markers(whatsapp_formatted)
                logger.debug(f"Response contains {emoji_count} emojis and formatting markers: {formatting_markers}")
                
                logger.info("=== RESPONSE FORMATTER COMPLETED ===")
                
                # Prepare the output
                return AgentOutput(
                    content=whatsapp_formatted,
                    confidence=1.0,  # High confidence for formatting
                    status="success",
                    metadata={
                        "original_content": content,
                        "format_type": format_type,
                        "emoji_count": emoji_count,
                        "formatting_markers": formatting_markers
                    }
                )
            except Exception as e:
                logger.error(f"Error formatting response: {str(e)}", exc_info=True)
                
                # Create a readable fallback for query results
                if format_type == 'query_result':
                    if isinstance(content, dict):
                        query = content.get('query', 'your query')
                        count = content.get('count', 0)
                        error = content.get('error', None)
                        
                        if error:
                            fallback_response = QUERY_FALLBACKS["query_error"]
                        elif count == 0:
                            fallback_response = QUERY_FALLBACKS["no_results"]
                        else:
                            fallback_response = QUERY_FALLBACKS["ambiguous_query"]
                        
                        logger.debug(f"Created fallback response for query_result: {fallback_response}")
                    else:
                        fallback_response = GENERAL_FALLBACKS["no_response"]
                else:
                    fallback_response = GENERAL_FALLBACKS["error"]
                
                logger.info("=== RESPONSE FORMATTER COMPLETED WITH FALLBACK ===")
                
                return AgentOutput(
                    content=fallback_response,
                    confidence=0.5,
                    status="error",
                    error=f"Formatting failed: {str(e)}",
                    metadata={
                        "original_content": str(content),
                        "format_type": format_type
                    }
                )
            
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}", exc_info=True)
            logger.info("=== RESPONSE FORMATTER FAILED ===")
            
            # In case of error, return the original content with minimal formatting
            if isinstance(agent_input, dict):
                original_content = agent_input.get("content", agent_input)
            else:
                original_content = agent_input.content
            
            if isinstance(original_content, (dict, list)):
                import json
                fallback_response = GENERAL_FALLBACKS["error"]
            else:
                fallback_response = GENERAL_FALLBACKS["error"]
            
            return AgentOutput(
                content=fallback_response,
                confidence=0.5,
                status="error",
                error=f"Formatting failed: {str(e)}",
                metadata={
                    "original_content": original_content,
                    "format_type": format_type if 'format_type' in locals() else 'default'
                }
            )
    
    def _apply_whatsapp_formatting(self, text: str) -> str:
        """
        Apply WhatsApp-specific formatting adjustments.
        
        Args:
            text: The text to format
            
        Returns:
            WhatsApp-formatted text
        """
        logger.debug("Applying WhatsApp-specific formatting adjustments")
        
        # This could include:
        # - Enforcing character limits
        # - Breaking up long messages
        # - Ensuring proper emoji rendering
        # - Formatting lists properly
        
        # Example: Check if message is too long for WhatsApp
        MAX_WHATSAPP_LENGTH = 4096  # WhatsApp message length limit
        
        if len(text) > MAX_WHATSAPP_LENGTH:
            logger.warning(f"Message exceeds WhatsApp length limit: {len(text)} characters")
            # Truncate with indicator
            text = text[:MAX_WHATSAPP_LENGTH - 100] + "\n\n[Message truncated due to length limits]"
            logger.debug("Message truncated to fit WhatsApp length limit")
        
        # Example: Ensure proper spacing after emojis
        # This regex would be more sophisticated in a real implementation
        import re
        original_length = len(text)
        text = re.sub(r'([\U00010000-\U0010ffff])', r'\1 ', text)
        
        if len(text) != original_length:
            logger.debug(f"Adjusted emoji spacing (original: {original_length}, new: {len(text)})")
        
        return text
    
    def _count_emojis(self, text: str) -> int:
        """
        Count the number of emojis in the text.
        
        Args:
            text: The text to analyze
            
        Returns:
            Number of emojis found
        """
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # geometric shapes
            "\U0001F800-\U0001F8FF"  # supplemental arrows
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # extended symbols
            "\U0001FA70-\U0001FAFF"  # extended symbols
            "\U00002702-\U000027B0"  # misc symbols
            "\U000024C2-\U0001F251" 
            "]+"
        )
        emojis = emoji_pattern.findall(text)
        return len(emojis)
    
    def _detect_formatting_markers(self, text: str) -> List[str]:
        """
        Detect WhatsApp formatting markers in the text.
        
        Args:
            text: The text to analyze
            
        Returns:
            List of formatting markers found
        """
        markers = []
        if "*" in text:
            markers.append("bold")
        if "_" in text:
            markers.append("italic")
        if "~" in text:
            markers.append("strikethrough")
        if "```" in text:
            markers.append("code_block")
        if "`" in text and "```" not in text:
            markers.append("inline_code")
        if "•" in text or "·" in text or "⁃" in text or "◦" in text:
            markers.append("bullet_list")
        return markers 