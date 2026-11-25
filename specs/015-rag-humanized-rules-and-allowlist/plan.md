# Implementation Plan: Respuestas Humanizadas, Reglas Dinámicas y Allowlist por Vectorización

**Branch**: `015-rag-humanized-rules-and-allowlist` | **Date**: 2026-11-24 | **Spec**: `specs/015-rag-humanized-rules-and-allowlist/spec.md`

## Summary

1. **Respuestas 100% humanizadas**: Reforzar el *system prompt* de síntesis en `AskChatUseCase` para prohibir mencionar nombres técnicos de tablas, columnas, esquemas o SQL crudo.
2. **Allowlist estricta por vectorización**: Extender `SQLGuardrail.validate_and_sanitize()` y `execute_sql_tool()` para aceptar `allowed_tables` (extraído de `conn_model.synced_tables`) y rechazar mediante AST (`sqlglot`) cualquier consulta que toque tablas no vectorizadas.
3. **Reglas y alias editables**: Asegurar soporte de edición/actualización (`PUT/PATCH`) de reglas de negocio y alias en `knowledge.py` re-vectorizando su contenido en `pgvector`.

---

## Phase 1: Backend (`d:\Python\python-db`)

1. **Allowlist en `SQLGuardrail` (`app/infrastructure/llm/sql_guardrail.py`)**:
   - Agregar parámetro opcional `allowed_tables: Optional[Set[str]] = None` en `validate_and_sanitize()`.
   - Extraer todas las tablas referenciadas en el AST de `sqlglot` (`parsed.find_all(exp.Table)`) y rechazar si alguna no pertenece a `allowed_tables` (case-insensitive).
2. **Propagar `allowed_tables` en `execute_sql_tool` y `AskChatUseCase`**:
   - Pasar `allowed_tables` desde `conn_model.synced_tables` a `SQLGuardrail` y `execute_sql_tool()`.
3. **Prompt humanizado en `AskChatUseCase` (`app/use_cases/ask_chat.py`)**:
   - Agregar regla explícita de no revelar nombres de tablas, columnas, IDs internos ni código SQL en la respuesta final al usuario.
4. **Pruebas (`pytest`)**:
   - Verificar que `SQLGuardrail` bloquea tablas fuera de `allowed_tables` y permite las que sí están vectorizadas.
