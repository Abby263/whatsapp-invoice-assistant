from io import BytesIO

from PIL import Image, ImageDraw

from utils.document_ingest import ingest_document


def _digital_pdf_bytes(text: str = "Acme Supplies Invoice Total 123.45 INR") -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _png_bytes(text: str = "Receipt 123") -> bytes:
    image = Image.new("RGB", (480, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), text, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _scanned_pdf_bytes(page_count: int = 1) -> bytes:
    import fitz

    image_bytes = _png_bytes()
    document = fitz.open()
    for _ in range(page_count):
        page = document.new_page(width=480, height=240)
        page.insert_image(page.rect, stream=image_bytes)
    data = document.tobytes()
    document.close()
    return data


def test_ingest_document_classifies_digital_pdf_text_layer():
    document = ingest_document(
        _digital_pdf_bytes(),
        content_type="application/pdf",
        file_name="digital_invoice.pdf",
    )

    assert document.kind == "digital_pdf"
    assert document.page_count == 1
    assert document.pages_processed == 1
    assert document.pages[0].source == "pdf_text"
    assert "Acme Supplies" in document.pages[0].text
    assert document.pages[0].image_bytes is None


def test_ingest_document_renders_scanned_pdf_pages():
    document = ingest_document(
        _scanned_pdf_bytes(page_count=2),
        content_type="application/pdf",
        file_name="scan.pdf",
        max_pages=2,
    )

    assert document.kind == "scanned_pdf"
    assert document.page_count == 2
    assert document.pages_processed == 2
    assert len(document.pages) == 2
    assert document.pages[0].source == "render"
    assert document.pages[0].mime_type == "image/png"
    assert document.pages[0].image_bytes.startswith(b"\x89PNG")


def test_ingest_document_respects_pdf_page_limit():
    document = ingest_document(
        _scanned_pdf_bytes(page_count=3),
        content_type="application/pdf",
        file_name="scan.pdf",
        max_pages=1,
    )

    assert document.kind == "scanned_pdf"
    assert document.page_count == 3
    assert document.pages_processed == 1
    assert len(document.pages) == 1
