# Feature Specification: Resiliencia Conversacional, Reintento con Reparación y Aclaración de Ambigüedades

**Feature Branch**: `006-conversational-resilience-and-ambiguity-repair`  
**Created**: 2026-11-11  
**Status**: Draft Specification  
**Input**: Prevenir que el asistente falle en silencio o lance errores técnicos crudos cuando no comprende una consulta o cuando la consulta es ambigua:
1. **Reintento con Auto-Reparación (Self-Healing SQL)**: Si el SQL generado falla en ejecución o validación (sintaxis, tabla o columna inexistente), reintentar hasta 2 veces retroalimentando al LLM con el mensaje de error exacto y el esquema específico, siempre bajo el amparo de `SQLGuardrail` y con límite estricto de timeout.
2. **Aclaración Activa en vez de Adivinar**: Si la similitud semántica queda por debajo del umbral de confianza o existen múltiples tablas candidatas en empate cercano, el asistente no inventa SQL; formula una pregunta aclaratoria con opciones interactivas (ej: *"¿Te refieres a `animal` o a `mascota`?"*).
3. **Cola de Términos Desconocidos / No Entendidos**: Registro persistente del término no comprendido, la pregunta completa y las tablas candidatas descartadas, accesible para programadores/administradores para su conversión en sinónimos (`glossary.yaml` o reglas mediante el CLI de la feature 005).
4. **Aprendizaje de la Aclaración Resuelta**: Si el usuario responde la aclaración eligiendo una opción, la correspondencia `término -> tabla/columna` nace como candidato con `scope = 'user'` a través del ciclo de vida de candidatos (Fase 1/3), jamás como regla global directa.
5. **Métricas de Observabilidad**: Medición de tasa de auto-reparación exitosa, volumen de aclaraciones solicitadas, términos en cola y sobrecosto de latencia en CPU con límite de tiempo de corte.

---

## 1. User Scenarios & Testing *(mandatory)*

### User Story 1 - Auto-Reparación de SQL sin Exponer Errores Técnicos al Usuario (Priority: P1)

Como usuario del chat de DataMind AI, cuando formulo una pregunta compleja donde el modelo comete un error inicial en un nombre de columna o sintaxis de `JOIN`, quiero que el asistente intente corregirse internamente en un segundo intento enviándose el error a sí mismo, para que yo reciba una respuesta válida y limpia sin ver excepciones técnicas crudas (`ProgrammingError`, `UndefinedColumn`, `SyntaxError`).

**Why this priority**: Es la causa número uno de frustración del usuario en sistemas Text-to-SQL. En muchos casos, el LLM solo se equivoca por una letra en un alias o columna; retroalimentarlo con el error permite salvar la respuesta sin intervención humana.

**Independent Test**:
1. Formular una pregunta que induzca un error de columna (ej: invocar una columna que el modelo confunda con plural/singular).
2. El primer intento de ejecución falla con: `no existe la columna «id_parte» (debe ser «id_parte_maquina»)`.
3. El middleware de reparación captura el error, prepara un sub-prompt con el error exacto y el fragmento del DDL correspondiente, y solicita una corrección (Intento 2).
4. El modelo genera el SQL corregido, `SQLGuardrail` lo valida, la base de datos lo ejecuta y el usuario recibe su respuesta sin enterarse del fallo inicial.
5. Si tras 2 reintentos sigue fallando, se devuelve un mensaje cortés explicativo en lenguaje natural, nunca el stack trace de la base de datos.

**Acceptance Scenarios**:
1. **Given** un error de compilación o ejecución en la base de datos remota, **When** el contador de reintentos es $< 2$, **Then** el sistema reintenta la generación inyectando el error exacto en el prompt de corrección.
2. **Given** cualquier SQL generado en el ciclo de reintento, **When** pasa a ejecución, **Then** DEBE someterse a `SQLGuardrail` (solo `SELECT`, prohibición de DDL/DML, `LIMIT 500`).
3. **Given** un límite de tiempo acumulado (timeout global de 60s para la petición), **When** el tiempo se agota durante los reintentos, **Then** el proceso se interrumpe y entrega una disculpa cortés solicitando reformular la consulta.

---

### User Story 2 - Pregunta de Aclaración Asistida ante Incertidumbre o Ambigüedad (Priority: P1)

Como usuario que realiza una pregunta con términos ambiguos o con bajo nivel de confianza en la recuperación (ej: *"dime los registros de clientes"* cuando existen `clientes_nacionales` y `clientes_exportacion`), quiero que el asistente me pida aclaración ofreciéndome botones u opciones claras, en lugar de adivinar o consultar la tabla equivocada.

**Why this priority**: Adivinar en bases de datos empresariales conduce a datos falsos ("alucinaciones de datos"). Una pregunta de aclaración rápida genera confianza y garantiza que el reporte sea el que el usuario realmente necesita.

