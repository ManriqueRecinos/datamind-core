# Implementation Plan: Resiliencia Conversacional, Reintento con Reparación y Aclaración de Ambigüedades

**Especificación**: `specs/006-conversational-resilience-and-ambiguity-repair/spec.md`  
**Research de Referencia**: `specs/006-conversational-resilience-and-ambiguity-repair/research.md`  
**Modelo de Datos**: `specs/006-conversational-resilience-and-ambiguity-repair/data-model.md`  

---

## Technical Stack & Architecture

- **Backend**: FastAPI, SQLAlchemy 2.0 Async, Pydantic V2.
- **Frontend**: Laravel 12 Blade (`chat_stream.js`): Manejador de evento SSE `clarification` con botones interactivos.
- **Guardarraíles y Sintaxis**: `SQLGuardrail` (reutilizado en todos los intentos de auto-reparación), `sqlglot`.
- **Motor LLM**: Ollama con `qwen2.5:3b` (manteniendo el mismo modelo en CPU para evitar latencias de cold-swap) y `nomic-embed-text`.
- **Persistencia**: PostgreSQL 17 (`unresolved_query_terms`, `knowledge_vector_chunks`, `knowledge_audit_logs`).

---

## Fases de Implementación Secuenciales

### FASE 1: Reintento con Auto-Reparación (Self-Healing SQL)
**Objetivo**: Prevenir que errores de sintaxis o nombres de columnas mal aprendidos causen caídas visibles al usuario.
- En `app/use_cases/ask_chat.py`:
  - Implementar bucle de ejecución controlada con `MAX_REPAIR_ATTEMPTS = 2`.
  - Capturar excepciones de `asyncpg` / `SQLAlchemy` (`UndefinedColumnError`, `UndefinedTableError`, `ProgrammingError`).
  - Preparar sub-prompt de reparación: error exacto de la BD + SQL fallido + DDL focalizado de las tablas involucradas.
  - Validar toda respuesta del reintento con `SQLGuardrail` (solo `SELECT`, `LIMIT 500`).
  - Límite de tiempo global (timeout de corte a los 35s acumulados).
  - Si el reintento se agota, responder con mensaje cortés en lenguaje natural en lugar de volcar el error técnico.

### FASE 2: Detección de Ambigüedad y Pregunta de Aclaración Activa
**Objetivo**: Impedir que el modelo genere consultas a ciegas cuando la similitud es baja o hay colisiones.
- En `app/use_cases/ask_chat.py` y `app/infrastructure/intent/classifier.py`:
  - Evaluar scores de recuperación semántica con los umbrales calibrados (`CONFIDENCE_THRESHOLD_MIN = 0.65`, $\Delta Score \le 0.04$).
  - Si se activa la condición de ambigüedad, emitir evento SSE `clarification` con opciones legibles.
- En `D:\Laravel\Supertex AI\public\js\chat_stream.js`:
  - Manejador de evento `clarification`: renderiza botones interactivos de selección dentro de la burbuja del asistente.
  - Al hacer clic en una opción, envía de inmediato la respuesta al backend.

### FASE 3: Cola de Términos No Entendidos para Desarrolladores/Admins
**Objetivo**: Registrar dudas y consultas fallidas para enriquecer el glosario formal del sistema.
- Migración SQL: crear tabla `unresolved_query_terms` con índices y constraints CHECK.
- Modelo SQLAlchemy: `UnresolvedQueryTermModel` en `app/infrastructure/database/models.py`.
- Casos de uso y API:
  - Registro automático al dispararse una aclaración o agotarse los reintentos.
  - `GET /api/v1/knowledge/unresolved-terms` para listar términos pendientes.
  - `POST /api/v1/knowledge/unresolved-terms/{id}/resolve` para marcar como resuelto.
- CLI de soporte: Comando para revisar términos e integrarlos directamente a `glossary.yaml`.

### FASE 4: Integración con Candidatos de Conocimiento y Métricas de Observabilidad
**Objetivo**: Convertir la respuesta del usuario en aprendizaje personal y medir la resiliencia del sistema.
- En `AskChatUseCase`:
  - Cuando el usuario resuelve una aclaración, persistir automáticamente el candidato con `trigger_signal = 'clarification_resolved'`, `scope = 'user'`, `status = 'candidate'`.
  - Registro inmutable en `knowledge_audit_logs`.
- Telemetría y Métricas:
  - Registro de contadores atómicos en memoria:
    - `sql_repair_attempts_total`
    - `sql_repair_success_total`
    - `sql_repair_exhausted_total`
    - `clarifications_requested_total`
    - `clarifications_resolved_total`
  - Suite de pruebas automatizadas: `tests/unit/test_self_healing_sql.py` y `tests/unit/test_clarification_flow.py`.
