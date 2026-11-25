"""Pruebas unitarias para allowlist de tablas vectorizadas en SQLGuardrail."""

from app.infrastructure.llm.sql_guardrail import SQLGuardrail


def test_guardrail_allows_vectorized_table():
    guardrail = SQLGuardrail(max_limit=500)
    ok, safe_sql, err = guardrail.validate_and_sanitize(
        "SELECT nom_rollo, cant_rollo FROM cant_rollo LIMIT 10",
        allowed_tables={"cant_rollo", "rollo"},
    )
    assert ok is True
    assert err == ""
    assert "cant_rollo" in safe_sql


def test_guardrail_blocks_non_vectorized_table():
    guardrail = SQLGuardrail(max_limit=500)
    ok, safe_sql, err = guardrail.validate_and_sanitize(
        "SELECT * FROM tabla_secreta_no_vectorizada LIMIT 10",
        allowed_tables={"cant_rollo", "rollo"},
    )
    assert ok is False
    assert "tabla_secreta_no_vectorizada" in err
