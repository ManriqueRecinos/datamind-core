# Implementation Plan: Integración de Google Gemini API (Backend + Frontend)

**Branch**: `014-gemini-api-integration` | **Date**: 2026-11-24

## Summary

Conectar la API de **Google AI Studio (Gemini)** al ecosistema **DataMind** en dos fases:
1. **Backend (`d:\Python\python-db` - FastAPI)**: Implementar un adaptador `GeminiLlmAdapter` que cumpla con `LLMProviderInterface`, configurable vía `.env` (`GEMINI_API_KEY`, `GEMINI_MODEL`, `LLM_PROVIDER`) para alternar o combinar con Ollama sin romper la arquitectura limpia.
2. **Frontend (`d:\Laravel\Supertex AI` - Laravel 13)**: Conectar la vista de chat existente para permitir seleccionar/usar el proveedor Gemini y mostrar respuestas (incluyendo streaming SSE y manejo de errores).

---

## Technical Context

- **Backend**: Python 3.11+, FastAPI (async), Pydantic V2, `httpx.AsyncClient`, `pytest`
- **Frontend**: Laravel 13 (PHP 8.3+), Blade, jQuery / Axios, `toastr` / `Swal` (Offline / Zero CDNs)
- **External API**: Google Gemini REST API (`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` y `:streamGenerateContent`)
- **Security**: `GEMINI_API_KEY` almacenada únicamente en `.env` (nunca en código ni en el frontend).

---

## Constitution Check

- **Clean Architecture**: `GeminiLlmAdapter` vive en la capa de **Infrastructure**, implementando `LLMProviderInterface` del **Domain**. Los casos de uso (`AskChatUseCase`, etc.) no cambian.
- **Async by Default**: Todas las llamadas a Gemini usan `httpx.AsyncClient` (`async def`).
- **Tests**: Pruebas unitarias con `pytest` mockeando respuestas HTTP de Gemini.

---

## Phase 1: Backend (`d:\Python\python-db`)

1. **Variables de entorno y configuración**:
   - Agregar `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`) y `LLM_PROVIDER` (`ollama` | `gemini`) en `.env` y en la clase de configuración (`Settings`).
2. **Adaptador de Infraestructura (`GeminiLlmAdapter`)**:
   - Implementar `LLMProviderInterface` usando `httpx.AsyncClient`.
   - Soportar generación estándar (`generateContent`) y streaming (`streamGenerateContent?alt=sse`).
   - Mapear mensajes del historial (`system`, `user`, `assistant`) al formato `contents` / `systemInstruction` de Gemini.
3. **Inyección de dependencias**:
   - Actualizar el proveedor de dependencias para instanciar `GeminiLlmAdapter` cuando `LLM_PROVIDER=gemini` (o cuando el request indique el proveedor).
4. **Pruebas (`pytest`)**:
   - Verificar mapeo de prompts, manejo de errores HTTP (401, 429, 503) y streaming.

---

## Phase 2: Frontend (`d:\Laravel\Supertex AI`)

1. **Backend Laravel (Proxy / Cliente HTTP)**:
   - Asegurar que el controlador/servicio de chat en Laravel envíe el parámetro de proveedor/modelo (si aplica) hacia FastAPI manteniendo el Bearer token de servicio.
2. **Interfaz de Chat (Blade + JS local)**:
   - Agregar selector opcional de motor/modelo (ej. `Local (Ollama)` vs `Google Gemini`) en la vista de chat.
   - Mostrar estados de carga y errores amigables con `toastr` / `Swal`.
3. **Control de Versiones (`Supertex AI`)**:
   - Incrementar la versión en `README.md` y `AGENTS.md` de `1.0.7` a `1.0.8` al finalizar los cambios en Laravel.

---

## Phase 3: Vectorización de Rutinas y Tool Calling Nativo (`ejecutar_sql`)

1. **Endpoint de Vectorización de Rutinas (`d:\Python\python-db`)**:
   - Exponer `POST /api/v1/connections/{connection_id}/vectorize-routines` en el router de conexiones llamando a `ManageConnectionsUseCase.vectorize_routines()`.
   - Conectar botón en `explorer.blade.php` / `connections_manager.js` para vectorizar funciones y procedimientos almacenados desde `Supertex AI`.
2. **Tool Calling Nativo `ejecutar_sql(query)`**:
   - Definir el esquema de herramienta `ejecutar_sql(query: str)` compatible con OpenAI/OpenRouter (`tools`), Gemini (`functionDeclarations`) y Ollama.
   - Integrar el bucle de *tool calling* en `AskChatUseCase` manteniendo `SQLGuardrail` (`sqlglot`, solo `SELECT`, `LIMIT` máximo 500, timeout) antes de ejecutar cualquier consulta.
