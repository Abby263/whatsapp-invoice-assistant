"""
Tests package for WhatsApp Invoice Assistant.

This init file helps with importing test modules and fixtures.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
