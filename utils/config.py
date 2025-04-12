"""Configuration loader for the WhatsApp Invoice Assistant."""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database settings
    DATABASE_URL: str

    # OpenAI settings
    OPENAI_API_KEY: str

    # Twilio settings
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    # AWS settings
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str
    S3_REGION: str

    # Redis settings (with default value)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Logging settings
    LOG_LEVEL: str = "INFO"

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        case_sensitive = True


class ConfigLoader:
    """Utility for loading and accessing configuration."""

    def __init__(self) -> None:
        """Initialize the configuration loader."""
        try:
            self.settings = Settings()  # type: ignore
            self.config: Dict[str, Any] = {}
            self._load_yaml_config()
        except Exception:
            # In case of missing environment variables, initialize with empty config
            self.settings = None  # type: ignore
            self.config = {}

    def _load_yaml_config(self) -> None:
        """Load configuration from YAML file with environment variable interpolation."""
        config_path = Path(__file__).parent.parent / "config" / "env.yaml"
        if not config_path.exists():
            return

        with open(config_path, "r") as f:
            config_template = f.read()

        # Replace environment variables in the YAML
        config_str = os.path.expandvars(config_template)
        self.config = yaml.safe_load(config_str)

    def get(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            section: The section name in the config.
            key: The key within the section. If None, returns the entire section.
            default: Default value to return if section or key not found.

        Returns:
            The configuration value or section.
        """
        if section not in self.config:
            if default is not None:
                return default
            raise KeyError(f"Section '{section}' not found in configuration")

        if key is None:
            return self.config[section]

        if key not in self.config[section]:
            if default is not None:
                return default
            raise KeyError(f"Key '{key}' not found in section '{section}'")

        return self.config[section][key]


# Create a singleton instance
config = ConfigLoader()


def get_db_config() -> Dict[str, Any]:
    """
    Get database configuration.
    
    This function parses the database connection string and merges it with 
    additional database configuration from the config file.
    
    Returns:
        Dict[str, Any]: Dictionary with database configuration
    """
    db_config = {}
    
    # Get configuration from config file
    if config.config and "database" in config.config:
        db_config.update(config.config["database"])
    
    # Parse DATABASE_URL if it exists in settings
    if hasattr(config, "settings") and config.settings and hasattr(config.settings, "DATABASE_URL"):
        database_url = config.settings.DATABASE_URL
        
        # Extract connection details from URL
        # Example URL format: postgresql://username:password@host:port/database
        if database_url:
            # Handle URL if it's already parsed in the config
            if "url" in db_config:
                database_url = db_config["url"]
                
            parts = database_url.split("://")
            if len(parts) > 1:
                # Get the protocol
                db_config["protocol"] = parts[0]
                
                # Parse the rest
                rest = parts[1]
                
                # Extract credentials and host
                auth_host, rest = rest.split("@") if "@" in rest else (None, rest)
                
                if auth_host:
                    # Extract username and password
                    if ":" in auth_host:
                        username, password = auth_host.split(":")
                        db_config["username"] = username
                        db_config["password"] = password
                    else:
                        db_config["username"] = auth_host
                        db_config["password"] = ""
                
                # Extract host, port and database name
                if "/" in rest:
                    host_part, database = rest.split("/", 1)
                    db_config["database"] = database
                    
                    if ":" in host_part:
                        host, port = host_part.split(":")
                        db_config["host"] = host
                        db_config["port"] = port
                    else:
                        db_config["host"] = host_part
                        # Default ports
                        default_ports = {
                            "postgresql": "5432",
                            "postgres": "5432",
                            "mysql": "3306",
                            "sqlite": "",
                        }
                        db_config["port"] = default_ports.get(db_config["protocol"], "")
    
    # Set default values if not present
    if "host" not in db_config:
        # Check if we're running in Docker
        if os.environ.get("PYTHONPATH") == "/app" or os.path.exists("/.dockerenv"):
            db_config["host"] = "whatsapp-invoice-assistant-db"
        else:
            db_config["host"] = "localhost"
    if "port" not in db_config:
        db_config["port"] = "5432"  # Default PostgreSQL port
    if "username" not in db_config:
        db_config["username"] = "postgres"
    if "password" not in db_config:
        db_config["password"] = ""
    if "database" not in db_config:
        db_config["database"] = "whatsapp_invoice_assistant"
    
    return db_config
