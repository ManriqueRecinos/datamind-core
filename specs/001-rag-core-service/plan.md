# Implementation Plan: AI Chat Service with Local LLM, pgvector & MariaDB Integration (001-rag-core-service)

**Branch**: `001-rag-core-service` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-rag-core-service/spec.md`  

---

## Summary

Build an asynchronous REST microservice in Python using FastAPI, Pydantic V2, and PostgreSQL with `pgvector`, consumed by a Laravel 11 web platform. The service leverages a locally hosted LLM engine (Ollama with Qwen 2.5: 7B Instruct and `nomic-embed-text`) to ingest corporate process manuals and MariaDB table schemas into `pgvector`. It features an intelligent dual-branch agent pipeline that performs conversational RAG for process rules and safe Text-to-SQL analytics against an external MariaDB business database. Responses are delivered as warm, humanized narrative text (with optional SSE real-time streaming), while query results are cached to provide an on-demand "Generar Excel" button for formatted `.xlsx` downloads using `openpyxl`.

---

## Technical Context

- **Language/Version**: Python 3.11+ (Python 3.13 detected)
- **Primary Dependencies**:
  - `fastapi` + `uvicorn[standard]` (Asynchronous web API & SSE streaming)
  - `pydantic` >= 2.0 & `pydantic-settings` (Type validation & environment configuration)
  - `sqlalchemy` >= 2.0 + `asyncpg` + `pgvector` (Async PostgreSQL 17 ORM & vector operations)
  - `aiomysql` (Async read-only connection to external MariaDB)
  - `sqlglot` (SQL AST parsing, AST validation, and safe query rewriting)
  - `openpyxl` (On-demand enterprise Excel `.xlsx` generation)
  - `httpx` (Async HTTP client for Ollama API interaction)
- **Local AI Engine**:
  - Host: Ollama on Windows host (`http://127.0.0.1:11434`)
  - Inference Model: `qwen2.5:7b` (4.7 GB RAM in Q4_K_M, fast CPU inference on Intel i5-14500T)
  - Embedding Model: `nomic-embed-text` (768-dim, 8k context window, ~275 MB RAM)
- **Storage / Vector Database**:
  - PostgreSQL 17 with `pgvector` extension (HNSW index, cosine distance metric)
- **External Enterprise Database**:
  - MariaDB (read-only credentials, strict `SELECT` enforcement, `LIMIT 500` safeguard)
- **Frontend / Client Stack**:
  - DataMind Studio - Laravel 13 (`https://github.com/ManriqueRecinos/datamind-studio.git`), Full Local / Offline Ready, Tailwind CSS v4, DataTables `<x-data-table>`, SweetAlert2, Toastr, FontAwesome v7.
- **Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, `httpx`
- **Target Platform**: Windows / Linux / Docker
- **Project Type**: Asynchronous REST Web Microservice + Client Web Platform
- **Performance Goals**:
  - < 25ms vector retrieval via HNSW index in PostgreSQL
  - Real-time streaming response starting < 800ms
  - On-demand Excel generation < 300ms for datasets up to 500 rows
- **Security**:
  - Pre-shared API Key (Bearer token) for machine-to-machine communication
  - AST SQL parsing preventing any DDL/DML execution
  - Read-only database user permissions

---

## Constitution Check

*GATE: Post-Phase 1 Design Evaluation*

