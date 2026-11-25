# Tasks: Respuestas Humanizadas, Reglas Dinámicas y Allowlist por Vectorización

**Plan**: `specs/015-rag-humanized-rules-and-allowlist/plan.md`

---

- [x] **T001** Extender `SQLGuardrail.validate_and_sanitize()` en `app/infrastructure/llm/sql_guardrail.py` para aceptar `allowed_tables: Optional[Set[str]] = None` y bloquear con `sqlglot` cualquier tabla no vectorizada.
- [x] **T002** Actualizar `execute_sql_tool()` en `app/infrastructure/llm/sql_tool.py` para recibir y aplicar `allowed_tables`.
- [x] **T003** Actualizar `AskChatUseCase` en `app/use_cases/ask_chat.py` para pasar `allowed_tables` (desde `conn_model.synced_tables`) a `SQLGuardrail` y reforzar el *system prompt* de síntesis prohibiendo mencionar nombres de tablas, columnas o SQL crudo.
- [x] **T004** Escribir pruebas unitarias en `pytest` (`tests/unit/test_sql_guardrail_allowlist.py`) verificando el bloqueo de tablas no vectorizadas y la aceptación de tablas permitidas.
