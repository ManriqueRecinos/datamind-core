"""Fábrica del cliente LLM: texto según LLM_PROVIDER, embeddings siempre en Ollama."""

import logging
from typing import AsyncIterator, List, Optional

from app.core.config import get_settings
from app.infrastructure.llm.nvidia_nim_adapter import NvidiaNimAdapter, NvidiaNimError
from app.infrastructure.llm.ollama_adapter import OllamaAdapter

logger = logging.getLogger(__name__)


class HybridLLMClient:
    """Genera texto con NVIDIA NIM y calcula embeddings con Ollama (768 dim)."""

    def __init__(self, text_client: NvidiaNimAdapter, embedding_client: OllamaAdapter, fallback: bool = False):
        self.text_client = text_client
        self.embedding_client = embedding_client
        self.fallback = fallback

    async def generate_embedding(self, text: str) -> List[float]:
        return await self.embedding_client.generate_embedding(text)

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        try:
            return await self.text_client.generate_completion(prompt, system_prompt, max_tokens, temperature)
        except NvidiaNimError as exc:
            if not self.fallback:
                raise
            logger.warning("NVIDIA NIM falló (%s); usando Ollama como respaldo.", exc)
            return await self.embedding_client.generate_completion(prompt, system_prompt, max_tokens, temperature)

    async def stream_completion(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        async for token in self.text_client.stream_completion(prompt, system_prompt):
            yield token


def get_llm_client():
    """Devuelve OllamaAdapter (por defecto) o el cliente híbrido NVIDIA + Ollama."""
    settings = get_settings()
    if (settings.llm_provider or "ollama").lower() == "nvidia":
        return HybridLLMClient(
            text_client=NvidiaNimAdapter(),
            embedding_client=OllamaAdapter(),
            fallback=settings.nvidia_fallback_to_ollama,
        )
    return OllamaAdapter()
