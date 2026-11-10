# Feature Specification: AI Chat Service with Local LLM, pgvector & MariaDB Integration (001-rag-core-service)

**Feature Branch**: `001-rag-core-service`  
**Created**: 2026-11-06  
**Status**: Ready for Planning  
**Input**: Local AI service (Ollama) with PostgreSQL + pgvector for corporate process learning, querying an external MariaDB business database with humanized conversational answers and manual Excel generation button.

---

## Clarifications

### Session 2026-11-09
- Q: Cuando le pides a la IA analizar o graficar una consulta (por ejemplo, relacionando el estado de un rollo con otra tabla) sin especificar qué campos exactos graficar, ¿cuál debe ser el flujo exacto entre la IA y la interfaz? → A: Option A (Análisis previo + Selector de Campos antes de graficar: la IA cruza las tablas solicitadas mediante JOIN, analiza sus columnas, pregunta al usuario con qué campos desea generar el gráfico mostrando un asistente/selector de campos súper sencillo, y una vez el usuario elige o confirma los campos —por clic o por chat— la IA genera y dibuja el gráfico exacto).

---

## User Scenarios & Requirements

### User Story 1 - Corporate Process Knowledge Ingestion & Vector Storage (Priority: P1)

As a system administrator or automated ingestion job, I want to submit business process manuals, workflow definitions, and MariaDB schema annotations to the Python API, so that they are chunked, embedded using a local embedding model, and indexed in PostgreSQL with `pgvector` for semantic retrieval.

**Why this priority**: Without knowledge representation of corporate processes and table schema mappings in pgvector, the AI cannot understand business-specific terms or generate accurate queries for MariaDB.

**Acceptance Scenarios**:
1. **Document Ingestion**:
   - **Given** an authenticated request containing process documentation text and metadata (category, department, related tables).
   - **When** the client calls `POST /api/v1/knowledge/ingest`.
   - **Then** the service partitions text into overlapping chunks, generates embeddings (via local `nomic-embed-text`), saves them into the `pgvector` table (`knowledge_vectors`), and returns `HTTP 201 Created` with chunk statistics.
2. **Schema & Process Dictionary Ingestion**:
   - **Given** MariaDB schema descriptions (e.g. table definitions, column comments, process relationships).
   - **When** the client submits `POST /api/v1/knowledge/schema-sync`.
   - **Then** schema vectors are created/updated in `pgvector` for precise retrieval during Text-to-SQL tasks.

---

### User Story 2 - Humanized Conversational Q&A with MariaDB Querying (Priority: P1)

As an enterprise user interacting with the chat interface in Laravel, I want to ask questions in plain Spanish/English regarding business processes and live database records, so that the AI understands my intent, queries MariaDB safely if necessary, and produces a warm, professional, humanized explanation.

**Why this priority**: Core value of the product: democratizing access to complex MariaDB process data through natural conversation powered by local AI.

**Acceptance Scenarios**:
1. **Data-Driven Question**:
   - **Given** an enterprise user asking "¿Cuáles son las 5 órdenes con mayor retraso en el proceso de logística?".
   - **When** the client calls `POST /api/v1/chat` or opens a Server-Sent Events stream `POST /api/v1/chat/stream`.
   - **Then** the service retrieves relevant process documentation and schema definitions from `pgvector`, builds an augmented prompt for the local LLM (Qwen 2.5 / Llama 3.1 via Ollama), generates a safe `SELECT` query, executes it against the external MariaDB, synthesizes a clear humanized narrative, and returns the response alongside a structured `dataset_id` / tabular preview.
2. **Pure Process Question (Non-SQL)**:
   - **Given** a user asking "¿Cuál es el procedimiento cuando un lote es rechazado por control de calidad?".
   - **When** the chat request is sent.
   - **Then** the AI answers directly from the vectorized corporate process manuals without executing SQL, citing relevant policy sections.

---

### User Story 3 - On-Demand / Manual Excel Export (Priority: P1)

As an enterprise user, after receiving a response with tabular or process data, I want to click a "Generar Excel" button at the bottom of the answer, so that an `.xlsx` file is generated containing the exact query results with clean formatting, column headers, and timestamping.

