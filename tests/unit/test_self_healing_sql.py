"""Pruebas unitarias para el agente de auto-reparación de SQL y bucle de resiliencia."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.use_cases.sql_repair_agent import SqlRepairAgent
from app.infrastructure.llm.sql_guardrail import SQLGuardrail
from app.core.telemetry_resilience import ResilienceMetrics


@pytest.mark.asyncio
async def test_sql_repair_agent_success():
    """Valida que el agente de reparación corrija un SQL con columna errónea y respete el guardrail."""
    mock_ollama = MagicMock()
    # Simular que el LLM devuelve el SELECT corregido
    mock_ollama.generate_completion = AsyncMock(
        return_value="SELECT id_parte_maquina, nombre FROM hop.parte_maquina LIMIT 10;"
    )

    agent = SqlRepairAgent(ollama=mock_ollama)
    is_ok, safe_sql, err = await agent.attempt_repair(
        original_prompt="cuántos repuestos hay",
        failed_sql="SELECT id_parte, nombre FROM hop.parte_maquina;",
        error_details='no existe la columna "id_parte"',
        schema_context="Tabla: hop.parte_maquina (id_parte_maquina, nombre, codigo)",
        dialect="postgres",
        engine_title="PostgreSQL"
    )

    assert is_ok is True
    assert safe_sql is not None
    assert "id_parte_maquina" in safe_sql
    assert "LIMIT" in safe_sql
    assert err is None


@pytest.mark.asyncio
async def test_sql_repair_agent_rejects_unsafe():
    """Valida que si el LLM intenta generar una sentencia destructiva sea rechazada por el guardrail."""
    mock_ollama = MagicMock()
    mock_ollama.generate_completion = AsyncMock(
        return_value="DROP TABLE hop.parte_maquina;"
    )

    agent = SqlRepairAgent(ollama=mock_ollama)
    is_ok, safe_sql, err = await agent.attempt_repair(
        original_prompt="elimina la tabla",
        failed_sql="SELECT * FROM hop.parte_maquina",
        error_details="error",
        schema_context="Tabla: hop.parte_maquina",
        dialect="postgres",
        engine_title="PostgreSQL"
    )

    assert is_ok is False
    assert safe_sql is None
    assert "Guardrail rechazó" in err


def test_resilience_metrics_counters():
    """Prueba que los contadores atómicos sumen y calculen el porcentaje de éxito correctamente."""
    metrics = ResilienceMetrics()
    metrics.reset()

    metrics.inc_repair_attempts(2)
    metrics.inc_repair_success(1)
    metrics.inc_repair_exhausted(1)
    metrics.inc_clarifications_requested(3)
    metrics.inc_clarifications_resolved(2)

    data = metrics.get_metrics()
    assert data["sql_repair_attempts_total"] == 2
    assert data["sql_repair_success_total"] == 1
    assert data["sql_repair_exhausted_total"] == 1
    assert data["sql_repair_success_rate_pct"] == 50.0
    assert data["clarifications_requested_total"] == 3
    assert data["clarifications_resolved_total"] == 2
