"""Pruebas de contrato para el router de chat (Fase 5)."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_contract_chat_sync():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        req = {"prompt": "Hola, ¿cuál es tu función en DataMind AI?"}
        res = await client.post("/api/v1/chat", json=req)
        assert res.status_code == 200
        data = res.json()
        assert "message" in data
        assert "session_id" in data
        assert data["intent"] in ["general_chat", "process_qa"]


@pytest.mark.asyncio
async def test_contract_chat_stream():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        req = {"prompt": "Hola"}
        async with client.stream("POST", "/api/v1/chat/stream", json=req) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            events_received = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    events_received.append(line.split(":")[1].strip())
            assert "session" in events_received
            assert "done" in events_received