**Why this priority**: Essential enterprise feature requested by business stakeholders to take data from chat directly into operational workflows without manual copy-pasting.

**Acceptance Scenarios**:
1. **Manual Trigger from Chat**:
   - **Given** a chat response that resulted in tabular data (associated with a `dataset_id` or query payload).
   - **When** the user clicks "Generar Excel" in the Laravel chat UI.
   - **Then** a request is dispatched to `GET /api/v1/export/excel/{dataset_id}` (or processed via Laravel), downloading an Excel file `reporte_proceso_[timestamp].xlsx` with styled headers, auto-adjusted columns, and proper numeric formatting.
2. **Response with No Tabular Data**:
   - **Given** a conversational or procedural question that did not query tabular records.
   - **When** the response is displayed.
   - **Then** no "Generar Excel" button is rendered, keeping the UI intuitive and clean.

---

### User Story 4 - SQL Safety & Read-Only Governance for External MariaDB (Priority: P1)

As a database administrator, I want to ensure that AI-generated queries can never mutate or harm the production MariaDB database.

**Why this priority**: Security and data integrity are non-negotiable for enterprise databases.

**Acceptance Scenarios**:
1. **Read-Only Enforcement**:
   - All connection credentials to MariaDB must possess solely `SELECT` privileges.
2. **AST Parsing & Query Validation**:
   - Before executing any generated SQL, the service inspects the query with `sqlglot`. If any command other than `SELECT` is detected (e.g. `UPDATE`, `DROP`, `DELETE`, `INSERT`, `ALTER`), the execution is immediately halted, returning a safety warning.
3. **Automatic Safeguards**:
   - A hard `LIMIT 500` is enforced on every query, and a strict timeout (5 seconds) prevents query hanging.

---

### User Story 5 - Laravel Web Application & User Experience (Priority: P2)

As an end user, I want a modern, fast, responsive web interface built in Laravel, so that I can easily navigate past chat sessions, ask questions, see streaming text as it generates, and export reports with one click.

**Acceptance Scenarios**:
1. **Livewire / Alpine.js Chat Interface**:
   - Displays real-time typing effect (SSE streaming).
   - Renders Markdown (tables, bullet points, code snippets).
   - Shows "Generar Excel" button conditionally on answers with tabular data.
2. **Authentication & History**:
   - Session storage in Laravel for user audit trail and previous conversation recall.

---

### User Story 6 - Guided Multi-Table Analysis & Two-Step Interactive Chart Generation (Priority: P1)

As an enterprise analyst, when I ask the AI to review or chart related tables (e.g., checking the roll status linked with another table) without specifying the exact axes, I want the AI to first join/inspect the tables, analyze all available columns, and ask me which fields I want to use to create the chart via a super-simple visual field selector (or chat reply) before rendering the final chart.

**Acceptance Scenarios**:
1. **Ambiguous / Exploratory Chart or Cross-Table Request (`needs_field_selection = true`)**:
   - **Given** a user prompt requesting a chart or cross-table analysis without explicit X/Y axes (e.g., *"Revísame el estado del rollo vinculado con la tabla de órdenes y hazme un gráfico"*).
   - **When** the AI processes the request.
   - **Then** the AI generates a relational `SELECT ... JOIN` query bringing the relevant columns from both tables, analyzes which columns are categorical dimensions (`dimension_columns`) and which are numeric metrics (`metric_columns`), asks the user in Markdown which fields they want to plot, and displays a **Guided Field Selector Step** in the UI (`¿Con qué campos deseas generar tu gráfico?`) with clickable field pills and a **`[ ✨ Generar Gráfico con estos Campos ]`** button (without drawing the chart prematurely).
2. **Confirmed Field Selection (via UI Click or Follow-up Chat Message)**:
   - **Given** the Guided Field Selector or an explicit user prompt that already names the exact columns to plot (e.g., *"Créame el gráfico agrupando por `estado_rollo` y sumando `peso_kg`"*).
   - **When** the user clicks **`[ ✨ Generar Gráfico ]`** or replies in the chat specifying the fields.
   - **Then** the chart canvas immediately renders the detailed visualization using those exact fields, and allows switching chart types (`Barras`, `Líneas`, `Dona`, `Pastel`, `Barras Horizontales`) or downloading the PNG.

