import os
import logging
import mimetypes
from typing import Dict, List, Optional, Union, Tuple
from enum import Enum

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext

# Configure logger for this module
logger = logging.getLogger(__name__)


class InputType(str, Enum):
    """Enumeration of possible input types."""
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    UNKNOWN = "unknown"


class InputTypeRouter:
    """
    Routes input to the appropriate agent based on input type detection.
    
    This router determines whether the input is text or a file, and if it's a file,
    what type of file it is (image, PDF, Excel, CSV, etc.), then routes the input
    to the appropriate agent for processing.
    """
    
    # File extensions mapped to input types
    EXTENSION_MAPPING = {
        '.jpg': InputType.IMAGE,
        '.jpeg': InputType.IMAGE,
        '.png': InputType.IMAGE,
        '.gif': InputType.IMAGE,
        '.bmp': InputType.IMAGE,
        '.webp': InputType.IMAGE,
        '.pdf': InputType.PDF,
        '.xlsx': InputType.EXCEL,
        '.xls': InputType.EXCEL,
        '.csv': InputType.CSV
    }
    
    # MIME types mapped to input types
    MIME_MAPPING = {
        'image/jpeg': InputType.IMAGE,
        'image/png': InputType.IMAGE,
        'image/gif': InputType.IMAGE,
        'image/bmp': InputType.IMAGE,
        'image/webp': InputType.IMAGE,
        'application/pdf': InputType.PDF,
        'application/vnd.ms-excel': InputType.EXCEL,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': InputType.EXCEL,
        'text/csv': InputType.CSV,
        'application/csv': InputType.CSV
    }
    
    def __init__(self, agent_mapping: Optional[Dict[InputType, BaseAgent]] = None):
        """
        Initialize the InputTypeRouter.
        
        Args:
            agent_mapping: A dictionary mapping input types to agent instances
        """
        self.agent_mapping = agent_mapping or {}
        
    def register_agent(self, input_type: InputType, agent: BaseAgent) -> None:
        """
        Register an agent for a specific input type.
        
        Args:
            input_type: The input type that the agent can process
            agent: The agent instance to register
        """
        self.agent_mapping[input_type] = agent
        logger.info(f"Registered {agent.__class__.__name__} for input type: {input_type}")
    
    def detect_input_type(self, agent_input: AgentInput) -> InputType:
        """
        Detect the type of input based on content and metadata.
        
        Args:
            agent_input: The input to analyze
            
        Returns:
            The detected input type
        """
        # Check if there's a file_path in metadata
        file_path = agent_input.metadata.get('file_path')
        mime_type = agent_input.metadata.get('mime_type')
        
        # If there's content but no file path, assume it's text
        if agent_input.content and not file_path:
            return InputType.TEXT
        
        # If there's a file path, check file extension
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in self.EXTENSION_MAPPING:
                detected_type = self.EXTENSION_MAPPING[ext]
                logger.debug(f"Detected input type {detected_type} based on file extension {ext}")
                return detected_type
            
            # Try to detect MIME type if extension doesn't give a clear answer
            if not mime_type:
                mime_type, _ = mimetypes.guess_type(file_path)
        
        # Use MIME type if available
        if mime_type and mime_type in self.MIME_MAPPING:
            detected_type = self.MIME_MAPPING[mime_type]
            logger.debug(f"Detected input type {detected_type} based on MIME type {mime_type}")
            return detected_type
        
        # If we couldn't determine the type, return UNKNOWN
        logger.warning(f"Could not determine input type for: {agent_input}")
        return InputType.UNKNOWN
    
    async def route(self, 
                 agent_input: AgentInput, 
                 context: Optional[AgentContext] = None) -> Tuple[InputType, AgentOutput]:
        """
        Route the input to the appropriate agent based on its type.
        
        Args:
            agent_input: The input to route
            context: Optional context information
            
        Returns:
            A tuple of (detected_input_type, agent_output)
            
        Raises:
            ValueError: If no agent is registered for the detected input type
        """
        input_type = self.detect_input_type(agent_input)
        
        # Add the detected input type to metadata
        agent_input.metadata['input_type'] = input_type
        
        if input_type not in self.agent_mapping:
            error_msg = f"No agent registered for input type: {input_type}"
            logger.error(error_msg)
            return input_type, AgentOutput(
                content=None,
                status="error",
                error=error_msg,
                metadata={"original_input": agent_input.dict()}
            )
        
        # Execute the appropriate agent
        agent = self.agent_mapping[input_type]
        logger.info(f"Routing input to {agent.__class__.__name__} for input type: {input_type}")
        result = await agent.execute(agent_input, context)
        
        return input_type, result 