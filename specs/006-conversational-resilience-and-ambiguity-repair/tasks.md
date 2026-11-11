# Tasks: Resiliencia Conversacional, Reintento con Auto-Reparación y Aclaración de Ambigüedades

**Feature**: `specs/006-conversational-resilience-and-ambiguity-repair/spec.md`  
**Plan**: `specs/006-conversational-resilience-and-ambiguity-repair/plan.md`  
**Data Model**: `specs/006-conversational-resilience-and-ambiguity-repair/data-model.md`  
**Research**: `specs/006-conversational-resilience-and-ambiguity-repair/research.md`  

---

## Task Overview & Progress Tracking

| ID | Task | Subtasks | Status |
| :--- | :--- | :--- | :--- |
| **TASK-006-01** | **Persistencia y Modelado de Términos No Entendidos** | Migración SQL `006_create_unresolved_query_terms.sql`, Modelo SQLAlchemy `UnresolvedQueryTermModel` | [x] Completed |
| **TASK-006-02** | **Módulo de Auto-Reparación de SQL (Self-Healing SQL Loop)** | Bucle de 2 reintentos con captura de errores, sub-prompt de reparación, validación estricta con `SQLGuardrail` y timeout acumulado | [x] Completed |
| **TASK-006-03** | **Detección de Ambigüedad y Emisión de Aclaración** | Evaluación de umbral $< 0.65$ y empate técnico $\Delta Score \le 0.04$, evento SSE `clarification` con opciones amigables | [x] Completed |
| **TASK-006-04** | **Componente UI Interactivo de Aclaración (Laravel/Blade/JS)** | Escucha del evento SSE `clarification` en `chat_stream.js`, renderizado de botones de selección, envío de elección como respuesta rápida | [x] Completed |
| **TASK-006-05** | **Registro de Términos y Endpoints de Gestión Administrativa** | Registro automático en `unresolved_query_terms`, endpoints `GET /unresolved-terms` y `POST /unresolved-terms/{id}/resolve` | [x] Completed |
| **TASK-006-06** | **Ciclo de Aprendizaje de Candidatos y Gobernanza** | Creación de candidato `scope='user'`, `status='candidate'`, `trigger_signal='clarification_resolved'` en `knowledge_vector_chunks` y auditoría | [x] Completed |
| **TASK-006-07** | **Métricas, Observabilidad y Suite de Pruebas Unitarias** | Contadores atómicos en memoria, pruebas unitarias para reintentos (`test_self_healing_sql.py`) y aclaración (`test_clarification_flow.py`) | [x] Completed |

---

## Detailed Task Breakdown

### TASK-006-01: Persistencia y Modelado de Términos No Entendidos
- [x] **01.1**: Crear script de migración SQL `app/infrastructure/database/migrations/006_create_unresolved_query_terms.sql`:
  - Definir tabla `unresolved_query_terms` con UUID PK, `session_id`, `user_id`, `connection_id`, `raw_query`, `extracted_term`, `failure_reason` (CHECK: `sql_repair_exhausted`, `low_retrieval_confidence`, `ambiguous_candidates`), `candidate_tables` (JSONB), `error_details` (TEXT), `status` (CHECK: `pending`, `promoted_to_glossary`, `dismissed`), `created_at`, `resolved_at`, `resolved_by`.
  - Crear índices: `idx_unresolved_terms_status`, `idx_unresolved_terms_connection_id`, `idx_unresolved_terms_user_id`.
- [x] **01.2**: Declarar `UnresolvedQueryTermModel` en `app/infrastructure/database/models.py` alineado al data model.
- [x] **01.3**: Ejecutar migración contra PostgreSQL `enterprise_rag` y verificar estructura.

### TASK-006-02: Módulo de Auto-Reparación de SQL (Self-Healing SQL Loop)
- [x] **02.1**: Crear `app/use_cases/sql_repair_agent.py`:
  - Definir prompt de auto-reparación focalizado: recibe el dialecto exacto, el error reportado por el motor (DuckDB / PostgreSQL), el SQL fallido y el DDL/esquema reducido de las tablas en conflicto.
  - Implementar llamada al LLM local `qwen2.5:3b` exigiendo formato puro ````sql ... ````.
- [x] **02.2**: Integrar bucle de reintento en `app/use_cases/ask_chat.py`:
  - Limitar a un máximo de 2 reintentos (`MAX_REPAIR_ATTEMPTS = 2`).
  - Filtrar cada nuevo SQL generado mediante `SQLGuardrail.validate()` antes de ejecutar.
  - Envolver en control de timeout acumulativo (máximo 35s global para no agotar la paciencia del usuario ni los límites HTTP).