---

### User Story 7 - Relational Schema Graph Vectorization & Automatic Foreign-Key Label Resolution (Priority: P1)

As a database analyst or business user, when I query or chart tables that reference other tables via foreign keys (e.g., `usuario` linked to `empresa` via `id_empresa`), I want the AI to learn those relationships during schema vectorization (`pgvector`), automatically retrieve both the primary and related table schemas via hybrid/graph expansion, and generate `JOIN` queries that replace raw numeric IDs (`id_empresa`) with human-readable labels from the related table (`empresa.nombre AS empresa_nombre`).

**Acceptance Scenarios**:
1. **Relational Graph Introspection & Enriched Vectorization**:
   - **Given** a database with related tables (via explicit `FOREIGN KEY` constraints in `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` or naming conventions such as `id_empresa` / `empresa_id` -> `empresa.id`).
   - **When** the user vectorizes tables in `/connections`.
   - **Then** `DynamicDBAdapter` and `ManageConnectionsUseCase` detect both explicit and inferred foreign-key relationships, identify the target table's human-readable label columns (`nombre`, `razon_social`, `descripcion`, `titulo`, `codigo`), embed an explicit `RELACIONES Y JOINS APRENDIDOS` section into the `pgvector` chunk, and store `related_tables` and `foreign_keys` in the document `metadata_`.
2. **1-Hop Relational Graph Expansion & Hybrid Retrieval**:
   - **Given** a user prompt mentioning only one side of a relationship or asking for a breakdown by a related entity (e.g., *"Hazme un gráfico de usuarios por empresa"*).
   - **When** `VectorRepository` searches `pgvector`.
   - **Then** it combines dense cosine similarity + lexical table/column matching (`Hybrid Search`) AND automatically expands 1-hop neighbor tables listed in `metadata_["related_tables"]` so both `usuario` and `empresa` schemas are injected into the LLM prompt.
3. **Human Label Resolution in SQL & Chart Builder**:
   - **Given** a query involving foreign keys (`id_empresa`).
   - **When** the SQL query and Chart Builder options are generated.
   - **Then** the SQL query performs the `JOIN` to select the human-readable column (`empresa.nombre AS nombre_empresa`), and `analyze_columns_for_chart()` deprioritizes/excludes raw foreign key ID columns (`id_empresa`) from the suggested X/Y chart axes in favor of the descriptive joined columns.

---

### User Story 8 - Interactive AI Knowledge Trainer ("Centro de Entrenamiento IA"), Conversational Learning & Explicit Output Mode Control (Priority: P1)

As a product owner, database administrator, or business analyst, I want to teach the AI custom table relationships, business glossary/synonyms, status code meanings, KPI formulas, and verified "Golden SQL" examples **both directly in the chat and via an interactive "Centro de Entrenamiento IA" (`🎓 Entrenar IA`)**—and I want the AI to accurately distinguish when I am **teaching it a rule**, when I am **asking for a chart**, when I am **asking for a table**, or when I just want a **text answer**—so that it never renders unwanted charts/tables when I am teaching it or asking a simple question.

**Acceptance Scenarios**:
1. **Direct Conversational Teaching in Chat (`intent = "teach_knowledge"`)**:
   - **Given** a user typing a declarative/instructive rule directly in the chat (e.g., *"La tabla `users` se relaciona con la tabla `companies` uniendo `users.current_company_id = companies.id`. Cuando el usuario pida datos o gráficos por empresa, nunca muestres `current_company_id`; haz siempre `JOIN companies` y muestra `companies.name`"*).
   - **When** `IntentClassifier` processes the message.
   - **Then** it classifies the intent as `teach_knowledge` (even if the text contains words like `"tabla"`, `"relaciona"`, or `"gráficos"` inside a conditional clause), automatically extracts and vectorizes the rule/relationship into `pgvector` scoped to the active `connection_id`, updates the relational `join_hints`/`related_tables` metadata, and replies with a clear **Learning Confirmation Card** (*"🧠 ¡Regla Aprendida y Vectorizada!"*) **without** executing a SQL query and **without** rendering any chart or table.
