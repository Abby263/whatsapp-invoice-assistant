"""
Environment variable handling module.

This module handles loading environment variables from env.yaml or .env files
and provides utility functions for accessing them.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ENV_ALIASES = {
    "SUPABASE_URL": ("NEXT_PUBLIC_SUPABASE_URL",),
    "SUPABASE_KEY": (
        "SUPABASE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ),
    "SUPABASE_SERVICE_ROLE_KEY": ("SUPABASE_SECRET_KEY",),
    "CLERK_PUBLISHABLE_KEY": ("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",),
}

# Load configuration from env.yaml
config_path = Path(__file__).parent / "env.yaml"
_config: Dict[str, Any] = {}

try:
    if config_path.exists():
        with open(config_path, "r") as f:
            _config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from {config_path}")
    else:
        logger.debug(f"Configuration file not found at {config_path}")
except Exception as e:
    logger.error(f"Error loading configuration from {config_path}: {str(e)}")


def _candidate_env_names(name: str) -> tuple[str, ...]:
    return (name, *ENV_ALIASES.get(name, ()))


def get_env_variable(name: str, default: Optional[str] = None) -> str:
    """
    Get an environment variable, with fallback to env.yaml config and optional default.

    Args:
        name: The name of the environment variable
        default: Optional default value if not found

    Returns:
        The variable value

    Raises:
        ValueError: If the variable is not found and no default is provided
    """
    # First check actual environment variables, including deployment aliases.
    for candidate_name in _candidate_env_names(name):
        value = os.environ.get(candidate_name)
        if value is not None:
            return value

    # Next check in nested config
    path_parts = name.lower().split('_')
    current = _config
    for part in path_parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            current = None
            break

    if current is not None and not isinstance(current, dict):
        return str(current)

    lowered_name = name.lower()
    for section in _config.values():
        if isinstance(section, dict) and lowered_name in section:
            return str(section[lowered_name])

    # Check for variable template format in yaml (${VAR_NAME})
    for section in _config.values():
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    if env_var in _candidate_env_names(name):
                        # Look up the actual environment variable
                        actual_value = os.environ.get(env_var)
                        if actual_value is not None:
                            return actual_value

    # Fallback to default
    if default is not None:
        return default

    # Not found
    raise ValueError(f"Environment variable {name} not found and no default provided")

def get_config_section(section: str) -> Dict[str, Any]:
    """
    Get a full configuration section.

    Args:
        section: Section name

    Returns:
        Dictionary with configuration values
    """
    return _config.get(section, {})
