"""Pruebas unitarias para GeminiAdapter."""

import pytest
import httpx

from app.infrastructure.llm.gemini_adapter import GeminiAdapter, GeminiError


@pytest.mark.asyncio
async def test_generate_completion_missing_key():
    adapter = GeminiAdapter(api_key="")
    with pytest.raises(GeminiError, match="GEMINI_API_KEY"):
        await adapter.generate_completion("Hola")


@pytest.mark.asyncio
async def test_generate_completion_success(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "Hola desde Gemini"}]}}
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, params=None, json=None):
            assert "gemini-2.5-flash:generateContent" in url
            assert params == {"key": "test-key"}
            assert json["systemInstruction"]["parts"][0]["text"] == "Eres útil"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    adapter = GeminiAdapter(api_key="test-key", model="gemini-2.5-flash")
    result = await adapter.generate_completion("Hola", system_prompt="Eres útil")
    assert result == "Hola desde Gemini"


@pytest.mark.asyncio
async def test_generate_completion_http_error(monkeypatch):
    req = httpx.Request("POST", "https://example.com")
    resp = httpx.Response(401, text="Unauthorized", request=req)

    class FakeResponse:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("401", request=req, response=resp)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    adapter = GeminiAdapter(api_key="bad-key")
    with pytest.raises(GeminiError, match="Gemini HTTP 401"):
        await adapter.generate_completion("Hola")
