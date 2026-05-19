"""Workflow orchestration package for the WhatsApp Invoice Assistant.

The modules in this package route text, file, query, and generated-invoice
requests through validation, extraction, approval, storage, and response
formatting stages.
"""

import logging

logger = logging.getLogger(__name__)