**Independent Test**:
1. Formular una pregunta con coincidencia semántica dividida entre dos tablas de similar puntaje RRF (ej: score de diferencia $< 0.05$) o donde el puntaje máximo esté por debajo del umbral mínimo de confianza ($0.65$).
2. El clasificador detecta ambigüedad y detiene la generación de SQL.
3. El asistente responde: *"Para responderte con exactitud, ¿a cuál de las siguientes tablas te refieres?"* presentando opciones interactivas: `[1. Clientes Nacionales]` `[2. Clientes Exportación]`.
4. El usuario hace clic en `Clientes Nacionales`.
5. El sistema procede con la consulta correcta y registra el aprendizaje.

**Acceptance Scenarios**:
1. **Given** una recuperación con score vectorial máximo inferior a `CONFIDENCE_THRESHOLD_MIN` (ej: 0.68), **When** se evalúa la consulta, **Then** el sistema emite una respuesta de aclaración guiada sin ejecutar SQL a ciegas.
2. **Given** dos o más tablas en empate técnico (diferencia relativa $< 5\%$), **When** no hay contexto previo en la sesión, **Then** el asistente solicita al usuario elegir entre las opciones candidatas.

---

### User Story 3 - Aprendizaje Guiado de la Elección del Usuario (Priority: P2)

Como usuario que acaba de resolver una aclaración (ej: elegí que *"perros"* se refiere a `animal.especie`), quiero que el sistema recuerde mi elección para mis próximas consultas dentro de mi espacio de trabajo, registrándolo como un candidato de conocimiento personal (`scope = 'user'`), sin alterar las reglas globales de la empresa hasta que sea verificado.

**Why this priority**: Evita que el usuario tenga que responder la misma aclaración una y otra vez, integrando la resolución directamente en el ciclo de vida de candidatos preexistente.

**Independent Test**:
1. El usuario aclara que *"repuestos de corte"* se refiere a `hop.parte_maquina` con filtro `id_tipo_parte_maquina = 4`.
2. El sistema guarda la correspondencia como candidato en `knowledge_vector_chunks` con `scope = 'user'`, `status = 'candidate'`, `user_id = current_user`.
3. En la siguiente consulta del mismo usuario: *"cuántos repuestos de corte hay"*, el asistente aplica la regla directamente mostrando el badge de regla aplicada.

**Acceptance Scenarios**:
1. **Given** la resolución de una aclaración por parte del usuario, **When** se guarda la directiva, **Then** nace estrictamente como `scope: 'user'` y `status: 'candidate'` (cumpliendo con la gobernanza de Fases 1 a 4).
2. **Given** una regla personal aprendida de una aclaración, **When** otro usuario consulta lo mismo, **Then** la regla no se le aplica hasta que un administrador la promueva a `scope: 'global'`.

---

### User Story 4 - Bandeja de Términos No Entendidos para Administradores (Priority: P3)

Como administrador o ingeniero de datos, quiero disponer de una bandeja o reporte de "Términos No Entendidos" donde pueda ver qué palabras o preguntas generaron dudas o aclaraciones en los usuarios, junto con las tablas que el sistema evaluó, para poder incorporarlas formalmente al glosario de la empresa (`glossary.yaml`) con un solo clic o comando.

**Why this priority**: Proporciona telemetría real del uso del sistema. Cierra el ciclo entre la experiencia del usuario final y el mantenimiento del conocimiento por parte de los desarrolladores.

**Independent Test**:
1. Múltiples usuarios preguntan por *"troqueles"* o *"guías aéreas"* y el sistema pide aclaraciones o no encuentra coincidencias.
2. Los eventos se registran en la tabla `unresolved_query_terms`.
3. El administrador consulta `GET /api/v1/knowledge/unresolved-terms` o ejecuta `python -m app.cli.review_unresolved`.
4. El administrador selecciona el término y lo exporta como sinónimo a `knowledge/<conn>/glossary.yaml` para re-ejecutar `load_knowledge`.

**Acceptance Scenarios**:
1. **Given** una consulta que requirió aclaración o cuyos reintentos fallaron, **When** concluye la petición, **Then** se registra una fila en `unresolved_query_terms` con `(connection_id, user_query, extracted_term, candidate_tables, created_at)`.
2. **Given** la resolución del término por un administrador en el archivo YAML, **When** se ejecuta `load_knowledge`, **Then** el término se marca como resuelto en la base de datos.

---

## 2. Requirements & Guardrails *(mandatory)*

### Functional Requirements

- **FR-001 (Ciclo de Reintento con Auto-Reparación)**:
  - En `AskChatUseCase`, si la ejecución de la consulta SQL generada produce un error de base de datos (`ProgrammingError`, `UndefinedTable`, `UndefinedColumn`, `DataError`) o falla la validación sintáctica de `sqlglot`:
    - El sistema DEBE capturar el error y reintentar la generación hasta un **máximo de 2 veces** (`MAX_SQL_REPAIR_ATTEMPTS = 2`).
    - En el prompt de reintento DEBE incluirse:
      ```
      LA CONSULTA ANTERIOR FALLÓ CON EL SIGUIENTE ERROR:
      {mensaje_error_base_datos}
      CONSULTA ERRÓNEA:
      {sql_anterior}
      ESQUEMA EXACTO DISPONIBLE:
      {ddl_o_columnas_relevantes}
      INSTRUCCIÓN: Corrige la consulta SQL para solucionar el error exacto reportado. Retorna ÚNICAMENTE la sentencia SELECT corregida.
      ```
    - Todo intento subsiguiente DEBE pasar obligatoriamente por `SQLGuardrail` antes de tocar la base de datos.
    - Se debe contabilizar el tiempo de CPU consumido; si el tiempo total de la solicitud excede 45 segundos, se aborta el ciclo de reintento.
