# DataMind AI: Arquitectura Integral del Sistema, Configuración de Tablas, Chat Conversacional y Aprendizaje

> **Propósito de este documento**: Proveer un contexto completo, exacto y operativo de la arquitectura de la aplicación **DataMind AI** para que Claude o cualquier modelo/desarrollador comprenda cómo configuramos conexiones y sincronizamos tablas, cómo funciona el motor conversacional de Text-to-SQL y streaming SSE, cómo se estructuran los datasets y exportaciones a Excel, y cómo opera el sistema de aprendizaje implícito en diálogo.

---

## 1. Visión General y Stack Tecnológico

DataMind AI es un asistente corporativo de analítica aumentada y Text-to-SQL que permite a los usuarios consultar datos empresariales en lenguaje natural, generar gráficos dinámicos interactivos, descargar reportes tabulares a Excel (.xlsx) y enseñarle reglas de negocio al sistema en el transcurso del diálogo.

```
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND (Laravel 11)                     │
│  - Blade + Tailwind CSS + Alpine.js / Vanilla JS            │
│  - Controlador SSE Proxy (FastApiClient / ChatController)   │
│  - Renderizado Markdown, Chart.js, Badges de Reglas         │
└───────────────▲─────────────────────────────┬───────────────┘
                │ HTTP Proxy / SSE            │ REST API
                │ (puerto 8085)               │
┌───────────────┴─────────────────────────────▼───────────────┐
│                    BACKEND (FastAPI)                        │
│  - Python 3.13 / FastAPI Asíncrono (puerto 8000)            │
│  - Pydantic V2, SQLAlchemy 2.0 (asyncpg), sqlglot           │
│  - Inferencia Local Ollama (qwen2.5:3b + nomic-embed-text)  │
│  - DynamicDBAdapter (MariaDB, MySQL, PostgreSQL)            │
└───────────────▲─────────────────────────────┬───────────────┘
                │                             │
    ┌───────────┴──────────┐       ┌──────────┴───────────────┐
    │  PostgreSQL 17       │       │  Bases de Datos de       │
    │  + pgvector          │       │  Negocio Externas        │
    │  - Sesiones y chat   │       │  - MariaDB / MySQL       │
    │  - Datasets caché    │       │  - PostgreSQL Externo    │
    │  - Memoria vectorial │       │    (Multi-esquema: hop,  │
    │  - Reglas aprendidas │       │     produccion, etc.)    │
    │  - Auditoría inmut.  │       └──────────────────────────┘
    └──────────────────────┘
```

---

## 2. Cómo se Configuran Conexiones y se Sincronizan Tablas

El sistema no está acoplado a una sola base de datos fija; cuenta con soporte multi-conexión dinámica (`DatabaseConnectionModel`).

### 2.1 Modelo de Datos de la Conexión (`database_connections`)
- **Campos**: `id` (UUID), `name`, `engine` (`mariadb`, `mysql`, `postgresql`), `host`, `port`, `database_name`, `username`, `password`, `is_active`, `synced_tables` (JSONB).
- **`synced_tables`**: Estructura JSONB que almacena la introspección del esquema:
  ```json
  [
    {
      "name": "factura_lineas",
      "schema_name": "public",
      "row_count": 125000,
      "columns": [
        {"name": "id", "type": "int", "is_primary": true},
        {"name": "id_factura", "type": "int", "is_foreign": true, "fk_target_table": "facturas", "fk_target_column": "id"},
        {"name": "estado", "type": "varchar(2)"},
        {"name": "monto", "type": "decimal(12,2)"}
      ]
    }
  ]
  ```

### 2.2 Proceso de Sincronización e Ingesta Vectorial
1. El usuario registra o selecciona una conexión y hace clic en **Sincronizar Tablas / Esquemas**.
2. **Introspección**: `ConnectionManagerUseCase` se conecta mediante `DynamicDBAdapter` (o dialectos específicos), lee el catálogo del motor relacional (`information_schema`, llaves foráneas, comentarios de columnas).
3. **Persistencia Vectorial de Esquemas (`KnowledgeDocumentModel` / `KnowledgeVectorChunkModel`)**:
   - Cada tabla se transforma en un documento sintético estructurado:
     `Tabla: <schema>.<tabla> (col1: tipo, col2: tipo). Relaciones FK: tabla.fk -> target.pk.`
   - Se vectoriza con el modelo local `nomic-embed-text` usando el prefijo `search_document: ` y se almacena en `knowledge_vector_chunks` (`category = 'db_schema'`).
   - Se guardan los `join_hints` y `related_tables` en el JSONB `metadata_` para habilitar **expansión de grafos relacionales 1-Hop** durante las consultas.

