# Feature Specification: Implicit Dialogue Learning & Knowledge Candidate Lifecycle

**Feature Branch**: `003-implicit-dialogue-learning`  
**Created**: 2026-11-10  
**Status**: Specification Refined (Governance, Ingestion Guardrails & Conflict Resolution)  
**Input**: Aprendizaje implícito en diálogo. Candidatos por usuario, promoción con autorización estricta, validación de condiciones con `sqlglot`, filtrado previo por catálogo, cancelación activa de inferencias en segundo plano, persistencia de `rules_applied` e inmutabilidad de auditoría.

---

## 1. User Scenarios & Testing *(mandatory)*

### User Story 1 - Detección Precisa de Correcciones con Filtro de Catálogo y Concurrencia Cancelable (Priority: P1)

Como analista o usuario del chat, cuando realizo una corrección prescriptiva sobre una consulta ("En la tabla `factura_lineas`, filtra siempre por `estado = 'A'`"), quiero que el sistema detecte de forma asíncrona esta directiva solo si la tabla y columna pertenecen al catálogo de la base de datos conectada y existió un SQL previo, validando la sintaxis booleana con `sqlglot`, para registrar un candidato personal sin saturar Ollama ni degradar la latencia de mi siguiente turno.

**Why this priority**: Es la base del aprendizaje continuo. Filtra el ruido descartando mensajes que no mencionen tablas/columnas reales y cancela activamente peticiones en segundo plano si el usuario envía una nueva pregunta antes de que termine el detector.

**Independent Test**:
1. El usuario ejecuta una consulta que genera SQL sobre `factura_lineas`.
2. En el turno siguiente, el usuario envía una corrección mencionando `factura_lineas` y `estado`.
3. El filtro rápido valida que existió SQL en el turno anterior y que `factura_lineas` y `estado` están en `synced_tables`.
4. El detector LLM se ejecuta en background con un límite estricto de 120 tokens de salida; si el usuario envía otra pregunta mientras corre, se cancela la conexión HTTP a Ollama de inmediato.
5. `sqlglot` valida que `prescriptive_condition` sea estrictamente una expresión booleana sobre la columna objetivo (`estado = 'A'`), sin subconsultas ni `;`.
6. La regla nace como `status: 'candidate'`, `scope: 'user'`.

**Acceptance Scenarios**:
1. **Given** un mensaje del usuario que no menciona tablas ni columnas del catálogo de la conexión activa, **When** pasa por el filtro previo, **Then** se descarta de inmediato sin invocar al LLM.
2. **Given** un detector en background procesando una corrección previa, **When** el usuario envía una nueva consulta al chat, **Then** el contador de inferencias en vuelo detecta la nueva petición y cancela la conexión a Ollama del detector para dar paso a la inferencia del usuario.
3. **Given** un candidato extraído, **When** `sqlglot` analiza `prescriptive_condition`, **Then** exige que sea una expresión booleana válida referente a la columna objetivo, con longitud máxima de 250 caracteres y sin `;`, subconsultas ni llamadas a funciones del sistema.

---

### User Story 2 - Ciclo de Vida Persistente: Confirmación Personal, Postulación y Promoción por Admin (Priority: P2)

Como usuario o administrador, quiero que el ciclo de vida del candidato refleje estados persistentes claros: el usuario autor puede confirmar la regla para su propio uso (`confirmed_at`) o postularla a revisión corporativa (`proposed_global_at`); mientras que la promoción a `scope: global` queda reservada exclusivamente a administradores, al igual que cualquier `reject` o `rollback` sobre reglas globales.

**Why this priority**: Garantiza la gobernanza estricta de datos. Impide que usuarios sin privilegios modifiquen o revoquen reglas corporativas globales.

**Independent Test**:
- Usuario normal ejecuta `confirm-user` $\to$ se asigna `confirmed_at = NOW()`, regla se mantiene en `scope: user`.
- Usuario normal ejecuta `propose-global` $\to$ se asigna `proposed_global_at = NOW()`.
- Administrador lista candidatos pendientes con `GET /knowledge/candidates?proposed_only=true`.
- Usuario normal intenta `reject` o `rollback` sobre una regla de `scope: global` $\to$ `403 Forbidden`.
- Administrador ejecuta `promote-global` $\to$ pasa a `scope: global`, `status: verified`, re-sanitiza, re-vectoriza y genera nueva versión.

