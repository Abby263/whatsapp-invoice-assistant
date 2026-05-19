"""Document ingestion helpers for PDF/image extraction paths."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


logger = logging.getLogger(__name__)

DocumentKind = Literal[
    "digital_pdf",
    "scanned_pdf",
    "image",
    "spreadsheet",
    "unsupported",
]
PageSource = Literal["pdf_text", "render", "upload"]

DEFAULT_PDF_MAX_PAGES = 3
MIN_DIGITAL_TEXT_CHARS = 30


@dataclass(frozen=True)
class IngestedPage:
    page_number: int
    image_bytes: Optional[bytes] = None
    mime_type: str = "application/octet-stream"
    text: Optional[str] = None
    source: PageSource = "upload"


@dataclass(frozen=True)
class IngestedDocument:
    kind: DocumentKind
    pages: List[IngestedPage] = field(default_factory=list)
    page_count: int = 0
    pages_processed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


def get_pdf_max_pages() -> int:
    try:
        value = int(os.environ.get("PDF_MAX_PAGES", DEFAULT_PDF_MAX_PAGES))
    except (TypeError, ValueError):
        return DEFAULT_PDF_MAX_PAGES
    return max(1, value)


def ingest_document(
    content: bytes,
    *,
    content_type: Optional[str] = None,
    file_name: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> IngestedDocument:
    """Classify document bytes and prepare page text or images for LLM extraction."""

    if not isinstance(content, bytes) or not content:
        return IngestedDocument(kind="unsupported")

    if _looks_like_pdf(content, content_type, file_name):
        return _ingest_pdf(content, max_pages=max_pages or get_pdf_max_pages())

    if _looks_like_image(content, content_type, file_name):
        return IngestedDocument(
            kind="image",
            pages=[
                IngestedPage(
                    page_number=1,
                    image_bytes=content,
                    mime_type=_image_mime(content_type, file_name),
                    source="upload",
                )
            ],
            page_count=1,
            pages_processed=1,
            metadata={"ocr_sources": ["vision"]},
        )

    if _looks_like_spreadsheet(content_type, file_name):
        return IngestedDocument(kind="spreadsheet", metadata={"ocr_sources": []})

    return IngestedDocument(kind="unsupported")


def format_pdf_text_for_llm(document: IngestedDocument, file_name: str = "") -> str:
    """Build deterministic text input for a digital PDF extraction prompt."""

    lines = [
        "Extract this financial document from the PDF text layer.",
        "Return only the required JSON schema.",
    ]
    if file_name:
        lines.append(f"File: {file_name}")
    lines.append(
        f"Pages processed: {document.pages_processed} of {document.page_count or document.pages_processed}"
    )
    for page in document.pages:
        text = (page.text or "").strip()
        if not text:
            continue
        lines.extend(["", f"--- Page {page.page_number} ---", text])
    return "\n".join(lines).strip()


def _ingest_pdf(content: bytes, *, max_pages: int) -> IngestedDocument:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        logger.error("PyMuPDF is required for PDF ingestion: %s", exc)
        return IngestedDocument(
            kind="unsupported",
            metadata={"error": "pymupdf_not_installed", "ocr_sources": []},
        )

    try:
        with fitz.open(stream=content, filetype="pdf") as pdf:
            page_count = int(pdf.page_count)
            pages_to_process = min(max_pages, page_count)
            extracted_pages: List[IngestedPage] = []

            for index in range(pages_to_process):
                page = pdf.load_page(index)
                text = _clean_text(page.get_text("text") or "")
                extracted_pages.append(
                    IngestedPage(
                        page_number=index + 1,
                        text=text or None,
                        mime_type="text/plain",
                        source="pdf_text",
                    )
                )

            first_page_text = extracted_pages[0].text if extracted_pages else ""
            if _has_readable_text(first_page_text):
                return IngestedDocument(
                    kind="digital_pdf",
                    pages=extracted_pages,
                    page_count=page_count,
                    pages_processed=pages_to_process,
                    metadata={
                        "ocr_sources": ["pdf_text"],
                        "pdf_text_chars": sum(
                            len(page.text or "") for page in extracted_pages
                        ),
                    },
                )

            rendered_pages: List[IngestedPage] = []
            zoom = 200 / 72
            matrix = fitz.Matrix(zoom, zoom)
            for index in range(pages_to_process):
                page = pdf.load_page(index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                rendered_pages.append(
                    IngestedPage(
                        page_number=index + 1,
                        image_bytes=pixmap.tobytes("png"),
                        mime_type="image/png",
                        source="render",
                    )
                )

            return IngestedDocument(
                kind="scanned_pdf",
                pages=rendered_pages,
                page_count=page_count,
                pages_processed=pages_to_process,
                metadata={"ocr_sources": ["pdf_render", "vision"]},
            )
    except Exception as exc:
        logger.exception("PDF ingestion failed: %s", exc)
        return IngestedDocument(
            kind="unsupported",
            metadata={"error": str(exc), "ocr_sources": []},
        )


def _looks_like_pdf(
    content: bytes, content_type: Optional[str], file_name: Optional[str]
) -> bool:
    normalized_type = str(content_type or "").lower()
    normalized_name = str(file_name or "").lower()
    return (
        content.startswith(b"%PDF")
        or "pdf" in normalized_type
        or normalized_name.endswith(".pdf")
    )


def _looks_like_image(
    content: bytes, content_type: Optional[str], file_name: Optional[str]
) -> bool:
    normalized_type = str(content_type or "").lower()
    normalized_name = str(file_name or "").lower()
    if "image" in normalized_type or normalized_type in {"png", "jpg", "jpeg"}:
        return True
    if normalized_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return True
    return content.startswith(
        (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"RIFF")
    )


def _looks_like_spreadsheet(
    content_type: Optional[str], file_name: Optional[str]
) -> bool:
    normalized_type = str(content_type or "").lower()
    normalized_name = str(file_name or "").lower()
    return any(
        token in normalized_type
        for token in ("csv", "excel", "spreadsheet", "xlsx", "xls")
    ) or normalized_name.endswith((".csv", ".xls", ".xlsx"))


def _image_mime(content_type: Optional[str], file_name: Optional[str]) -> str:
    normalized = f"{content_type or ''} {file_name or ''}".lower()
    if "png" in normalized:
        return "image/png"
    if "webp" in normalized:
        return "image/webp"
    if "gif" in normalized:
        return "image/gif"
    return "image/jpeg"


def _clean_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)


def _has_readable_text(value: Optional[str]) -> bool:
    text = str(value or "").strip()
    if len(text) < MIN_DIGITAL_TEXT_CHARS:
        return False
    printable = sum(1 for char in text if char.isprintable() and not char.isspace())
    non_space = sum(1 for char in text if not char.isspace())
    if not non_space:
        return False
    return printable / non_space >= 0.85