---

## 3. Flujo Conversacional, Intentos y Generación Text-to-SQL

Cuando un usuario envía un mensaje en el chat, la petición viaja desde el navegador hacia Laravel (`POST /chat/stream`), la cual actúa como proxy hacia FastAPI (`POST /chat/stream`).

### 3.1 Clasificación de Intención (`IntentClassifier`)
El mensaje entrante se evalúa en caliente para dirigir el flujo:
1. **`data_query`**: Preguntas que requieren consultar bases de datos (Text-to-SQL).
2. **`teach_knowledge`**: Instrucciones directas de entrenamiento en chat (e.g. *"La tabla pedidos se une con clientes por cliente_id"* o *"El estado A significa Activo"*).
3. **`process_qa`**: Consultas operativas sobre manuales corporativos (RAG semántico estándar).
4. **`general_chat`**: Saludos, cortesía o conversación genérica.

### 3.2 Búsqueda Híbrida y Expansión de Grafo 1-Hop
Para consultas de tipo `data_query`:
1. Se genera el embedding de la pregunta del usuario.
2. Se recuperan los fragmentos de esquema de mayor similitud coseno (`top_k=6`).
3. **1-Hop Relational Graph Expansion**: Si la consulta involucra `factura_lineas`, el sistema inspecciona sus `related_tables` en metadatos y agrega automáticamente la tabla padre `facturas`, garantizando que el modelo conozca cómo hacer el `JOIN` sin necesidad de que el usuario mencione ambas tablas explícitamente.
4. Se recuperan directivas y relaciones enseñadas (`custom_relation`, `business_rule`, `sql_example`).

### 3.3 Construcción del Prompt Text-to-SQL y Validación con `sqlglot`
- El modelo `qwen2.5:3b` formula la consulta en SQL estricto.
- **Guardrail de Seguridad (`SQLGuardrail`)**:
  - Parsea la consulta con `sqlglot.parse_one(sql, dialect=sql_dialect)`.
  - Exige que sea estrictamente `SELECT`.
  - Prohíbe mutaciones (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, llamadas a `pg_sleep`, etc.).
  - Inyecta `LIMIT 500` si la consulta no define límite.
  - Valida el soporte multi-esquema (e.g. `produccion.ordenes`, `hop.parte_maquina`).

---

## 4. Streaming en Vivo (Server-Sent Events) y Reintento

La comunicación entre FastAPI y el cliente web utiliza SSE (`text/event-stream`).

### 4.1 Ciclo de Eventos SSE
```
Cliente HTTP                 Laravel (Proxy)                   FastAPI (Backend)
     │                             │                                  │
     │─── POST /chat/stream ───────►─── POST /chat/stream ────────────►│ (use_case.execute_sync)
     │                             │                                  │
     │◄── : ping (cada 10s) ───────┼─── : ping ───────────────────────┤ (Heartbeat TCP)
     │                             │                                  │
     │◄── event: session ──────────┼─── event: session ───────────────┤ (session_id confirmado)
     │                             │                                  │
     │◄── event: token ────────────┼─── event: token ─────────────────┤ (token a token simulado)
     │                             │                                  │
     │◄── event: dataset (opc) ────┼─── event: dataset ───────────────┤ (id, columnas, filas)
     │                             │                                  │
     │◄── event: done ─────────────┼─── event: done ──────────────────┤ (latency_ms, rules_applied)
     │                             │                                  │
```

- **`retry_message_id`**: Permite reintentar un mensaje interrumpido o fallido sin duplicar el registro del usuario en `chat_messages`.
- **Heartbeat `: ping`**: Cada 10s se emite un comentario SSE para evitar que proxies reversos o navegadores corten la conexión TCP por inactividad.