| Principle | Status | Architectural Justification |
| :--- | :--- | :--- |
| **I. Clean Architecture & Layer Separation** | **PASS** | Domain entities (`DocumentChunk`, `ChatMessage`, `SqlQuery`, `QueryResult`) and repository interfaces (`VectorRepositoryInterface`, `RelationalQueryInterface`, `LLMProviderInterface`) have zero external framework dependencies. All orchestration lives in application use cases (`AskChatUseCase`, `IngestKnowledgeUseCase`, `ExportExcelUseCase`). FastAPI controllers remain thin HTTP wrappers. |
| **II. Strict API Contracts & Validation** | **PASS** | Multi-model Pydantic V2 schemas (`ChatRequest`, `ChatResponse`, `IngestRequest`, `IngestResponse`, `ErrorResponse`). SSE streaming protocol is fully standardized in [contracts/sse-events.md](contracts/sse-events.md). |
| **III. Vector Database Discipline (PostgreSQL + pgvector)** | **PASS** | Uses native PostgreSQL 17 `pgvector` with HNSW cosine index (`vector_cosine_ops`), typed metadata JSONB payloads, and hybrid retrieval (`tsvector` + vector cosine similarity). |
| **IV. Safe Database RAG & Text-to-SQL Governance** | **PASS** | AST inspection via `sqlglot` permits strictly `exp.Select` statements. Automated `LIMIT 500` injection and 5.0-second execution timeouts are enforced. MariaDB connection credentials have solely `SELECT` privileges. |
| **V. Resilient Inter-Service Integration (Laravel ↔ FastAPI)** | **PASS** | Secure Bearer token authentication, SSE token streaming for responsive chat UI, and decoupled dataset caching (`query_datasets`) allowing on-demand Excel downloads without re-executing LLM queries. |
| **VI. Test-First & Comprehensive Verification** | **PASS** | Pytest suites isolate use cases and mock external adapters (Ollama, PostgreSQL, MariaDB). Contract tests verify FastAPI routers with `httpx.AsyncClient`. |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-rag-core-service/
├── plan.md              # This implementation plan
├── research.md          # Phase 0: Technology selection & benchmarks
├── data-model.md        # Phase 1: Entity definitions & database schemas
├── contracts/           # Phase 1: OpenAPI specifications & SSE streaming contracts
│   ├── chat-api.yaml
│   └── sse-events.md
├── quickstart.md        # Phase 1: Runnable validation and setup guide
└── tasks.md             # Phase 2: Actionable dependency-ordered tasks (generated via /speckit-tasks)
```

### Source Code (repository root)

```text
app/
├── api/                             # Presentation Layer (FastAPI Routers & Middleware)
│   ├── v1/
│   │   ├── routers/
│   │   │   ├── chat.py             # POST /chat, POST /chat/stream
│   │   │   ├── knowledge.py        # POST /knowledge/ingest, POST /knowledge/schema-sync
│   │   │   └── export.py           # GET /export/excel/{dataset_id}
│   │   └── api.py                   # Combined v1 APIRouter
│   ├── dependencies.py              # FastAPI Dependency Injection (Auth, Use Cases)
│   └── errors.py                    # Standardized error handlers & HTTP error schemas
├── core/                            # Cross-Cutting Infrastructure
│   ├── config.py                    # Pydantic Settings (env vars: DB URLs, Ollama, API keys)
│   └── logging.py                   # Structured JSON logging with Correlation IDs
├── domain/                          # Core Business Domain (Zero Framework Dependencies)
│   ├── entities.py                  # DocumentChunk, ChatSession, ChatMessage, QueryDataset
│   └── interfaces.py                # VectorStoreInterface, RelationalDbInterface, LLMInterface
├── infrastructure/                  # External Adapters
│   ├── database/
│   │   ├── postgres_adapter.py      # SQLAlchemy 2.0 + asyncpg + pgvector repository
│   │   └── mariadb_adapter.py       # aiomysql read-only query executor
│   ├── llm/
│   │   ├── ollama_adapter.py        # Async client for Ollama LLM and Embeddings
│   │   └── sql_guardrail.py         # sqlglot AST query validator & LIMIT enforcer
│   ├── export/
│   │   └── excel_generator.py       # openpyxl workbook generator with corporate styles
│   └── parsers/
│       └── text_chunker.py          # Overlapping text partitioner
└── use_cases/                       # Application Layer (Business Workflows)
    ├── ingest_knowledge.py          # Chunking -> embedding -> pgvector upsert
    ├── sync_schema_dictionary.py    # MariaDB schema introspection -> vector indexing
    ├── ask_chat.py                  # Intent classification -> RAG/SQL -> humanized synthesis
    └── export_excel.py              # Cached dataset retrieval -> Excel stream generation

tests/
├── contract/                        # Router contract tests (httpx.AsyncClient)
│   ├── test_chat_router.py
│   └── test_export_router.py
├── integration/                     # Database adapter tests
│   ├── test_pgvector_adapter.py
│   └── test_mariadb_adapter.py
└── unit/                            # Domain & Use Case unit tests
    ├── test_sql_guardrail.py
    ├── test_text_chunker.py
    └── test_ask_chat_use_case.py
