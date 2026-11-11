"""Validador y guardrail de seguridad para sentencias SQL generadas por la IA."""

import re
from typing import Tuple
import sqlglot
from sqlglot import exp


class SQLSecurityViolation(Exception):
    """Excepción lanzada cuando una consulta SQL generada viola las políticas de seguridad."""
    pass


class SQLGuardrail:
    """Inspecciona el árbol sintáctico abstracto (AST) de las consultas para MariaDB/MySQL."""

    FORBIDDEN_EXPRESSIONS = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.TruncateTable,
        exp.Command,
    )

    def __init__(self, max_limit: int = 500):
        self.max_limit = max_limit

    @staticmethod
    def extract_sql_query(raw_text: str) -> str:
        """
        Extrae limpiamente la sentencia SQL de la respuesta del LLM, descartando
        cualquier texto conversacional previo o posterior (ej. 'Para responder... ```sql ... ```').
        """
        if not raw_text:
            return ""

        # 1. Buscar bloques con sintaxis de código ```sql ... ``` o ``` ... ```
        code_block_match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE)
        if code_block_match:
            candidate = code_block_match.group(1).strip()
            if candidate:
                return candidate

        # 2. Si no hay bloques de código delimitados, buscar el primer SELECT hasta el final o punto y coma
        select_match = re.search(r"(?i)\b(SELECT\s+[\s\S]+)", raw_text)
        if select_match:
            candidate = select_match.group(1).strip()
            # Si hay texto explicativo después del punto y coma, cortarlo
            if ";" in candidate:
                candidate = candidate.split(";")[0].strip() + ";"
            return candidate

        return raw_text.strip()

    def validate_and_sanitize(self, raw_sql: str, dialect: str = "mysql") -> Tuple[bool, str, str]:
        """
        Valida que la consulta sea estrictamente un SELECT y fuerza la cláusula LIMIT.
        Soporta dialectos 'mysql' (MariaDB/MySQL) y 'postgres' (PostgreSQL).
        Retorna: (es_valido, sql_limpio, mensaje_error)
        """
        target_dialect = "postgres" if dialect.lower() in ("postgres", "postgresql", "pgsql") else "mysql"
        
        # Extraer únicamente el bloque SQL
        cleaned = self.extract_sql_query(raw_sql)

        if not cleaned:
            return False, "", "La consulta SQL está vacía."

        try:
            parsed = sqlglot.parse_one(cleaned, read=target_dialect)
        except Exception:
            try:
                parsed = sqlglot.parse_one(cleaned)
            except Exception as e:
                return False, "", f"Error de sintaxis SQL: {str(e)}"

        # Verificar que la raíz del árbol sea un SELECT
        if not isinstance(parsed, exp.Select):
            return False, "", "Únicamente se permiten consultas de lectura (SELECT)."

        # Inspeccionar si hay mutaciones anidadas en subconsultas
        for forbidden in self.FORBIDDEN_EXPRESSIONS:
            if parsed.find(forbidden):
                return False, "", f"Operación prohibida detectada: {forbidden.__name__}."

        # Inspeccionar o forzar la cláusula LIMIT
        limit_exp = parsed.args.get("limit")
        if limit_exp is None:
            parsed = parsed.limit(self.max_limit)
        else:
            try:
                current_limit = int(limit_exp.expression.this)
                if current_limit > self.max_limit:
                    parsed = parsed.limit(self.max_limit)
            except Exception:
                parsed = parsed.limit(self.max_limit)

        safe_sql = parsed.sql(dialect=target_dialect)
        return True, safe_sql, ""
