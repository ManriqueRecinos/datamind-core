# Tasks: Implicit Dialogue Learning & Knowledge Candidate Lifecycle

**Input**: Design documents from `specs/003-implicit-dialogue-learning/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/`, `research.md`, `quickstart.md`).  
**Prerequisites**: FastAPI, PostgreSQL + pgvector, Laravel 12 (Frontend/Auth), Ollama (`qwen2.5:3b`, `nomic-embed-text`).  
**Organization**: Tareas agrupadas en 4 fases secuenciales con checkpoints de verificación independientes. Rutas de archivo exactas. Marca `[P]` únicamente en tareas verdaderamente paralelas en archivos independientes.

---

## FASE 1: Esquema de Datos, Migración No Destructiva, Permisos y UI Mínima de Candidatos

**Propósito**: Establecer las bases de datos relacionales y vectoriales con auditoría inmutable desacoplada, RBAC en Laravel, API de candidatos con endpoints de ciclo de vida (`confirm-user`, `propose-global`, `promote-global`, `reject`, `rollback`) y controles de interfaz con escapado anti-XSS.

- [x] **T101**: [P] Crear script de migración SQL no destructivo para `knowledge_vector_chunks`, `knowledge_audit_logs`, trigger anti-mutación y vista de estadísticas en `D:\Python\python-db\migrations\004_implicit_knowledge_candidates.sql`.
  - Agregar `status`, `scope`, `trigger_signal` con `DEFAULT` temporal (`'verified'`, `'global'`, `'manual_teach'`).
  - Agregar `user_id` (`VARCHAR(100)`), `target_entity`, `target_column`, `prescriptive_condition` ($\le 250$ chars), `source_session_id` (UUID plano sin FK), `source_message_id` (UUID plano sin FK), `version` (INT default 1), `parent_rule_id`, `conflict_with_id`, `confirmed_at`, `proposed_global_at`, `embedding_model` (`nomic-embed-text`).
  - Ejecutar backfill de filas preexistentes y ejecutar `ALTER TABLE ... DROP DEFAULT` en `status`, `scope` y `trigger_signal`.
  - Aplicar `CHECK constraints` (`chk_kvc_status`, `chk_kvc_scope`, `chk_kvc_user_scope`).
  - Crear índice único condicional `uq_kvc_source_message_signal` sobre `(source_message_id, trigger_signal)` con soporte para inserciones `ON CONFLICT DO NOTHING`.
  - Añadir columna `metadata_` (`JSONB`, default `dict`) a `chat_messages` si no existe para persistir `rules_applied`.
  - Crear tabla `knowledge_audit_logs` con `rule_id` UUID plano, `source_session_id` UUID plano sin FK, y trigger PostgreSQL `trg_audit_logs_immutable` que prohíba sentencias `UPDATE` y `DELETE`.
  - Crear vista `v_knowledge_candidates_stats` agrupando por conexión, estado, alcance y señal, calculando métricas temporales sobre `created_at`.

- [x] **T102**: [P] Actualizar modelos ORM de SQLAlchemy y Pydantic V2 en FastAPI.
  - En `D:\Python\python-db\app\infrastructure\database\models.py`:
    - Extender `KnowledgeVectorChunkModel` con las nuevas columnas (`status`, `scope`, `user_id`, `target_entity`, `target_column`, `prescriptive_condition`, `trigger_signal`, `source_session_id`, `source_message_id`, `version`, `conflict_with_id`, `confirmed_at`, `proposed_global_at`, `embedding_model`).
    - Añadir columna `metadata_ = Column("metadata", JSONB, nullable=False, default=dict)` a `ChatMessageModel`.
    - Crear `KnowledgeAuditLogModel`.
  - En `D:\Python\python-db\app\api\v1\schemas\knowledge.py`:
    - Crear esquemas `KnowledgeCandidateResponse`, `ConfirmUserCandidateRequest`, `PromoteCandidateRequest`, `RejectCandidateRequest`, `RollbackCandidateRequest`.

- [x] **T103**: [P] Registrar roles y permisos en Laravel para la curación de candidatos.
  - En `D:\Laravel\Supertex AI\database\seeders\RoleAndPermissionSeeder.php`:
    - Registrar permiso `manage-knowledge` (descripción: "Administrar y promover cápsulas de conocimiento").
    - Asignar `manage-knowledge` a los roles `super-admin` y `admin`.
  - Ejecutar `php artisan db:seed --class=RoleAndPermissionSeeder`.