**Acceptance Scenarios**:
1. **Given** un candidato de Usuario A, **When** Usuario A ejecuta `confirm-user`, **Then** se actualiza `confirmed_at` persistente en base de datos.
2. **Given** un candidato postulado, **When** un admin consulta la bandeja con filtro de propuestas pendientes, **Then** la regla se lista para su curación.
3. **Given** una regla con `scope: global`, **When** un usuario sin rol de administrador intenta rechazarla (`reject`) o revertirla (`rollback`), **Then** la API rechaza la solicitud con `HTTP 403 Forbidden`.

---

### User Story 3 - Detección Determinista de Conflictos al Insertar y Resolución de Candidatos (Priority: P3)

Como motor de inferencia, quiero que cualquier candidato nuevo cuya tupla `(connection_id, target_entity, target_column)` ya exista con una condición normalizada diferente nazca automáticamente en estado `status: 'conflict'`, evitando que reglas incompatibles se apliquen en silencio.

**Why this priority**: La detección determinista en base de datos elimina ambigüedades antes de cualquier cálculo vectorial y previene alucinaciones en el SQL generado.

**Independent Test**:
- Existe una regla con `(conn_1, factura_lineas, estado)` con condición `estado = 'A'`.
- Se detecta una nueva corrección para `(conn_1, factura_lineas, estado)` con condición `estado = 'P'`.
- La nueva regla se inserta directamente como `status: 'conflict'`, vinculando `conflict_with_id`.
- Si ambas reglas pertenecen al mismo usuario, la nueva regla candidata suspende a la anterior marcándola como `rolled_back` tras confirmación explícita del usuario.

**Acceptance Scenarios**:
1. **Given** una tupla `(connection_id, target_entity, target_column)` preexistente en el mismo alcance, **When** se evalúa la nueva condición normalizada y difiere, **Then** la regla se guarda directamente con `status: 'conflict'`.
2. **Given** dos candidatos del mismo usuario sobre la misma columna, **When** el usuario confirma la más reciente, **Then** la anterior pasa a `status: 'rolled_back'` registrando el reemplazo en auditoría.

---

### User Story 4 - Persistencia de `rules_applied` en Mensajes y Sobrevivencia a Hidratación (Priority: P4)

Como usuario que revisa el chat o recarga la página, quiero ver qué reglas de negocio o correcciones fueron inyectadas en la respuesta del asistente, tanto durante el streaming en vivo como al hidratar la conversación desde la base de datos (`GET /chat/sessions/{id}`).

**Why this priority**: Da explicabilidad al usuario de por qué el modelo filtró de determinada manera y asegura consistencia total ante navegación y recargas.

**Independent Test**:
1. Asistente responde aplicando una regla activa.
2. La respuesta incluye metadata `"rules_applied": [{"id": "...", "title": "Filtro Estado Activo"}]`.
3. El frontend renderiza un badge `"Reglas aplicadas: Filtro Estado Activo"`.
4. El usuario recarga la página (F5) o cambia de sesión; al cargar la sesión desde la BD, `rules_applied` se recupera de los metadatos persistidos en `chat_messages.metadata`.

**Acceptance Scenarios**:
1. **Given** una inferencia donde se recuperaron reglas activas, **When** se emite el evento SSE `done` y se commitea el mensaje del asistente, **Then** `rules_applied` se almacena en `chat_messages.metadata`.
2. **Given** una sesión reabierta vía `GET /chat/sessions/{id}`, **When** se devuelven los mensajes, **Then** cada mensaje del asistente incluye su array `rules_applied` intacto.

---

## 2. Requirements *(mandatory)*

- **FR-001 (Migración No Destructiva)**: La migración de `knowledge_vector_chunks` DEBE aplicar las columnas `status`, `scope` y `trigger_signal` mediante un `DEFAULT` temporal (`'verified'`, `'global'`, `'manual_teach'`), ejecutar el backfill sobre filas existentes, y luego remover el `DEFAULT` (`ALTER TABLE ... ALTER COLUMN ... DROP DEFAULT`) aplicando `CHECK constraints`.
- **FR-002 (Inmutabilidad de Auditoría Desacoplada)**:
  - `knowledge_audit_logs` NO debe tener foreign key a `chat_sessions` (almacena `source_session_id` como UUID plano sin restricción de integridad referencial).
  - `knowledge_audit_logs.rule_id` DEBE implementar borrado lógico o prescindir de `RESTRICT` para no romper el ciclo de vida de la tabla principal ante limpiezas.
  - El trigger PostgreSQL anti-mutación DEBE impedir `UPDATE` y `DELETE` manuales en auditoría, sin bloquear el borrado de sesiones de chat.
