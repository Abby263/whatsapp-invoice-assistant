import time
import uuid
from typing import Union, Dict, Optional
from log import logger
from agent_context import AgentContext
from agent_output import AgentOutput
import json
import logging
from pathlib import Path
from constants.fallback_messages import GENERAL_FALLBACKS

class WorkflowRouter:
    def __init__(self, memory):
        self.memory = memory

    async def route(self, user_input: Union[str, Dict], user_id: str, conversation_id: Optional[str] = None) -> Dict:
        """
        Route the user input to the appropriate workflow.
        
        Args:
            user_input: User input as string or dict with content and metadata
            user_id: ID of the user
            conversation_id: Optional conversation ID
            
        Returns:
            Response from the selected workflow
        """
        logger.info(f"=== WORKFLOW ROUTER STARTED === User: {user_id}")
        start_time = time.time()
        
        try:
            # Process the input to determine intent
            logger.info("Processing input to determine intent")
            
            # Convert user_input to standard format
            if isinstance(user_input, str):
                content = user_input
                metadata = {}
                input_type = "text"
                logger.debug(f"Received string input: '{content[:50]}...' (truncated)")
            else:
                content = user_input.get("content", "")
                metadata = user_input.get("metadata", {})
                input_type = metadata.get("type", "text")
                logger.debug(f"Received dict input with type: {input_type}")
                logger.debug(f"Dict metadata keys: {list(metadata.keys())}")
            
            logger.info(f"Input type: {input_type}")
            
            # Add user_id to metadata for all workflows
            metadata["user_id"] = user_id
            
            # Create or retrieve conversation for context
            if not conversation_id:
                # Generate a new conversation ID if not provided
                conversation_id = str(uuid.uuid4())
                logger.info(f"Generated new conversation ID: {conversation_id}")
            
            metadata["conversation_id"] = conversation_id
            logger.debug(f"Using conversation ID: {conversation_id}")
            
            # Load conversation if exists to maintain context
            if self.memory:
                logger.debug(f"Loading conversation state for {conversation_id}")
                conversation = await self.memory.load_conversation_history(conversation_id)
                if conversation:
                    logger.debug(f"Loaded existing conversation with {len(conversation.get('messages', []))} messages")
                else:
                    logger.debug("No existing conversation found, creating new")
                    conversation = {"messages": []}
            else:
                logger.warning("No memory system available, operating without conversation history")
                conversation = {"messages": []}
            
            # Prepare context for agents
            context = AgentContext(conversation_id=conversation_id, memory=self.memory)
            
            # First, determine if this is a file or text input
            logger.info(f"Determining processing path for input type: {input_type}")
            if input_type.lower() in ["file", "image", "document", "pdf"]:
                logger.info(f"Routing to file processing workflow")
                response = await self._handle_file_input(content, metadata, context)
            else:
                logger.info(f"Routing to text processing workflow")
                # Process with the text intent classifier
                intent_result = await self._classify_intent(content, metadata, context)
                
                if isinstance(intent_result, AgentOutput):
                    intent_data = intent_result.metadata.get("intent", {})
                    intent_type = intent_data.get("intent_type", "unknown")
                    confidence = intent_result.confidence
                    logger.info(f"Classified intent: {intent_type} (confidence: {confidence:.2f})")
                    
                    # Add intent to metadata for downstream processing
                    metadata["intent"] = intent_data
                    
                    # Route based on intent
                    logger.info(f"Routing to workflow based on intent: {intent_type}")
                    if intent_type == "invoice_query":
                        logger.info(f"Routing to invoice query workflow")
                        response = await self.invoice_query_workflow.run(content, metadata, context)
                    elif intent_type == "invoice_creation":
                        logger.info(f"Routing to invoice creation workflow")
                        response = await self.invoice_creation_workflow.run(content, metadata, context)
                    elif intent_type == "greeting":
                        logger.info(f"Routing to greeting workflow (general response)")
                        response = await self.general_response_workflow.run(
                            content, 
                            {**metadata, "format_type": "greeting"},
                            context
                        )
                    elif intent_type == "general_question":
                        logger.info(f"Routing to general question workflow")
                        response = await self.general_response_workflow.run(
                            content, 
                            {**metadata, "format_type": "general"},
                            context
                        )
                    else:
                        logger.warning(f"Unknown intent type: {intent_type}, using general response workflow")
                        response = await self.general_response_workflow.run(
                            content, 
                            {**metadata, "format_type": "default"},
                            context
                        )
                else:
                    logger.error(f"Intent classifier did not return AgentOutput: {type(intent_result)}")
                    # Fallback to general response if intent classification fails
                    logger.info(f"Falling back to general response workflow")
                    response = await self.general_response_workflow.run(
                        content, 
                        {**metadata, "format_type": "fallback"},
                        context
                    )
            
            # Store the message and response in conversation history
            if self.memory:
                logger.debug(f"Storing conversation in memory")
                user_message = {
                    "role": "user",
                    "content": content,
                    "timestamp": time.time(),
                    "metadata": metadata
                }
                
                # Extract response content
                if isinstance(response, AgentOutput):
                    response_content = response.content
                    response_metadata = response.metadata
                elif isinstance(response, dict):
                    response_content = response.get("content", "")
                    response_metadata = response.get("metadata", {})
                else:
                    response_content = str(response)
                    response_metadata = {}
                
                assistant_message = {
                    "role": "assistant",
                    "content": response_content,
                    "timestamp": time.time(),
                    "metadata": response_metadata
                }
                
                # Update conversation with new messages
                conversation["messages"].append(user_message)
                conversation["messages"].append(assistant_message)
                
                # Store updated conversation
                logger.debug(f"Storing updated conversation with {len(conversation['messages'])} messages")
                await self.memory.store_conversation_history(conversation_id, conversation)
            
            # Standardize response format
            if isinstance(response, AgentOutput):
                result = {
                    "content": response.content,
                    "metadata": {
                        **response.metadata,
                        "conversation_id": conversation_id,
                        "response_type": "agent_output"
                    }
                }
            elif isinstance(response, dict):
                result = {
                    "content": response.get("content", ""),
                    "metadata": {
                        **(response.get("metadata", {})),
                        "conversation_id": conversation_id,
                        "response_type": "dict"
                    }
                }
            else:
                result = {
                    "content": str(response),
                    "metadata": {
                        "conversation_id": conversation_id,
                        "response_type": "string"
                    }
                }
            
            # Add processing time to metadata
            end_time = time.time()
            processing_time = end_time - start_time
            result["metadata"]["processing_time"] = processing_time
            
            logger.info(f"Processing completed in {processing_time:.2f} seconds")
            logger.info(f"=== WORKFLOW ROUTER COMPLETED === Response length: {len(result['content'])}")
            
            return result
            
        except Exception as e:
            end_time = time.time()
            processing_time = end_time - start_time
            
            logger.error(f"Error in workflow router: {str(e)}", exc_info=True)
            logger.info(f"=== WORKFLOW ROUTER FAILED === Time: {processing_time:.2f}s")
            
            # Generate error response
            error_response = {
                "content": GENERAL_FALLBACKS["error"],
                "metadata": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "conversation_id": conversation_id if 'conversation_id' in locals() else None,
                    "processing_time": processing_time
                }
            }
            
            return error_response 