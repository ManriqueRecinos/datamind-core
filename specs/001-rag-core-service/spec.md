# Feature Specification: AI Chat Service with Local LLM, pgvector & MariaDB Integration (001-rag-core-service)

**Feature Branch**: `001-rag-core-service`  
**Created**: 2026-11-06  
**Status**: Ready for Planning  
**Input**: Local AI service (Ollama) with PostgreSQL + pgvector for corporate process learning, querying an external MariaDB business database with humanized conversational answers and manual Excel generation button.

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

## Technical Constraints & Boundaries

1. **Local AI Execution**: Ollama running locally on Windows (using CPU AVX2 acceleration on Intel Core i5-14500T, Qwen 2.5 7B / Llama 3.1 8B, memory footprint <= 6GB).
2. **Database Separation**:
   - **Internal Storage**: PostgreSQL 17 + `pgvector` for vector embeddings, vector similarity search, and schema dictionary.
   - **External Storage**: MariaDB for read-only enterprise process data.
3. **Clean Architecture Isolation**: Application use cases must remain fully decoupled from FastAPI routes and specific database drivers.
4. **Pydantic V2 Multi-Model**: Strict validation for all requests and responses.