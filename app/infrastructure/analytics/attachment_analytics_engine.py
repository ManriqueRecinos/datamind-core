"""Motor de analítica local en CPU para archivos tabulares (DuckDB + Polars Calamine)."""

import os
import re
from typing import Dict, Any, List, Tuple
import duckdb
import polars as pl
from app.infrastructure.security.file_security_validator import FileSecurityValidator


class AttachmentAnalyticsEngine:
    """
    Gestiona la lectura en streaming real de CSV/TSV y lectura completa en memoria de XLSX/XLS
    mediante Polars y Calamine, con sandbox seguro y extracción de esquema.
    """

    MAX_ROWS_EXCEL = 50000

    @classmethod
    def get_sandboxed_duckdb_conn(cls, allow_file_read: bool = False) -> duckdb.DuckDBPyConnection:
        """Crea una conexión DuckDB en memoria aislada. Si allow_file_read es False, bloquea acceso al FS."""
        conn = duckdb.connect(database=":memory:")
        if not allow_file_read:
            conn.execute("SET enable_external_access = false;")
        conn.execute("SET max_memory = '256MB';")
        conn.execute("SET threads = 2;")
        return conn

    @classmethod
    def process_and_inspect_file(
        cls,
        file_path: str,
        mime_type: str
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Lee el archivo con DuckDB o Polars/Calamine, extrae el número de filas y las columnas inferidas.
        Retorna (row_count, schema_preview_dict).
        """
        ext = os.path.splitext(file_path)[1].lower()

        # 1. Procesamiento CSV / TSV con DuckDB (lectura en streaming con read_csv_auto)
        if ext in {".csv", ".tsv"}:
            conn = cls.get_sandboxed_duckdb_conn(allow_file_read=True)
            # En DuckDB podemos consultar directamente read_csv_auto con limit
            escaped_path = file_path.replace("\\", "/")
            delim = "\t" if ext == ".tsv" else ","

            # Obtener conteo y tipos
            cnt_res = conn.execute(
                f"SELECT count(*) FROM read_csv_auto('{escaped_path}', delim='{delim}', header=true)"
            ).fetchone()
            total_rows = int(cnt_res[0]) if cnt_res else 0

            # Obtener columnas y muestra de filas
            sample_df = conn.execute(
                f"SELECT * FROM read_csv_auto('{escaped_path}', delim='{delim}', header=true) LIMIT 5"
            ).fetchdf()

            columns = []
            for col in sample_df.columns:
                dtype = str(sample_df[col].dtype)
                norm_type = cls._normalize_dtype(dtype)
                clean_name = cls._clean_column_name(col)
                sample_vals = [
                    FileSecurityValidator.sanitize_cell_value(v)
                    for v in sample_df[col].dropna().tolist()[:5]
                ]
                columns.append({
                    "name": clean_name,
                    "type": norm_type,
                    "sample_values": sample_vals
                })

            sample_rows = sample_df.to_dict(orient="records")
            conn.close()

            return total_rows, {
                "columns": columns,
                "sample_rows": sample_rows,
                "total_rows": total_rows
            }

        # 2. Procesamiento XLSX / XLS con Polars + Calamine
        elif ext in {".xlsx", ".xls"}:
            # Validar Zip-Bomb primero
            FileSecurityValidator.check_zip_bomb(file_path)

            try:
                # Polars con motor calamine
                df = pl.read_excel(file_path, engine="calamine")
            except Exception as e:
                # Fallback a motor estándar
                df = pl.read_excel(file_path)

            total_rows = len(df)
            if total_rows > cls.MAX_ROWS_EXCEL:
                raise ValueError(
                    f"El archivo Excel contiene {total_rows:,} filas, superando el límite máximo permitido de {cls.MAX_ROWS_EXCEL:,} filas."
                )

            columns = []
            sample_df = df.head(5)
            for col in df.columns:
                dtype = str(df[col].dtype)
                norm_type = cls._normalize_dtype(dtype)
                clean_name = cls._clean_column_name(col)
                sample_vals = [
                    FileSecurityValidator.sanitize_cell_value(v)
                    for v in df[col].drop_nulls().head(5).to_list()
                ]
                columns.append({
                    "name": clean_name,
                    "type": norm_type,
                    "sample_values": sample_vals
                })

            sample_rows = sample_df.to_dicts()

            return total_rows, {
                "columns": columns,
                "sample_rows": sample_rows,
                "total_rows": total_rows
            }

        # 3. Procesamiento Documental No Estructurado (PDF y DOCX) - Fase 2
        elif ext in {".pdf", ".docx"}:
            if ext == ".docx":
                FileSecurityValidator.check_zip_bomb(file_path)

            extracted_text = ""
            page_or_para_count = 0

            if ext == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                page_or_para_count = len(reader.pages)
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        extracted_text += txt + "\n\n"
            else:
                import docx
                doc = docx.Document(file_path)
                page_or_para_count = len(doc.paragraphs)
                extracted_text = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])

            char_count = len(extracted_text)
            clean_excerpt = extracted_text[:500].strip()

            return page_or_para_count, {
                "document_type": "text_document",
                "page_or_para_count": page_or_para_count,
                "character_count": char_count,
                "excerpt": clean_excerpt,
                "columns": [
                    {"name": "parrafo_id", "type": "INTEGER", "sample_values": [1, 2, 3]},
                    {"name": "seccion", "type": "TEXT", "sample_values": ["Página 1", "Página 2"]},
                    {"name": "contenido", "type": "TEXT", "sample_values": [clean_excerpt[:120] + "..."]}
                ],
                "sample_rows": [{"parrafo_id": 1, "seccion": "Página 1", "contenido": clean_excerpt[:200]}],
                "total_rows": page_or_para_count
            }

        else:
            raise ValueError(f"Formato de archivo no soportado: {ext}")

    @staticmethod
    def _clean_column_name(col_name: str) -> str:
        """Limpia el nombre de la columna para que sea un identificador SQL seguro y legible."""
        clean = re.sub(r"[^\w\s]", "", str(col_name).strip())
        clean = re.sub(r"\s+", "_", clean).lower()
        return clean or "columna"

    @staticmethod
    def _normalize_dtype(dtype: str) -> str:
        d = dtype.lower()
        if "int" in d:
            return "INTEGER"
        if "float" in d or "double" in d or "decimal" in d:
            return "DECIMAL"
        if "date" in d or "time" in d:
            return "DATE"
        if "bool" in d:
            return "BOOLEAN"
        return "TEXT"
