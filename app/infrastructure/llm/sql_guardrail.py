"""Validador y guardrail de seguridad para sentencias SQL generadas por la IA."""

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

    def validate_and_sanitize(self, raw_sql: str, dialect: str = "mysql") -> Tuple[bool, str, str]:
        """
        Valida que la consulta sea estrictamente un SELECT y fuerza la cláusula LIMIT.
        Soporta dialectos 'mysql' (MariaDB/MySQL) y 'postgres' (PostgreSQL).
        Retorna: (es_valido, sql_limpio, mensaje_error)
        """
        target_dialect = "postgres" if dialect.lower() in ("postgres", "postgresql", "pgsql") else "mysql"
        cleaned = raw_sql.strip()
        # Eliminar bloques markdown como ```sql ... ```
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

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
