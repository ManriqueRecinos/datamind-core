"""Caso de uso para consultar archivos tabulares en memoria con DuckDB."""

import os
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import sqlglot

from app.infrastructure.database.models import ChatAttachmentModel
from app.infrastructure.analytics.attachment_analytics_engine import AttachmentAnalyticsEngine
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
import duckdb
import polars as pl


class QueryAttachmentUseCase:
    """
    Carga los archivos adjuntos en una conexión DuckDB en memoria aislada,
    construye el esquema para el prompt de Text-to-SQL y ejecuta la consulta segura.
    """

    def __init__(self, session: AsyncSession, ollama: Optional[OllamaAdapter] = None):
        self.session = session
        self.ollama = ollama or OllamaAdapter()

    async def get_attachments(self, attachment_ids: List[str]) -> List[ChatAttachmentModel]:
        uuids = []
        for aid in attachment_ids:
            try:
                uuids.append(uuid.UUID(str(aid)))
            except ValueError:
                continue

        if not uuids:
            return []

        stmt = select(ChatAttachmentModel).where(ChatAttachmentModel.id.in_(uuids))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    def mount_views_in_duckdb(
        self,
        conn: duckdb.DuckDBPyConnection,
        attachments: List[ChatAttachmentModel]
    ) -> Dict[str, str]:
        """
        Crea vistas temporales en DuckDB para cada archivo adjunto.
        Retorna mapeo {view_name: original_name}.
        """
        view_map = {}
        for att in attachments:
            clean_view = re.sub(r"[^\w]", "_", os.path.splitext(att.original_name)[0]).lower()
            if not clean_view or clean_view[0].isdigit():
                clean_view = f"t_{clean_view}"

            storage_p = att.storage_path.replace("\\", "/")
            ext = os.path.splitext(att.storage_path)[1].lower()

            if ext in {".csv", ".tsv"}:
                delim = "\t" if ext == ".tsv" else ","
                conn.execute(
                    f"CREATE VIEW {clean_view} AS SELECT * FROM read_csv_auto('{storage_p}', delim='{delim}', header=true)"
                )
            elif ext in {".xlsx", ".xls"}:
                df = pl.read_excel(att.storage_path, engine="calamine")
                conn.register(clean_view, df)
            elif ext in {".pdf", ".docx"}:
                # Para documentos de texto, extraer secciones y párrafos garantizando columnas (seccion, contenido, parrafo_id)
                sections = []
                paragraphs = []

                if ext == ".pdf":
                    from pypdf import PdfReader
                    reader = PdfReader(att.storage_path)
                    for page_num, page in enumerate(reader.pages, start=1):
                        txt = page.extract_text() or ""
                        page_paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
                        for p in page_paras:
                            sections.append(f"Página {page_num}")
                            paragraphs.append(p)
                else:
                    import docx
                    doc = docx.Document(att.storage_path)
                    current_section = "General"
                    for p in doc.paragraphs:
                        text_val = p.text.strip()
                        if not text_val:
                            continue
                        if p.style and p.style.name and "heading" in p.style.name.lower():
                            current_section = text_val
                        sections.append(current_section)
                        paragraphs.append(text_val)

                if not paragraphs:
                    sections = ["General"]
                    paragraphs = ["Documento sin texto legible"]

                df_doc = pl.DataFrame({
                    "parrafo_id": list(range(1, len(paragraphs) + 1)),
                    "seccion": sections,
                    "contenido": paragraphs
                })
                conn.register(clean_view, df_doc)

            view_map[clean_view] = att.original_name

        return view_map

    def build_schema_context(
        self,
        attachments: List[ChatAttachmentModel],
        view_map: Dict[str, str]
    ) -> str:
        lines = []
        for att in attachments:
            clean_view = next((v for v, orig in view_map.items() if orig == att.original_name), "archivo")
            cols = (att.schema_preview or {}).get("columns", [])
            col_str = ", ".join([f"{c['name']} ({c['type']})" for c in cols])
            lines.append(f"Vista: `{clean_view}` (Archivo origen: '{att.original_name}', total filas: {att.row_count or 'N/A'})\nColumnas: {col_str}")
        return "\n\n".join(lines)

    @staticmethod
    def clean_and_validate_sql(raw_sql: str) -> str:
        """
        Limpia y valida que la consulta sea un SELECT válido para DuckDB, forzando LIMIT 500.
        """
        clean_sql = re.sub(r"```(?:sql)?|```", "", raw_sql).strip()
        parsed = sqlglot.parse_one(clean_sql, read="duckdb")
        if not isinstance(parsed, sqlglot.exp.Select):
            raise ValueError("La consulta sobre el archivo debe ser estrictamente SELECT.")

        if not parsed.args.get("limit"):
            clean_sql = f"{clean_sql.rstrip(';')} LIMIT 500"
        return clean_sql

    async def generate_and_execute_query(
        self,
        prompt: str,
        attachments: List[ChatAttachmentModel]
    ) -> Tuple[str, Optional[str], List[Dict[str, Any]], int]:
        """
        Formula SQL para DuckDB, lo valida con sqlglot, lo ejecuta y retorna
        (message_text, generated_sql, rows, row_count).
        """
        conn = AttachmentAnalyticsEngine.get_sandboxed_duckdb_conn(allow_file_read=True)
        try:
            view_map = self.mount_views_in_duckdb(conn, attachments)
            schema_context = self.build_schema_context(attachments, view_map)

            sql_prompt = (
                f"Eres un analista de datos experto en DuckDB SQL.\n"
                f"El usuario adjuntó archivos o documentos convertidos en vistas SQL en DuckDB:\n"
                f"{schema_context}\n\n"
                f"REGLAS ESTRICTAS DE CONSULTA:\n"
                f"- Escribe ÚNICAMENTE una consulta SQL SELECT válida para DuckDB.\n"
                f"- No uses markdown, explicaciones ni comentarios.\n"
                f"- Usa únicamente las vistas y columnas definidas arriba.\n"
                f"- IMPORTANTE PARA DOCUMENTOS DE TEXTO: La columna 'contenido' contiene el texto completo de los párrafos y 'seccion' el número de página o título. Para buscar temas, palabras clave o aprender conceptos, usa SIEMPRE operadores de texto insensible a mayúsculas como `ILIKE '%termino%'` sobre la columna `contenido` (ej: `SELECT seccion, contenido FROM vista WHERE contenido ILIKE '%repuesto%' OR contenido ILIKE '%parte%' LIMIT 20`).\n"
                f"- NUNCA compares la columna 'seccion' con texto largo o conceptos mediante '=' exacto (ej: NO hagas `WHERE seccion = 'Proceso de Repuestos'`), porque las secciones son nombres como 'Página 1' o encabezados cortos. Busca en 'contenido'.\n\n"
                f"PREGUNTA DEL USUARIO: {prompt}\n"
                f"SQL DUCKDB:"
            )

            raw_sql = await self.ollama.generate_completion(sql_prompt, max_tokens=250, temperature=0.0)
            clean_sql = self.clean_and_validate_sql(raw_sql)

            # Ejecutar con timeout
            result_df = conn.execute(clean_sql).fetchdf()
            rows = result_df.to_dict(orient="records")
            row_count = len(rows)

            # Síntesis ejecutiva de la respuesta
            synth_prompt = (
                f"El usuario preguntó: '{prompt}' sobre los archivos adjuntos.\n"
                f"Se ejecutó la consulta SQL DuckDB: `{clean_sql}` y se obtuvieron {row_count} registros.\n"
                f"Muestra de datos: {str(rows[:5])}\n"
                f"Redacta una respuesta ejecutiva y concisa en español explicando los hallazgos en Markdown."
            )
            message_text = await self.ollama.generate_completion(synth_prompt, max_tokens=200, temperature=0.2)

            return message_text, clean_sql, rows, row_count
        finally:
            conn.close()
