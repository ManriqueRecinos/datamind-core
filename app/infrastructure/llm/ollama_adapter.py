"""Adaptador asíncrono para el motor de IA local Ollama."""

import json
from typing import AsyncIterator, List, Optional
import httpx
from app.core.config import get_settings
from app.domain.interfaces import LLMClientInterface


class OllamaAdapter(LLMClientInterface):
    """Cliente HTTP asíncrono para Ollama."""

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.llm_model = settings.llm_model
        self.embedding_model = settings.embedding_model
        self.timeout = settings.ollama_timeout_seconds

    async def generate_embedding(self, text: str) -> List[float]:
        """Calcula el vector de 768 dimensiones usando nomic-embed-text."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.embedding_model, "prompt": text}
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """Genera una respuesta de texto completa usando qwen2.5:3b con opciones de rendimiento."""
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False
        }
        if system_prompt:
            payload["system"] = system_prompt

        options = {}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if temperature is not None:
            options["temperature"] = temperature
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def stream_completion(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Transmite la respuesta token por token mediante streaming."""
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": True
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/generate", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done", False):
                        break
