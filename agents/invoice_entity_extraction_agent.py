import logging
import json
import re
from typing import Dict, Any, Optional, List, Union

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from services.llm_factory import LLMFactory
from constants.prompt_mappings import AgentType, get_prompt_for_agent

# Configure logger for this module
logger = logging.getLogger(__name__)


class InvoiceEntityExtractionAgent(BaseAgent):
    """
    Agent for extracting invoice-related entities from text inputs.
    
    This agent analyzes natural language text to identify and extract
    entities relevant to creating an invoice, such as:
    - Vendor information
    - Items and quantities
    - Amounts and totals
    - Dates and deadlines
    """
    
    def __init__(self, llm_factory: LLMFactory):
        """
        Initialize the InvoiceEntityExtractionAgent.
        
        Args:
            llm_factory: LLMFactory instance for LLM operations
        """
        super().__init__(llm_factory)
        self.agent_type = AgentType.INVOICE_ENTITY_EXTRACTION
    
    async def process(self, 
                     agent_input: AgentInput, 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process text input to extract invoice-related entities.
        
        Args:
            agent_input: User's text input
            context: Optional context including conversation history
            
        Returns:
            AgentOutput with the extracted entities
        """
        try:
            # Extract user text from input - handle both AgentInput object and dict
            if isinstance(agent_input, dict):
                user_text = agent_input.get("content", "")
                conversation_history = agent_input.get("conversation_history", [])
            else:
                user_text = agent_input.content
                # Extract conversation history if available
                conversation_history = []
                if context and context.conversation_history:
                    conversation_history = context.conversation_history[-5:]  # Last 5 messages for context
            
            # Combine current input with relevant history for better entity extraction
            combined_text = self._prepare_combined_text(user_text, conversation_history)
            
            logger.info(f"Extracting invoice entities from text (length: {len(combined_text)})")
            
            # Call LLM to extract entities
            extraction_result = await self.llm_factory.extract_invoice_entities(combined_text)
            
            # Parse the response
            try:
                # Extract JSON from triple backticks if present
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', extraction_result)
                if json_match:
                    json_str = json_match.group(1)
                    logger.debug(f"Extracted JSON from backticks: {json_str}")
                else:
                    json_str = extraction_result
                
                parsed_result = json.loads(json_str)
                logger.debug(f"Parsed entity extraction result: {parsed_result}")
                
                # If parsed_result is already in the expected format, use it directly
                # (LLMFactory may already return a properly structured response)
                if isinstance(parsed_result, dict):
                    entities = parsed_result
                    confidence = 0.8  # Default confidence for successful parsing
                else:
                    entities = {}
                    confidence = 0.0
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse entity extraction result as JSON: {extraction_result}")
                entities = {}
                confidence = 0.0
                explanation = f"Failed to parse extraction response: {str(e)[:100]}..."
                status = "error"
                
                return AgentOutput(
                    content=entities,
                    confidence=confidence,
                    status=status,
                    metadata={
                        "original_text": user_text,
                        "explanation": explanation,
                        "raw_extraction_result": extraction_result
                    }
                )
            
            # Validate extraction result
            is_valid, validation_score = self._validate_extraction(entities, has_context=bool(conversation_history))
            
            if not is_valid:
                logger.warning(f"Entity extraction result appears invalid: {entities}")
                status = "incomplete_extraction"
            else:
                status = "success"
                confidence = max(confidence, validation_score)  # Use the higher of the two confidences
            
            # Prepare the output
            return AgentOutput(
                content=entities,
                confidence=confidence,
                status=status,
                metadata={
                    "original_text": user_text,
                    "raw_extraction_result": extraction_result
                }
            )
            
        except Exception as e:
            logger.error(f"Error extracting invoice entities: {str(e)}", exc_info=True)
            # Handle the case where agent_input might be a dict
            original_text = agent_input.get("content", "") if isinstance(agent_input, dict) else getattr(agent_input, "content", "")
            return AgentOutput(
                content={},
                confidence=0.0,
                status="error",
                error=f"Entity extraction failed: {str(e)}",
                metadata={
                    "original_text": original_text
                }
            )
    
    def _prepare_combined_text(self, current_text: str, conversation_history: List[Dict[str, Any]]) -> str:
        """
        Combine current text with relevant conversation history.
        
        Args:
            current_text: The current user input
            conversation_history: List of previous conversation messages
            
        Returns:
            Combined text for entity extraction
        """
        # If no history, just return the current text
        if not conversation_history:
            return current_text
        
        # Start with the current text
        combined_text = f"Current message: {current_text}\n\n"
        
        # Add relevant history
        combined_text += "Previous conversation:\n"
        
        for i, message in enumerate(conversation_history):
            role = message.get("role", "user")
            content = message.get("content", "")
            combined_text += f"{role}: {content}\n"
        
        return combined_text
    
    def _validate_extraction(self, entities: Dict[str, Any], has_context: bool = False) -> tuple[bool, float]:
        """
        Validate the extracted entities for completeness.
        
        Args:
            entities: The extracted entities dictionary
            has_context: Whether the extraction was performed with conversation context
            
        Returns:
            A tuple of (is_valid, confidence_score)
        """
        # If entities is completely empty, it's not valid
        if not entities:
            return False, 0.0
        
        # Score the extraction result based on the entities present
        score = 0.0
        max_score = 0.0
        
        # Define scoring weights for different entity types
        entity_weights = {
            "vendor": 0.3,
            "total_amount": 0.3,
            "currency": 0.1,
            "invoice_date": 0.1,
            "due_date": 0.1,
            "items": 0.4,
            "invoice_number": 0.1,
            "status": 0.1
        }
        
        # Calculate the score based on present entities
        for key, weight in entity_weights.items():
            max_score += weight
            if key in entities and entities[key]:
                score += weight
                
                # Extra points for detailed items
                if key == "items" and isinstance(entities[key], list):
                    items = entities[key]
                    if items and all(isinstance(item, dict) for item in items):
                        # Bonus for well-structured items
                        score += 0.1
        
        # Calculate confidence as a percentage of max possible score
        confidence = (score / max_score) if max_score > 0 else 0.0
        
        # When using context, we're more lenient about incomplete extractions
        # because the context may not contain all the necessary information
        validity_threshold = 0.2 if has_context else 0.3
        
        # Return validity and confidence
        return confidence >= validity_threshold, confidence 