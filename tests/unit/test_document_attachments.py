import io
import pytest
from app.infrastructure.security.file_security_validator import FileSecurityValidator
from app.infrastructure.analytics.attachment_analytics_engine import AttachmentAnalyticsEngine
from app.use_cases.query_attachment import QueryAttachmentUseCase


def test_validator_detects_pdf_and_docx():
    pdf_header = b"%PDF-1.4 header test"
    mime_pdf = FileSecurityValidator.detect_real_mime(pdf_header, "manual.pdf")
    assert mime_pdf == "application/pdf"

    docx_header = b"PK\x03\x04\x14\x00\x06\x00"
    mime_docx = FileSecurityValidator.detect_real_mime(docx_header, "procedimiento.docx")
    assert "wordprocessingml" in mime_docx


def test_validator_rejects_fake_pdf():
    fake_header = b"Not a real pdf header"
    with pytest.raises(Exception) as exc:
        FileSecurityValidator.detect_real_mime(fake_header, "malicioso.pdf")
    assert "no coincide con una firma válida" in str(exc.value.detail)


def test_attachment_analytics_processes_pdf_sample(tmp_path):
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf_file = tmp_path / "sample.pdf"
    with open(pdf_file, "wb") as f:
        writer.write(f)

    count, schema = AttachmentAnalyticsEngine.process_and_inspect_file(str(pdf_file), "application/pdf")
    assert count == 1
    assert schema["document_type"] == "text_document"