- **FR-002 (Detección de Ambigüedad y Aclaración Activa)**:
  - Si la similitud máxima de recuperación de esquema es menor a `SIMILARITY_THRESHOLD_AMBIGUITY` (0.65) o si las dos tablas principales tienen un score RRF con diferencia menor a `0.04`:
    - El asistente NO DEBE generar SQL.
    - DEBE emitir un mensaje conversacional estructurado con evento SSE `clarification`:
      ```json
      {
        "type": "clarification_request",
        "question": "¿A cuál de las siguientes opciones te refieres para tu consulta?",
        "options": [
          {"id": "tabla_a", "label": "Inventario de Repuestos (inventario_partes)", "hint": "Piezas físicas en bodega"},
          {"id": "tabla_b", "label": "Catálogo de Ingeniería (hop.parte_maquina)", "hint": "Definición técnica de la máquina"}
        ],
        "original_prompt": "{prompt_usuario}"
      }
      ```
- **FR-003 (Persistencia de la Aclaración Resuelta como Candidato)**:
  - Cuando el usuario responde a una aclaración seleccionando una opción, el endpoint `/chat/stream` recibe `clarification_resolved: {term: "...", selected_target: "..."}`.
  - La relación se persiste automáticamente en `knowledge_vector_chunks` con:
    - `target_entity = selected_target`
    - `trigger_signal = 'clarification_resolved'`
    - `status = 'candidate'`
    - `scope = 'user'`
    - `user_id = current_user`
    - Registro de trazabilidad en `knowledge_audit_logs`.
- **FR-004 (Cola de Términos No Entendidos)**:
  - Crear tabla en PostgreSQL `unresolved_query_terms`:
    - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
    - `connection_id UUID NOT NULL REFERENCES database_connections(id) ON DELETE CASCADE`
    - `session_id UUID NOT NULL`
    - `user_id VARCHAR(100) NOT NULL`
    - `prompt TEXT NOT NULL`
    - `extracted_term VARCHAR(150) NOT NULL`
    - `discarded_candidates JSONB NOT NULL DEFAULT '[]'`
    - `status VARCHAR(30) NOT NULL DEFAULT 'pending'` (`pending`, `resolved`, `ignored`)
    - `resolved_by VARCHAR(100) NULL`
    - `resolved_at TIMESTAMP WITH TIME ZONE NULL`
    - `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL`
  - Exponer endpoint `GET /api/v1/knowledge/unresolved-terms` con filtro por `connection_id` y `status`.
- **FR-005 (Métricas de Observabilidad y Telemetría)**:
  - El sistema DEBE medir y registrar en memoria/logs estructurados:
    - `sql_repair_attempts_total`: Contador de intentos de auto-reparación disparados.
    - `sql_repair_success_total`: Contador de reparaciones exitosas en intento 1 o 2.
    - `sql_repair_exhausted_total`: Consultas que fallaron tras agotar los 2 intentos.
    - `clarifications_requested_total`: Preguntas de aclaración emitidas.
    - `clarifications_resolved_total`: Aclaraciones respondidas por el usuario.
    - `repair_latency_seconds`: Latencia incremental incurrida por los reintentos.

---

## 3. Success Criteria *(mandatory)*

- **SC-001 (Tasa de Recuperación por Auto-Reparación)**: Al menos el **70%** de las consultas que presentan errores tipográficos en nombres de columnas o pequeñas discrepancias de `JOIN` se resuelven exitosamente en el intento 1 de reparación sin intervención del usuario.
- **SC-002 (Cero Excepciones Técnicas Visibles)**: El 100% de las consultas no entendidas o fallidas devuelven un mensaje amigable o una aclaración interactiva; cero (0%) mensajes muestran excepciones internas de base de datos o stack traces de Python.
- **SC-003 (Tope Estricto de Latencia en Reintentos)**: Ningún ciclo de reintento de SQL incrementa el tiempo de respuesta total en más de **12 segundos** en hardware de CPU local.
- **SC-004 (Aislamiento de Reglas Aprendidas por Aclaración)**: El 100% de las aclaraciones resueltas por un usuario normal se registran como `scope: 'user'` y `status: 'candidate'`; ninguna muta directamente a regla global.
- **SC-005 (Auditabilidad y Telemetría)**: El 100% de las preguntas que requieren aclaración o fallan los reintentos quedan registradas en `unresolved_query_terms` para su incorporación en el glosario.
