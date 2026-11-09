# Python RAG & AI Service (python-db) Constitution

## Core Principles

### I. Clean Architecture & Layer Separation (NON-NEGOTIABLE)
The application strictly enforces separation of concerns through Clean / Hexagonal Architecture:
- **Domain Layer**: Core business models, entities (`DocumentChunk`, `ChatMessage`, `SqlQuery`, `QueryResult`), and repository interfaces (`VectorRepositoryInterface`, `RelationalQueryInterface`, `LLMProviderInterface`). Zero dependencies on external frameworks (FastAPI, SQLAlchemy, Ollama).
- **Application Layer**: Use cases and orchestrators (`AskChatUseCase`, `IngestKnowledgeUseCase`, `TextToSqlUseCase`, `ExportExcelUseCase`). Coordinates domain rules, safeguards, and interface contracts.
- **Infrastructure Layer**: Concrete implementations of interfaces (`PgVectorRepository`, `MariaDbQueryAdapter`, `OllamaLlmAdapter`, `OpenPyXlExcelExporter`).
- **Presentation / API Layer**: FastAPI routers, dependency injection (`Depends`), Server-Sent Events (SSE) streaming handlers, HTTP status mapping, and serialization. Controllers must remain thin, delegating all logic to application use cases.

### II. Strict API Contracts & Validation (FastAPI & Pydantic V2)
All external communication with client services (especially Laravel) is governed by strict, versioned API contracts:
- **Multi-Model Pattern**: Separate Pydantic schemas for `Base`, `Create`, `Update`, `Response`, and internal representations.
- **Strict Typing & Runtime Validation**: Pydantic V2 models for all request bodies, query parameters, SSE chunk events, and responses. No raw `dict` responses or untyped payloads.
- **Deterministic Error Responses**: Standardized JSON error schema (`detail`, `code`, `timestamp`, `trace_id`) across all HTTP status codes (400, 401, 403, 404, 422, 500).
- **Asynchronous by Default**: All route handlers, service methods, and I/O bound operations must be `async def`. Heavy processing (embedding computation, SQL query execution) must not block the Uvicorn event loop.

### III. Vector Database Discipline (PostgreSQL + pgvector)
Vector operations must follow robust engineering standards:
- **Vector Engine**: PostgreSQL with the `pgvector` extension (`vector(768)` or configured model dimension) using HNSW (Hierarchical Navigable Small World) indexing with cosine distance (`vector_cosine_ops`).
- **Schema & Metadata Integrity**: Vector tables must store embeddings alongside rich metadata payloads (document source, domain/process category, MariaDB table/column annotations, verified SQL queries).
- **Hybrid Retrieval**: Combine dense semantic similarity (HNSW cosine search) with keyword/BM25 full-text search (PostgreSQL `tsvector` / `tsquery`) to ensure high recall for technical terms and table schemas.

### IV. Safe Database RAG & Text-to-SQL Governance (MariaDB External Access)
Access to external enterprise business databases (MariaDB) is governed by strict security guardrails:
- **Least-Privilege Credentials**: The AI service connects to MariaDB strictly using a Read-Only user (`SELECT` privileges only).
- **Query Validation & AST Inspection**: All generated SQL queries must be parsed (e.g. via `sqlglot`) to verify they are single `SELECT` statements without mutation clauses (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `EXEC`, `SHOW GRANTS`).
- **Safety Limits**: Automatic injection of `LIMIT` clauses (maximum 500 rows) and execution timeouts (e.g., 5 seconds) to prevent Denial of Service or full-table scans.
- **Dual Representation**: Query results must produce both a structured tabular payload (for potential Excel export) and a natural, humanized conversational synthesis.

### V. Resilient Inter-Service Integration (Laravel ↔ FastAPI)
The service is consumed reliably by Laravel 11 and web clients:
- **Authentication**: Service-to-service communication protected via pre-shared API Key (Bearer token) verified through FastAPI security dependencies.
- **Streaming & Polling Flexibility**: Support Server-Sent Events (`text/event-stream`) for token-by-token humanized chat rendering, alongside synchronous REST endpoints for discrete actions like Excel generation.
- **Manual Export Decoupling**: Excel generation is triggered on-demand via a distinct endpoint or action, returning a streamable `.xlsx` file without re-executing costly LLM queries.

### VI. Test-First & Comprehensive Verification (NON-NEGOTIABLE)
- **Unit Testing**: Tests written in `pytest` isolating domain entities and application use cases. External adapters (Ollama, PostgreSQL, MariaDB) must be mocked using fixtures.
- **Integration Testing**: Contract tests for API routers using `httpx.AsyncClient` verifying status codes, schema validation, and error boundaries.
- **RAG & SQL Guardrail Tests**: Specific test suites asserting that unauthorized SQL statements are rejected, and retrieval matches expected domain contexts.

## Technology Stack Standards

- **Runtime**: Python 3.11+ (Python 3.13 supported)
- **Framework**: FastAPI (async) + Uvicorn
- **Validation**: Pydantic V2 / Pydantic Settings
- **Vector Database**: PostgreSQL 17 + `pgvector` (via `asyncpg` / `SQLAlchemy 2.0`)
- **External Enterprise DB**: MariaDB (read-only adapter via `aiomysql`)
- **Local AI Engine**: Ollama (Qwen 2.5 7B / Llama 3.1 8B for inference; `nomic-embed-text` for embeddings)
- **Frontend / Client**: Laravel 11 (Blade + Livewire / Alpine.js + Tailwind CSS)
- **Excel Generation**: `openpyxl` / `pandas` (FastAPI) or `Maatwebsite/Laravel-Excel` (Laravel)
- **Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, `httpx`

## Governance

This Constitution represents the non-negotiable architectural law of the `python-db` project. Any changes to these principles require explicit documentation, impact assessment, and version amendment.

**Version**: 1.1.0 | **Ratified**: 2026-11-06 | **Last Amended**: 2026-11-06