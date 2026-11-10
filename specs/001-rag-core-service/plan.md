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

---

## Phase 11: Real-Time Markdown Preview Rendering for AI Responses & User Prompts (`DataMind Rich Markdown`)

**Objective**: Upgrade the Chat interface in `datamind-studio` (`D:\Laravel\Supertex AI`) so that **both the AI Assistant's streaming/completed responses and the User's questions** are rendered as a rich **Markdown Preview** (formatted headings, bold/italic emphasis, bulleted & numbered lists, styled code blocks with a one-click copy button, inline code badges, blockquotes, and GFM tables) instead of plain text with raw `**` or `###` symbols, while strictly preserving the **100% Local / Zero CDNs** architecture and XSS protection.

### 1. Architectural & Technical Decisions

- **100% Local Markdown Engine (`public/js/chat_stream.js`)**:
  - Zero external CDN dependencies (implemented via a fast, deterministic, XSS-safe local GFM Markdown parser & sanitizer in `public/js/chat_stream.js`).
  - **Security First (XSS-Safe)**: Raw text is first HTML-escaped or tokenized so arbitrary `<script>` or HTML injection from user input or database records can never execute, while transforming valid Markdown syntax into clean semantic HTML.
- **Dual-Context Markdown Rendering (Assistant + User)**:
  - **AI Assistant Responses (`.markdown-body.markdown-ai`)**:
    - Accumulates raw Markdown tokens in `textSpan.dataset.rawMarkdown` as SSE `token` events arrive.
    - Re-renders the live Markdown preview smoothly on every token chunk so headings, bold text, lists, and code blocks take shape in real time without flickering.
    - Includes a **"Copiar código"** button on fenced code blocks (` ```sql `, ` ```python `, etc.).
  - **User Prompts (`.markdown-body.markdown-user`)**:
    - Upgraded from `<input type="text">` to an auto-expanding `<textarea rows="1">` in `resources/views/chat/index.blade.php` (`Enter` sends the message, `Shift + Enter` inserts a newline so users can write multi-line Markdown lists or code snippets).
    - Renders user messages through the same Markdown Preview engine with inverted high-contrast typography (`markdown-user` theme over `--datamind-primary` `#0476D9`).
- **System Prompt Enhancement (`app/use_cases/ask_chat.py`)**:
  - Reinforce the synthesis prompt so `qwen2.5:3b` structures answers using clean Markdown headings (`###`), bullet lists, bold key metrics, and inline code for column/table names.

### 2. Planned Modifications

1. **Markdown Typography & Preview Styles (`public/css/global_styles/globales.css` & `resources/css/global_styles/globales.css`)**:
   - Add `.markdown-body` rules for `h1`–`h4`, `p`, `ul`, `ol`, `li`, `strong`, `em`, `blockquote`, `hr`, `code`, `pre`, and `.markdown-table`.
   - Differentiate `.markdown-ai` (dark slate text, `#0468BF` headings, `#F2F2F2` inline code badges, dark slate code blocks) and `.markdown-user` (white text, translucent white code badges and blockquotes over `#0476D9` bubble).
2. **Multi-Line Markdown Input & UI (`resources/views/chat/index.blade.php`)**:
   - Replace single-line `<input id="chatPromptInput">` with an auto-resizing `<textarea id="chatPromptInput" rows="1">` supporting `Enter` (send) and `Shift+Enter` (new line), plus a subtle Markdown support hint (`Soporta **Markdown** y Shift+Enter`).
3. **Real-Time Streaming Markdown Renderer (`public/js/chat_stream.js`)**:
   - Implement `renderMarkdownPreview(rawText, isUser = false)` supporting:
     - Fenced code blocks (` ```lang ... ``` `) with language header badge and copy-to-clipboard button.
     - Inline code (`` `code` ``).
     - Headings (`#`, `##`, `###`, `####`).
     - Bold (`**texto**`), Italic (`*texto*`), Strikethrough (`~~texto~~`).
     - Unordered lists (`- `, `* `) and Ordered lists (`1. `).
     - Blockquotes (`> `) and Horizontal rules (`---`).
     - Markdown tables (`| col1 | col2 |`).
   - Update `appendUserMessage(text)` to render `renderMarkdownPreview(text, true)` inside `.markdown-body.markdown-user`.
   - Update `processSSEEvent('token', ...)` to append `data.text` to `rawMarkdown` buffer and update `textSpan.innerHTML = renderMarkdownPreview(rawMarkdown, false)`.
4. **Verification & Version Bump**:
   - Run `npm run build`, `php artisan test`, and `pytest`, and bump `datamind-studio` version to `1.0.4`.

---

## Phase 12: User Authentication (Login / Register) & Multi-User Conversation History (`DataMind Auth & Chat History`)

**Objective**: Implement complete user authentication in `datamind-studio` (Login, Registration, Logout, and default demo credentials) and link every chat conversation to the authenticated user (`user_id`), enabling users to browse, resume, and delete their own past conversation threads from the Chat sidebar—restoring both user prompts, Markdown-formatted AI responses, and any cached tabular datasets/Excel download buttons.

### 1. Backend Architecture & Endpoints (`datamind-core` - Python FastAPI)

- **Complete Dual-Role Message Persistence (`app/use_cases/ask_chat.py`)**:
  - Persist **both** the `user` message (`role="user"`, `content=prompt`) and the `assistant` response (`role="assistant"`, `content=message_text`, `intent`, `generated_sql`, `dataset_id`, `latency_ms`) in `chat_messages` associated with `ChatSessionModel(user_id=user_id)`, updating `ChatSessionModel.updated_at` on each turn.
  - Inject the last 4 messages of the session as conversational memory context when continuing an existing `session_id`.
