"""Compatibility helpers for LangGraph version differences."""

import importlib
import logging

logger = logging.getLogger(__name__)


def apply_langgraph_compatibility_patches() -> None:
    """Add a minimal CheckpointAt shim when the installed LangGraph lacks it."""

    try:
        checkpoint_base = importlib.import_module("langgraph.checkpoint.base")
    except ImportError:
        logger.warning("LangGraph checkpoint base is unavailable; skipping compatibility patch")
        return

    if hasattr(checkpoint_base, "CheckpointAt"):
        logger.info("LangGraph CheckpointAt is available; no compatibility patch needed")
        return

    class CheckpointAt:
        """Stub implementation retained for older local LangGraph workflows."""

        def __init__(self, *args, **kwargs):
            pass

    setattr(checkpoint_base, "CheckpointAt", CheckpointAt)

    try:
        checkpoint_package = importlib.import_module("langgraph.checkpoint")
    except ImportError:
        checkpoint_package = None
    if checkpoint_package is not None:
        setattr(checkpoint_package, "CheckpointAt", CheckpointAt)

    logger.info("Applied LangGraph CheckpointAt compatibility shim")
