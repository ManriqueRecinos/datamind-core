"""Pruebas unitarias para el adaptador de Ollama (Fase 2)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.llm.ollama_adapter import OllamaAdapter


@pytest.mark.asyncio
async def test_ollama_generate_embedding_mock():
    adapter = OllamaAdapter(base_url="http://fake-ollama:11434")
    fake_vector = [0.1] * 768

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": fake_vector}
        mock_post.return_value = mock_response

        vec = await adapter.generate_embedding("Texto de prueba")
        assert len(vec) == 768
        assert vec[0] == 0.1
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_generate_completion_mock():
    adapter = OllamaAdapter(base_url="http://fake-ollama:11434")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Respuesta simulada de Qwen"}
        mock_post.return_value = mock_response

        text = await adapter.generate_completion("Hola")
        assert text == "Respuesta simulada de Qwen"
