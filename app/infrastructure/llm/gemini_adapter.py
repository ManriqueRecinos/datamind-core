"""Adaptador asíncrono para la API REST de Google Gemini (Google AI Studio)."""

import json
import logging
from typing import AsyncIterator, Dict, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    """Error al invocar la API de Google Gemini."""


class GeminiAdapter:
    """Adaptador de generación de texto usando Google Gemini API."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_llm_model
        self.timeout_seconds = timeout_seconds or settings.gemini_timeout_seconds

    def _build_payload(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict:
        payload: Dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        generation_config: Dict = {}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if temperature is not None:
            generation_config["temperature"] = temperature
        if generation_config:
            payload["generationConfig"] = generation_config
        return payload

    def _ensure_api_key(self) -> str:
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY no está configurada.")
        return self.api_key

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        api_key = self._ensure_api_key()
        url = f"{self.BASE_URL}/{self.model}:generateContent"
        payload = self._build_payload(prompt, system_prompt, max_tokens, temperature)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    params={"key": api_key},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise GeminiError(f"Gemini HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise GeminiError(f"Error de red al conectar con Gemini: {exc}") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            raise GeminiError("Gemini no devolvió candidatos en la respuesta.")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(part.get("text", "") for part in parts)

    async def stream_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        api_key = self._ensure_api_key()
        url = f"{self.BASE_URL}/{self.model}:streamGenerateContent"
        payload = self._build_payload(prompt, system_prompt)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    url,
                    params={"key": api_key, "alt": "sse"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        chunk = json.loads(raw)
                        candidates = chunk.get("candidates") or []
                        if not candidates:
                            continue
                        parts = candidates[0].get("content", {}).get("parts") or []
                        text = "".join(part.get("text", "") for part in parts)
                        if text:
                            yield text
        except httpx.HTTPStatusError as exc:
            raise GeminiError(f"Gemini stream HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise GeminiError(f"Error de red en stream Gemini: {exc}") from exc