- [x] **T104**: Implementar repositorio y casos de uso de gestión de candidatos con autorización RBAC estricta.
  - En `D:\Python\python-db\app\infrastructure\database\candidate_repository.py`:
    - Implementar `list_candidates(connection_id, user_id, user_role, proposed_only)`.
    - Implementar `confirm_user_candidate(candidate_id, user_id)`: actualiza `confirmed_at = NOW()`.
    - Implementar `propose_global_candidate(candidate_id, user_id)`: actualiza `proposed_global_at = NOW()`.
    - Implementar `promote_global_candidate(candidate_id, admin_user_id, edited_content)`:
      - Validar que no exista otra regla global con la misma tupla `(connection_id, target_entity, target_column)` y condición normalizada distinta; si existe, rechazar con `HTTP 409 Conflict`.
      - Re-sanitizar y re-vectorizar el contenido con prefijo `search_document: `, mutar a `scope = 'global'`, `status = 'verified'`, e incrementar `version`.
    - Implementar `reject_candidate(candidate_id, actor_id, actor_role)`: validar que si `scope == 'global'` exige rol de admin; muta a `status = 'rejected'`.
    - Implementar `rollback_candidate(candidate_id, actor_id, actor_role)`: validar que si `scope == 'global'` exige rol de admin; restaura `previous_state` desde `knowledge_audit_logs` con re-vectorización o pasa a `status = 'rolled_back'`.
    - Registrar todas las acciones en `knowledge_audit_logs`.

- [x] **T105**: Exponer router REST de candidatos en FastAPI.
  - En `D:\Python\python-db\app\api\v1\routers\knowledge.py`:
    - Montar endpoints `GET /candidates`, `POST /candidates/{id}/confirm-user`, `POST /candidates/{id}/propose-global`, `POST /candidates/{id}/promote-global`, `POST /candidates/{id}/reject`, `POST /candidates/{id}/rollback`.
    - Validar encabezados inyectados `X-User-Id`, `X-User-Role` y `X-User-Permissions`.

- [x] **T106**: Integrar cliente HTTP y proxy en Laravel para candidatos.
  - En `D:\Laravel\Supertex AI\app\Services\FastApiClient.php`:
    - Agregar métodos `listCandidates()`, `confirmUserCandidate()`, `proposeGlobalCandidate()`, `promoteGlobalCandidate()`, `rejectCandidate()`, `rollbackCandidate()`.
  - En `D:\Laravel\Supertex AI\app\Http\Controllers\KnowledgeController.php`:
    - Añadir acciones de controlador protegiendo la promoción global con `$this->authorize('manage-knowledge')` o comprobación de rol `hasPermission('manage-knowledge')`.

- [x] **T107**: Implementar UI discreta de chip de candidato y panel administrativo en Laravel Blade con protección XSS.
  - En `D:\Laravel\Supertex AI\resources\views\chat\partials\candidate_chip.blade.php`:
    - Renderizar chip interactivo con botones "Confirmar para mí" y "Proponer para la organización".
    - Escapar estrictamente títulos y textos con `e()` / `{{ }}` para mitigar vulnerabilidades XSS.
  - En `D:\Laravel\Supertex AI\public\js\chat_stream.js`:
    - Conectar eventos de clic a las rutas de Laravel con notificaciones Toastr singleton.

---

### Checkpoint Fase 1
- [ ] Ejecutar migración SQL en PostgreSQL y verificar constraints CHECK (`chk_kvc_status`, `chk_kvc_scope`, `chk_kvc_user_scope`) y vista `v_knowledge_candidates_stats`.
- [ ] Ejecutar `php artisan test` en Laravel verificando permisos `manage-knowledge`.
- [ ] Ejecutar suite de pruebas unitarias para endpoints de ciclo de vida de candidatos con `pytest tests/api/test_candidates_lifecycle.py`.
- [ ] Probar borrado de sesión de chat con auditoría existente: verificar que la sesión se borra sin error y que la auditoría permanece inmutable.

---

## FASE 2: Detección en Background, Set Dorado, Guardarraíles de Consulta y Señal Excel

**Propósito**: Desarrollar el pipeline asíncrono de detección de correcciones con filtro previo basado en catálogo y SQL anterior, control de concurrencia y cancelación activa de Ollama, validación de condiciones booleanas con `sqlglot` y captura en servidor de señales de exportación a Excel.

