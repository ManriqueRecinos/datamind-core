"""Validación Extremo a Extremo de los 4 Escenarios del Quickstart (Fase 8)."""

import io
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import httpx
import openpyxl
from app.infrastructure.database.models import QueryDatasetModel
from app.infrastructure.database.postgres_adapter import AsyncSessionLocal
from app.infrastructure.llm.sql_guardrail import SQLGuardrail
from app.main import app


@pytest.mark.asyncio
async def test_scenario_1_corporate_process_knowledge_ingestion():
    """Escenario 1: Ingesta de manual de procesos y vectorización con pgvector."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "title": "Manual de Control de Calidad en Ensamble",
            "category": "process_manual",
            "department": "Calidad",
            "content": "Si una orden de ensamble presenta una desviación mayor a 5 horas o piezas defectuosas, debe marcarse como RECHAZADO y notificarse al supervisor de turno."
        }
        res = await client.post("/api/v1/knowledge/ingest", json=payload)
        assert res.status_code == 201, f"Error en ingesta: {res.text}"
        data = res.json()
        assert data["status"] == "indexed"
        assert data["chunks_created"] >= 1
        assert "document_id" in data

        # Validar búsqueda semántica inmediata
        search_payload = {
            "query": "desviación mayor a 5 horas en ensamble y piezas defectuosas",
            "top_k": 2,
            "category": "process_manual"
        }
        search_res = await client.post("/api/v1/knowledge/search", json=search_payload)
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert search_data["total_results"] >= 1
        assert "RECHAZADO" in search_data["results"][0]["chunk_text"]


@pytest.mark.asyncio
async def test_scenario_2_conversational_chat_and_stream():
    """Escenario 2: Conversación interactiva con RAG y streaming SSE."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Consulta conversacional síncrona
        chat_req = {
            "prompt": "¿Qué procedimiento debo seguir si una orden de ensamble presenta desviación mayor a 5 horas?"
        }
        res = await client.post("/api/v1/chat", json=chat_req)
        assert res.status_code == 200
        data = res.json()
        assert "message" in data
        assert len(data["message"]) > 0
        assert "session_id" in data
        assert data["intent"] in ["process_qa", "general_chat", "data_query"]

        # Consulta con streaming SSE
        stream_req = {
            "prompt": "Hola, ¿cuáles son los procedimientos de calidad en ensamble?",
            "session_id": data["session_id"]
        }
        async with client.stream("POST", "/api/v1/chat/stream", json=stream_req) as stream_res:
            assert stream_res.status_code == 200
            assert "text/event-stream" in stream_res.headers["content-type"]
            events = []
            async for line in stream_res.aiter_lines():
                if line.startswith("event:"):
                    events.append(line.split(":")[1].strip())
            assert "session" in events
            assert "token" in events
            assert "done" in events


@pytest.mark.asyncio
async def test_scenario_3_on_demand_excel_generation():
    """Escenario 3: Generación manual y descarga de reporte Excel estilizado (.xlsx)."""
    dataset_id = f"ds_qs_{uuid.uuid4().hex[:8]}"
    # Insertar dataset simulando resultado de MariaDB
    async with AsyncSessionLocal() as session:
        ds = QueryDatasetModel(
            dataset_id=dataset_id,
            sql_executed="SELECT id_orden, codigo_proceso, horas_retraso FROM ordenes_proceso WHERE horas_retraso > 2",
            columns=["id_orden", "codigo_proceso", "horas_retraso"],
            rows=[
                {"id_orden": 101, "codigo_proceso": "CORTE", "horas_retraso": 4.5},
                {"id_orden": 102, "codigo_proceso": "ENSAMBLE", "horas_retraso": 12.0},
                {"id_orden": 103, "codigo_proceso": "COSTURA", "horas_retraso": 6.2}
            ],
            row_count=3,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
        )
        session.add(ds)
        await session.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/export/excel/{dataset_id}")
        assert res.status_code == 200
        assert "application/vnd.openxmlformats" in res.headers["content-type"]
        assert 'attachment; filename="datamind_report_' in res.headers["content-disposition"]

        # Validar estructura y estilos del Excel con openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        sheet = wb.active
        # Banner de título
        assert "Reporte" in str(sheet["A1"].value)
        # Cabeceras en fila 4
        assert sheet["A4"].value == "ID ORDEN"
        assert sheet["B4"].value == "CODIGO PROCESO"
        assert sheet["C4"].value == "HORAS RETRASO"
        # Datos a partir de fila 5
        assert sheet["A5"].value == 101
        assert sheet["B5"].value == "CORTE"
        assert sheet["C5"].value == 4.5
        # Formato de celda cabecera (negrita y color azul DataMind #0468BF)
        assert sheet["A4"].font.bold is True
        assert sheet["A4"].fill.start_color.rgb in ["000468BF", "0468BF", "FF0468BF", "001E3A8A", "1E3A8A"]


def test_scenario_4_sql_guardrail_protection():
    """Escenario 4: Prueba de seguridad AST para rechazar mutaciones DDL/DML."""
    guardrail = SQLGuardrail()

    # Intentos de mutación
    malicious_queries = [
        "DELETE FROM ordenes_proceso WHERE estado = 'CANCELADO'",
        "DROP TABLE ordenes_proceso",
        "UPDATE ordenes_proceso SET horas_retraso = 0 WHERE id_orden = 1",
        "INSERT INTO ordenes_proceso (codigo) VALUES ('HACK')",
        "TRUNCATE TABLE ordenes_proceso",
        "ALTER TABLE ordenes_proceso DROP COLUMN horas_retraso"
    ]

    for q in malicious_queries:
        is_valid, sanitized_sql, error_msg = guardrail.validate_and_sanitize(q)
        assert is_valid is False, f"La consulta maliciosa '{q}' no fue rechazada!"
        assert "consultas de lectura (SELECT)" in error_msg

    # Consulta SELECT legítima con inyección automática de LIMIT 500
    valid_query = "SELECT * FROM ordenes_proceso WHERE horas_retraso > 2"
    is_valid, sanitized_sql, error_msg = guardrail.validate_and_sanitize(valid_query)
    assert is_valid is True
    assert "LIMIT 500" in sanitized_sql
