"""Pruebas unitarias para la herramienta segura `ejecutar_sql`."""

import pytest

from app.infrastructure.llm.sql_tool import EJECUTAR_SQL_TOOL_SCHEMA, execute_sql_tool


class FakeDbAdapter:
    async def execute_query(self, sql: str):
        return [{"id": 1, "total": 100}]


@pytest.mark.asyncio
async def test_execute_sql_tool_allows_select():
    res = await execute_sql_tool("SELECT id, total FROM ventas LIMIT 10", FakeDbAdapter())
    assert res["ok"] is True
    assert res["row_count"] == 1
    assert "LIMIT" in res["sql"].upper()


@pytest.mark.asyncio
async def test_execute_sql_tool_blocks_drop():
    res = await execute_sql_tool("DROP TABLE ventas", FakeDbAdapter())
    assert res["ok"] is False
    assert "seguridad" in res["error"].lower()


def test_tool_schema_has_ejecutar_sql():
    assert EJECUTAR_SQL_TOOL_SCHEMA["function"]["name"] == "ejecutar_sql"
    assert "query" in EJECUTAR_SQL_TOOL_SCHEMA["function"]["parameters"]["properties"]