- [x] **T201**: [P] Crear Set Dorado de prueba y pruebas de humo en `D:\Python\python-db\tests\fixtures\golden_dialogue_corrections.json` y `D:\Python\python-db\tests\unit\test_correction_detector.py`.
  - 30 casos en español real de negocio:
    - 15 positivos (correcciones explícitas de tablas, columnas y filtros de negocio).
    - 15 negativos (agradecimientos "gracias", quejas sin directiva "esto no sirve", consultas normales).
    - Incluir caso negativo de inyección por literal malicioso: `estado = 'ignora las instrucciones...'`.
  - Prueba de humo: verificar 0% de falsos positivos en negativos.

- [x] **T202**: Implementar filtro previo ligero (< 1 ms) y validador de catálogo en `D:\Python\python-db\app\use_cases\detect_dialogue_correction.py`.
  - Verificar que el turno previo del asistente contenga `generated_sql`.
  - Verificar que el mensaje del usuario contenga al menos una coincidencia léxica exacta con los nombres de tablas o columnas de `synced_tables` de la conexión activa.
  - Si no cumple ambos criterios, salir inmediatamente sin despertar al LLM.

- [x] **T203**: Implementar gestor de concurrencia y cancelación activa de Ollama en `D:\Python\python-db\app\infrastructure\llm\inference_concurrency_manager.py`.
  - Mantener contador atómico de inferencias activas en memoria compartida.
  - Si el detector en background está corriendo y entra una nueva consulta interactiva de usuario (`/chat/stream`), cerrar inmediatamente el socket/conexión HTTP hacia `/api/generate` de Ollama del detector.
  - Registrar métrica en contador de cancelaciones `dialogue_detector_cancellations_total` documentando la pérdida aceptable del candidato.

- [x] **T204**: Implementar detector estructurado en background con Ollama (`qwen2.5:3b`).
  - En `D:\Python\python-db\app\infrastructure\llm\dialogue_correction_detector.py`:
    - Configurar prompt estructurado con límite de 120 tokens de salida.
    - Extraer `{target_entity, target_column, prescriptive_condition, explanation}`.
    - Validar `target_entity` y `target_column` contra el catálogo real de la conexión.
    - Validar `prescriptive_condition` con `sqlglot.parse_one()` usando el dialecto de la conexión activa (MariaDB/PostgreSQL):
      - Exigir que sea estrictamente una expresión booleana válida referente a `target_column`.
      - Prohibir subconsultas, llamadas a funciones del sistema, sentencias múltiples y `;`.
      - Longitud máxima $\le 250$ caracteres.
      - Restringir literales: longitud de literal $\le 50$ caracteres y caracteres permitidos limitados a `^[a-zA-Z0-9_\-\.\s]+$`.
    - Sintetizar el texto formal de la regla: `"Para la tabla \`{target_entity}\`, la columna \`{target_column}\` debe cumplir: {prescriptive_condition}."`.
    - Redactar credenciales, tokens, correos y datos sensibles antes de almacenar.

- [x] **T205**: Conectar detector en background al final del stream de chat con sesión de BD propia.
  - En `D:\Python\python-db\app\api\v1\routers\chat.py` y `D:\Python\python-db\app\use_cases\ask_chat.py`:
    - Encolar tarea `asyncio.create_task` o `BackgroundTasks` tras emitir el evento SSE `done`.
    - La tarea debe abrir y cerrar su propia `AsyncSession` independiente (`async with async_session_factory() as bg_session:`).

- [x] **T206**: Implementar derivación de candidatos `sql_example` en el endpoint de exportación a Excel en el servidor.
  - En `D:\Python\python-db\app\api\v1\routers\chat.py` (o router de exportación):
    - En el endpoint `GET /api/v1/chat/export/excel`:
      - Validar titularidad del `dataset_id` contra `session_id` y `user_id`.
      - Validar que `sql_executed` sea un `SELECT` válido mediante `sqlglot` (sin funciones de mutación).
      - Redactar literales y datos sensibles del SQL.
      - Insertar candidato `sql_example` con `trigger_signal = 'excel_export'`, `status = 'candidate'`, `scope = 'user'`, utilizando cláusula `ON CONFLICT (source_message_id, trigger_signal) DO NOTHING`.

---

