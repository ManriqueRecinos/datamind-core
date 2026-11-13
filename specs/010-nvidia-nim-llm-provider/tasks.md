# Tasks: 010-nvidia-nim-llm-provider

## Fase 0: Prerrequisitos (usuario)
- [ ] T001 Revocar las API keys `nvapi-...` expuestas y generar una nueva en build.nvidia.com; guardarla solo en `.env` (`NVIDIA_API_KEY`).
- [ ] T002 Confirmar que enviar esquemas/filas de muestra a la nube de NVIDIA es aceptable.
- [ ] T003 Validar con la clave nueva quÃ© modelo responde (probar `google/gemma-4-31b-it`; si da timeout/404, elegir otro de `/v1/models`).

## Fase 1: ConfiguraciÃ³n
- [x] T004 `app/core/config.py`: agregar `llm_provider`, `nvidia_api_key`, `nvidia_base_url`, `nvidia_llm_model`, `nvidia_timeout_seconds`, `nvidia_fallback_to_ollama`.
- [x] T005 `.env.example`: documentar variables nuevas sin valores reales.

## Fase 2: Adaptador y fÃ¡brica
- [x] T006 Crear `app/infrastructure/llm/nvidia_nim_adapter.py` con `generate_completion` (`messages` system+user, `max_tokens`, `temperature`).
- [x] T007 Agregar `stream_completion` (SSE `data:` / `[DONE]`) al mismo adaptador.
- [x] T008 Manejo de errores: 401/404/410 con mensaje claro, 429 con 1 reintento, timeout, fallback opcional a Ollama.
- [x] T009 Crear `app/infrastructure/llm/llm_factory.py` con `get_llm_client()` y `HybridLLMClient` (texto â†’ proveedor configurado, embeddings â†’ `OllamaAdapter`).

## Fase 3: IntegraciÃ³n
- [x] T010 Reemplazar `OllamaAdapter()` por `get_llm_client()` en los 4 use cases que generan texto (dejar intacta la instancia de embeddings `nomic-embed-text`).
- [x] T011 `/health`: reportar proveedor LLM activo.

## Fase 4: Pruebas y verificaciÃ³n
- [x] T012 `tests/unit/test_nvidia_nim_adapter.py` con `httpx` simulado: completion con/sin system prompt, streaming, 401/429/timeout.
- [x] T013 Test de la fÃ¡brica: `ollama` â†’ `OllamaAdapter`; `nvidia` â†’ hÃ­brido.
- [ ] T014 Ejecutar `pytest` completo y comprobar que `LLM_PROVIDER=ollama` no cambia el comportamiento.
- [ ] T015 Prueba manual: `LLM_PROVIDER=nvidia`, Ollama solo para embeddings, enviar una pregunta en el chat.

## Dependencias
T001â€“T003 â†’ T004 â†’ T006â€“T009 â†’ T010 â†’ T012â€“T015. T005 y T011 son paralelizables.