2. **Explicit Output Mode Detection (`text_only` vs `table` vs `chart` vs `both`)**:
   - **Given** a user prompt with `intent = "data_query"`.
   - **When** `IntentClassifier.detect_output_format(prompt)` analyzes what visual artifacts the user explicitly requested.
   - **Then**:
     - If the user explicitly asks for a **chart** (*"hazme un gráfico"*, *"grafica"*, *"diagrama de barras/pastel"* — excluding conditional rules like *"cuando pida gráficos"*): `wants_chart = true`, and `wants_table = false` (unless they also asked for a table).
     - If the user explicitly asks for a **table/list** (*"hazme una tabla"*, *"muéstrame en tabla"*, *"lístame los registros"*): `wants_table = true`, and `wants_chart = false`.
     - If the user asks a **general data question** without requesting a table or chart (e.g., *"¿Cuántos usuarios hay por empresa?"*): `wants_chart = false` and `wants_table = false` — the AI answers cleanly in Markdown text, showing only a compact toolbar with optional action buttons (*"📋 Ver Tabla"*, *"📊 Crear Gráfico"*, *"📥 Generar Excel"*) hidden until clicked.
3. **Multi-Channel Knowledge Teaching via UI (`business_rule`, `custom_relation`, `kpi_formula`, `sql_example`)**:
   - **Given** an authenticated user in the **"🎓 Entrenar IA"** modal/panel (or clicking *"🧠 Enseñar este SQL a la IA"* on a chat response).
   - **When** the user saves or updates a custom table relationship, business rule/status mapping (`CASE WHEN`), KPI formula, or verified Golden SQL `SELECT ... JOIN` example.
   - **Then** the system validates the entry (enforcing `sqlglot` read-only `SELECT` validation for SQL examples), prevents duplicates by updating existing matching rules for the same `connection_id`, embeds it with `nomic-embed-text` into `pgvector`, and displays it in the active AI knowledge capsules list.
4. **Cross-Channel Retrieval & Observability During SQL & Chart Generation (`data_query`)**:
   - **Given** business rules, custom relationships, or Golden SQL examples stored in `pgvector` for a database connection.
   - **When** a user asks a `data_query` question or requests a chart in the chat.
   - **Then** `AskChatUseCase` retrieves both `db_schema` (+ `1-Hop` related tables) and the top matching `custom_relation` / `business_rule` / `kpi_formula` / `sql_example` vectors, injects them into the SQL prompt, and exposes the applied knowledge fragments in the audit section so the user can verify what knowledge the AI used.
5. **Guided User Curriculum ("Aprender a Enseñarle a la IA")**:
   - **Given** a user who wants to learn how to train the AI effectively.
   - **When** the user opens the 5-level interactive training curriculum / playbook in DataMind.
   - **Then** the user is guided step-by-step with 1-click fill templates and before/after verification tests to master: (1) Master-Detail Schema Vectorization, (2) Custom Relationships & Legacy FK Mapping, (3) Business Glossary & Status Codes, (4) KPI Formulas for Charts, and (5) Few-Shot Golden SQL Queries.

---

## Technical Constraints & Boundaries

1. **Local AI Execution**: Ollama running locally on Windows (using CPU AVX2 acceleration on Intel Core i5-14500T, Qwen 2.5 7B / Llama 3.1 8B, memory footprint <= 6GB).
2. **Database Separation**:
   - **Internal Storage**: PostgreSQL 17 + `pgvector` for vector embeddings, vector similarity search, and schema dictionary.
   - **External Storage**: MariaDB for read-only enterprise process data.
3. **Clean Architecture Isolation**: Application use cases must remain fully decoupled from FastAPI routes and specific database drivers.
4. **Pydantic V2 Multi-Model**: Strict validation for all requests and responses.