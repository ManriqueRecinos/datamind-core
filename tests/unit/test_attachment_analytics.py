import os
import io
import pytest
import polars as pl
from fastapi import HTTPException
from app.infrastructure.security.file_security_validator import FileSecurityValidator
from app.infrastructure.analytics.attachment_analytics_engine import AttachmentAnalyticsEngine
from app.use_cases.query_attachment import QueryAttachmentUseCase


def test_validator_detects_csv_and_tsv():
    csv_bytes = b"id,producto,precio\n1,Hilo,15.5\n2,Boton,2.0\n"
    mime_csv = FileSecurityValidator.detect_real_mime(csv_bytes, "datos.csv")
    assert mime_csv == "text/csv"

    tsv_bytes = b"id\tproducto\tprecio\n1\tHilo\t15.5\n"
    mime_tsv = FileSecurityValidator.detect_real_mime(tsv_bytes, "datos.tsv")
    assert mime_tsv == "text/tab-separated-values"


def test_validator_rejects_zip_bomb():
    import zipfile
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as z:
        # Añadir un archivo comprimido que descomprima a > 50MB
        z.writestr('xl/worksheets/sheet1.xml', b'0' * (55 * 1024 * 1024))
    
    bio.seek(0)
    with pytest.raises(HTTPException) as exc:
        FileSecurityValidator.check_zip_bomb(bio)
    assert exc.value.status_code == 413
    assert "Zip-Bomb" in exc.value.detail or "50 MB" in exc.value.detail


def test_duckdb_sandbox_prevents_filesystem_access():
    conn = AttachmentAnalyticsEngine.get_sandboxed_duckdb_conn()
    with pytest.raises(Exception):
        # Con enable_external_access = false, read_csv directo desde el filesystem local está bloqueado
        conn.execute("SELECT * FROM read_csv_auto('C:/Windows/win.ini')")
    conn.close()


def test_duckdb_registers_and_queries_csv_and_polars():
    conn = AttachmentAnalyticsEngine.get_sandboxed_duckdb_conn()
    
    # Crear un DataFrame Polars simulando lectura XLSX
    df = pl.DataFrame({
        "codigo": ["REP-001", "REP-002", "REP-003"],
        "stock": [120, 45, 0],
        "categoria": ["Mecanico", "Electrico", "Mecanico"]
    })
    
    conn.register("repuestos_polars", df)
    
    res = conn.execute("SELECT categoria, SUM(stock) as total_stock FROM repuestos_polars GROUP BY categoria ORDER BY total_stock DESC").fetchall()
    assert len(res) == 2
    assert res[0][0] == "Mecanico"
    assert res[0][1] == 120
    conn.close()


def test_clean_sql_and_limits():
    raw_sql = "SELECT id, nombre, total FROM ventas WHERE total > 100;"
    cleaned = QueryAttachmentUseCase.clean_and_validate_sql(raw_sql)
    assert "LIMIT 500" in cleaned
    assert "SELECT" in cleaned
