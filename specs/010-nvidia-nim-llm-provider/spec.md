# Feature Specification: 010-nvidia-nim-llm-provider

## 1. Contexto y Problema
La generación de texto (síntesis, Text-to-SQL, chat) corre hoy en Ollama local (`qwen2.5:3b`) y consume mucha RAM/VRAM/CPU de la PC. NVIDIA NIM (`https://integrate.api.nvidia.com/v1`, API compatible con OpenAI) ofrece modelos gratuitos (créditos de desarrollo) como `google/gemma-4-31b-it`, ejecutados en la nube.

## 2. Objetivo
Permitir elegir el proveedor LLM por configuración (`LLM_PROVIDER=ollama|nvidia`) y usar NVIDIA NIM para **generación de texto**, descargando ese trabajo de la PC local.

## 3. Alcance
- **Dentro**: `generate_completion` y `stream_completion` vía `POST /v1/chat/completions` (formato `messages`, SSE para streaming).
- **Fuera / Decisión clave**: los **embeddings siguen en Ollama** (`nomic-embed-text`, ~270 MB, 768 dim). Cambiarlos a un modelo NVIDIA alteraría la dimensión y obligaría a re-vectorizar todo pgvector. Queda como mejora futura opcional.

## 4. Requisitos Funcionales
- FR-1: Nuevas variables `.env`: `LLM_PROVIDER`, `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_LLM_MODEL`, `NVIDIA_TIMEOUT_SECONDS`.
- FR-2: Nuevo `NvidiaNimAdapter` que implementa `LLMClientInterface`; selección vía fábrica según `LLM_PROVIDER`.
- FR-3: `max_tokens` y `temperature` se respetan; `system_prompt` se envía como mensaje `system`.
- FR-4: Streaming SSE (`data: {...}` / `[DONE]`) mapeado a tokens.
- FR-5: Fallback: si NVIDIA falla (timeout/401/404/410/429), error claro en español; opcionalmente fallback a Ollama si está activo.
- FR-6: La API key NUNCA se escribe en código ni en git; solo en `.env` (ya ignorado).

## 5. Criterios de Aceptación
- Con `LLM_PROVIDER=nvidia` y Ollama apagado (salvo embeddings), el chat responde.
- Con `LLM_PROVIDER=ollama` el comportamiento actual no cambia.
- Tests unitarios con `httpx` mockeado para ambos modos (completion, streaming, errores).

## 6. Riesgos y Notas
- **Seguridad**: las claves `nvapi-...` pegadas en el chat deben considerarse expuestas; revócalas y genera una nueva en build.nvidia.com.
- **Privacidad**: el prompt (incluyendo esquemas y filas de muestra) sale a servidores de NVIDIA. Evaluar si los datos de SUMAIE pueden enviarse a la nube.
- **Disponibilidad**: en pruebas desde esta PC, `gemma-4-31b-it` expiró por timeout (la lista `/v1/models` sí responde, pero varios modelos devuelven 404/410 para la cuenta). Hay que validar primero un modelo que responda y fijar un timeout generoso (≥60 s).
- **Límites**: cuota gratuita con rate limit (~40 req/min típico); manejar 429 con reintento.
- **Rendimiento real**: libera CPU/RAM/GPU locales, pero añade latencia de red.
