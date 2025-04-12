import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from langgraph.agent import AgentContext
from services.llm_factory import LLMFactory
from utils.agent_base import AgentInput, AgentOutput, LangGraphAgent

logger = logging.getLogger(__name__)

class ResponseFormatterAgent(LangGraphAgent):
    """Agent for formatting responses to present to the user."""
    
    def __init__(self, llm_factory: LLMFactory):
        """
        Initialize the ResponseFormatterAgent.
        
        Args:
            llm_factory: An instance of LLMFactory to use for formatting responses
        """
        self.llm_factory = llm_factory
        super().__init__()
        
    def _serialize_for_json(self, data: Any) -> Any:
        """
        Convert data to JSON-serializable format.
        
        Args:
            data: The data to serialize
            
        Returns:
            JSON-serializable data
        """
        if isinstance(data, dict):
            return {k: self._serialize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._serialize_for_json(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data
    
    def process(self, agent_input: AgentInput, agent_context: AgentContext) -> AgentOutput:
        """
        Process the input and format a response.
        
        Args:
            agent_input: The input to the agent
            agent_context: The context of the agent
            
        Returns:
            Formatted response
        """
        logger.info("ResponseFormatterAgent processing input")
        
        try:
            content = agent_input.content
            if isinstance(content, str):
                # If content is a JSON string, parse it
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    # Not a JSON string, use as is
                    pass
            
            if not isinstance(content, dict):
                logger.error(f"Expected content to be a dict, got {type(content)}")
                return AgentOutput(
                    content="I encountered an error while formatting the response.",
                    success=False,
                    error="Invalid content format"
                )
            
            # Serialize any non-JSON-serializable objects (like datetime or Decimal)
            serialized_content = self._serialize_for_json(content)
            
            # Format the response based on the content type
            if content.get("type") == "query_result":
                response = self.llm_factory.format_response(serialized_content)
            elif content.get("type") == "invoice_data":
                response = self.llm_factory.format_invoice_data(serialized_content)
            else:
                response = {"message": "Unknown content type"}
                logger.warning(f"Unknown content type: {content.get('type')}")
            
            logger.info("ResponseFormatterAgent successfully formatted response")
            return AgentOutput(
                content=response,
                success=True
            )
        except Exception as e:
            logger.exception(f"Error in ResponseFormatterAgent: {str(e)}")
            return AgentOutput(
                content="I encountered an error while formatting the response.",
                success=False,
                error=str(e)
            ) 