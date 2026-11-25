"""Definición y ejecutor seguro de la herramienta `ejecutar_sql(query)` para tool calling."""

from typing import Any, Dict, Optional, Set

from app.infrastructure.llm.sql_guardrail import SQLGuardrail

EJECUTAR_SQL_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ejecutar_sql",
        "description": (
            "Ejecuta una consulta SQL de solo lectura (SELECT) contra la base de datos conectada "
            "y devuelve las filas resultantes. Nunca usar para INSERT, UPDATE, DELETE, DROP o ALTER."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Sentencia SQL SELECT válida con LIMIT.",
                }
            },
            "required": ["query"],
        },
    },
}


async def execute_sql_tool(
    query: str,
    db_adapter: Any,
    max_limit: int = 500,
    allowed_tables: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Valida con SQLGuardrail y ejecuta la consulta SQL de solo lectura."""
    guardrail = SQLGuardrail(max_limit=max_limit)
    try:
        is_valid, safe_sql, error_msg = guardrail.validate_and_sanitize(
            query,
            allowed_tables=allowed_tables,
        )
        if not is_valid:
            return {"ok": False, "error": f"Consulta bloqueada por seguridad: {error_msg}"}
        rows = await db_adapter.execute_query(safe_sql)
        return {
            "ok": True,
            "sql": safe_sql,
            "row_count": len(rows),
            "rows": rows[:max_limit],
        }
    except ValueError as exc:
        return {"ok": False, "error": f"Consulta bloqueada por seguridad: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"Error al ejecutar SQL: {exc}"}