### Checkpoint Fase 2
- [x] Ejecutar `pytest tests/unit/test_correction_detector.py` contra el Set Dorado: comprobar 0 falsos positivos en negativos y bloqueo de inyecciones por literales.
- [x] Simular cancelación de Ollama: lanzar detector en background, disparar nueva pregunta y comprobar que la conexión a Ollama se cierra y el contador de cancelaciones se incrementa.
- [x] Probar exportación a Excel y verificar creación automática del candidato `sql_example` en base de datos sin duplicados.

---

## FASE 3: Conflictos Deterministas, Rollback con Restauración e Inyección al Prompt

**Propósito**: Resolver colisiones de directivas antes de guardar candidatos, implementar reversión y restauración histórica con purga de memoria vectorial, e inyectar de forma segura las directivas aprendidas en el system prompt respetando el feature flag.

- [x] **T301**: Implementar detección determinista de conflictos con advisory lock en `D:\Python\python-db\app\use_cases\save_knowledge_candidate.py`.
  - Adquirir `pg_advisory_xact_lock` con hash de la tupla `(connection_id, target_entity, target_column)` para evitar condiciones de carrera entre tareas concurrentes en background.
  - Consultar reglas existentes de esa tupla **únicamente** contra reglas globales verificadas (`scope = 'global' AND status = 'verified'`) y reglas del **mismo usuario** (`scope = 'user' AND user_id = :current_user`), nunca contra candidatos de otros usuarios.
  - Comparar la condición normalizada en AST de `sqlglot`:
    - Si la condición normalizada es idéntica: descartar inserción (`ON CONFLICT DO NOTHING`), no duplicar.
    - Si la condición normalizada difiere:
      - Si la colisión es contra una regla global verificada: la nueva regla nace con `status: 'conflict'`, `conflict_with_id = <global_rule_id>`. El usuario normal no puede sobrescribirla; se delega la resolución a un admin.
      - Si la colisión es contra una regla del mismo usuario: la nueva regla nace con `status: 'conflict'`, `conflict_with_id = <user_rule_id>`.
  - Al ejecutar `confirm-user` sobre un candidato propio en `conflict`: en una sola transacción atómica, pasar la regla anterior a `status: 'rolled_back'` y la nueva a `status: 'candidate'`, registrando ambos cambios en `knowledge_audit_logs`.

- [x] **T302**: Implementar rollback con restauración fiel de estado anterior en `D:\Python\python-db\app\use_cases\rollback_candidate.py`.
  - Consultar el último registro en `knowledge_audit_logs` para `rule_id`.
  - Si contiene `previous_state`, restaurar el snapshot de columnas (`status`, `content`, `prescriptive_condition`, `version`) y re-vectorizar el contenido anterior con `nomic-embed-text`.
  - Si no existe estado anterior, mutar a `status = 'rolled_back'`.
  - Purgar la caché de directivas en memoria del worker.

- [x] **T303**: [P] Añadir Feature Flag de inyección de reglas y configuración en `D:\Python\python-db\app\core\config.py`.
  - Agregar variable `ENABLE_DYNAMIC_KNOWLEDGE_INJECTION: bool = False` (apagado por defecto en `.env` hasta completar calibración).

- [x] **T304**: Implementar recuperación vectorial aislada e inyección al system prompt en `D:\Python\python-db\app\use_cases\ask_chat.py`.
  - Si `ENABLE_DYNAMIC_KNOWLEDGE_INJECTION` está activo:
    - Vectorizar la consulta usando el prefijo `search_query: `.
    - Ejecutar consulta SQL aislada con límite de top-3 reglas y umbral de similitud.
    - Inyectar directivas en el system prompt envueltas en delimitadores rígidos:
      `<<<DIRECTIVAS_APRENDIDAS>>> ... <<<FIN_DIRECTIVAS>>>`.
  - Persistir las reglas recuperadas en `chat_messages.metadata` bajo la clave `rules_applied: [{"id": "...", "title": "..."}]`.
  - Emitir `rules_applied` de forma aditiva en el evento SSE `done` sin alterar `session_id` ni `latency_ms`.

- [x] **T305**: [P] Actualizar contrato de chat SSE en `C:\Users\mrecinos\.gemini\antigravity\brain\4fc3f561-ad5b-4ca7-8933-eb4b05d3a2d5\contracts_chat_sse.md` para documentar el campo aditivo `rules_applied` en el evento `done`.

