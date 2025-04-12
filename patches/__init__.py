"""
Patches for compatibility issues with different package versions.
"""

import sys
import logging
import importlib
from types import ModuleType

logger = logging.getLogger(__name__)

def patch_langgraph_checkpoint():
    """
    Monkey patch LangGraph's checkpoint imports to handle CheckpointAt not being available.
    """
    try:
        # First check if langgraph is installed
        import langgraph
        
        # Try to check if CheckpointAt already exists
        try:
            from langgraph.checkpoint.base import CheckpointAt
            logger.info("CheckpointAt already exists in LangGraph, no patching needed")
            return
        except ImportError:
            pass
        
        # Get the module where the import is failing
        checkpoint_base = sys.modules.get('langgraph.checkpoint.base', None)
        checkpoint_init = sys.modules.get('langgraph.checkpoint', None)
        
        if checkpoint_base:
            # Add the missing class
            class CheckpointAt:
                """Stub implementation of CheckpointAt for compatibility."""
                def __init__(self, *args, **kwargs):
                    pass
            
            # Add it to the module
            setattr(checkpoint_base, 'CheckpointAt', CheckpointAt)
            logger.info("Successfully patched langgraph.checkpoint.base with CheckpointAt")
            
            # If checkpoint is already imported, patch that too
            if checkpoint_init:
                setattr(checkpoint_init, 'CheckpointAt', CheckpointAt)
                logger.info("Successfully patched langgraph.checkpoint with CheckpointAt")
        
    except ImportError:
        logger.warning("LangGraph not installed, skipping patch")
    except Exception as e:
        logger.error(f"Error patching LangGraph: {e}")

# Apply patches
patch_langgraph_checkpoint() 