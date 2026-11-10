"""Pruebas de contrato para el router de chat, historial de sesiones y análisis de gráficos."""

import pytest
import httpx
from app.main import app
from app.use_cases.ask_chat import AskChatUseCase


def test_analyze_columns_for_chart():
    columns = ["estado", "departamento", "total_ordenes", "monto_usd"]
    rows = [
        {"estado": "ACTIVO", "departamento": "CORTE", "total_ordenes": 12, "monto_usd": 1540.50},
        {"estado": "PENDIENTE", "departamento": "COSTURA", "total_ordenes": 8, "monto_usd": 920.00},
    ]
    cfg = AskChatUseCase.analyze_columns_for_chart(columns, rows, wants_chart=True, preferred_type="bar")
    assert cfg["wants_chart"] is True
    assert cfg["suggested_type"] == "bar"
    assert "estado" in cfg["dimension_columns"]
    assert "total_ordenes" in cfg["metric_columns"]
    assert "monto_usd" in cfg["metric_columns"]
    assert cfg["suggested_x"] == "estado"
    assert cfg["suggested_y"] == "total_ordenes"
    assert cfg["suggested_agg"] == "SUM"


@pytest.mark.asyncio
async def test_contract_chat_sync():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        req = {"prompt": "Hola, ¿cuál es tu función en DataMind AI?", "user_id": "test_user_99"}
        res = await client.post("/api/v1/chat", json=req)
        assert res.status_code == 200
        data = res.json()
        assert "message" in data
        assert "session_id" in data
        assert data["intent"] in ["general_chat", "process_qa"]


@pytest.mark.asyncio
async def test_contract_chat_stream():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        req = {"prompt": "Hola", "user_id": "test_user_stream"}
        async with client.stream("POST", "/api/v1/chat/stream", json=req) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            events_received = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    events_received.append(line.split(":")[1].strip())
            assert "session" in events_received
            assert "done" in events_received

