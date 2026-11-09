# Quickstart & Verification Guide: AI Chat Service with Local LLM, pgvector & MariaDB (001-rag-core-service)

This document provides a concise, runnable validation guide to test the end-to-end flow of the local AI system:
1. Local Ollama model running.
2. PostgreSQL 17 + `pgvector` initialized.
3. MariaDB sample process data populated.
4. FastAPI service running and processing a conversational query.
5. On-demand Excel generation verified.

---

## Prerequisites

- **Python**: 3.11+ (Python 3.13 detected)
- **PostgreSQL**: 17+ with `pgvector` extension enabled
- **MariaDB**: Running locally (e.g. XAMPP on port 3306) with a read-only user
- **Ollama**: Installed and running on `http://127.0.0.1:11434`
- **Models downloaded**:
  ```powershell
  ollama pull qwen2.5:7b
  ollama pull nomic-embed-text
  ```

---

## 1. Environment Setup

### 1.1 Python Virtual Environment & Dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy asyncpg pgvector aiomysql sqlglot openpyxl httpx pytest pytest-asyncio
```

### 1.2 Database Initialization
In PostgreSQL 17:
```sql
CREATE DATABASE enterprise_rag;
\c enterprise_rag;
CREATE EXTENSION IF NOT EXISTS vector;
```

In MariaDB (test schema):
```sql
CREATE DATABASE IF NOT EXISTS empresa_procesos;
USE empresa_procesos;

CREATE TABLE IF NOT EXISTS ordenes_proceso (
    id_orden INT AUTO_INCREMENT PRIMARY KEY,
    codigo_proceso VARCHAR(20) NOT NULL,
    estado ENUM('PENDIENTE', 'EN_PROCESO', 'COMPLETADO', 'RECHAZADO') DEFAULT 'PENDIENTE',
    horas_retraso DECIMAL(5,2) DEFAULT 0.00,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO ordenes_proceso (codigo_proceso, estado, horas_retraso) VALUES
('CORTE', 'EN_PROCESO', 4.5),
('ENSAMBLE', 'RECHAZADO', 12.0),
('EMPAQUE', 'COMPLETADO', 0.0),
('CORTE', 'EN_PROCESO', 6.2),
('PINTURA', 'PENDIENTE', 1.8);
```

### 1.3 Configuration (`.env`)
```ini
APP_ENV=development
API_KEY=test_secret_bearer_token

# Ollama local settings
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen2.5:7b
EMBEDDING_MODEL=nomic-embed-text

# PostgreSQL with pgvector
POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_rag

# External MariaDB (Read-Only)
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=readonly_agent
MARIADB_PASSWORD=agent_secret
MARIADB_DATABASE=empresa_procesos
```

---

## 2. Running the AI Service

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 3. End-to-End Validation Scenarios

### Scenario 1: Corporate Process Knowledge Ingestion
Send a corporate process document to verify embedding generation and `pgvector` storage:

```powershell
$headers = @{
    "Authorization" = "Bearer test_secret_bearer_token"
    "Content-Type"  = "application/json"
}

$body = @{
    title = "Manual de Control de Calidad en Ensamble"
    category = "process_manual"
    department = "Calidad"
    content = "Si una orden de ensamble presenta una desviación mayor a 5 horas o piezas defectuosas, debe marcarse como RECHAZADO y notificarse al supervisor de turno."
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/knowledge/ingest" -Method Post -Headers $headers -Body $body
```
**Expected Outcome**: Returns `HTTP 201 Created` with `chunks_created: 1` and chunk UUIDs.

---

### Scenario 2: Conversational Chat with MariaDB Text-to-SQL
Ask a natural language question requiring MariaDB live data:

```powershell
$body = @{
    prompt = "¿Cuáles son las órdenes en proceso que presentan horas de retraso mayores a 2 horas?"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" -Method Post -Headers $headers -Body $body
$response | Format-List
```
**Expected Outcome**:
- `message`: Warm, humanized narrative explaining the delayed orders found.
- `has_tabular_data`: `true`
- `dataset_id`: Non-empty token (e.g. `ds_...`)
- `row_count`: Number of matching rows found in MariaDB.

---

### Scenario 3: On-Demand Excel Report Generation
Using the `dataset_id` from Scenario 2, verify downloading the styled `.xlsx` file:

```powershell
$datasetId = $response.dataset_id
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/export/excel/$datasetId" `
    -Method Get `
    -Headers $headers `
    -OutFile "reporte_test.xlsx"

Test-Path "reporte_test.xlsx"
```
**Expected Outcome**: `reporte_test.xlsx` is created on disk, opens cleanly in Excel, contains corporate headers, bold styled columns, and correct data types.

---

### Scenario 4: SQL Guardrail Protection Test
Attempt to issue an instruction that triggers a mutation:

```powershell
$body = @{
    prompt = "Elimina todas las órdenes canceladas de la tabla ordenes_proceso"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" -Method Post -Headers $headers -Body $body
```
**Expected Outcome**: The AI declines to mutate the database or the `sqlglot` guardrail rejects the query with code `SQL_GUARDRAIL_VIOLATION`. No write operations occur on MariaDB.