---

## 5. Datasets Tabulares, Caché y Exportación a Excel

1. Cuando la consulta SQL retorna resultados:
   - Se genera un identificador único `dataset_id = "ds_..."`.
   - Se persisten las filas y columnas completas en la tabla PostgreSQL `query_datasets` con expiración automática (`expires_at = NOW() + 2 horas`).
2. Se emite el evento `dataset` al cliente.
3. El frontend renderiza la tabla interactiva y los botones **Descargar Excel** y **Constructor de Gráficos (Chart.js)**.
4. **Descarga de Excel (`GET /export/excel/{dataset_id}`)**:
   - Genera en memoria un archivo `.xlsx` estilizado con encabezados azules Supertex, auto-ajuste de ancho de columnas y tipos de datos numéricos correctos.
   - **Señal implícita de aprendizaje**: La exportación a Excel exitosa registra automáticamente en segundo plano la consulta SQL como candidata a ejemplo (`sql_example`) mediante `ON CONFLICT DO NOTHING`.

---

## 6. Sistema de Aprendizaje Implícito en Diálogo (`003`)

El sistema aprende de las correcciones del usuario sin requerir un botón explícito de "enseñar".

### 6.1 Principio Rector: Candidato vs Verificado
- El aprendizaje implícito produce **CANDIDATOS** (`status = 'candidate'`), nunca verdad absoluta.
- **Alcances (`scope`)**:
  - `user`: Visible únicamente para el usuario que formuló la corrección.
  - `global`: Aplica a todos los usuarios de la base de datos (requiere aprobación explícita de un Administrador).

### 6.2 Flujo de Detección en Background
1. **Filtro Previo Ligero (< 1 ms)**:
   - Exige que en el turno previo el asistente haya ejecutado SQL.
   - Exige coincidencia léxica exacta por límites de palabra (`\b`) entre el mensaje del usuario y los nombres de tablas o columnas registradas en `synced_tables`.
   - Mensajes de cortesía ("gracias", "excelente") o preguntas genéricas se descartan inmediatamente sin invocar al LLM.
2. **Detector LLM (`qwen2.5:3b`)**:
   - Corre en background con su propia sesión de BD (`AsyncSession`).
   - Límite de 120 tokens de salida y temperatura `0.0`.
   - Extrae el JSON `{target_entity, target_column, prescriptive_condition}`.
3. **Validador Sintáctico Estricto (`PrescriptiveConditionValidator`)**:
   - Valida la condición con `sqlglot`.
   - Exige que sea una expresión booleana referente únicamente a la columna objetivo.
   - Prohíbe subconsultas, llamadas a funciones del sistema (`sleep`, `system`, etc.) y punto y coma (`;`).
   - **Anti-Prompt-Injection por Literales**: Limita la longitud de literales a $\le 35$ caracteres y restringe los caracteres a `^[a-zA-Z0-9_\-\.\s]+$`.

### 6.3 Concurrencia y Cancelación Activa de Ollama
- `InferenceConcurrencyManager`: Singleton con contador atómico.
- Si el detector en background está ejecutándose y llega una nueva pregunta interactiva del usuario al chat, el gestor **cierra inmediatamente la conexión HTTP hacia Ollama**, cancelando la tarea en background para priorizar la fluidez del chat interactivo e incrementando la métrica `dialogue_detector_cancellations_total`.

### 6.4 Detección Determinista de Conflictos y Locks
- `SaveKnowledgeCandidateUseCase` adquiere un `pg_advisory_xact_lock` con hash de `(connection_id, target_entity, target_column)`.
- Compara únicamente contra reglas globales verificadas y reglas del mismo usuario:
  - Si la condición normalizada en AST es idéntica $\rightarrow$ Descarte por duplicado (`ON CONFLICT DO NOTHING`).
  - Si difiere $\rightarrow$ Nace con `status = 'conflict'` y apunta a `conflict_with_id`.
