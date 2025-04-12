import time
import re
from typing import Union, Dict, Any, Optional
from log import logger
from agents.agent_output import AgentOutput
from agents.agent_input import AgentInput
from agents.agent_context import AgentContext

class FileProcessor:
    async def process(self, 
                     agent_input: Union[AgentInput, Dict[str, Any]], 
                     context: Optional[AgentContext] = None) -> AgentOutput:
        """
        Process a file input based on its type and content.
        
        Args:
            agent_input: File to process, either as AgentInput or Dict
            context: Optional context for processing
            
        Returns:
            AgentOutput with extracted information and processing results
        """
        logger.info("=== FILE PROCESSOR STARTED ===")
        start_time = time.time()
        
        try:
            # Get the file content and metadata
            if isinstance(agent_input, dict):
                # If input is a dict, extract content and metadata
                file_content = agent_input.get("content")
                metadata = agent_input.get("metadata", {})
                user_id = metadata.get("user_id")
                file_path = metadata.get("file_path")
                file_type = metadata.get("file_type")
                file_name = metadata.get("file_name")
                
                logger.debug(f"Using dictionary input with metadata keys: {list(metadata.keys())}")
                logger.info(f"Processing file: {file_name} | Type: {file_type} | User: {user_id}")
                
                if file_content is None:
                    if file_path:
                        logger.debug(f"No content provided, loading from file_path: {file_path}")
                        file_content = self._load_file_content(file_path)
                    else:
                        logger.error("No file content or path provided")
                        return AgentOutput(
                            content="Error: No file content or path provided",
                            confidence=0.0,
                            status="error",
                            error="Missing file content",
                            metadata=metadata
                        )
            else:
                # Extract from AgentInput
                file_content = agent_input.content
                metadata = agent_input.metadata
                user_id = metadata.get("user_id")
                file_path = metadata.get("file_path")
                file_type = metadata.get("file_type")
                file_name = metadata.get("file_name")
                
                logger.debug(f"Using AgentInput object with metadata keys: {list(metadata.keys())}")
                logger.info(f"Processing file: {file_name} | Type: {file_type} | User: {user_id}")
            
            # Detect file type if not provided
            if not file_type:
                logger.info("File type not provided, detecting automatically")
                file_type = self._detect_file_type(file_content, file_name, file_path)
                logger.info(f"Detected file type: {file_type}")
                metadata["file_type"] = file_type
            
            # Process based on file type
            logger.info(f"Starting processing for file type: {file_type}")
            
            # Track processing stats
            processing_stats = {
                "file_type": file_type,
                "file_size": len(file_content) if isinstance(file_content, bytes) else "unknown",
                "processing_time": 0
            }
            
            # Process the file based on its type
            if file_type.lower() in ['pdf', 'application/pdf']:
                logger.info("Processing PDF file")
                result = await self._process_pdf(file_content, metadata)
                processing_stats["page_count"] = result.get("page_count", 0)
                
            elif file_type.lower() in ['image', 'jpg', 'jpeg', 'png', 'image/jpeg', 'image/png']:
                logger.info("Processing Image file")
                result = await self._process_image(file_content, metadata)
                processing_stats["image_dimensions"] = result.get("dimensions", "unknown")
                
            elif file_type.lower() in ['doc', 'docx', 'application/msword', 
                                      'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                logger.info("Processing Word document file")
                result = await self._process_document(file_content, metadata)
                
            elif file_type.lower() in ['xls', 'xlsx', 'application/vnd.ms-excel', 
                                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                logger.info("Processing Excel spreadsheet file")
                result = await self._process_spreadsheet(file_content, metadata)
                processing_stats["sheet_count"] = result.get("sheet_count", 0)
                
            elif file_type.lower() in ['csv', 'text/csv']:
                logger.info("Processing CSV file")
                result = await self._process_csv(file_content, metadata)
                processing_stats["row_count"] = result.get("row_count", 0)
                
            elif file_type.lower() in ['txt', 'text/plain']:
                logger.info("Processing Text file")
                result = await self._process_text(file_content, metadata)
                
            else:
                logger.warning(f"Unsupported file type: {file_type}")
                return AgentOutput(
                    content=f"Unsupported file type: {file_type}. Please provide a PDF, image, Word, Excel, CSV, or text file.",
                    confidence=0.0,
                    status="error",
                    error=f"Unsupported file type: {file_type}",
                    metadata=metadata
                )
            
            # Get processing time
            end_time = time.time()
            processing_time = end_time - start_time
            processing_stats["processing_time"] = processing_time
            logger.info(f"File processing completed in {processing_time:.2f} seconds")
            
            # Add processing stats to metadata
            metadata["processing_stats"] = processing_stats
            
            # Check result structure
            if not isinstance(result, dict):
                logger.warning(f"Unexpected result type: {type(result)}, converting to dict")
                result = {"content": str(result)}
            
            # Extract content and any additional metadata
            content = result.get("content", "")
            result_metadata = result.get("metadata", {})
            metadata.update(result_metadata)
            
            # Set storage reference if available
            storage_ref = result.get("storage_ref")
            if storage_ref:
                logger.info(f"File stored with reference: {storage_ref}")
                metadata["storage_ref"] = storage_ref
            
            # Log content length
            content_length = len(content) if isinstance(content, str) else "non-string content"
            logger.debug(f"Extracted content length: {content_length}")
            if isinstance(content, str) and len(content) > 100:
                logger.debug(f"Content preview: {content[:100]}...")
            
            # Calculate confidence based on extracted content
            confidence = self._calculate_confidence(content, file_type)
            logger.info(f"Processing confidence: {confidence:.2f}")
            
            logger.info("=== FILE PROCESSOR COMPLETED ===")
            
            return AgentOutput(
                content=content,
                confidence=confidence,
                status="success",
                metadata=metadata
            )
            
        except Exception as e:
            end_time = time.time()
            processing_time = end_time - start_time
            
            logger.error(f"Error processing file: {str(e)}", exc_info=True)
            logger.info("=== FILE PROCESSOR FAILED ===")
            
            if 'metadata' not in locals():
                metadata = {}
                
            metadata["error_details"] = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "processing_time": processing_time
            }
            
            return AgentOutput(
                content=f"Error processing file: {str(e)}",
                confidence=0.0,
                status="error",
                error=str(e),
                metadata=metadata
            )

    def _calculate_confidence(self, content: str, file_type: str) -> float:
        """
        Calculate confidence score based on content quality.
        
        Args:
            content: Extracted content
            file_type: Type of the file processed
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        logger.debug(f"Calculating confidence for {file_type} file")
        
        # Base confidence
        confidence = 0.5
        
        # If no content extracted, low confidence
        if not content or (isinstance(content, str) and not content.strip()):
            logger.debug("Empty content, setting low confidence")
            return 0.1
            
        # Length-based confidence boost
        if isinstance(content, str):
            # More content generally means better extraction
            length = len(content)
            
            if length > 5000:
                confidence += 0.3
                logger.debug(f"Long content length ({length} chars): +0.3 confidence")
            elif length > 1000:
                confidence += 0.2
                logger.debug(f"Medium content length ({length} chars): +0.2 confidence")
            elif length > 100:
                confidence += 0.1
                logger.debug(f"Short content length ({length} chars): +0.1 confidence")
                
            # Check for key structural elements based on file type
            if file_type.lower() in ['pdf', 'application/pdf', 'doc', 'docx']:
                # For documents, check for paragraphs, headings
                if '\n\n' in content:
                    confidence += 0.1
                    logger.debug("Document has paragraph structure: +0.1 confidence")
                    
                if re.search(r'\b(total|amount|invoice|date|customer|client|bill)\b', content.lower()):
                    confidence += 0.1
                    logger.debug("Document contains invoice-related keywords: +0.1 confidence")
                    
            elif file_type.lower() in ['xls', 'xlsx', 'csv']:
                # For data files, check for tabular structure
                if ',' in content or '\t' in content:
                    confidence += 0.1
                    logger.debug("Data file has delimiter structure: +0.1 confidence")
                    
                # Look for numbers which may indicate financial data
                if re.search(r'\$?\d+\.\d{2}\b', content):
                    confidence += 0.1
                    logger.debug("Data file contains currency values: +0.1 confidence")
        
        # Cap at 1.0
        confidence = min(confidence, 1.0)
        logger.debug(f"Final calculated confidence: {confidence:.2f}")
        
        return confidence 