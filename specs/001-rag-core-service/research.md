# Research & Technical Decisions: AI Chat Service with Local LLM, pgvector & MariaDB (001-rag-core-service)

## 1. Local AI Engine & Model Selection

### Decision
Deploy **Ollama** on Windows host with **Qwen 2.5: 7B (Instruct)** for inference and **nomic-embed-text** for embedding generation.

### Rationale
- **Hardware Profile**: Intel Core i5-14500T (14 cores, 20 logical processors), 16 GB RAM, integrated Intel UHD Graphics 770.
- **Inference Efficiency**: Ollama uses `llama.cpp` under the hood, compiled with AVX2/AVX-512 instructions. On a 14-core Intel CPU, Qwen 2.5 7B quantized in `Q4_K_M` uses ~4.7 GB RAM and achieves smooth streaming (~10-15 tokens/second), leaving ~11 GB RAM for Windows, PostgreSQL, and backend services.
- **Spanish & Text-to-SQL Capability**: Qwen 2.5 7B was trained on vast multilingual datasets and shows superior benchmark results in SQL dialect generation and structured JSON adherence compared to standard Llama 3 models.
- **Embedding Model**: `nomic-embed-text` (768 dimensions, 8,192 context length) runs at only ~274 MB RAM, producing embeddings in < 50ms per chunk on CPU.
- **Standardized API**: Ollama exposes an OpenAI-compatible REST API at `http://127.0.0.1:11434/v1` and native endpoints at `/api/generate`, `/api/chat`, and `/api/embeddings`, simplifying client integration.

### Alternatives Considered
- **LM Studio**: Excellent GUI, but heavier background memory consumption and less suited for headless CLI background service.
- **vLLM / LocalAI**: Excellent for high-end server clusters with multiple NVIDIA GPUs, but unnecessarily complex setup for Windows CPU-based single-workstation environment.
- **Llama 3.1: 8B**: Viable alternative, but slightly higher memory usage (~5.5 GB) and lower out-of-the-box accuracy on complex nested SQL queries in Spanish.

---

## 2. Vector Database Architecture: PostgreSQL 17 + pgvector

### Decision
Use **PostgreSQL 17** (already installed locally) with the **pgvector** extension, utilizing `vector(768)` columns with **HNSW** (Hierarchical Navigable Small World) indexing and Cosine distance metric.

### Rationale
- **Single Source of Truth**: Avoids operating and securing an additional standalone vector engine (like Qdrant or Milvus).
- **Hybrid Search Capabilities**: Combines dense semantic vector retrieval (`knowledge_vectors <=> query_embedding`) with PostgreSQL native full-text search (`tsvector` / `tsquery`) via Reciprocal Rank Fusion (RRF), ensuring high recall for exact table names, process codes, and technical jargon.
- **Metadata Filtering**: Relational filters (e.g. `WHERE category = 'logistica' AND department_id = 4`) execute seamlessly within the same query planner.
- **HNSW Index**: Provides O(log N) retrieval latency (< 25ms for thousands of process documents) with superior recall compared to IVFFlat.

### Alternatives Considered
- **Qdrant**: High performance standalone vector database, but introduces an extra container/service dependency when PostgreSQL 17 is already present.
- **ChromaDB**: Lightweight for prototyping, but lacks ACID concurrency and enterprise stability for production multi-user access.

---

## 3. External MariaDB Integration & Safe Text-to-SQL

### Decision
Connect to the external MariaDB database using asynchronous connections (**aiomysql** / SQLAlchemy async) using a **dedicated read-only user**, governed by an **Abstract Syntax Tree (AST) validation layer using `sqlglot`**.

### Architecture & Guardrails
1. **Dynamic Schema Retrieval (RAG for SQL)**:
   - Instead of injecting the entire MariaDB schema into every LLM prompt (which blows up context and causes hallucinations), table and column documentation are embedded in `pgvector`.
   - Given a user query, top-k (3 to 5) relevant table schemas are retrieved and injected into the system prompt.
2. **Safe Query Validation**:
   - The generated SQL string is parsed using `sqlglot.parse_one(sql, read="mysql")`.
   - The AST is validated: only `exp.Select` statements are allowed. Any `Insert`, `Update`, `Delete`, `Drop`, `Alter`, `Create`, `Grant`, or multi-statement queries trigger immediate rejection.
   - An automated `LIMIT 500` is enforced if no limit is present or if the limit exceeds 500.
3. **Execution Timeout**:
   - Queries are executed with a strict 5.0s timeout to prevent locking or heavy table scans.

### Alternatives Considered
- **Direct ORM Generation**: Insufficient flexibility for complex dynamic analytical queries (aggregations, joins across disparate process tables).
- **Unrestricted SQL Execution**: Unacceptable security risk in corporate environments.