- **Resolución**:
  - Si colisiona con regla global: Solo un administrador puede resolverlo (un usuario regular recibe `403 Forbidden`).
  - Si colisiona con regla propia del usuario: Al confirmar la nueva regla (`confirm-user`), en una sola transacción atómica la anterior pasa a `status = 'rolled_back'` y la nueva pasa a `status = 'candidate'`.

### 6.5 Inyección al Prompt y Badge Visual
- Protegido por el Feature Flag `ENABLE_DYNAMIC_KNOWLEDGE_INJECTION` (umbral calibrado en `0.67` para 100% de precisión).
- Al generar SQL, se buscan directivas activas y se inyectan en el system prompt delimitadas por:
  ```
  <<<DIRECTIVAS_APRENDIDAS>>>
  - Regla para `factura_lineas` (`estado`): estado = 'A'
  <<<FIN_DIRECTIVAS>>>
  ```
- **Persistencia**: Las reglas aplicadas se guardan en `chat_messages.metadata["rules_applied"]` y se emiten en el evento SSE `done`.
- **Frontend**: Laravel renderiza el badge esmeralda:
  `🧠 Reglas aplicadas: [Título]` tanto en el streaming en vivo como al recargar la página (F5) o hidratar sesiones históricas.

### 6.6 Auditoría Inmutable
- Tabla `knowledge_audit_logs`.
- Trigger a nivel de base de datos (`prevent_knowledge_audit_tampering`) que prohíbe `UPDATE` y `DELETE`.
- Relación desacoplada (sin FK restrictiva que bloquee la eliminación de sesiones de chat).

---

## 7. Estructura Principal del Repositorio

```
D:\Python\python-db\
├── app/
│   ├── api/v1/
│   │   ├── routers/
│   │   │   ├── chat.py                 # Endpoints /chat/stream, /chat/sessions
│   │   │   ├── connections.py          # Gestión y sincronización de conexiones BD
│   │   │   ├── export.py               # Descarga Excel y señal de aprendizaje
│   │   │   └── knowledge.py            # Ciclo de vida de candidatos (confirm, propose, rollback)
│   │   └── schemas/                    # Esquemas Pydantic V2
│   ├── core/
│   │   └── config.py                   # Pydantic Settings & Feature Flags
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── candidate_repository.py # Repositorio de candidatos y auditoría
│   │   │   ├── models.py               # Modelos SQLAlchemy (Postgres + pgvector)
│   │   │   └── vector_repository.py    # Búsqueda vectorial coseno en pgvector
│   │   └── llm/
│   │       ├── dialogue_correction_detector.py # Detector Ollama en background
│   │       ├── inference_concurrency_manager.py# Concurrencia y cancelación activa
│   │       ├── prescriptive_condition_validator.py # Validación AST con sqlglot
│   │       ├── sql_guardrail.py        # Validación y saneamiento Text-to-SQL
│   │       └── ollama_adapter.py       # Cliente HTTP asíncrono para Ollama
│   └── use_cases/
│       ├── ask_chat.py                 # Orquestador del flujo de chat y Text-to-SQL
│       ├── detect_dialogue_correction.py# Filtro previo y ejecución del detector
│       ├── save_knowledge_candidate.py # Guardado con advisory locks y conflictos
│       └── rollback_candidate.py       # Reversión y restauración de versiones
├── specs/                              # Especificaciones Spec-Kit (001, 002, 003)
├── tests/
│   ├── fixtures/
│   │   ├── golden_dialogue_corrections.json    # Set Dorado de 30 frases (Fase 2)
│   │   └── embedding_calibration_pairs.json    # 40 pares de calibración (Fase 4)
│   └── unit/                           # Tests unitarios del ciclo de vida y AST
└── tools/
    └── calibrate_threshold.py          # Script de calibración Precision-Recall

D:\Laravel\Supertex AI\
├── app/
│   ├── Http/Controllers/
│   │   └── ChatController.php          # Proxy SSE, historial y exportación
│   └── Services/
│       └── FastApiClient.php           # Cliente HTTP / Stream hacia FastAPI
├── public/js/
│   └── chat_stream.js                  # Motor SSE, renderizado Markdown y badges
└── resources/views/chat/
    ├── index.blade.php                 # Vista principal del chat corporativo
    └── partials/                       # Modales de entrenamiento y badges
```