```

**Structure Decision**:
Clean / Hexagonal architecture cleanly separating `domain`, `use_cases`, `infrastructure`, and `api`. This guarantees that Ollama, PostgreSQL/pgvector, MariaDB, and openpyxl are isolated adapters that can be individually tested, mocked, or upgraded without modifying business rules or domain models.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| *None* | Architecture strictly adheres to all 6 Constitution principles. | Direct SQL generation without AST validation rejected due to catastrophic mutation risk on corporate databases. |

---

## Phase 9: Corporate Design System & Global Color Palette Optimization

**Objective**: Unify the visual identity across `datamind-studio` (Blade views, DataTables, SSE dynamic cards, SweetAlert2) and `datamind-core` (`ExcelGenerator`) using a centralized global CSS token architecture (`globales.css` + Tailwind CSS v4 `@theme`) based on the official 5-color DataMind palette:

| Token | Hex | RGB | Semantic Role |
| :--- | :--- | :--- | :--- |
| `--datamind-primary` | `#0476D9` | `4, 118, 217` | Primary brand actions, active buttons, user chat bubbles, primary icons, active pagination |
| `--datamind-primary-dark` | `#0468BF` | `4, 104, 191` | Hover/Active states for primary actions, corporate headers, gradients, Excel header background |
| `--datamind-secondary` | `#4B89BF` | `75, 137, 191` | Secondary buttons, muted accents, helper icons, assistant avatar accent, subtle badges |
| `--datamind-accent-light` | `#99D0F2` | `153, 208, 242` | Focus rings, soft badge backgrounds/borders, DataTables selected row & hover tint, scrollbar hover |
| `--datamind-bg-neutral` | `#F2F2F2` | `242, 242, 242` | Main application background (`body`), input/panel surfaces, table zebra striping |

### Planned Modifications

1. **Global CSS Token System (`public/css/global_styles/globales.css`)**:
   - Define `:root` CSS Custom Properties for the 5 core hex colors, RGB triplets (`--datamind-primary-rgb`, etc.), alpha surface variants (`--datamind-accent-soft`, `--datamind-primary-soft`), focus ring tokens, and reusable utility classes (`.bg-datamind-primary`, `.btn-datamind-primary`, `.badge-datamind`, `.custom-scrollbar`).
2. **Tailwind CSS v4 Theme Mapping (`resources/css/app.css`)**:
   - Register custom `@theme` tokens (`--color-datamind-primary: #0476D9`, `--color-datamind-dark: #0468BF`, `--color-datamind-secondary: #4B89BF`, `--color-datamind-light: #99D0F2`, `--color-datamind-neutral: #F2F2F2`) so Tailwind v4 utility classes (`bg-datamind-primary`, `hover:bg-datamind-dark`, `border-datamind-light`, `bg-datamind-neutral`) compile natively offline via Vite.
3. **Frontend Views & Components (`datamind-studio`)**:
   - Refactor `resources/views/chat/index.blade.php`, `resources/views/welcome.blade.php`, `resources/views/components/data-table.blade.php`, and `public/js/chat_stream.js` to replace default `indigo-*` styles with the new DataMind palette tokens.
4. **Excel Corporate Styling (`app/infrastructure/export/excel_generator.py`)**:
   - Align `openpyxl` report colors (`HEADER_FILL` `#0468BF`, `TITLE_FONT` `#0468BF`, `ZEBRA_FILL` `#F2F2F2`, `BORDER_SIDE` `#99D0F2`) with the web platform.
5. **Build & Governance**:
   - Recompile local Vite assets (`npm run build`), increment version to `1.0.2` in `README.md` and `AGENTS.md`, and run regression suites (`pytest` & `php artisan test`).

---

## Phase 10: Dynamic Multi-Database Connection Manager & Selective Table Vectorization (`DataMind Universal`)

**Objective**: Transform the platform from a single hardcoded database integration into a universal **Multi-Database AI Analyst (`DataMind`)**. Users can dynamically connect **any PostgreSQL or MariaDB/MySQL database** via UI credentials, test connectivity, inspect all detected tables and column counts, selectively choose which tables to vectorize into `pgvector`, and select the active database connection directly from the Chat interface.

### 1. Architecture & Data Model (`datamind-core`)

- **New ORM Model (`DatabaseConnectionModel` in `app/infrastructure/database/models.py`)**:
  - `id`: `UUID` (Primary Key)
  - `name`: `String(120)` (Friendly alias, e.g., `"ERP Ventas"`, `"Analytics DB"`)
  - `engine`: `String(30)` (`"mariadb"` | `"mysql"` | `"postgresql"`)
  - `host`: `String(255)`
  - `port`: `Integer` (`3306`, `5432`, etc.)
  - `database_name`: `String(120)`
  - `username`: `String(120)`
  - `password`: `Text` (Stored securely in local PostgreSQL metadata; masked in all API responses and logs)
  - `is_active`: `Boolean` (Marks the default/active connection for Chat queries)
  - `synced_tables`: `JSONB` (List of table names already vectorized in `pgvector` for this connection)
  - `created_at` / `updated_at`: `DateTime(timezone=True)`

