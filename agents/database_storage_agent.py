"""
Database Storage Agent for WhatsApp Invoice Assistant.

This module implements the agent responsible for storing extracted invoice data
in the database using appropriate schema mapping and data validation.
"""

import logging
import json
from typing import Dict, Any, Optional, Union
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from utils.base_agent import BaseAgent, AgentInput, AgentOutput, AgentContext
from services.llm_factory import LLMFactory
from database import schemas
from utils.vector_utils import get_embedding_generator

# Configure logger for this module
logger = logging.getLogger(__name__)


class DatabaseStorageAgent(BaseAgent):
    """
    Agent for storing extracted invoice data in the database.

    This agent handles the creation of database records for invoices,
    invoice items, and media files, with appropriate error handling
    and data validation.
    """

    def __init__(self, llm_factory: Optional[LLMFactory] = None):
        """
        Initialize the DatabaseStorageAgent.

        Args:
            llm_factory: Optional LLMFactory instance for LLM operations
        """
        super().__init__(llm_factory)
        # Initialize the embedding generator
        self.embedding_generator = get_embedding_generator()

    async def process(self, agent_input: AgentInput, context: AgentContext) -> AgentOutput:
        """
        Process the agent input to store invoice data in the database.

        Args:
            agent_input: The input containing the invoice data
            context: Agent context with user information

        Returns:
            An AgentOutput object with the status of the database operation
        """
        logger.info(f"DatabaseStorageAgent processing request for user: {context.user_id}")

        try:
            # Extract content from agent input
            content = agent_input.content

            # Check if content is a JSON string or a dict
            if isinstance(content, str):
                try:
                    # Try to parse as JSON
                    logger.info("Content is a string, attempting to parse as JSON")
                    logger.debug(f"JSON string length: {len(content)} bytes")
                    extraction_result = json.loads(content)
                    logger.info(f"JSON parse success, keys: {extraction_result.keys() if isinstance(extraction_result, dict) else 'not a dict'}")
                except json.JSONDecodeError as e:
                    error_message = f"Invalid JSON: {str(e)}"
                    logger.error(f"JSON parse error: {error_message}")
                    return AgentOutput(
                        content={"error": error_message},
                        status="error",
                        error=error_message
                    )
            elif isinstance(content, dict):
                # Already a dictionary
                logger.info("Content is already a dictionary")
                extraction_result = content
                logger.info(f"Dictionary content keys: {extraction_result.keys()}")
            else:
                error_message = f"Unsupported content type: {type(content)}"
                logger.error(error_message)
                return AgentOutput(
                    content={"error": error_message},
                    status="error",
                    error=error_message
                )

            # Get user_id from context or metadata
            user_id = context.user_id
            if not user_id and agent_input.metadata and "user_id" in agent_input.metadata:
                user_id = agent_input.metadata.get("user_id")
                logger.info(f"Using user_id from metadata: {user_id}")

            if not user_id:
                error_message = "User ID not provided."
                logger.error(error_message)
                return AgentOutput(
                    content={"error": error_message},
                    status="error",
                    error=error_message
                )

            # Log structured data availability before storage
            if isinstance(extraction_result, dict):
                logger.info(f"Invoice data summary before storage:")
                if "vendor" in extraction_result:
                    vendor_data = extraction_result.get("vendor", {})
                    vendor_name = vendor_data.get("name", "Unknown") if isinstance(vendor_data, dict) else vendor_data
                    logger.info(f"- Vendor: {vendor_name}")

                # Log items data presence
                items = []
                if "items" in extraction_result:
                    items = extraction_result.get("items", [])
                    logger.info(f"- Items count at root level: {len(items) if isinstance(items, list) else 'not a list'}")

                # Check for nested data structure
                if "data" in extraction_result and isinstance(extraction_result["data"], dict):
                    data = extraction_result["data"]
                    if "items" in data:
                        items = data.get("items", [])
                        logger.info(f"- Items count in data node: {len(items) if isinstance(items, list) else 'not a list'}")

            # Store the invoice data
            logger.info(f"Calling store_invoice_data with user_id: {user_id}")
            store_result = self.store_invoice_data(extraction_result, user_id)
            logger.info(f"Store invoice data returned: {store_result}")

            # Ensure the store_result has a status field
            if "status" not in store_result:
                logger.info("Adding missing 'status' field with default value 'success'")
                store_result["status"] = "success"

            if "status" in store_result and store_result["status"] in {"success", "duplicate"}:
                logger.info(f"Storage successful: {store_result}")
                return AgentOutput(
                    content=store_result,
                    status="success"
                )
            else:
                error_message = store_result.get("error", "Unknown error")
                logger.error(f"Storage failed with error: {error_message}")
                return AgentOutput(
                    content={"error": error_message},
                    status="error",
                    error=error_message
                )

        except Exception as e:
            error_message = f"Error storing invoice data: {str(e)}"
            logger.exception(error_message)
            return AgentOutput(
                content={"error": error_message},
                status="error",
                error=error_message
            )

    def store_invoice_data(self, extraction_result: Dict[str, Any], user_id: Union[str, UUID]) -> Dict[str, Any]:
        """
        Store extracted invoice data in the database.

        Args:
            extraction_result: Extracted invoice data
            user_id: User ID to associate with the invoice

        Returns:
            Dict containing storage operation results or error information
        """
        # Get database session
        from database.connection import SessionLocal

        db = SessionLocal()

        try:
            # Extract the invoice data - handle different structure possibilities
            # First log the extraction_result structure for debugging
            logger.info(f"extraction_result keys: {extraction_result.keys() if isinstance(extraction_result, dict) else 'not a dict'}")

            # Handle both direct structure and nested 'data' structure
            if "data" in extraction_result:
                invoice_data = extraction_result.get("data", {})
                logger.info("Using 'data' field from extraction_result")
            else:
                # The extraction_result itself contains the invoice data
                invoice_data = extraction_result
                logger.info("Using extraction_result directly as invoice data")

            # Log the invoice_data keys for debugging
            logger.info(f"invoice_data keys: {invoice_data.keys() if isinstance(invoice_data, dict) else 'not a dict'}")

            user_id_value = self._coerce_user_id(user_id)

            vendor_name = self._extract_vendor_name(invoice_data)
            invoice_number, invoice_date = self._extract_transaction_fields(invoice_data)
            total_amount, currency, tax_amount = self._extract_financial_fields(invoice_data)
            notes = self._extract_notes(invoice_data, extraction_result)

            file_storage = self._get_file_storage(extraction_result)
            file_url = file_storage.get("url") if file_storage else None
            file_content_type = file_storage.get("content_type") if file_storage else None
            content_hash = self._extract_content_hash(extraction_result, file_storage)
            raw_data = self._build_raw_data(invoice_data, extraction_result)

            # Create an invoice record directly using SQLAlchemy model
            invoice = schemas.Invoice(
                user_id=user_id_value,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                vendor=vendor_name,
                total_amount=self._to_float(total_amount, 0.0),
                tax_amount=tax_amount,
                currency=currency,
                file_url=file_url,
                file_content_type=file_content_type,
                raw_data=raw_data,
                notes=notes,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            # Add and commit the invoice
            db.add(invoice)
            db.flush()  # Flush to get the invoice.id without committing yet

            # Extract items
            item_ids = []
            # Try to get items directly from the invoice_data
            items = invoice_data.get("items", [])
            logger.info(f"Found {len(items) if items else 0} items in invoice data")

            if not items and "items" in extraction_result:
                # If items not in invoice_data but in extraction_result, use that
                items = extraction_result.get("items", [])
                logger.info(f"Using items directly from extraction_result: {len(items) if items else 0} items")

            if items and isinstance(items, list):
                # Pre-generate embeddings for all item descriptions in batch for efficiency
                item_descriptions = [
                    item.get("description") or item.get("name") or "Item"
                    for item in items
                    if isinstance(item, dict)
                ]
                logger.info(f"Generating embeddings for {len(item_descriptions)} items")

                batch_embeddings = None
                try:
                    # Generate embeddings for all descriptions in a single batch operation
                    batch_embeddings = self.embedding_generator.generate_batch_embeddings(item_descriptions)
                    logger.info(f"Successfully generated {len(batch_embeddings) if batch_embeddings else 0} embeddings")
                except Exception as e:
                    logger.exception(f"Error generating batch embeddings: {str(e)}")
                    batch_embeddings = [None] * len(item_descriptions)

                # Process each item
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        logger.warning(f"Skipping item {i}: not a dictionary, type: {type(item)}")
                        continue

                    logger.info(f"Processing item {i+1}: {item}")
                    description = item.get("description") or item.get("name") or "Item"
                    quantity = self._to_float(item.get("quantity"), 1.0)
                    unit_price = self._first_float(
                        item.get("unit_price"),
                        item.get("price"),
                    )
                    total_price = self._first_float(
                        item.get("total_price"),
                        item.get("amount"),
                        item.get("total"),
                    )
                    if total_price is None and unit_price is not None:
                        total_price = unit_price * quantity
                    if unit_price is None and total_price is not None and quantity:
                        unit_price = total_price / quantity
                    unit_price = unit_price if unit_price is not None else 0.0
                    total_price = total_price if total_price is not None else 0.0
                    item_category = item.get("item_category") or item.get("entry_type")
                    item_code = item.get("item_code") or item.get("transaction_date") or item.get("raw_date")
                    if item_code is not None:
                        item_code = str(item_code)[:50]

                    # Log item values for debugging
                    logger.info(f"Item details - description: {description}, quantity: {quantity}, "
                               f"unit_price: {unit_price}, total_price: {total_price}, "
                               f"item_category: {item_category}, item_code: {item_code}")

                    # Get the embedding for this item
                    embedding = None
                    if batch_embeddings and i < len(batch_embeddings):
                        embedding = batch_embeddings[i]
                        logger.info(f"Using pre-generated embedding for item {i+1}")

                    try:
                        # Create an item record directly using SQLAlchemy model
                        item_record = schemas.Item(
                            invoice_id=invoice.id,
                            description=description,
                            quantity=quantity,
                            unit_price=unit_price,
                            total_price=total_price,
                            item_category=item_category,  # Set item_category
                            item_code=item_code,  # Set item_code
                            description_embedding=embedding,  # Set the embedding
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )

                        # Add the item
                        db.add(item_record)
                        db.flush()  # Flush to get the item.id
                        logger.info(f"Item record created with ID: {item_record.id} {'with embedding' if embedding else 'without embedding'}")
                        item_ids.append(str(item_record.id))
                    except Exception as e:
                        logger.exception(f"Error creating item record: {str(e)}")
            else:
                logger.warning(f"No items found in invoice data or items not a list. Items data: {items}")

            invoice_embedding_id = None
            try:
                content_text = self._build_invoice_embedding_text(invoice_data)
                invoice_embedding = self.embedding_generator.generate_embedding(content_text)
                if invoice_embedding:
                    embedding_record = schemas.InvoiceEmbedding(
                        invoice_id=invoice.id,
                        user_id=user_id_value,
                        content_text=content_text,
                        embedding=invoice_embedding,
                        model_name=getattr(self.embedding_generator, "model_name", None),
                        embedding_type="invoice_full",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(embedding_record)
                    db.flush()
                    invoice_embedding_id = embedding_record.id
            except Exception as e:
                logger.exception("Error creating invoice embedding: %s", str(e))

            media_id = None
            if file_storage:
                media_id = self._upsert_media_record(
                    db=db,
                    user_id=user_id_value,
                    invoice_id=invoice.id,
                    file_storage=file_storage,
                    content_hash=content_hash,
                    extraction_result=extraction_result,
                )

            # Commit all changes
            db.commit()

            logger.info(f"Invoice stored in database with ID: {invoice.id}")

            # Return success information
            return {
                "status": "success",
                "invoice_id": str(invoice.id),
                "item_ids": item_ids,
                "media_id": str(media_id) if media_id else None,
                "invoice_embedding_id": str(invoice_embedding_id) if invoice_embedding_id else None,
                "invoice_number": invoice_number,
                "vendor": vendor_name,
                "total_amount": self._to_float(total_amount, 0.0)
            }

        except Exception as e:
            # Roll back on error
            db.rollback()
            if isinstance(e, IntegrityError):
                duplicate_result = self._duplicate_result_from_hash(db, user_id, extraction_result)
                if duplicate_result:
                    return duplicate_result
            logger.exception(f"Error storing invoice: {str(e)}")
            return {
                "status": "error",
                "error": f"Database error: {str(e)}"
            }
        finally:
            # Always close the session
            db.close()

    def _coerce_user_id(self, user_id: Union[str, UUID, int]) -> int:
        if isinstance(user_id, int):
            return user_id
        if isinstance(user_id, str) and user_id.isdigit():
            return int(user_id)
        raise ValueError(
            f"Invalid user_id '{user_id}'. The active schema uses integer user IDs."
        )

    def _get_file_storage(self, extraction_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        metadata = extraction_result.get("metadata") if isinstance(extraction_result, dict) else None
        if not isinstance(metadata, dict):
            return None
        storage = metadata.get("file_storage") or metadata.get("s3_storage")
        return storage if isinstance(storage, dict) else None

    def _extract_content_hash(
        self,
        extraction_result: Dict[str, Any],
        file_storage: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        metadata = extraction_result.get("metadata") if isinstance(extraction_result, dict) else {}
        file_metadata = metadata.get("file_metadata") if isinstance(metadata, dict) else {}
        for source in (file_storage, metadata, file_metadata):
            if isinstance(source, dict) and source.get("checksum_sha256"):
                return source["checksum_sha256"]
        return None

    def _duplicate_result_from_hash(
        self,
        db,
        user_id: Union[str, UUID, int],
        extraction_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        checksum = self._extract_content_hash(extraction_result)
        if not checksum:
            return None
        try:
            user_id_value = self._coerce_user_id(user_id)
            duplicate_media = (
                db.query(schemas.Media)
                .filter(
                    schemas.Media.user_id == user_id_value,
                    schemas.Media.content_hash == checksum,
                )
                .order_by(schemas.Media.created_at.desc())
                .first()
            )
        except Exception:
            return None
        if not duplicate_media:
            return None
        return {
            "status": "duplicate",
            "duplicate": True,
            "invoice_id": str(duplicate_media.invoice_id) if duplicate_media.invoice_id else None,
            "item_ids": [],
            "media_id": str(duplicate_media.id),
            "invoice_embedding_id": None,
            "invoice_number": None,
            "vendor": None,
            "total_amount": 0,
            "content_hash": checksum,
        }

    def _upsert_media_record(
        self,
        db,
        user_id: int,
        invoice_id: int,
        file_storage: Dict[str, Any],
        content_hash: Optional[str],
        extraction_result: Dict[str, Any],
    ) -> Optional[int]:
        """Link an existing original upload row to the invoice, or create it."""

        media_record = None
        media_id = file_storage.get("media_id")
        try:
            if media_id is not None:
                media_record = (
                    db.query(schemas.Media)
                    .filter(schemas.Media.id == int(media_id), schemas.Media.user_id == user_id)
                    .first()
                )
        except (TypeError, ValueError):
            media_record = None

        if media_record is None and content_hash:
            media_record = (
                db.query(schemas.Media)
                .filter(
                    schemas.Media.user_id == user_id,
                    schemas.Media.content_hash == content_hash,
                )
                .order_by(schemas.Media.created_at.desc())
                .first()
            )

        file_path = file_storage.get("file_key") or file_storage.get("path") or ""
        if media_record is None and file_path:
            media_record = (
                db.query(schemas.Media)
                .filter(schemas.Media.user_id == user_id, schemas.Media.file_path == file_path)
                .first()
            )

        if media_record is None:
            media_record = schemas.Media(
                user_id=user_id,
                filename=file_storage.get("original_filename", "invoice"),
                original_filename=file_storage.get("original_filename", "invoice"),
                file_path=file_path,
                file_url=file_storage.get("url", ""),
                content_hash=content_hash,
                content_type=file_storage.get("content_type", "application/octet-stream"),
                file_size=file_storage.get("file_size") or extraction_result.get("file_size", 0),
                file_type=self._media_file_type(file_storage.get("content_type")),
                created_at=datetime.utcnow(),
            )
            db.add(media_record)

        media_record.invoice_id = invoice_id
        media_record.filename = file_storage.get("original_filename") or media_record.filename
        media_record.original_filename = file_storage.get("original_filename") or media_record.original_filename
        media_record.file_path = file_path or media_record.file_path
        media_record.file_url = file_storage.get("url") or media_record.file_url
        media_record.content_hash = content_hash or media_record.content_hash
        media_record.content_type = file_storage.get("content_type") or media_record.content_type
        media_record.file_size = file_storage.get("file_size") or media_record.file_size
        media_record.file_type = self._media_file_type(media_record.content_type)
        media_record.status = "processed"
        existing_metadata = (
            media_record.processing_metadata
            if isinstance(media_record.processing_metadata, dict)
            else {}
        )
        media_record.processing_metadata = {
            **existing_metadata,
            "file_storage": file_storage,
            "access_scope": file_storage.get("access_scope") or "user",
            "user_scope_prefix": file_storage.get("user_scope_prefix"),
            "processing_status": "processed",
        }
        media_record.updated_at = datetime.utcnow()
        db.flush()
        return media_record.id

    def _extract_vendor_name(self, invoice_data: Dict[str, Any]) -> str:
        vendor_data = invoice_data.get("vendor", {})
        if isinstance(vendor_data, dict):
            vendor_name = (
                vendor_data.get("name")
                or vendor_data.get("vendor_name")
                or vendor_data.get("company")
            )
        else:
            vendor_name = vendor_data
        vendor_text = str(vendor_name or "").strip()
        return vendor_text or "Unknown Vendor"

    def _extract_transaction_fields(self, invoice_data: Dict[str, Any]) -> tuple[Optional[str], Optional[datetime]]:
        transaction_data = invoice_data.get("transaction", {})
        transaction = transaction_data if isinstance(transaction_data, dict) else {}
        invoice_number = (
            transaction.get("invoice_number")
            or transaction.get("receipt_no")
            or transaction.get("receipt_number")
            or invoice_data.get("invoice_number")
            or invoice_data.get("receipt_no")
            or invoice_data.get("receipt_number")
        )
        invoice_date = self._parse_date(
            transaction.get("date")
            or transaction.get("invoice_date")
            or invoice_data.get("invoice_date")
            or invoice_data.get("date")
        )
        return invoice_number, invoice_date

    def _extract_financial_fields(self, invoice_data: Dict[str, Any]) -> tuple[float, str, Optional[float]]:
        financial_data = invoice_data.get("financial", {})
        financial = financial_data if isinstance(financial_data, dict) else {}
        additional_info = invoice_data.get("additional_info", {})
        additional = additional_info if isinstance(additional_info, dict) else {}

        total_amount = self._first_float(
            financial.get("total"),
            financial.get("total_amount"),
            invoice_data.get("total_amount"),
            invoice_data.get("total"),
            financial.get("subtotal"),
        )
        currency = (
            financial.get("currency")
            or invoice_data.get("currency")
            or additional.get("currency")
            or "INR"
        )
        return total_amount if total_amount is not None else 0.0, str(currency or "INR")[:3], self._extract_tax_amount(financial)

    def _extract_notes(self, invoice_data: Dict[str, Any], extraction_result: Dict[str, Any]) -> str:
        additional_info = invoice_data.get("additional_info", {})
        notes = additional_info.get("notes", "") if isinstance(additional_info, dict) else ""
        metadata = extraction_result.get("metadata", {}) if isinstance(extraction_result, dict) else {}
        if isinstance(metadata, dict) and metadata.get("extraction_error"):
            error_note = f"Extraction warning: {metadata['extraction_error']}"
            notes = f"{notes}\n{error_note}".strip() if notes else error_note
        return notes

    def _build_raw_data(self, invoice_data: Dict[str, Any], extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        raw_data = self._json_safe(invoice_data)
        metadata = extraction_result.get("metadata", {}) if isinstance(extraction_result, dict) else {}
        if isinstance(raw_data, dict) and isinstance(metadata, dict):
            file_metadata = metadata.get("file_metadata")
            raw_data["_extraction"] = self._json_safe(
                {
                    "file_type": extraction_result.get("file_type"),
                    "file_path": extraction_result.get("file_path"),
                    "checksum_sha256": metadata.get("checksum_sha256"),
                    "file_metadata": file_metadata if isinstance(file_metadata, dict) else None,
                    "status": metadata.get("extraction_status"),
                    "confidence": metadata.get("extraction_confidence"),
                    "error": metadata.get("extraction_error"),
                    "raw_result": metadata.get("raw_extraction_result"),
                }
            )
        return raw_data if isinstance(raw_data, dict) else {"value": raw_data}

    def _extract_tax_amount(self, financial_data: Any) -> Optional[float]:
        if not isinstance(financial_data, dict):
            return None
        tax_data = financial_data.get("tax")
        if isinstance(tax_data, dict):
            for key in ("amount", "total", "tax_amount"):
                if tax_data.get(key) is not None:
                    return self._to_float(tax_data[key])
        if financial_data.get("tax_amount") is not None:
            return self._to_float(financial_data["tax_amount"])
        if financial_data.get("tax") is not None:
            return self._to_float(financial_data["tax"])
        return None

    def _build_invoice_embedding_text(self, invoice_data: Dict[str, Any]) -> str:
        vendor_name = self._extract_vendor_name(invoice_data)
        invoice_number, _ = self._extract_transaction_fields(invoice_data)
        total, _, _ = self._extract_financial_fields(invoice_data)
        items = invoice_data.get("items") or []
        item_text = "; ".join(
            " ".join(
                str(part)
                for part in [
                    item.get("transaction_date") or item.get("raw_date") or item.get("item_code"),
                    item.get("entry_type"),
                    item.get("description") or item.get("name") or "",
                    item.get("total_price") or item.get("amount"),
                ]
                if part not in (None, "")
            )
            for item in items
            if isinstance(item, dict) and (item.get("description") or item.get("name"))
        )
        return " | ".join(
            str(part)
            for part in [vendor_name, invoice_number, total, item_text]
            if part not in (None, "")
        )

    def _media_file_type(self, content_type: Optional[str]) -> str:
        value = (content_type or "").lower()
        if "image" in value:
            return "image"
        if "pdf" in value:
            return "pdf"
        if "spreadsheet" in value or "excel" in value:
            return "excel"
        if "word" in value:
            return "word"
        if "text" in value:
            return "text"
        return "other"

    def _first_float(self, *values: Any) -> Optional[float]:
        for value in values:
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _to_float(self, value: Any, default: Optional[float] = None) -> Optional[float]:
        parsed = self._first_float(value)
        return parsed if parsed is not None else default

    def _parse_date(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if not value:
            return None
        text = str(value).strip()
        for parser in (
            lambda candidate: datetime.fromisoformat(candidate.replace("Z", "+00:00")),
            lambda candidate: datetime.strptime(candidate, "%Y-%m-%d"),
            lambda candidate: datetime.strptime(candidate, "%d-%m-%Y"),
            lambda candidate: datetime.strptime(candidate, "%m/%d/%Y"),
            lambda candidate: datetime.strptime(candidate, "%d/%m/%Y"),
        ):
            try:
                return parser(text)
            except ValueError:
                continue
        logger.warning("Could not parse invoice date: %s", value)
        return None

    def _json_safe(self, value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))
