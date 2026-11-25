# Tasks: Integración de Google Gemini API (Backend + Frontend)

**Plan**: `specs/014-gemini-api-integration/plan.md`

---

## Phase 1: Backend (`d:\Python\python-db` - FastAPI)

- [x] **T001** Agregar `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`) y `LLM_PROVIDER` (`ollama` | `gemini`) en `.env` / `.env.example` y en `Settings`.
- [x] **T002** Crear `GeminiLlmAdapter` en la capa de infraestructura implementando `LLMProviderInterface` con `httpx.AsyncClient` (`generateContent` y `streamGenerateContent?alt=sse`).
- [x] **T003** Registrar `GeminiLlmAdapter` en la inyección de dependencias para seleccionarlo cuando `LLM_PROVIDER=gemini` (o según el parámetro del request).
- [x] **T004** Escribir pruebas unitarias en `pytest` para `GeminiLlmAdapter` (mapeo de mensajes, respuestas y manejo de errores 401/429/503).

---

## Phase 2: Frontend (`d:\Laravel\Supertex AI` - Laravel 13)

- [ ] **T005** Actualizar el controlador/servicio de chat en Laravel para enviar el proveedor/modelo seleccionado hacia el backend FastAPI.
- [ ] **T006** Agregar selector de motor/modelo (`Local Ollama` vs `Google Gemini`) en la vista de chat (Blade + JS local, sin CDNs) con manejo de errores vía `toastr`/`Swal`.
- [x] **T007** Actualizar la versión en `README.md` y `AGENTS.md` de `Supertex AI` (`1.0.7` → `1.0.8`).

---

## Phase 3: Rutinas y Tool Calling Nativo (`ejecutar_sql`)

- [x] **T008** Exponer `POST /api/v1/connections/{connection_id}/vectorize-routines` en FastAPI y botón en `Supertex AI` (`explorer.blade.php`).
- [x] **T009** Implementar soporte de `tools` (`ejecutar_sql(query)`) en los adaptadores LLM y bucle de ejecución segura con `SQLGuardrail` en `AskChatUseCase`.
- [x] **T010** Escribir pruebas unitarias en `pytest` para el endpoint de rutinas y el flujo de *tool calling* `ejecutar_sql`.
