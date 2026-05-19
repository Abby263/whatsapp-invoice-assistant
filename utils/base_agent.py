from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import logging
from pydantic import BaseModel, Field
import asyncio

from services.llm_factory import LLMFactory
from constants.prompt_mappings import get_prompt_for_agent

# Configure logger for this module
logger = logging.getLogger(__name__)


class AgentInput(BaseModel):
    """Base model for standardized input to agents."""
    content: Union[str, bytes] = Field(description="Text content or binary file data")
    file_path: Optional[str] = Field(default=None, description="Path to the file if applicable")
    file_name: Optional[str] = Field(default=None, description="Original filename if applicable")
    content_type: Optional[str] = Field(default=None, description="Type of content (e.g., text, image, pdf)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AgentOutput(BaseModel):
    """Base model for standardized output from agents."""
    content: Any
    confidence: float = 1.0
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None
    status: str = "success"  # success, error, partial


class AgentContext(BaseModel):
    """Context information for agent execution including conversation history."""
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    session_data: Dict[str, Any] = {}
    conversation_history: List[Dict[str, Any]] = []
    system_config: Dict[str, Any] = {}


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the system.
    
    This class provides a common interface for all agents, ensuring
    standardized input/output formats and consistent behavior.
    """
    
    def __init__(self, 
                llm_factory: Optional[LLMFactory] = None, 
                max_history_messages: int = 5):
        """
        Initialize the BaseAgent.
        
        Args:
            llm_factory: An instance of LLMFactory for LLM operations
            max_history_messages: Maximum number of conversation history messages to include
        """
        self.llm_factory = llm_factory
        self.name = self.__class__.__name__
        self.max_history_messages = max_history_messages
        self.agent_type = None  # Subclasses should set this to the appropriate AgentType
        logger.info(f"Initialized {self.name} agent")
    
    def get_prompt_template(self):
        """
        Get the prompt template for this agent based on its agent_type.
        
        Returns:
            The prompt template for this agent
            
        Raises:
            ValueError: If agent_type is not set or prompt template not found
        """
        if not self.agent_type:
            raise ValueError(f"{self.name} does not have agent_type set")
        
        return self.llm_factory.load_prompt_template(
            get_prompt_for_agent(self.agent_type)
        )
    
    @abstractmethod
    async def process(self, 
                     agent_input: AgentInput, 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process the input and return a standardized output.
        
        Args:
            agent_input: Standardized input to the agent
            context: Optional context information
            
        Returns:
            Standardized agent output
        """
        pass
    
    def process_sync(self, 
                   agent_input: Union[AgentInput, Dict[str, Any]], 
                   context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process the input synchronously.
        
        This method runs the async process method in the current event loop
        if one is running, or in a new event loop otherwise.
        
        Args:
            agent_input: Input to the agent
            context: Optional context information
            
        Returns:
            Standardized agent output
        """
        # Convert dict to AgentInput if needed
        if isinstance(agent_input, dict):
            agent_input = AgentInput(**agent_input)
            
        # Create default context if needed
        if context is None:
            context = AgentContext()
            
        # Run the async process method
        try:
            # Check if we're in an event loop
            try:
                loop = asyncio.get_running_loop()
                is_running = True
            except RuntimeError:
                is_running = False
            
            if is_running:
                # Mock a synchronous call with a default response
                logger.warning(f"{self.name} called synchronously in async context - using placeholder response")
                return AgentOutput(
                    content="I'm processing your request.",
                    status="success",
                    confidence=0.5
                )
            else:
                # We can safely create a new event loop
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(self.process(agent_input, context))
                loop.close()
                return result
        except Exception as e:
            return self._handle_error(e, agent_input)
    
    def _log_input_output(self, agent_input: AgentInput, output: AgentOutput) -> None:
        """Log input and output for debugging and monitoring purposes."""
        content_preview = agent_input.content
        if isinstance(content_preview, bytes):
            content_preview = f"<binary data, {len(content_preview)} bytes>"
        logger.debug(f"{self.name} Input: {content_preview}")
        logger.debug(f"{self.name} Output: {output}")
    
    def _handle_error(self, error: Exception, agent_input: AgentInput) -> AgentOutput:
        """
        Handle errors that occur during processing.
        
        Args:
            error: The exception that was raised
            agent_input: The input that caused the error
            
        Returns:
            An AgentOutput with error status and message
        """
        error_msg = f"{type(error).__name__}: {str(error)}"
        logger.error(f"Error in {self.name}: {error_msg}", exc_info=True)
        
        # Create a safe dict representation for logging
        input_dict = agent_input.dict()
        if isinstance(agent_input.content, bytes):
            input_dict["content"] = f"<binary data, {len(agent_input.content)} bytes>"
        
        return AgentOutput(
            content=None,
            status="error",
            error=error_msg,
            metadata={"original_input": input_dict}
        )
    
    async def execute(self, 
                    agent_input: Union[AgentInput, str, bytes, Dict[str, Any]], 
                    context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Execute the agent with appropriate error handling and logging.
        
        This method provides a consistent wrapper around the process method,
        handling input conversion, error handling, and logging.
        
        Args:
            agent_input: Input to the agent (can be AgentInput, str, bytes, or dict)
            context: Optional context information
            
        Returns:
            Standardized agent output
        """
        # Convert input to AgentInput if needed
        if isinstance(agent_input, str):
            agent_input = AgentInput(content=agent_input)
        elif isinstance(agent_input, bytes):
            agent_input = AgentInput(content=agent_input, content_type="binary")
        elif isinstance(agent_input, dict):
            agent_input = AgentInput(**agent_input)
        
        # Create default context if none provided
        if context is None:
            context = AgentContext()
        
        try:
            # Process the input
            output = await self.process(agent_input, context)
            self._log_input_output(agent_input, output)
            
            return output
        except Exception as e:
            return self._handle_error(e, agent_input)
