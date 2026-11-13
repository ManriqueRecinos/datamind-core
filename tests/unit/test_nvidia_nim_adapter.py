"""Pruebas del adaptador NVIDIA NIM y de la fábrica del cliente LLM (httpx simulado)."""

import json

import httpx
import pytest

from app.core.config import get_settings
from app.infrastructure.llm import llm_factory
from app.infrastructure.llm.nvidia_nim_adapter import NvidiaNimAdapter, NvidiaNimError
from app.infrastructure.llm.ollama_adapter import OllamaAdapter


def _patch_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr("app.infrastructure.llm.nvidia_nim_adapter.httpx.AsyncClient", factory)


def _adapter():
    return NvidiaNimAdapter(api_key="test-key", base_url="https://nim.test/v1", model="m", timeout=5)


async def test_completion_envia_system_y_user(monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "391"}}]})

    _patch_client(monkeypatch, handler)
    out = await _adapter().generate_completion("17*23", system_prompt="sé breve", max_tokens=50, temperature=0.1)

    assert out == "391"
    assert captured["auth"] == "Bearer test-key"
    assert [m["role"] for m in captured["body"]["messages"]] == ["system", "user"]
    assert captured["body"]["max_tokens"] == 50
    assert captured["body"]["temperature"] == 0.1


async def test_completion_sin_system_prompt(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert [m["role"] for m in body["messages"]] == ["user"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _patch_client(monkeypatch, handler)
    assert await _adapter().generate_completion("hola") == "ok"


@pytest.mark.parametrize("status", [401, 404, 410])
async def test_errores_http_dan_mensaje_claro(monkeypatch, status):
    _patch_client(monkeypatch, lambda r: httpx.Response(status, json={}))
    with pytest.raises(NvidiaNimError):
        await _adapter().generate_completion("x")


async def test_429_reintenta_una_vez(monkeypatch):
    calls = {"n": 0}

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.infrastructure.llm.nvidia_nim_adapter.asyncio.sleep", no_sleep)

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _patch_client(monkeypatch, handler)
    assert await _adapter().generate_completion("x") == "ok"
    assert calls["n"] == 2


async def test_timeout_se_traduce(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("lento")

    _patch_client(monkeypatch, handler)
    with pytest.raises(NvidiaNimError, match="timeout"):
        await _adapter().generate_completion("x")


async def test_streaming_sse(monkeypatch):
    sse = (
        'data: {"choices":[{"delta":{"content":"Ho"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"la"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    _patch_client(monkeypatch, lambda r: httpx.Response(200, text=sse))
    tokens = [t async for t in _adapter().stream_completion("hi")]
    assert "".join(tokens) == "Hola"


def test_sin_api_key_falla():
    get_settings.cache_clear()
    with pytest.raises(NvidiaNimError):
        NvidiaNimAdapter(api_key="", base_url="https://x", model="m")


def test_fabrica_ollama_por_defecto(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    get_settings.cache_clear()
    assert isinstance(llm_factory.get_llm_client(), OllamaAdapter)
    get_settings.cache_clear()


def test_fabrica_nvidia_devuelve_hibrido(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    get_settings.cache_clear()
    client = llm_factory.get_llm_client()
    assert isinstance(client, llm_factory.HybridLLMClient)
    assert isinstance(client.embedding_client, OllamaAdapter)
    get_settings.cache_clear()
