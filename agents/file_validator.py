import logging
import json
import base64
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from services.llm_factory import LLMFactory
from constants.fallback_messages import FILE_VALIDATION_PROMPTS, FILE_VALIDATION_MESSAGES
from constants.prompt_mappings import AgentType, get_prompt_for_agent

# Configure logger for this module
logger = logging.getLogger(__name__)


class FileValidatorAgent(BaseAgent):
    """
    Agent for validating whether a file is a valid invoice.
    
    This agent analyzes an uploaded file (image, PDF, Excel, CSV)
    to determine if it contains valid invoice data.
    """
    
    def __init__(self, llm_factory: LLMFactory):
        """
        Initialize the FileValidatorAgent.
        
        Args:
            llm_factory: LLMFactory instance for LLM operations
        """
        super().__init__(llm_factory)
    
    async def process(self, 
                     agent_input: AgentInput, 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process a file to determine if it's a valid invoice.
        
        Args:
            agent_input: Input containing file content or path
            context: Optional context information
            
        Returns:
            AgentOutput with validation results
        """
        try:
            # Extract file content and metadata from input
            file_content = agent_input.content
            file_path = agent_input.file_path or ""
            file_name = agent_input.file_name or ""
            file_type = agent_input.content_type or "unknown"
            
            logger.info(f"Validating file: {file_path} (type: {file_type})")
            
            # For binary content like images, we need special handling
            if isinstance(file_content, bytes):
                # For image types, we'll use GPT-4o-mini to validate if it's an invoice
                if file_type and ("image" in file_type.lower() or file_type.lower() in ["png", "jpg", "jpeg"]):
                    # Get additional file info
                    file_size = len(file_content)
                    
                    # Try to get image dimensions if possible
                    dimensions = "unknown"
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(file_content))
                        dimensions = f"{img.width}x{img.height}"
                    except Exception as e:
                        logger.warning(f"Could not determine image dimensions: {str(e)}")
                    
                    # Prepare for image analysis using GPT-4o-mini
                    try:
                        # Convert image to base64 for analysis
                        base64_image = base64.b64encode(file_content).decode('utf-8')
                        
                        # Use GPT-4o-mini to analyze if the image is an invoice
                        from openai import OpenAI
                        client = OpenAI()
                        
                        # Define a prompt for invoice validation
                        try:
                            # Try to load prompt using LLMFactory
                            agent_type = AgentType.FILE_VALIDATION
                            image_prompt_name = "file_validator_image_prompt"
                            
                            # First try to load through the factory
                            try:
                                prompt = self.llm_factory.load_prompt_template(image_prompt_name)
                                logger.debug(f"Loaded {image_prompt_name} via LLMFactory")
                            except Exception as e:
                                logger.warning(f"Could not load {image_prompt_name} via LLMFactory: {str(e)}")
                                
                                # Fall back to direct file loading
                                prompt_path = Path(__file__).parent.parent / "prompts" / "file_validator_image_prompt.txt"
                                
                                if prompt_path.exists():
                                    with open(prompt_path, "r") as f:
                                        prompt = f.read()
                                    logger.debug("Loaded image validation prompt from file")
                                else:
                                    logger.warning("file_validator_image_prompt.txt not found, using fallback prompt")
                                    # Use fallback prompt from constants
                                    prompt = FILE_VALIDATION_PROMPTS["image_validation"]
                        except Exception as e:
                            logger.error(f"Error loading image validation prompt: {str(e)}")
                            logger.warning("Using fallback image validation prompt")
                            # Use fallback prompt from constants
                            prompt = FILE_VALIDATION_PROMPTS["image_validation"]
                        
                        # Detect proper MIME type for the image
                        mime_type = "image/jpeg"  # default
                        try:
                            from PIL import Image
                            import io
                            img = Image.open(io.BytesIO(file_content))
                            img_format = img.format.lower() if img.format else "jpeg"
                            if img_format == "jpeg" or img_format == "jpg":
                                mime_type = "image/jpeg"
                            elif img_format == "png":
                                mime_type = "image/png"
                            elif img_format == "gif":
                                mime_type = "image/gif"
                            elif img_format == "webp":
                                mime_type = "image/webp"
                            else:
                                mime_type = f"image/{img_format}"
                            logger.info(f"Detected image format: {img_format}, using MIME type: {mime_type}")
                        except Exception as e:
                            logger.warning(f"Could not determine image format: {str(e)}. Using default: {mime_type}")
                        
                        # Call OpenAI with the image
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": prompt
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Is this a valid invoice?"
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:{mime_type};base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }
                            ],
                            max_tokens=500
                        )
                        
                        # Extract the validation result
                        validation_text = response.choices[0].message.content
                        logger.debug(f"Image validation response: {validation_text}")
                        
                        # Parse the JSON response
                        clean_result = self._strip_code_blocks(validation_text)
                        parsed_result = json.loads(clean_result)
                        
                        # Extract validation status and confidence
                        is_valid = parsed_result.get("is_valid_invoice", False)
                        confidence = parsed_result.get("confidence_score", 0.0)
                        missing_elements = parsed_result.get("missing_elements", [])
                        reasons = parsed_result.get("reasons", "")
                        
                        logger.info(f"Image validation result: {'Valid' if is_valid else 'Invalid'} invoice with {confidence:.2f} confidence")
                        
                        return AgentOutput(
                            content=is_valid,
                            confidence=confidence,
                            status="success" if is_valid else "invalid_invoice",
                            metadata={
                                "file_path": file_path,
                                "file_type": file_type,
                                "file_size": file_size,
                                "dimensions": dimensions,
                                "missing_elements": missing_elements,
                                "reasons": reasons
                            }
                        )
                        
                    except Exception as e:
                        logger.error(f"Error during image validation: {str(e)}", exc_info=True)
                        # If image analysis fails, fall back to regular validation
                        logger.warning("Falling back to basic file validation for image")
                        
                        # For safety, assume it's NOT a valid invoice when validation fails
                        return AgentOutput(
                            content=False,
                            confidence=0.5,
                            status="invalid_invoice",
                            metadata={
                                "file_path": file_path,
                                "file_type": file_type,
                                "file_size": file_size,
                                "dimensions": dimensions,
                                "missing_elements": ["validation failed"],
                                "reasons": f"{FILE_VALIDATION_MESSAGES['image_validation_failed']}: {str(e)}"
                            }
                        )
                
                # For other binary files, create a descriptive message
                content_for_validation = f"Binary file: {file_name}, type: {file_type}, size: {len(file_content)} bytes"
            else:
                # For text content, we can pass it directly
                content_for_validation = file_content
            
            # Call LLM to validate the file
            validation_result = await self.llm_factory.validate_invoice_file(content_for_validation)
            
            # Parse the response - handle possible code blocks in the response
            try:
                # Strip any markdown code block formatting if present
                clean_result = self._strip_code_blocks(validation_result)
                parsed_result = json.loads(clean_result)
                logger.debug(f"Parsed validation result: {parsed_result}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse validation result as JSON: {validation_result}")
                logger.error(f"JSON parsing error: {str(e)}")
                # Create a fallback result if parsing fails
                parsed_result = {
                    "is_valid_invoice": False,
                    "confidence_score": 0.5,
                    "missing_elements": ["unable to parse validation result"],
                    "reasons": FILE_VALIDATION_MESSAGES["parse_validation_failed"]
                }
            
            # Extract validation status and confidence
            is_valid = parsed_result.get("is_valid_invoice", False)
            confidence = parsed_result.get("confidence_score", 0.0)
            missing_elements = parsed_result.get("missing_elements", [])
            reasons = parsed_result.get("reasons", "")
            
            # If it's not a file type we support, provide a specific reason
            if file_type == "text":
                reasons = FILE_VALIDATION_MESSAGES["plain_text_invalid"]
                confidence = 0.99  # High confidence that plain text is not an invoice
            
            # Prepare the output
            status = "invalid_invoice" if not is_valid else "success"
            
            return AgentOutput(
                content=is_valid,
                confidence=confidence,
                status=status,
                metadata={
                    "file_path": file_path,
                    "file_type": file_type,
                    "missing_elements": missing_elements,
                    "reasons": reasons,
                    "raw_validation_result": parsed_result
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating file: {str(e)}", exc_info=True)
            return AgentOutput(
                content=False,
                confidence=0.0,
                status="error",
                error=f"File validation failed: {str(e)}",
                metadata={
                    "file_path": agent_input.file_path or "",
                    "file_type": agent_input.content_type or "unknown"
                }
            )
    
    def _strip_code_blocks(self, text: str) -> str:
        """
        Strip markdown code block formatting from the text.
        
        Args:
            text: Text that may contain markdown code block formatting
            
        Returns:
            Clean text with code block formatting removed
        """
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove markdown code block backticks (```json and ```)
        code_block_pattern = r'^```(?:json)?\s*([\s\S]*?)```$'
        match = re.match(code_block_pattern, text, re.DOTALL)
        
        if match:
            # Extract the content inside the code block
            return match.group(1).strip()
        
        return text 