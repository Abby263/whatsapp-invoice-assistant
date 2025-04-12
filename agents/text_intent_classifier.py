import logging
import json
from typing import Dict, Any, Optional, List, Tuple

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from langchain_app.state import IntentType
from constants.intent_types import INTENT_CONFIDENCE_THRESHOLDS
from constants.prompt_mappings import AgentType, get_prompt_for_agent
from services.llm_factory import LLMFactory

# Configure logger for this module
logger = logging.getLogger(__name__)


class TextIntentClassifierAgent(BaseAgent):
    """
    Agent for classifying the intent of text inputs using LLM.
    
    This agent analyzes user text input and determines the user's intent
    to enable proper routing to specialized agents.
    """
    
    def __init__(self, llm_factory: LLMFactory):
        """
        Initialize the TextIntentClassifierAgent.
        
        Args:
            llm_factory: LLMFactory instance for LLM operations
        """
        super().__init__(llm_factory)
        self.agent_type = AgentType.TEXT_INTENT_CLASSIFIER
        
    async def process(self, 
                     agent_input: AgentInput, 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process text input to classify the user's intent.
        
        Args:
            agent_input: User's text input
            context: Optional conversation context including history
            
        Returns:
            AgentOutput with the classified intent and confidence score
        """
        logger.info("=== TEXT INTENT CLASSIFIER STARTED ===")
        
        # Get user's text input - handle both dict and AgentInput objects
        if isinstance(agent_input, dict):
            user_input = agent_input.get("content", "")
            conversation_history = agent_input.get("conversation_history", [])
            logger.debug(f"Using dictionary input with content: '{user_input[:50]}...'")
            logger.debug(f"Dictionary input includes {len(conversation_history)} history items")
        else:
            user_input = agent_input.content
            logger.debug(f"Using AgentInput object with content: '{user_input[:50]}...'")
            # Extract conversation history if available
            conversation_history = []
            if context and hasattr(context, 'conversation_history') and context.conversation_history:
                # Make sure to get the whole conversation history for proper context
                conversation_history = context.conversation_history
                logger.debug(f"Extracted {len(conversation_history)} history items from context")
        
        # Format conversation history in the expected format for the LLM
        formatted_history = []
        for message in conversation_history:
            if isinstance(message, dict):
                # If already in the right format, use it directly
                formatted_history.append(message)
            elif hasattr(message, 'role') and hasattr(message, 'content'):
                # Convert from object to dict if needed
                formatted_history.append({
                    "role": message.role,
                    "content": message.content
                })
            
        # Prepare the input for intent classification
        classification_input = {
            "user_input": user_input,
            "conversation_history": formatted_history
        }
        
        logger.info(f"Classifying intent for text: '{user_input}'")
        logger.debug(f"Using {len(formatted_history)} conversation history items for context")
        logger.debug(f"Conversation history: {formatted_history}")
        
        # Call LLM to classify intent
        try:
            # Render the prompt with the input
            logger.info("Calling LLM to classify text intent")
            classification_result = await self.llm_factory.classify_text_intent(
                input_text=json.dumps(classification_input)
            )
            
            # Parse the response
            logger.debug(f"LLM classification raw result: {classification_result}")
            logger.info("Parsing LLM classification result")
            parsed_result = self._parse_classification_result(classification_result)
            
            # Determine confidence level
            confidence_level = self._determine_confidence_level(parsed_result["confidence"])
            logger.info(f"Intent classification result: {parsed_result['intent']} with confidence {parsed_result['confidence']} ({confidence_level})")
            
            # Prepare output
            metadata = {
                "confidence_level": confidence_level,
                "alternative_intents": parsed_result.get("alternative_intents", []),
                "explanation": parsed_result.get("explanation", "")
            }
            
            logger.debug(f"Intent metadata: {metadata}")
            logger.info("=== TEXT INTENT CLASSIFIER COMPLETED ===")
            
            return AgentOutput(
                content=parsed_result["intent"],
                confidence=parsed_result["confidence"],
                metadata=metadata,
                status="success"
            )
            
        except Exception as e:
            logger.error(f"Error classifying intent: {str(e)}", exc_info=True)
            logger.info("=== TEXT INTENT CLASSIFIER FAILED ===")
            return AgentOutput(
                content=IntentType.UNKNOWN,
                confidence=0.0,
                status="error",
                error=f"Intent classification failed: {str(e)}"
            )
    
    def _parse_classification_result(self, result: str) -> Dict[str, Any]:
        """
        Parse the LLM classification result into a structured format.
        
        Args:
            result: The raw LLM response
            
        Returns:
            A dictionary containing the parsed intent and confidence
        """
        logger.info("Parsing classification result")
        
        try:
            # Try to parse as JSON
            logger.debug("Attempting to parse result as JSON")
            parsed = json.loads(result)
            
            # Validate required fields
            if "intent" not in parsed or "confidence" not in parsed:
                logger.warning("Missing required fields in classification result")
                raise ValueError("Missing required fields in classification result")
            
            # Convert string intent to enum value if it's not already
            if isinstance(parsed["intent"], str):
                logger.debug(f"Converting string intent '{parsed['intent']}' to enum")
                try:
                    parsed["intent"] = IntentType(parsed["intent"].lower())
                    logger.debug(f"Successfully converted to enum: {parsed['intent']}")
                except ValueError:
                    logger.warning(f"Unknown intent type: {parsed['intent']}, defaulting to UNKNOWN")
                    parsed["intent"] = IntentType.UNKNOWN
            
            logger.info(f"Successfully parsed JSON result: {parsed['intent']} with confidence {parsed['confidence']}")
            return parsed
            
        except json.JSONDecodeError:
            # If not JSON, try to extract intent and confidence from text
            logger.warning("Failed to parse classification result as JSON, attempting text extraction")
            
            # First, try to handle simple responses like "Greeting", "General", etc.
            intent_str = result.strip().lower()
            logger.debug(f"Attempting to match plain text intent: '{intent_str}'")
            
            # Map the plain text response to the correct IntentType
            intent_map = {
                "greeting": IntentType.GREETING,
                "general": IntentType.GENERAL,
                "invoicequery": IntentType.INVOICE_QUERY,
                "invoice query": IntentType.INVOICE_QUERY,
                "invoicecreator": IntentType.INVOICE_CREATOR,
                "invoice creator": IntentType.INVOICE_CREATOR
            }
            
            # Remove spaces and convert to lowercase
            normalized_intent = intent_str.replace(" ", "").lower()
            logger.debug(f"Normalized intent string: '{normalized_intent}'")
            
            if normalized_intent in intent_map:
                # If we have a direct match, use it with high confidence
                logger.info(f"Found direct match for normalized intent: {normalized_intent}")
                return {
                    "intent": intent_map[normalized_intent],
                    "confidence": 0.9,
                    "explanation": f"Extracted from text response: {intent_str}"
                }
            
            # If no direct match, try more complex extraction
            logger.debug("No direct match found, attempting to extract intent:confidence pattern")
            if "intent:" in result.lower() and "confidence:" in result.lower():
                logger.info("Detected intent:confidence pattern in text")
                lines = result.split("\n")
                intent_line = next((l for l in lines if "intent:" in l.lower()), "")
                confidence_line = next((l for l in lines if "confidence:" in l.lower()), "")
                
                logger.debug(f"Intent line: '{intent_line}'")
                logger.debug(f"Confidence line: '{confidence_line}'")
                
                intent_str = intent_line.split(":", 1)[1].strip() if ":" in intent_line else ""
                confidence_str = confidence_line.split(":", 1)[1].strip() if ":" in confidence_line else ""
                
                logger.debug(f"Extracted intent string: '{intent_str}'")
                logger.debug(f"Extracted confidence string: '{confidence_str}'")
                
                normalized_intent = intent_str.replace(" ", "").lower()
                if normalized_intent in intent_map:
                    intent = intent_map[normalized_intent]
                    logger.info(f"Matched extracted intent to: {intent}")
                else:
                    intent = IntentType.UNKNOWN
                    logger.warning(f"Could not match extracted intent '{intent_str}', using UNKNOWN")
                    
                try:
                    confidence = float(confidence_str)
                    if not 0 <= confidence <= 1:
                        logger.warning(f"Confidence value {confidence} out of range, defaulting to 0.5")
                        confidence = 0.5  # Default if out of range
                    else:
                        logger.info(f"Parsed confidence: {confidence}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse confidence '{confidence_str}', defaulting to 0.5")
                    confidence = 0.5  # Default if not parseable
                    
                return {
                    "intent": intent,
                    "confidence": confidence,
                    "explanation": "Extracted from text response"
                }
            
            # If all else fails, return UNKNOWN with low confidence
            logger.warning("Could not parse classification result in any format, using UNKNOWN intent")
            return {
                "intent": IntentType.UNKNOWN,
                "confidence": 0.1,
                "explanation": f"Could not parse classification result: {result}"
            }
    
    def _determine_confidence_level(self, confidence: float) -> str:
        """
        Determine the confidence level based on the confidence score.
        
        Args:
            confidence: Confidence score between 0 and 1
            
        Returns:
            String representing the confidence level (high, medium, low)
        """
        logger.debug(f"Determining confidence level for score: {confidence}")
        
        if confidence >= INTENT_CONFIDENCE_THRESHOLDS["high"]:
            level = "high"
        elif confidence >= INTENT_CONFIDENCE_THRESHOLDS["medium"]:
            level = "medium"
        else:
            level = "low"
        
        logger.debug(f"Confidence level: {level}")
        return level