- **Session History Management Use Case & Endpoints (`app/use_cases/manage_sessions.py` & `app/api/v1/routers/chat.py`)**:
  - `GET /api/v1/chat/sessions?user_id={user_id}`: Returns the authenticated user's chat sessions ordered by `updated_at DESC` (`id`, `title`, `user_id`, `created_at`, `updated_at`, `message_count`).
  - `GET /api/v1/chat/sessions/{session_id}?user_id={user_id}`: Returns session metadata and the chronological list of messages (`id`, `role`, `content`, `intent`, `generated_sql`, `dataset_id`, `latency_ms`, `created_at`), enriched with dataset preview metadata (`row_count`, `columns`, `preview_rows` from `query_datasets` if `dataset_id` is present) so historical tables and Excel buttons render seamlessly.
  - `DELETE /api/v1/chat/sessions/{session_id}?user_id={user_id}`: Deletes the specified conversation session (and cascades to `chat_messages`), verifying ownership by `user_id`.

### 2. Frontend Authentication & History UI (`datamind-studio` - Laravel 13)

- **Authentication Flow (`app/Http/Controllers/AuthController.php`, `resources/views/auth/login.blade.php`)**:
  - Unified, modern **Login & Quick Register** screen styled with the DataMind 5-color palette (`#0476D9`, `#0468BF`, `#4B89BF`, `#99D0F2`, `#F2F2F2`) and 100% local assets (Zero CDNs).
  - Pre-seeded default user (`admin@datamind.local` / `datamind2026`) via `DatabaseSeeder.php` + one-click **"Acceso Rápido Demo"** button on the login card and a tab to create new user accounts (`name`, `email`, `password`).
  - Protect `/chat` and `/connections` routes with Laravel `auth` middleware so every request has a verified `Auth::user()`.
- **User-Scoped Chat & Sidebar History (`ChatController.php`, `FastApiClient.php`, `resources/views/chat/index.blade.php`, `public/js/chat_stream.js`)**:
  - `ChatController` automatically passes `(string) Auth::id()` (or `user_{id}`) as `user_id` to `FastApiClient` on `/chat/send`, `/chat/stream`, `/chat/sessions`, `/chat/sessions/{id}`, and `DELETE /chat/sessions/{id}`.
  - **Header User Profile & Logout**: Displays the logged-in user's name/email badge and a **"Salir"** button in the top navigation bar.
  - **Sidebar "Mis Conversaciones"**:
    - Lists all saved conversations of the logged-in user with title, relative date, active highlight, and a delete (`trash`) icon.
    - Clicking any conversation loads its full message history via `GET /chat/sessions/{id}`, rendering both User and Assistant bubbles with `renderMarkdownPreview()` and reconstructing interactive DataTables previews + Excel export buttons.
    - Sending the first message in a `"Nuevo Chat"` automatically refreshes the sidebar list so the new session appears immediately.

---

## Phase 13: Interactive AI Chart Generation & Guided Field Builder (`DataMind Visual Analytics`)

**Objective**: Enable the AI Assistant and the user interface to generate **detailed interactive charts** (using local `Chart.js` `public/js/global_js/chart.umd.min.js`, 100% offline / Zero CDNs) from any database query result. When a user asks for a chart (e.g., *"Hazme un gráfico de ventas"*, *"Muéstrame una gráfica de órdenes por estado"*) or whenever tabular data is returned, the AI can ask/guide the user on which fields to plot, and the UI provides a **super simple, intuitive Interactive Chart Builder Card** where the user selects the **Chart Type**, **X-Axis / Category Field**, **Y-Axis / Metric Field**, and **Aggregation Function** (`Conteo`, `Suma`, `Promedio`, `Valor Directo`) with instant live rendering and PNG download.

### 1. Backend Architecture & Dataset Analytics (`datamind-core` - Python FastAPI)

- **Chart Intent & Conversational Field Guidance (`app/use_cases/intent_classifier.py` & `app/use_cases/ask_chat.py`)**:
  - Detect chart-related prompts (`gráfico`, `grafica`, `gráfica`, `chart`, `diagrama`, `barras`, `pastel`, `torta`, `líneas`, `tendencia`, `comparativa`) as `data_query` with `wants_chart = True`.
  - When `wants_chart` is detected and a dataset is returned from PostgreSQL/MariaDB:
    1. Automatically classify dataset columns into **`dimension_columns`** (categorical/text/date fields suitable for X-axis) and **`metric_columns`** (numeric fields suitable for Y-axis), and suggest a default `chart_config` (`type`, `x_field`, `y_field`, `aggregation`).
    2. Instruct the LLM synthesis prompt to explain the findings **and explicitly ask/guide the user in Markdown** which fields are available to customize the chart (e.g., *"He preparado tu gráfico inicial. Si deseas ajustarlo, ¿prefieres graficar en base a `estado`, `cliente` o `fecha`? Puedes elegir los campos y el tipo de gráfico directamente en el selector interactivo de abajo"*).
- **On-Demand Full Dataset Chart Data Endpoint (`GET /api/v1/export/dataset/{dataset_id}` in `app/api/v1/routers/export.py`)**:
  - Returns the cached dataset (`dataset_id`, `columns`, `rows` up to 500 records, `row_count`, `dimension_columns`, `metric_columns`, `suggested_chart`) so the frontend Chart Builder can compute accurate aggregations (`SUM`, `COUNT`, `AVG`) across all cached rows, not just the 10 preview rows.

### 2. Super Simple Interactive Chart Builder UI (`datamind-studio` - Laravel 13)

