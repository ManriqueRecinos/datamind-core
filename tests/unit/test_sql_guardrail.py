"""Pruebas unitarias para el guardrail AST de SQL (Fase 4)."""

import pytest
from app.infrastructure.llm.sql_guardrail import SQLGuardrail


@pytest.fixture
def guardrail():
    return SQLGuardrail(max_limit=500)


def test_allow_valid_select(guardrail):
    sql = "SELECT id, codigo, nombre FROM procesos WHERE activo = 1"
    is_valid, safe_sql, error = guardrail.validate_and_sanitize(sql)
    assert is_valid is True
    assert "LIMIT 500" in safe_sql
    assert error == ""


def test_enforce_max_limit_override(guardrail):
    sql = "SELECT * FROM procesos LIMIT 10000"
    is_valid, safe_sql, _ = guardrail.validate_and_sanitize(sql)
    assert is_valid is True
    assert "LIMIT 500" in safe_sql


def test_block_delete(guardrail):
    sql = "DELETE FROM procesos WHERE id = 5"
    is_valid, _, error = guardrail.validate_and_sanitize(sql)
    assert is_valid is False
    assert "Únicamente se permiten consultas de lectura" in error


def test_block_drop_table(guardrail):
    sql = "DROP TABLE ordenes_proceso"
    is_valid, _, error = guardrail.validate_and_sanitize(sql)
    assert is_valid is False


def test_block_update(guardrail):
    sql = "UPDATE procesos SET estado = 'CANCELADO' WHERE id = 1"
    is_valid, _, error = guardrail.validate_and_sanitize(sql)
    assert is_valid is False


def test_sanitize_markdown_codeblocks(guardrail):
    sql = "```sql\nSELECT id FROM inventario\n```"
    is_valid, safe_sql, _ = guardrail.validate_and_sanitize(sql)
    assert is_valid is True
    assert safe_sql.startswith("SELECT")
