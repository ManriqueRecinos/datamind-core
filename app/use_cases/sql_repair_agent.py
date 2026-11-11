"""Agente especializado en auto-reparación de sentencias SQL fallidas."""

import logging
from typing import Optional, Tuple
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.llm.sql_guardrail import SQLGuardrail

logger = logging.getLogger(__name__)


class SqlRepairAgent:
    """Corrige consultas SQL fallidas retroalimentando el error exacto del motor de base de datos."""

    def __init__(self, ollama: Optional[OllamaAdapter] = None, guardrail: Optional[SQLGuardrail] = None):
        self.ollama = ollama or OllamaAdapter()
        self.guardrail = guardrail or SQLGuardrail(max_limit=500)

    async def attempt_repair(
        self,
        original_prompt: str,
        failed_sql: str,
        error_details: str,
        schema_context: str,
        dialect: str = "mysql",
        engine_title: str = "MariaDB/MySQL"
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Genera una versión corregida del SQL considerando el error exacto reportado.
        Retorna: (is_repaired, safe_sql, error_or_reason)
        """
        repair_prompt = (
            f"Eres un analista experto en SQL para {engine_title}.\n"
            f"La siguiente consulta SQL generó un error en el motor de base de datos y debe ser reparada con precisión.\n\n"
            f"SOLICITUD ORIGINAL DEL USUARIO:\n{original_prompt}\n\n"
            f"CONSULTA SQL FALLIDA:\n{failed_sql}\n\n"
            f"MENSAJE DE ERROR REPORTADO POR LA BASE DE DATOS:\n{error_details}\n\n"
            f"ESQUEMA Y COLUMNAS REALES DISPONIBLES:\n{schema_context}\n\n"
            f"INSTRUCCIONES DE CORRECCIÓN:\n"
            f"1. Analiza el error exacto (ej: columna desconocida, nombre de tabla mal escrito, alias ambiguo o función no admitida).\n"
            f"2. Utiliza estrictamente las columnas y tablas existentes mostradas en el esquema.\n"
            f"3. Si una columna fue mal nombrada, sustitúyela por la columna correcta según el esquema.\n"
            f"4. Devuelve ÚNICAMENTE la sentencia SQL SELECT corregida y ejecutable, sin explicaciones ni bloques de comentarios.\n\n"
            f"CONSULTA SQL CORREGIDA:"
        )

        try:
            raw_repaired_sql = await self.ollama.generate_completion(
                prompt=repair_prompt,
                max_tokens=300,
                temperature=0.0
            )

            is_valid, safe_sql, guardrail_err = self.guardrail.validate_and_sanitize(raw_repaired_sql, dialect=dialect)
            if not is_valid:
                return False, None, f"Guardrail rechazó el SQL reparado: {guardrail_err}"

            return True, safe_sql, None
        except Exception as e:
            logger.error(f"Excepción durante auto-reparación de SQL: {str(e)}")
            return False, None, str(e)