- **FR-003 (Validación de Condición con `sqlglot`)**:
  - `prescriptive_condition` DEBE validarse mediante `sqlglot.parse_one()`.
  - Debe ser estrictamente una expresión booleana válida (e.g. `Binary`, `Between`, `In`).
  - Solo puede referenciar la columna objetivo `target_column`.
  - Prohibidas subconsultas, llamadas a funciones de sistema, comandos múltiples o caracteres `;`.
  - Longitud máxima permitida: 250 caracteres.
- **FR-004 (Filtro Previo Basado en Catálogo y SQL Previo)**:
  - El filtro rápido descarta el mensaje en < 1 ms si no existió una consulta SQL en el turno previo del asistente o si el texto del usuario no contiene al menos una coincidencia exacta de tabla o columna registrada en `synced_tables`.
- **FR-005 (Control de Concurrencia y Cancelación Activa de Ollama)**:
  - Se debe mantener un contador de inferencias activas en memoria compartida.
  - Si el detector en background está ejecutándose en Ollama y entra una nueva pregunta del usuario, el sistema DEBE abortar la conexión HTTP al endpoint `/api/generate` de Ollama de inmediato.
  - El prompt del detector limita su salida a un máximo de 120 tokens.
- **FR-006 (Conflictos Deterministas al Insertar)**:
  - La verificación de colisiones compara `(connection_id, target_entity, target_column)` con la condición normalizada en AST. Si existe discrepancia con una regla activa, la regla nace con `status: 'conflict'`.
- **FR-007 (Estados Persistentes de Confirmación y Postulación)**:
  - La tabla `knowledge_vector_chunks` incluye `confirmed_at TIMESTAMP NULL` y `proposed_global_at TIMESTAMP NULL`.
  - `confirm-user` establece `confirmed_at = NOW()`.
  - `propose-global` establece `proposed_global_at = NOW()`.
  - `GET /knowledge/candidates` soporta el filtro `proposed_only=true` para el panel administrativo.
- **FR-008 (Autorización Estricta en Reglas Globales)**:
  - Las acciones `reject` y `rollback` sobre reglas con `scope: 'global'` SOLO pueden ser ejecutadas por administradores (`super-admin` o permiso `manage-knowledge`).
  - La acción `rollback` restaura el estado previo desde `previous_state` en `knowledge_audit_logs` si existe, o marca `status: 'rolled_back'`.
- **FR-009 (Persistencia de Reglas Aplicadas en Chat)**:
  - El campo `rules_applied` se guarda en `chat_messages.metadata` y se expone tanto en el evento SSE final como en `GET /chat/sessions/{id}`.
- **FR-010 (Redacción y Escapado en Vistas)**:
  - Redacción estricta de literales y datos sensibles en candidatos `sql_example`.
  - Todo título y contenido de regla renderizado en Blade DEBE ser escapado explícitamente con `e()` / `{{ }}` para mitigar Cross-Site Scripting (XSS).
- **FR-011 (Permisos en Laravel)**:
  - Se debe crear el permiso `manage-knowledge` en la base de datos de Laravel y asignarlo al rol `super-admin` y `admin`.

---

## 3. Success Criteria *(mandatory)*

- **SC-001 (Prueba de Humo de Precisión)**: Cero (0%) falsos positivos sobre el conjunto de frases negativas del Set Dorado (mensajes de cortesía, consultas informales y preguntas generales no generan candidatos).
- **SC-002 (Calibración de Umbral Vectorial)**: El umbral de similitud de `nomic-embed-text` se calibra empíricamente con un set independiente de pares consulta-regla en español, optimizando el balance de recuperación.
- **SC-003 (Resistencia a Borrado de Sesiones)**: La eliminación de una sesión de chat con múltiples candidatos y auditorías asociadas se ejecuta en < 500 ms sin errores de integridad referencial ni excepciones de triggers.