- **Local Chart.js Integration (`resources/views/chat/index.blade.php` & `public/js/chat_stream.js`)**:
  - Load `{{ asset('js/global_js/chart.umd.min.js') }}` (already bundled locally in `public/js/global_js/`).
- **Interactive Chart Studio Widget inside Assistant Messages**:
  - Every tabular response displays a **`[ 📈 Configurar / Ver Gráfico ]`** button next to **`[ 📊 Generar Excel (.xlsx) ]`** (and auto-opens the Chart Studio panel automatically when the user's prompt asked for a chart!).
  - **Super-Simple 4-Step Visual Selector Bar**:
    1. **Tipo de Gráfico** (Pills visuales con iconos):
       - 📊 **Barras Verticales** (`bar`)
       - 📈 **Líneas / Tendencia** (`line`)
       - 🍩 **Anillo / Pastel** (`doughnut` / `pie`)
       - 📉 **Barras Horizontales** (`horizontalBar`)
    2. **Eje X (Categoría / Agrupar por)**: `<select>` poblado automáticamente con todas las columnas de la tabla (con chips rápidos clicables debajo para cambiar de campo con un solo clic).
    3. **Operación / Métrica**:
       - `Contar registros (COUNT)` (funciona con cualquier columna, ideal cuando solo hay texto/estados)
       - `Sumar valores (SUM)`
       - `Promedio (AVG)`
       - `Valor directo por fila`
    4. **Eje Y (Campo Numérico)**: `<select>` con las columnas numéricas detectadas (se oculta/deshabilita automáticamente si elige `Contar registros`).
  - **Acciones del Gráfico**:
    - Renderizado instantáneo con la paleta corporativa DataMind (`#0476D9`, `#0468BF`, `#4B89BF`, `#99D0F2`, más acentos armónicos para gráficos circulares), tooltips detallados y botón **`[ 📷 Descargar PNG ]`** para guardar la imagen del gráfico.

---

## Phase 14: Guided Multi-Table Field Discovery & Two-Step Chart Confirmation (`Option A Clarification`)

**Objective**: Align chart generation strictly with **Clarification Option A**: when a user asks the AI to analyze or chart data across one or multiple related tables (e.g., *"revísame el estado del rollo que está vinculado con otra tabla y hazme un gráfico"*) **without specifying the exact fields/axes**, the AI must **first** execute a broad relational `SELECT ... JOIN` query to inspect the linked tables, analyze the resulting columns, **ask the user in Markdown which fields they want to use**, and display a **Step-1 Guided Field Picker Wizard** in the UI (`needs_field_selection = true`) instead of drawing an unconfirmed chart prematurely. Once the user selects the fields in the super-simple wizard and clicks **`[ ✨ Generar Gráfico Ahora ]`** (or replies in the chat specifying the fields, e.g., *"haz el gráfico con estado_rollo y peso"*), the AI/UI immediately generates the exact chart (`ready_to_render = true`).

### 1. Backend Intelligence (`datamind-core` - Python FastAPI)

- **Multi-Table `JOIN` & Broad Column Discovery in `AskChatUseCase._generate_sql()` (`app/use_cases/ask_chat.py`)**:
  - Update the SQL generation prompt so that when the user mentions two or more related concepts/tables (e.g., rolls + orders/machines/status) or requests a chart/analysis, the LLM constructs a `SELECT` with the appropriate `JOIN` bringing descriptive categorical columns (`estado`, `tipo`, `nombre`, `proceso`, `fecha`) and numeric columns (`cantidad`, `peso`, `metros`, `total`) from both tables so the user has all candidate fields available.
- **Explicit vs. Ambiguous Field Detection (`AskChatUseCase.analyze_columns_for_chart()`)**:
  - Inspect whether the user's prompt explicitly names specific columns from the returned dataset (or uses explicit axis phrases like `"por <columna>"`, `"en base a <columna>"`, `"eje x <columna>"`, `"agrupado por <columna>"`) or references a follow-up turn in the same session that already has a `dataset_id`:
    - **Case 1: Ambiguous / Exploratory Request (`needs_field_selection = True`)**:
      - The user asked for a chart or multi-table review without specifying the exact columns to plot.
      - `chart_config` returns:
        - `wants_chart`: `True`
        - `needs_field_selection`: `True`
        - `dimension_columns`: list of categorical/date/status columns detected across the joined tables
        - `metric_columns`: list of numeric columns detected
        - `column_samples`: map of each column with its inferred type (`Categoría` vs `Numérico`) and a sample value from the dataset
        - `suggested_x`, `suggested_y`, `suggested_agg`, `suggested_type`
      - **LLM Synthesis Prompt (`needs_field_selection = True`)**:
        - Instructs the AI to summarize the cross-table analysis (`JOIN`), list the detected candidate fields grouped into **Campos de Agrupación (Eje X)** and **Campos Numéricos / Métricas (Eje Y)**, and **explicitly ask the user**: *"¿Con cuáles de estos campos deseas que genere el gráfico? Puedes seleccionarlos con un clic en el asistente de abajo o indicármelo por escrito."*
    - **Case 2: Explicit Field Request or Follow-Up Confirmation (`needs_field_selection = False`)**:
      - The user explicitly stated which column(s) to plot (either in the initial prompt or as a follow-up reply in the chat after the AI asked, e.g., *"créame el gráfico con el campo estado y peso"*).
      - If the user replies in the chat to answer the AI's field question, `AskChatUseCase` detects the follow-up confirmation against the session's last `dataset_id` (or executes the refined query), matches the requested columns to `suggested_x` and `suggested_y`, sets `wants_chart = True` and `needs_field_selection = False`, and renders the chart immediately.

### 2. Frontend Guided Wizard & Instant Chart Generation (`datamind-studio` - `public/js/chat_stream.js`)

- **Two-Stage Interactive Flow inside `renderDatasetSection` & `setupInteractiveChartBuilder`**:
  1. **Stage 1 — Asistente Guiado de Selección de Campos (Shown when `chart_config.wants_chart && chart_config.needs_field_selection`)**:
     - Instead of drawing a chart right away, the UI displays a highlighted, super-friendly **"Paso 1: ¿Con qué campos deseas crear el gráfico?"** wizard card:
       - **Paso A — ¿Por qué campo deseas agrupar? (Eje X)**: Interactive clickable cards/pills for every column found in the joined tables, showing a badge (`Categoría` or `Numérico`) and a real sample value from the query.
       - **Paso B — ¿Qué deseas medir o calcular? (Eje Y)**: Interactive clickable pills for `🔢 Contar registros (COUNT)` or summing/averaging any numeric column (`➕ Sumar`, `➗ Promedio`, `📍 Valor directo`).
       - **Paso C — Tipo de Gráfico**: Visual icon buttons (`📊 Barras`, `📉 Horizontales`, `📈 Líneas`, `🍩 Dona`, `🥧 Pastel`).
       - **Primary Action Buttons**:
         - **`[ ✨ Generar Gráfico con estos Campos ]`**: Renders the chart on the spot in the canvas below.
         - **`[ 💬 Pedirle a la IA con estos Campos ]`**: Sends a follow-up message to the AI (e.g., *"Genera el gráfico de Barras agrupando por `estado` y calculando `COUNT`"*), so the AI itself analyzes and generates the chart response in the conversation history.
  2. **Stage 2 — Gráfico Detallado Generado (Shown immediately when `needs_field_selection === false` or as soon as the user clicks `[ ✨ Generar Gráfico con estos Campos ]`)**:
     - Smoothly reveals the `Chart.js` canvas with the exact user-chosen fields, keeping the top bar of controls visible so the user can keep experimenting or click **`[ 📷 Descargar PNG ]`**.

---

## Phase 15: Relational Graph Embeddings, 1-Hop Hybrid Retrieval & Automatic FK Label Resolution for Charts (`rag-engineer` + `embedding-strategies` + `hybrid-search-implementation`)

**Objective**: Solve the core relational intelligence gap identified in `/speckit-analyze` (`C1`, `C2`, `U1`, `U2`) using the patterns from **`rag-engineer`**, **`embedding-strategies`**, and **`hybrid-search-implementation`**:
When a table `X` (e.g., `usuario`) links to a table `A` (e.g., `empresa`) via an ID column (`id_empresa` or `empresa_id`), the raw ID does not tell the user the company name. The AI must **learn how tables relate during vectorization**, **retrieve both tables together via Hybrid Search + 1-Hop Relational Graph Expansion**, and **automatically construct `JOIN` queries that fetch the human-readable descriptive columns (`empresa.nombre`)** so charts and Guided Field Selection display meaningful labels instead of raw numeric foreign keys.

### 1. Deep Relational Introspection (`app/infrastructure/database/dynamic_db_adapter.py`)

- **Explicit Foreign Key Introspection (`INFORMATION_SCHEMA`)**:
  - **MySQL / MariaDB (`_introspect_mysql`)**: Query `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` where `TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL` to extract `(table_name, column_name, referenced_table_name, referenced_column_name)`.
  - **PostgreSQL (`_introspect_postgres`)**: Query `information_schema.table_constraints` + `key_column_usage` + `constraint_column_usage` where `constraint_type = 'FOREIGN KEY'` to extract explicit foreign keys.
- **Heuristic Relationship & Descriptive Label Inference (`_infer_table_relationships`)**:
  - Many enterprise schemas omit formal `FOREIGN KEY` constraints. For any column matching `id_<entity>`, `<entity>_id`, `cod_<entity>`, or `fk_<entity>`:
    - Match `<entity>` against all table names in the database (supporting singular/plural Spanish & English variants: `empresa` ↔ `empresas`, `rollo` ↔ `rollos`, `orden` ↔ `ordenes`, `cliente` ↔ `clientes`, `usuario` ↔ `usuarios`).
    - Identify the target table's primary key (`id`, `id_<entity>`, `<entity>_id`, `codigo`) and its **Human-Readable Label Columns (`descriptive_columns`)** by prioritizing columns matching `nombre`, `name`, `razon_social`, `descripcion`, `titulo`, `detalle`, `estado`, `tipo`, `codigo`.
  - Attach `foreign_keys` and `referenced_by` (reverse relationships!) to every table dictionary returned by `introspect_schema()`.

### 2. Semantic Relational Graph Embedding (`app/use_cases/manage_connections.py` — `embedding-strategies`)

- When vectorizing tables in `vectorize_selected_tables()` (and when auto-syncing schemas):
  - Build a rich, structured semantic document for `nomic-embed-text`:
    1. **Identidad de Tabla y Propósito**: Table name, database, and column classification (*Llaves Primarias/Foráneas*, *Atributos Descriptivos / Categorías para Eje X*, *Métricas Numéricas para Eje Y*).
    2. **Relaciones Salientes (`FOREIGN KEYS` / `JOINs` Obligatorios para Nombres Reales)**:
       - Example embedded text:
         > `- Columna llave foránea 'usuario.id_empresa' se relaciona con 'empresa.id'. IMPORTANTE: 'id_empresa' solo contiene el ID numérico; para obtener los datos o el nombre real de la empresa SIEMPRE usa: JOIN empresa ON usuario.id_empresa = empresa.id y selecciona empresa.nombre (o empresa.razon_social).`
    3. **Relaciones Entrantes (`REFERENCED BY`)**:
       - Lists which child tables point to this table (e.g., on `empresa`: *"La tabla `usuario` se vincula con `empresa` mediante `usuario.id_empresa = empresa.id`"*).
  - Store structured graph metadata in `KnowledgeDocumentModel.metadata_` and `KnowledgeVectorChunkModel.metadata_`:
    - `table_name`: `"usuario"`
    - `related_tables`: `["empresa", ...]`
    - `join_hints`: `["JOIN empresa ON usuario.id_empresa = empresa.id (campos descriptivos: nombre)"]`

### 3. Hybrid Search + 1-Hop Relational Graph Expansion (`app/infrastructure/database/vector_repository.py` — `rag-engineer` & `hybrid-search-implementation`)

- Upgrade `VectorRepository.search_schema_with_relations(query_embedding, prompt_text, connection_id, top_k=5)`:
  1. **Dense + Lexical Hybrid Scoring**:
     - Retrieve top candidate `db_schema` chunks by `pgvector` cosine similarity.
     - Boost/include any `db_schema` chunk for the same `connection_id` whose `table_name` or `related_tables` appears lexically in `prompt_text` (even if its singular/plural form varies).
  2. **1-Hop Relational Graph Expansion (Parent-Child / Neighbor Expansion)**:
     - Collect all table names referenced in `metadata["related_tables"]` of the primary retrieved tables.
     - Automatically fetch the `db_schema` chunks for those related tables from `pgvector` (if vectorized) and append them to the retrieved context!
     - **Result**: Even if the user only asks *"Hazme un gráfico de usuarios por empresa"* and only `usuario` matched top-1, the retriever automatically pulls `empresa` via the 1-hop graph edge `usuario.id_empresa -> empresa`.

### 4. Smart JOIN SQL Generation & FK Filtering in Chart Builder (`app/use_cases/ask_chat.py` & `public/js/chat_stream.js`)

- **Relational SQL Prompt Rules (`AskChatUseCase.execute_sync`)**:
  - Inject explicit instructions into `sql_prompt`:
    - *"REGLA DE ORO DE RELACIONES (`JOIN`): Cuando una tabla tenga columnas de relación como `id_empresa`, `empresa_id`, `id_cliente`, `id_rollo`, etc., NUNCA devuelvas únicamente el ID numérico si existe la tabla relacionada en los esquemas. Realiza SIEMPRE el `INNER JOIN` o `LEFT JOIN` hacia la tabla maestra y selecciona su columna descriptiva con un alias claro (ej. `e.nombre AS nombre_empresa`) para que los gráficos muestren nombres reales y no IDs."*
- **FK De-prioritization in `analyze_columns_for_chart()`**:
  - Detect raw foreign-key columns (`id_*`, `*_id`) and separate them into `foreign_key_columns`.
  - Exclude raw `id_*` / `*_id` columns from `dimension_columns` and `metric_columns` whenever human-readable descriptive columns exist in the result set, ensuring the **Guided Field Selector (Paso 1)** and default axes highlight the real descriptive fields (`nombre_empresa`, `estado_rollo`, etc.).
- **Connections Explorer UI Badge (`resources/views/connections/index.blade.php` & `public/js/connections_manager.js`)**:
  - Show detected relationships (`🔗 Relacionada con: ...`) in the table explorer so the user can see at a glance how DataMind understands their database relationships.

---

## Phase 16: Interactive AI Knowledge Trainer ("🎓 Centro de Entrenamiento IA"), Conversational Learning (`teach_knowledge`), Output Mode Control (`wants_chart` vs `wants_table`) & User Training Curriculum (`v1.0.8`)

**Objective**: Address all findings from `/speckit-analyze` (`I1`, `A1`, `U1`, `C1`) and satisfy all 17 verified requirements in `/speckit-checklist` ([ai-training.md](checklists/ai-training.md): `CHK001`–`CHK017`, **17/17 PASS**) so the user has:
1. **Direct Conversational Learning in Chat (`intent = "teach_knowledge"`)**: When the user teaches a rule or table relationship in the chat (e.g., *"La tabla `users` se relaciona con la tabla `companies` uniendo `users.current_company_id= companies.id`. Cuando el usuario pida datos o gráficos por empresa, nunca muestres `current_company_id`; haz siempre `JOIN companies` y muestra `companies.name`"*), the AI immediately recognizes it is being taught, embeds the rule into `pgvector`, updates relational `join_hints`, and responds with a **Learning Confirmation Card** — **never** executing SQL or rendering unwanted charts/tables.
2. **Explicit Output Mode Control (`wants_chart` vs `wants_table` vs `text_only`)**: The AI understands when the user asks for **a Chart** (*"hazme un gráfico"*), when they ask for **a Table/List** (*"hazme una tabla"*, *"lístame"*), and when they only ask a **Text Question** (*"¿cuántos usuarios hay?"*), rendering only what was requested while keeping on-demand toggle buttons (`[ 📋 Ver Tabla ]`, `[ 📊 Crear Gráfico ]`, `[ 📥 Generar Excel ]`) available.
3. **Interactive "🎓 Centro de Entrenamiento IA" & 5-Level User Training Curriculum**: A visual modal/panel in `datamind-studio` with 4 guided teaching templates, active knowledge management, and a step-by-step curriculum so the user learns how to teach the AI.

### 0. Checklist Gate Verification Summary (`checklists/ai-training.md`)

| Checklist File | Total Items | Verified (`[x]`) | Unchecked (`[ ]`) | Gate Status |
| :--- | :---: | :---: | :---: | :---: |
| [checklists/ai-training.md](checklists/ai-training.md) | 17 | 17 (`CHK001`–`CHK017`) | 0 | **✓ PASS** |

### 1. Diagnóstico de Arquitectura y Solución Técnica (`I1`, `A1`, `U1`, `C1`)

- **Solución #1 (`I1` - Detección de Intención de Enseñanza en el Chat `teach_knowledge`)**:
  - En `app/use_cases/intent_classifier.py`, implementar `IntentClassifier.is_teaching_statement(prompt)` y `IntentClassifier.extract_teaching_capsule(prompt)` **antes** de evaluar `SQL_TRIGGER_PATTERNS`:
    - Detecta patrones instructivos/declarativos donde el usuario le enseña a la IA cómo funcionan sus tablas o reglas:
      - Declaración explícita de relación: `r"\bla\s+tabla\s+\w+\s+se\s+(relaciona|une|vincula)\s+con\b"`, `r"\buniendo\s+\w+\.\w+\s*=\s*\w+\.\w+"`, `r"\bse\s+relacionan?\s+(por\s+medio\s+de|mediante|uniendo)\b"`.
      - Instrucciones condicionadas para futuras consultas: `r"\bcuando\s+(el\s+usuario|te)\s+(pida[n]?|pregunte[n]?|solicite[n]?)\b"`, `r"\bnunca\s+muestres\b"`, `r"\bhaz\s+siempre\s+(inner\s+|left\s+)?join\b"`.
      - Comandos directos de aprendizaje: `r"\b(aprende|recuerda|memoriza|guarda\s+esta\s+regla|ten\s+en\s+cuenta)\s+que\b"`.
    - Cuando se detecta `intent == "teach_knowledge"`, `AskChatUseCase`:
      1. Clasifica automáticamente si la enseñanza es una **Relación entre Tablas (`custom_relation`)**, una **Fórmula (`kpi_formula`)**, un **Ejemplo SQL (`sql_example`)** o una **Regla de Negocio/Diccionario (`business_rule`)**.
      2. Si menciona tablas y columnas de unión (ej. `users.current_company_id = companies.id` y mostrar `companies.name`), extrae automáticamente:
         - `source_table = "users"`, `source_column = "current_company_id"`
         - `target_table = "companies"`, `target_column = "id"`, `label_column = "name"`
         - Guarda el documento en `pgvector` y actualiza también los chunks `db_schema` de `users` y `companies` agregando el `join_hint` y `related_tables` para que la expansión `1-Hop` funcione de inmediato.
      3. Devuelve `has_tabular_data = False`, `chart_config = None` y un mensaje estructurado en Markdown confirmando exactamente la regla que acaba de aprender y vectorizar.

- **Solución #2 (`A1` - Control Explícito de Formato: `wants_chart` vs `wants_table` vs `text_only`)**:
  - En `app/use_cases/intent_classifier.py`, crear `IntentClassifier.detect_output_format(prompt)`:
    1. **Limpieza de Cláusulas Condicionales/Negativas**: Antes de buscar si el usuario pidió gráfico o tabla, remueve o ignora frases condicionales o negativas como `r"cuando\s+(el\s+usuario\s+)?(pida[n]?|solicite[n]?|quiera[n]?)[^.,;]*"` y `r"\b(no\s+quiero|sin|nunca\s+muestres)\s+(un\s+)?(grafico|tabla)\b"`. Así, *"Cuando el usuario pida datos o gráficos por empresa..."* **jamás** activa un gráfico por error.
    2. **Detección de Gráfico (`wants_chart`)**: Solo `True` si el usuario pide un gráfico/diagrama/visualización para la consulta actual (*"hazme un gráfico"*, *"grafica"*, *"en un gráfico de barras/pastel/líneas"*).
    3. **Detección de Tabla (`wants_table`)**: Solo `True` si el usuario pide explícitamente una tabla o listado (*"hazme una tabla"*, *"muéstrame en una tabla"*, *"tabla de"*, *"lístame"*, *"lista los registros"*, *"ver registros"*).
  - En `public/js/chat_stream.js` (`renderDatasetSection`):
    - Leer `chart_config.wants_chart` y `chart_config.wants_table`:
      - Si `wants_chart == true` y `wants_table == false`: Se abre el panel del Gráfico (o el Asistente de Selección de Campos Opción A), y la tabla `DataTables` permanece **oculta** bajo el botón `[ 📋 Mostrar Tabla (N filas) ]`.
      - Si `wants_table == true` y `wants_chart == false`: Se muestra la **Tabla Interactiva (`DataTables`)** desplegada y el gráfico permanece **oculto** bajo el botón `[ 📊 Personalizar / Ver Gráfico ]`.
      - Si `wants_chart == false` y `wants_table == false` (pregunta normal en texto, ej. *"¿Cuántos usuarios hay?"*): La IA responde en texto limpio y debajo aparece únicamente la barra compacta con botones opcionales (`[ 📋 Ver Tabla ]`, `[ 📊 Crear Gráfico ]`, `[ 🧠 Enseñar este SQL a la IA ]`, `[ 📥 Generar Excel ]`) sin abrir ni la tabla ni el gráfico hasta que el usuario haga clic.

- **Solución #3 (`Silo de Categorías en pgvector`)**:
  - `AskChatUseCase.execute_sync` (`app/use_cases/ask_chat.py`) ahora ejecuta `VectorRepository.search_learned_rules()` durante cada `data_query` para recuperar las cápsulas de entrenamiento (`custom_relation`, `business_rule`, `kpi_formula`, `sql_example`) y las inyecta en el prompt SQL bajo `REGLAS DE NEGOCIO, RELACIONES Y EJEMPLOS APRENDIDOS DEL USUARIO` (con prioridad máxima sobre inferencias heurísticas).

### 2. Los 5 Canales de Enseñanza a la IA (`Teaching Taxonomy`)

Para que el usuario pueda entrenar a la IA con precisión quirúrgica, estructuramos el conocimiento en **5 Cápsulas de Aprendizaje**:

1. **Canal 1 — Esquema Relacional Automático (`db_schema`)**:
   - Selección conjunta de Tablas Maestras (`empresa`, `clientes`, `ordenes`) + Tablas Detalle (`usuario`, `rollos`, `movimientos`) en `/connections` + extracción de comentarios de columna (`COLUMN_COMMENT`).
2. **Canal 2 — Relaciones Manuales y Llaves Foráneas Heredadas (`custom_relation`)**:
   - Cuando dos tablas se relacionan con nombres que no siguen el estándar `id_<tabla>` (ej. `tbl_usr.cod_cia = tbl_emp.id_compania`), el usuario registra explícitamente: Tabla Origen, Columna Origen, Tabla Destino, Columna Destino y Columna Descriptiva (`razon_social`).
3. **Canal 3 — Glosario de Negocio, Sinónimos y Códigos de Estado (`business_rule`)**:
   - Traducción del lenguaje humano al lenguaje de la base de datos:
     - *Sinónimos*: *"Cuando pidan 'clientes VIP', filtra `categoria_cliente = 'A'`"*.
     - *Códigos de Estado*: *"En `rollos.estado`: `0` = Pendiente, `1` = En Tejeduría, `2` = Revisado, `9` = Rechazado. Usa `CASE WHEN` para mostrar el texto en gráficos"*.
4. **Canal 4 — Fórmulas y KPIs para Gráficos (`kpi_formula`)**:
   - Cómo calcular métricas compuestas: *"Porcentaje de Merma = `(peso_desperdicio / peso_bruto) * 100`"*.
5. **Canal 5 — Ejemplos SQL Verificados / "Golden SQL" (`sql_example` - Few-Shot Learning)**:
   - La técnica más potente en sistemas Text-to-SQL (`rag-engineer`): darle a la IA pares de **(Pregunta en lenguaje natural ➔ Consulta SQL `SELECT ... JOIN` exacta)**. Cuando el usuario haga una pregunta parecida o pida un gráfico similar, `pgvector` recupera ese SQL de ejemplo como plantilla base.

### 3. Backend Changes (`datamind-core` - FastAPI)

- **`app/infrastructure/database/dynamic_db_adapter.py`**:
  - Enriquecer `_introspect_mysql` y `_introspect_postgres` para extraer también los comentarios de cada columna (`COLUMN_COMMENT` en MySQL/MariaDB y `col_description()` en PostgreSQL) e incluirlos en el texto vectorizado de la tabla.
- **`app/api/v1/routers/knowledge.py` & `app/use_cases/manage_training.py`**:
  - Añadir endpoints para el **Centro de Entrenamiento IA**:
    - `GET /api/v1/knowledge/rules?connection_id={id}`: Lista todas las cápsulas de conocimiento enseñadas a la IA (`custom_relation`, `business_rule`, `kpi_formula`, `sql_example`, `process_manual`).
    - `POST /api/v1/knowledge/train`: Crea y vectoriza una cápsula estructurada de entrenamiento (validando con `sqlglot` que cualquier `sql_example` sea estrictamente `SELECT`). Si es un `custom_relation`, también actualiza los `join_hints` y `related_tables` de las tablas involucradas en `pgvector`.
    - `DELETE /api/v1/knowledge/rules/{document_id}`: Permite borrar o corregir una regla obsoleta para mantener limpio el índice vectorial (`pgvector`).
- **`app/infrastructure/database/vector_repository.py` & `app/use_cases/ask_chat.py`**:
  - Implementar `VectorRepository.search_learned_rules(query_embedding, prompt_text, connection_id, top_k=4)` que busca cápsulas en `["custom_relation", "business_rule", "kpi_formula", "sql_example"]`.
  - En `AskChatUseCase.execute_sync`, inyectar las cápsulas recuperadas tanto en la generación del SQL como en el análisis de campos para gráficos.

### 4. Frontend "🎓 Centro de Entrenamiento IA" & Playbook Interactivo (`datamind-studio` - Laravel)

- **Nueva Vista / Panel `/training` (o pestaña integrada en `/connections` + acceso directo `🎓 Entrenar IA` en el Header)**:
  - **Asistente Guiado de Enseñanza (4 Plantillas Inteligentes con 1 Clic)**:
    1. 🔗 **Enseñar Relación entre Tablas (`JOIN`)**: Selectores visuales de *Tabla A* + *Columna ID* ➔ *Tabla B* + *Columna Nombre/Etiqueta*.
    2. 📖 **Enseñar Significado de Estados o Sinónimos**: Formulario guiado (*"Cuando yo pregunte por..."* ➔ *"La IA debe buscar en la tabla/campo..."*).
    3. 📐 **Enseñar Fórmula o Indicador para Gráficos**: Nombre del indicador + fórmula o campos que se operan.
    4. 🏆 **Enseñar Consulta SQL de Ejemplo (Golden SQL)**: Pregunta ejemplo + consulta `SELECT ... JOIN` validada (incluso con botón **"Guardar como aprendizaje"** desde cualquier respuesta exitosa del chat).
    - **Academia / Guía Interactiva ("Cómo Enseñarle a tu IA en 5 Pasos")**:
    - Un checklist interactivo dentro de la interfaz que guía al usuario paso a paso con ejemplos reales para que aprenda a entrenar a la IA.

---

## Phase 17: Plan de Subida de Commits Atómicos y Versionado Semántico (`v1.0.4` ➔ `v1.0.8`)

**Objective**: Organizar todos los cambios acumulados desde el último push (`v1.0.3` / `ac3b9fa`) en **commits atómicos, limpios y semánticos (`Conventional Commits`)** para ambos repositorios (**`datamind-core`** en Python/FastAPI y **`datamind-studio`** en PHP/Laravel), garantizando trazabilidad por funcionalidad y cero archivos basura.

### 1. Repositorio 1: Backend Python (`D:\Python\python-db` ➔ `ManriqueRecinos/datamind-core`)

| Orden | Versión | Mensaje de Commit (`Conventional Commits`) | Archivos Incluidos | Propósito Técnico |
| :---: | :---: | :--- | :--- | :--- |
| **Commit 1** | `v1.0.5` | `feat(sessions): add per-user chat session history, dataset JSON endpoint and chart intent detection` | `app/api/v1/routers/chat.py`<br>`app/api/v1/routers/export.py`<br>`app/api/v1/schemas/chat.py` | Expone historial de conversaciones por `user_id` (`GET/DELETE /api/v1/chat/sessions`), endpoint de datasets JSON para gráficos (`GET /api/v1/export/dataset/{id}`) y esquemas `chart_config`. |
| **Commit 2** | `v1.0.6` | `feat(relations): implement FK introspection, relational graph embeddings and 1-hop hybrid retrieval` | `app/infrastructure/database/dynamic_db_adapter.py`<br>`app/use_cases/manage_connections.py`<br>`app/infrastructure/database/vector_repository.py` | Extrae llaves foráneas explícitas e inferidas (`id_empresa` ➔ `empresa.id`), comentarios de columna (`COLUMN_COMMENT`/`pg_description`), genera embeddings relacionales y aplica búsqueda híbrida + expansión `1-Hop` + `search_learned_rules`. |
| **Commit 3** | `v1.0.7` | `feat(training): add AI training endpoints, teach_knowledge intent and explicit chart/table output control` | `app/use_cases/intent_classifier.py`<br>`app/use_cases/ask_chat.py`<br>`app/api/v1/routers/knowledge.py`<br>`app/api/v1/schemas/knowledge.py` | Añade el intent `teach_knowledge` para aprender relaciones directo desde el chat sin disparar gráficos, control explícito `wants_chart` vs `wants_table` vs `text_only`, flujo guiado Opción A y endpoints `GET/POST/DELETE /api/v1/knowledge/train`. |
| **Commit 4** | `v1.0.8` | `test(specs): add relational, teaching and output-format unit tests and update Spec-Kit artifacts` | `tests/unit/test_intent_classifier.py`<br>`tests/contract/test_chat_router.py`<br>`specs/001-rag-core-service/spec.md`<br>`specs/001-rag-core-service/plan.md`<br>`specs/001-rag-core-service/tasks.md`<br>`specs/001-rag-core-service/data-model.md`<br>`specs/001-rag-core-service/checklists/ai-training.md` | Suite de 26 pruebas unitarias y de contrato aprobadas más documentación completa de Spec-Kit (Fases 11 a 17 y checklist `17/17 PASS`). |

---

### 2. Repositorio 2: Frontend Laravel (`D:\Laravel\Supertex AI` ➔ `ManriqueRecinos/datamind-studio`)

| Orden | Versión | Mensaje de Commit (`Conventional Commits`) | Archivos Incluidos | Propósito Técnico |
| :---: | :---: | :--- | :--- | :--- |
| **Commit 1** | `v1.0.4` | `feat(auth): add user authentication flow, login/register views and default database seeder (v1.0.4)` | `app/Http/Controllers/AuthController.php`<br>`resources/views/auth/login.blade.php`<br>`database/seeders/DatabaseSeeder.php`<br>`bootstrap/app.php` | Implementa autenticación local (`/login`, `/register`, `/logout`), usuario inicial en SQLite y exención CSRF controlada para streaming SSE. |
| **Commit 2** | `v1.0.5` | `feat(backend): add FastApiClient methods and routes for user sessions, datasets and AI training (v1.0.5)` | `app/Services/FastApiClient.php`<br>`app/Http/Controllers/ChatController.php`<br>`routes/web.php` | Conecta Laravel con FastAPI para historial de sesiones por usuario, recuperación de datasets para `Chart.js` y endpoints del Centro de Entrenamiento IA (`/chat/training/*`). |
| **Commit 3** | `v1.0.6` | `feat(ui): add rich Markdown renderer, relational table badges and AI Training Center modal (v1.0.6)` | `resources/views/chat/index.blade.php`<br>`public/css/global_styles/globales.css`<br>`resources/css/global_styles/globales.css`<br>`public/js/connections_manager.js` | Añade estilos GFM para Markdown, badges de relaciones `JOIN` detectadas en `/connections` y el modal interactivo **`🎓 Entrenar IA`** con las 4 plantillas guiadas y currículo de 5 niveles. |
| **Commit 4** | `v1.0.7` | `feat(analytics): implement 2-step guided chart builder, on-demand table/chart toggles and chat teaching (v1.0.7)` | `public/js/chat_stream.js` | Constructor interactivo `Chart.js` (Opción A en 2 pasos), apertura inteligente de tabla/gráfico solo cuando el usuario lo pide (`wants_table`/`wants_chart`), historial en sidebar y botón *"🧠 Enseñar este SQL a la IA"*. |
| **Commit 5** | `v1.0.8` | `docs(release): update feature tests, AGENTS.md and README documentation for v1.0.8` | `tests/Feature/ChatTest.php`<br>`AGENTS.md`<br>`README.md` | Pruebas de integración en PHPUnit (`11 passed`) y documentación actualizada a la versión `1.0.8`. |
