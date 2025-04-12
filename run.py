#!/usr/bin/env python
"""
Runner script for WhatsApp Invoice Assistant UI.

This script runs the Flask app using Gunicorn with asyncio worker
to properly handle asyncio operations.
"""

import os
import sys
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("runner")

def run_flask_app():
    """Run the Flask app using gunicorn with asyncio worker."""
    try:
        from gunicorn.app.base import BaseApplication

        # Import the Flask app
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from ui.app import app as flask_app

        class GunicornApp(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        # Configure Gunicorn options
        options = {
            'bind': '0.0.0.0:5001',
            'workers': 1,  # Single worker to avoid event loop issues
            'worker_class': 'aiohttp.GunicornWebWorker',  # Async worker
            'timeout': 120,
            'accesslog': '-',
            'errorlog': '-',
            'loglevel': 'info',
            'preload_app': True,
        }

        logger.info(f"Starting Flask app with gunicorn on {options['bind']}")
        GunicornApp(flask_app, options).run()

    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        logger.error("Make sure to run: pip install gunicorn aiohttp")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error running Flask app: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_flask_app() 