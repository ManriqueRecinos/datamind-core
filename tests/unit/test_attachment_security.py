import io
import pytest
from app.infrastructure.security.file_security_validator import FileSecurityValidator
from app.infrastructure.analytics.attachment_analytics_engine import AttachmentAnalyticsEngine


def test_validator_detects_csv_mime():
    header = b"id,nombre,precio\n1,tela,100\n"
    mime = FileSecurityValidator.detect_real_mime(header, "datos.csv")
    assert mime == "text/csv"


def test_validator_rejects_unsupported_extensions():
    with pytest.raises(Exception) as exc:
        FileSecurityValidator.detect_real_mime(b"fake", "archivo.exe")
    assert "Extensión no permitida" in str(exc.value.detail)


def test_validator_rejects_fake_xlsx():
    # Extensión .xlsx pero sin cabecera PK\x03\x04
    with pytest.raises(Exception) as exc:
        FileSecurityValidator.detect_real_mime(b"plain text file", "falso.xlsx")
    assert "no coincide con una firma válida" in str(exc.value.detail)


def test_validator_sanitizes_formula_injection():
    safe = FileSecurityValidator.sanitize_cell_value("=cmd|'/C calc'!A0")
    assert safe.startswith("'=")

    normal = FileSecurityValidator.sanitize_cell_value("Supertex")
    assert normal == "Supertex"


def test_duckdb_sandbox_connection():
    conn = AttachmentAnalyticsEngine.get_sandboxed_duckdb_conn()
    res = conn.execute("SELECT 1 + 1 AS resultado").fetchone()
    assert res[0] == 2
    conn.close()
