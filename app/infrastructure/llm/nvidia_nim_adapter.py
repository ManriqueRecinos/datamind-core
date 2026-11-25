"""Adaptador asíncrono para NVIDIA NIM (API compatible con OpenAI /v1/chat/completions)."""

import asyncio
import json
from typing import AsyncIterator, List, Optional

import httpx

from app.core.config import get_settings


class NvidiaNimError(RuntimeError):
    """Error controlado al invocar NVIDIA NIM, con mensaje claro en español."""


_ERROR_MESSAGES = {
    401: "NVIDIA NIM rechazó la API key (401). Revisa NVIDIA_API_KEY.",
    403: "NVIDIA NIM denegó el acceso (403) para esta cuenta o modelo.",
    404: "El modelo no está disponible para tu cuenta en NVIDIA NIM (404). Cambia NVIDIA_LLM_MODEL.",
    410: "El modelo fue retirado de NVIDIA NIM (410). Cambia NVIDIA_LLM_MODEL.",
    429: "Límite de peticiones de NVIDIA NIM alcanzado (429). Intenta de nuevo en unos segundos.",
}


class NvidiaNimAdapter:
    """Cliente HTTP asíncrono para generación de texto en NVIDIA NIM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = (base_url or settings.nvidia_base_url).rstrip("/")
        self.model = model or settings.nvidia_llm_model
        self.timeout = timeout or settings.nvidia_timeout_seconds
        if not self.api_key:
            raise NvidiaNimError("Falta NVIDIA_API_KEY en el archivo .env.")

    def _headers(self, stream: bool = False) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream" if stream else "application/json",
        }

    def _payload(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
        stream: bool,
    ) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "max_tokens": max_tokens or 2048,
            "temperature": 0.5 if temperature is None else temperature,
        }
        if "nemotron" in (self.model or "").lower():
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            msg = _ERROR_MESSAGES.get(response.status_code, f"NVIDIA NIM respondió con error {response.status_code}.")
            raise NvidiaNimError(msg)

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        payload = self._payload(prompt, system_prompt, max_tokens, temperature, stream=False)
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                if response.status_code == 429:
                    await asyncio.sleep(2)
                    response = await client.post(url, headers=self._headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise NvidiaNimError("NVIDIA NIM no respondió a tiempo (timeout).") from exc
        except httpx.HTTPError as exc:
            raise NvidiaNimError(f"No se pudo conectar con NVIDIA NIM: {exc}") from exc

        self._raise_for_status(response)
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise NvidiaNimError("Respuesta inesperada de NVIDIA NIM.") from exc

    async def stream_completion(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        payload = self._payload(prompt, system_prompt, None, None, stream=True)
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, headers=self._headers(stream=True), json=payload) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            token = chunk["choices"][0]["delta"].get("content") or ""
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if token:
                            yield token
        except httpx.TimeoutException as exc:
            raise NvidiaNimError("NVIDIA NIM no respondió a tiempo (timeout).") from exc
        except httpx.HTTPError as exc:
            raise NvidiaNimError(f"No se pudo conectar con NVIDIA NIM: {exc}") from exc
