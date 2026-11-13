# Implementation Plan: 010-nvidia-nim-llm-provider

## Enfoque
Mantener un único punto de entrada (`OllamaAdapter()` ya se instancia en 5 lugares con `self.ollama = ollama or OllamaAdapter()`). Se introduce un **adaptador híbrido**: la generación de texto va al proveedor configurado y los embeddings siempre a Ollama (768 dim, sin re-vectorizar).

## Cambios
1. `app/core/config.py`: agregar `llm_provider` (`LLM_PROVIDER`, default `ollama`), `nvidia_api_key`, `nvidia_base_url` (default `https://integrate.api.nvidia.com/v1`), `nvidia_llm_model` (default `google/gemma-4-31b-it`), `nvidia_timeout_seconds` (default 90), `nvidia_fallback_to_ollama` (bool).
2. `app/infrastructure/llm/nvidia_nim_adapter.py` (nuevo): `generate_completion` (POST `/chat/completions`, `messages` system+user, `max_tokens`, `temperature`) y `stream_completion` (SSE `data:` / `[DONE]`). Manejo de 401/404/410/429/timeout con mensaje claro y 1 reintento en 429.
3. `app/infrastructure/llm/llm_factory.py` (nuevo): `get_llm_client()` devuelve un `HybridLLMClient` (completions → NVIDIA si `LLM_PROVIDER=nvidia`, embeddings → `OllamaAdapter`). Con `ollama` devuelve el `OllamaAdapter` actual sin cambios.
4. Reemplazar `OllamaAdapter()` por `get_llm_client()` en los 4 use cases que generan texto (la instancia con `model="nomic-embed-text"` de embeddings se deja igual).
5. `.env.example`: documentar variables nuevas sin valores. La clave real solo en `.env` (ignorado por git).
6. `/health`: reportar proveedor activo.

## Tests (`tests/unit/test_nvidia_nim_adapter.py`, httpx mock)
- completion OK, con y sin system prompt.
- streaming SSE.
- errores 401/429/timeout → mensaje claro / fallback.
- factory: `ollama` → OllamaAdapter; `nvidia` → híbrido.

## Riesgos
- Timeouts observados en esta red con `gemma-4-31b-it`: validar con la clave nueva y, si falla, cambiar `NVIDIA_LLM_MODEL` por otro modelo activo de la cuenta.
- Privacidad: prompts con esquemas/filas salen a la nube.
- Clave expuesta en chat: revocar y regenerar antes de implementar.