- [x] **02.3**: Manejar falla total de reintentos:
  - Si tras 2 reintentos persiste el error, registrar en `unresolved_query_terms` y emitir respuesta explicativa en lenguaje natural en lugar de volcar el `ProgrammingError` o `Binder Error`.

### TASK-006-03: Detección de Ambigüedad y Emisión de Aclaración
- [x] **03.1**: Calibrar lógica de confianza en el recuperador de esquemas:
  - Si el chunk con mayor score tiene similitud $< 0.65$, clasificar como `LOW_CONFIDENCE`.
  - Si la diferencia entre el candidato #1 y el candidato #2 es $\le 0.04$, clasificar como `AMBIGUOUS_MATCH`.
- [x] **03.2**: En `AskChatUseCase`:
  - Interrumpir la generación de SQL si se clasifica como ambiguo o de baja confianza.
  - Formatear opciones claras para el usuario (ejemplo: "¿Deseas consultar la tabla de **inventario de repuestos** o el historial de **movimientos de bodega**?").
  - Emitir evento SSE `clarification` con payload `{ question: string, options: [{ label: string, value: string, explanation: string }] }`.

### TASK-006-04: Componente UI Interactivo de Aclaración (Laravel/Blade/JS)
- [x] **04.1**: Actualizar `D:\Laravel\Supertex AI\public\js\chat_stream.js`:
  - Agregar listener para el evento SSE `event: clarification`.
  - Construir dinámicamente un bloque de opciones interactivas (botones estilizados con bordes redondeados y badge de tabla) dentro del mensaje del asistente.
- [x] **04.2**: Implementar interacción rápida de selección:
  - Al hacer clic en una opción, deshabilitar los botones restantes para evitar doble envío.
  - Enviar de inmediato la opción seleccionada al chat como mensaje del usuario o comando de resolución contextual (`/clarify <value>`), disparando la consulta con la desambiguación resuelta.

### TASK-006-05: Registro de Términos y Endpoints de Gestión Administrativa
- [x] **05.1**: Crear repositorio `UnresolvedQueryTermRepository` en `app/infrastructure/database/repositories/unresolved_terms_repository.py`.
- [x] **05.2**: Crear endpoints en `app/api/v1/endpoints/knowledge.py`:
  - `GET /api/v1/knowledge/unresolved-terms`: Listar términos con filtros de estado (`pending`, `dismissed`, `promoted_to_glossary`) y paginación.
  - `POST /api/v1/knowledge/unresolved-terms/{id}/resolve`: Marcar término como resuelto o descartado, permitiendo opcionalmente vincularlo a un sinónimo formal de `glossary.yaml`.

### TASK-006-06: Ciclo de Aprendizaje de Candidatos y Gobernanza
- [x] **06.1**: Manejar respuesta de aclaración en `AskChatUseCase`:
  - Al recibir la resolución del usuario, guardar el chunk en `knowledge_vector_chunks` con:
    - `scope = 'user'`
    - `status = 'candidate'`
    - `trigger_signal = 'clarification_resolved'`
    - `user_id = session.user_id`
  - Garantizar que nunca entre como regla global o verificada directa sin la revisión del administrador.
- [x] **06.2**: Registrar entrada en `knowledge_audit_logs` con `action = 'candidate_created'`, detallando el término aclarado y la tabla/columna asociada.

### TASK-006-07: Métricas, Observabilidad y Suite de Pruebas Unitarias
- [x] **07.1**: Implementar módulo de métricas en memoria `app/core/telemetry_resilience.py`:
  - Rastrear contadores: reintentos de reparación totales, reparaciones exitosas, reintentos agotados, aclaraciones solicitadas y aclaraciones resueltas.
  - Exponer endpoint `GET /api/v1/system/resilience-metrics`.
- [x] **07.2**: Desarrollar pruebas automatizadas:
  - `tests/unit/test_self_healing_sql.py`: Simular fallo de columna inexistente, verificar que el agente de reparación produce el SQL corregido, valida con `SQLGuardrail` y ejecuta exitosamente dentro del límite de 2 reintentos.
  - `tests/unit/test_clarification_flow.py`: Simular búsqueda con score bajo o empate técnico, verificar emisión de evento `clarification` y posterior inserción de candidato `scope='user'`.