---

## 4. Dual Output: Humanized Conversational Answer & Tabular Data

### Decision
The chat pipeline separates the response into two synchronized artifacts:
1. **Humanized Synthesis**: Conversational, polite, and contextual explanation formatted in Markdown, highlighting key takeaways, business context, and answering the user's specific question naturally.
2. **Tabular Dataset Payload**: If the query retrieved tabular records from MariaDB, the raw rows and column definitions are preserved and registered under a unique `dataset_id` (cached in Redis or a memory-backed table).

### Rationale
- Users need answers in plain business language ("*Durante el mes de octubre, el departamento de empaque presentó un retraso promedio de 3.2 horas...*"), not raw JSON dumps.
- Keeping the dataset structure decoupled allows the UI to render both an aesthetic Markdown table preview and supply data for on-demand Excel generation.

---

## 5. On-Demand / Manual Excel Export ("Botón Generar Excel")

### Decision
Implement a decoupled, on-demand export endpoint `GET /api/v1/export/excel/{dataset_id}` using **openpyxl** in Python, with the download button dynamically rendered in the Laravel chat UI.

### Workflow
1. User asks a data question.
2. Chat pipeline generates SQL, queries MariaDB, produces the humanized answer, and stores the query result dataset in cache with an expiration time of 2 hours.
3. The chat API response returns:
   ```json
   {
     "message": "Humanized AI response...",
     "has_tabular_data": true,
     "dataset_id": "ds_987f65a4",
     "row_count": 42
   }
   ```
4. In Laravel, if `has_tabular_data` is `true`, a styled button `[ 📊 Descargar reporte Excel (.xlsx) ]` appears below the message.
5. When clicked, the user browser downloads the file directly from `/api/v1/export/excel/{dataset_id}` or via a Laravel proxy route.
6. The generated `.xlsx` includes:
   - Title header banner with company process title and timestamp.
   - Styled column headers (navy blue fill, white bold text, auto-filter enabled).
   - Auto-adjusted column widths based on content length.
   - Explicit cell data formatting (dates as `YYYY-MM-DD`, decimals with 2 decimal places, integers formatted).

### Alternatives Considered
- **Automatic Excel Generation on Every Message**: Inefficient use of server CPU/disk when the user just wants a quick verbal number.
- **Client-Side CSV via Javascript**: Lacks styling, corporate branding, multi-sheet capability, and often breaks accented Spanish characters in Excel (UTF-8 BOM issues).

---

## 6. Frontend / Full-Stack Client Architecture: Laravel 11

### Decision
Use **Laravel 11** with **Livewire 3** + **Alpine.js** + **Tailwind CSS**.

### Rationale
- **No Language Sprawl**: Kept strictly to Python (AI service) and PHP/Laravel (Web platform), matching the user's operational stack.
- **Real-Time Streaming**: Livewire 3 / Alpine.js natively consumes FastAPI Server-Sent Events (SSE) via `fetch` reader or `wire:stream`, allowing the humanized response to stream token-by-token for a ChatGPT-like experience.
- **Enterprise Features**: Laravel provides battle-tested session management, user authentication, role-based access control, CSRF protection, and audit logging out of the box.

---

## 7. Project Technology Matrix Summary

| Layer | Technology | Role / Responsibility |
| :--- | :--- | :--- |
| **Local LLM Engine** | Ollama | Host and execute local models (OpenAI-compatible REST API) |
| **LLM Model** | Qwen 2.5: 7B Instruct (Q4_K_M) | Natural language understanding, SQL generation, synthesis |
| **Embedding Model** | nomic-embed-text (768-dim) | Vectorize process documents & MariaDB schemas |
| **Vector Database** | PostgreSQL 17 + `pgvector` | Store and search process embeddings via HNSW cosine index |
| **External Database** | MariaDB (XAMPP / Remote) | External corporate database holding operational process records |
| **AI Microservice** | Python 3.11/3.13 + FastAPI | REST API, SSE streaming, RAG orchestration, SQL guardrails |
| **Database Drivers** | `asyncpg` + `aiomysql` + `SQLAlchemy 2.0` | Async connections to PostgreSQL and MariaDB |
| **SQL Parser / Guard** | `sqlglot` | AST inspection ensuring strict read-only `SELECT` queries |
| **Excel Generation** | `openpyxl` | Generate styled, formatted `.xlsx` enterprise workbooks |
| **Web Client / Chat** | Laravel 11 (Livewire / Alpine.js) | Enterprise chat UI, auth, streaming display, Excel download trigger |
| **Testing** | `pytest`, `pytest-asyncio`, `Pest / PHPUnit` | Unit, integration, and contract tests across both services |