- **Universal Dynamic Database Adapter (`app/infrastructure/database/dynamic_db_adapter.py`)**:
  - Implements `RelationalDbInterface` dynamically for both **MariaDB/MySQL** (via `aiomysql`) and **PostgreSQL** (via `asyncpg`).
  - `test_connection()`: Verifies network reachability, authentication, and server version within a 5s timeout.
  - `introspect_tables()`: Queries `INFORMATION_SCHEMA.COLUMNS` (filtered by `TABLE_SCHEMA = db` in MySQL/MariaDB or `table_schema = 'public'` in PostgreSQL) and returns all tables with column names, data types, and column counts, plus a flag `is_vectorized` comparing against `synced_tables`.
  - `execute_query(sql)`: Executes read-only `SELECT` queries validated by `SQLGuardrail` (converting dialect syntax via `sqlglot` between `mysql` and `postgres` automatically).

- **Selective Vectorization & Context Isolation (`SyncConnectionSchemaUseCase` & `AskChatUseCase`)**:
  - When the user selects $N$ tables in the UI and clicks **"Vectorizar Tablas Seleccionadas"**:
    1. Previous schema vectors for those specific `(connection_id, table_name)` pairs are replaced (idempotent upsert) so there are never duplicate chunks.
    2. Each selected table is embedded via `nomic-embed-text` with metadata `{"connection_id": str(conn.id), "engine": conn.engine, "database": conn.database_name, "table_name": t_name}`.
    3. `AskChatUseCase` accepts an optional `connection_id` (or uses the currently active connection), filters `pgvector` schema chunks by `connection_id`, generates SQL tailored to that engine (`MariaDB/MySQL` vs `PostgreSQL`), and executes the query on that target database.

### 2. FastAPI REST Endpoints (`app/api/v1/routers/connections.py`)

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `POST` | `/api/v1/connections/test` | Tests raw credentials (`engine`, `host`, `port`, `database_name`, `username`, `password`) without saving, returning latency and total tables detected. |
| `POST` | `/api/v1/connections` | Saves a new database connection (and optionally sets it as active). |
| `GET` | `/api/v1/connections` | Lists all saved connections (with passwords masked as `********` and count of vectorized tables). |
| `POST` | `/api/v1/connections/{id}/activate` | Sets connection `{id}` as the active target for the Chat assistant. |
| `GET` | `/api/v1/connections/{id}/tables` | Introspects the target database in real time and returns all tables, their column list, column count, and whether each table is already vectorized (`is_vectorized`). |
| `POST` | `/api/v1/connections/{id}/vectorize` | Receives `{"tables": ["tabla_1", "tabla_2", ...]}` and vectorizes only the user-selected tables into `pgvector`. |
| `DELETE` | `/api/v1/connections/{id}` | Removes the connection and cleans up its associated `db_schema` vectors in `pgvector`. |

### 3. Frontend UI in Laravel 13 (`datamind-studio`)

- **New View & Controller (`DatabaseConnectionController.php` & `resources/views/connections/index.blade.php`)**:
  1. **Formulario de Conexión Universal**: Selector de motor (`MariaDB / MySQL` o `PostgreSQL`), Alias, Host, Puerto, Base de Datos, Usuario y Contraseña, con botón **"Probar Conexión"** (SweetAlert2 / Toastr feedback con latencia en ms) y **"Guardar y Analizar Esquema"**.
  2. **Explorador Interactivo de Tablas Detectadas (`<x-data-table>` + Checkboxes)**:
     - Muestra todas las tablas detectadas en la base de datos conectada con buscador instantáneo, cantidad de columnas, vista previa de columnas (`modal` o `collapse`), estado (`Vectorizada` / `Sin vectorizar`) y botones **"Seleccionar Todas / Limpiar"**.
     - Botón principal **"🧠 Vectorizar Tablas Seleccionadas"** con barra/estado de progreso mientras Ollama genera los embeddings en `pgvector`.
  3. **Selector de Base de Datos Activa en el Chat (`resources/views/chat/index.blade.php`)**:
     - En la barra superior y sidebar del Chat, un selector permite cambiar en cualquier momento sobre qué base de datos conectada está respondiendo el asistente, más un botón directo a **"Gestionar Bases de Datos"**.