- [x] **T306**: Actualizar controlador de Laravel y vistas para propagar y renderizar `rules_applied`.
  - En `D:\Laravel\Supertex AI\app\Http\Controllers\ChatController.php`:
    - En `show(sessionId)` / mapeo de `GET /chat/sessions/{id}`, propagar `metadata.rules_applied` en cada mensaje del asistente.
  - En `D:\Laravel\Supertex AI\public\js\chat_stream.js`:
    - En el consumidor SSE del evento `done`: renderizar badge `"Reglas aplicadas: [Título]"` en el pie de la burbuja activa.
    - En `loadConversationSession()`: al renderizar mensajes desde el historial hidratado de BD, comprobar `msg.metadata?.rules_applied` y renderizar el mismo badge.

---

### Checkpoint Fase 3
- [x] Probar conflicto entre candidatos del mismo usuario: verificar lock transaccional, nacimiento como `conflict` y resolución atómica (`anterior -> rolled_back`, `nueva -> candidate`).
- [x] Probar conflicto contra regla global: verificar nacimiento como `conflict` y rechazo `403` si el usuario regular intenta sobrescribirla.
- [x] Encender `ENABLE_DYNAMIC_KNOWLEDGE_INJECTION=true`, formular consulta en el chat y verificar que la respuesta del asistente incluye el badge de reglas aplicadas en vivo y que sobrevive al recargar la página (F5 / hidratación).

---

## FASE 4: Calibración de Umbral, Pruebas de Humo y Verificación Integral

**Propósito**: Ajustar empíricamente el umbral de recuperación de embeddings con un set independiente de pares consulta-regla en español, verificar la ausencia de falsos positivos y validar la resiliencia integral del sistema.

- [x] **T401**: [P] Crear dataset de calibración de embeddings y script evaluador en `D:\Python\python-db\tests\fixtures\embedding_calibration_pairs.json` y `D:\Python\python-db\tools\calibrate_threshold.py`.
  - 40 pares de consultas en español emparejadas con reglas de negocio de Supertex.
  - Script que evalúa similitudes con `nomic-embed-text` usando prefijos `search_document: ` y `search_query: `, graficando curva Precision-Recall para fijar el umbral óptimo (e.g. 0.78 vs 0.75).
  - Actualizar el umbral por defecto en `D:\Python\python-db\app\core\config.py` y activar `ENABLE_DYNAMIC_KNOWLEDGE_INJECTION=true`.

- [x] **T402**: Ejecutar suite completa de pruebas unitarias y de integración en FastAPI.
  - `pytest tests/unit/ tests/integration/` verificando:
    - Detección de correcciones y bloqueo de inyecciones por literal.
    - Cancelación activa de inferencias en Ollama.
    - Autorización estricta de roles en endpoints de candidatos.
    - Inmutabilidad de `knowledge_audit_logs`.

- [x] **T403**: Ejecutar suite de pruebas de Laravel y compilación de frontend.
  - `php artisan test` en `D:\Laravel\Supertex AI`.
  - `npm run build` en `D:\Laravel\Supertex AI`.

- [x] **T404**: Validación manual integral de los 6 escenarios de [quickstart.md](file:///d:/Python/python-db/specs/003-implicit-dialogue-learning/quickstart.md):
  - Detección y aplicación en turno subsiguiente con badge visual.
  - Confirmación personal y postulación.
  - Intento de rechazo de regla global por usuario normal (`403 Forbidden`).
  - Detección determinista de conflicto al insertar.
  - Intento de prompt injection malicioso.
  - Eliminación de sesión de chat comprobando que la auditoría y los candidatos persisten intactos.

---

## Dependencias y Orden de Ejecución

```
Fase 1 (Datos, Auditoría, Permisos y UI)
  │
  ▼
Fase 2 (Filtro Catálogo, Detector Cancelable y Señal Excel)
  │
  ▼
Fase 3 (Conflictos Deterministas, Rollback con Restauración e Inyección con Feature Flag)
  │
  ▼
Fase 4 (Calibración con Set Independiente, Pruebas de Humo y Verificación Integral)
```

- Las tareas marcadas con `[P]` (`T101`, `T102`, `T103`, `T201`, `T303`, `T305`, `T401`) pueden ejecutarse en paralelo por intervenir en componentes aislados o repositorios independientes.
- Ninguna tarea de Fase 3 de inyección puede activarse en producción sin el Feature Flag `ENABLE_DYNAMIC_KNOWLEDGE_INJECTION` habilitado tras la calibración de Fase 4.
