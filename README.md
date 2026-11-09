# 🧠 DataMind Core — Open-Source Local AI RAG & Multi-Database Text-to-SQL Engine

[![Python](https://img.shields.io/badge/Python-3.11%2B%20%7C%203.13-0476D9?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Async%20REST%20%2B%20SSE-0468BF?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL%2017-pgvector%20HNSW-4B89BF?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Ollama](https://img.shields.io/badge/Ollama-100%25%20Local%20LLM-0476D9)](https://ollama.com/)
[![License](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)

**DataMind Core** es un motor backend *open-source* de inteligencia artificial **100% local (On-Premise / Zero Cloud Leaks)** construido con **FastAPI** y **Clean Architecture**. Permite conectar dinámicamente cualquier base de datos **PostgreSQL** o **MariaDB / MySQL**, detectar todas sus tablas, vectorizar selectivamente sus esquemas en **PostgreSQL + `pgvector`** y conversar en lenguaje natural mediante **RAG (Retrieval-Augmented Generation)** y **Text-to-SQL seguro** con exportación inmediata a **Excel (`.xlsx`)**.

> 🔗 **Frontend Oficial (UI Web)**: Este motor se complementa con [**DataMind Studio (`datamind-studio`)**](https://github.com/ManriqueRecinos/datamind-studio), una interfaz web interactiva en Laravel 13 con streaming SSE en tiempo real, explorador visual de tablas y previsualización DataTables.

---

## ✨ Características Principales

- 🔌 **Conector Universal Multi-Base de Datos**: Conecta en caliente múltiples bases de datos **PostgreSQL** (`asyncpg`) y **MariaDB / MySQL** (`aiomysql`) sin reiniciar el servidor.
- 🔎 **Introspección en Vivo y Vectorización Selectiva**: Explora automáticamente todas las tablas y columnas vía `INFORMATION_SCHEMA` y permite al usuario elegir exactamente qué tablas desea indexar en `pgvector` (evitando ruido y optimizando el contexto del LLM).
- 🛡️ **SQL Guardrail mediante Árbol Sintáctico (AST)**: Todas las consultas generadas por el LLM son analizadas con `sqlglot` antes de ejecutarse. Cualquier intento de mutación (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`) es bloqueado instantáneamente, permitiendo únicamente sentencias `SELECT` con inyección automática de `LIMIT 500`.
- 📚 **RAG Documental con Índice HNSW (`pgvector`)**: Ingesta manuales técnicos, políticas o documentación operativa con particionado recursivo (*overlapping chunks*) y búsqueda por similitud coseno en `< 25 ms`.
- ⚡ **Streaming en Tiempo Real (SSE)**: Emisión de eventos Server-Sent Events (`session`, `token`, `dataset`, `done`, `error`) para experiencias conversacionales fluidas.
- 📊 **Generación de Reportes Excel Bajo Demanda**: Caché temporal de resultados (`query_datasets` con TTL configurable) que permite descargar libros `.xlsx` estilizados con `openpyxl` en milisegundos sin re-ejecutar la consulta SQL ni invocar nuevamente al LLM.
- 🔒 **Privacidad Total y Enmascaramiento de Credenciales**: Impulsado por **Ollama** (`qwen2.5` + `nomic-embed-text`) corriendo en tu propio hardware. Incluye sanitización automática de contraseñas y tokens en los logs JSON.

---

## 🏛️ Arquitectura del Proyecto (Clean / Hexagonal Architecture)

```text
datamind-core/
├── app/
│   ├── api/                        # Capa de Presentación (FastAPI Routers, Schemas Pydantic V2, SSE)
│   │   └── v1/
│   │       ├── routers/
│   │       │   ├── chat.py         # POST /api/v1/chat, POST /api/v1/chat/stream
│   │       │   ├── connections.py  # CRUD de conexiones multi-BD, introspección y vectorización
│   │       │   ├── knowledge.py    # POST /api/v1/knowledge/ingest, /search, /schema-sync
│   │       │   └── export.py       # GET /api/v1/export/excel/{dataset_id}
│   │       ├── schemas/            # Contratos de entrada/salida tipados con Pydantic V2
│   │       └── streaming.py        # Formateador de eventos Server-Sent Events (SSE)
│   ├── core/                       # Configuración global (.env) y Logging JSON con enmascaramiento
│   ├── domain/                     # Entidades puras e interfaces de repositorios (Cero dependencias)
│   ├── infrastructure/             # Adaptadores externos desacoplados
│   │   ├── database/
│   │   │   ├── models.py           # Modelos SQLAlchemy 2.0 + pgvector (Vector(768) HNSW)
│   │   │   ├── postgres_adapter.py # Sesión asíncrona de PostgreSQL + pgvector
│   │   │   ├── vector_repository.py# Búsqueda semántica coseno filtrada por categoría y conexión
│   │   │   ├── dynamic_db_adapter.py# Conector dinámico para PostgreSQL y MariaDB/MySQL
│   │   │   └── mariadb_adapter.py  # Adaptador por defecto de respaldo
│   │   ├── llm/
│   │   │   ├── ollama_adapter.py   # Cliente HTTP asíncrono para Ollama (Embeddings + Chat)
│   │   │   └── sql_guardrail.py    # Validador AST multi-dialecto (mysql / postgres) con sqlglot
│   │   ├── parsers/
│   │   │   └── text_chunker.py     # Particionador recursivo de texto con solapamiento
│   │   └── export/
│   │       └── excel_generator.py  # Generador de libros Excel (.xlsx) con estilos corporativos
│   ├── use_cases/                  # Orquestadores de lógica de negocio
│   │   ├── manage_connections.py   # Test de conexión, listado de tablas y vectorización selectiva
│   │   ├── ingest_knowledge.py     # Chunking -> Embedding -> Almacenamiento en pgvector
│   │   ├── intent_classifier.py    # Clasificación (general_chat, process_qa, data_query)
│   │   ├── ask_chat.py             # Flujo híbrido RAG + Text-to-SQL + Síntesis humanizada
│   │   └── export_excel.py         # Recuperación de dataset en caché -> Stream .xlsx
│   └── main.py                     # Punto de entrada FastAPI, CORS, Lifespan y /health
├── tests/
│   ├── unit/                       # Pruebas unitarias aisladas (Guardrail, Chunker, Logging, Config)
│   ├── contract/                   # Pruebas de contrato HTTP con httpx.AsyncClient
│   └── integration/                # Pruebas extremo a extremo con pgvector y bases de datos
├── .env.example                    # Plantilla de variables de entorno
├── requirements.txt                # Dependencias fijadas de Python
└── pytest.ini                      # Configuración de suite de pruebas asíncronas
```

---

## 🛠️ Requisitos Previos

1. **Python 3.11, 3.12 o 3.13**
2. **PostgreSQL 16 o 17** con la extensión [`pgvector`](https://github.com/pgvector/pgvector) instalada (actúa como almacén vectorial y de metadatos del sistema).
3. **[Ollama](https://ollama.com/)** instalado y ejecutándose localmente (`http://127.0.0.1:11434`).
4. *(Opcional)* Cualquier base de datos **PostgreSQL**, **MariaDB** o **MySQL** que desees analizar.

---

## 🚀 Guía de Instalación Paso a Paso

### 1. Clonar el repositorio y crear el entorno virtual

```powershell
git clone https://github.com/ManriqueRecinos/datamind-core.git
cd datamind-core

# Crear entorno virtual
python -m venv .venv

# Activar en Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# O en Linux / macOS:
# source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Descargar los modelos locales en Ollama

```bash
# Modelo de embeddings (768 dimensiones, ultra rápido)
ollama pull nomic-embed-text

# Modelo generativo para Text-to-SQL y síntesis conversacional
# (Puedes usar qwen2.5:3b para CPUs o qwen2.5:7b si dispones de más RAM/GPU)
ollama pull qwen2.5:3b
```

### 3. Preparar la base de datos vectorial en PostgreSQL

Conéctate a tu instancia de PostgreSQL y crea la base de datos con la extensión `vector`:

```sql
CREATE DATABASE enterprise_rag;
\c enterprise_rag
CREATE EXTENSION IF NOT EXISTS vector;
```
*(Al iniciar, FastAPI creará automáticamente todas las tablas y el índice HNSW `idx_vector_chunks_hnsw`).*

### 4. Configurar las variables de entorno (`.env`)

Copia el archivo de ejemplo y ajusta las credenciales de tu PostgreSQL vectorial:

```powershell
copy .env.example .env
```

Variables principales en `.env`:

```ini
# Seguridad de la API (debe coincidir con FASTAPI_KEY en DataMind Studio)
API_BEARER_TOKEN=datamind_secret_token_2026

# PostgreSQL + pgvector (Almacén vectorial del sistema)
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password
POSTGRES_DB=enterprise_rag

# Ollama Local
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen2.5:3b
EMBEDDING_MODEL=nomic-embed-text

# Base de datos externa inicial opcional (también puedes agregarlas desde la UI web)
MARIADB_HOST=127.0.0.1
MARIADB_PORT=3306
MARIADB_USER=readonly_user
MARIADB_PASSWORD=secret
MARIADB_DB=mi_base_de_datos
```

### 5. Iniciar el servidor FastAPI

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Documentación Interactiva (Swagger UI)**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`
- **Health Check**: `http://127.0.0.1:8000/health`

---

## 🔌 Uso de la API y Flujo de Trabajo

### 1. Probar y Registrar una Nueva Base de Datos (PostgreSQL o MariaDB/MySQL)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/connections \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ERP Producción",
    "engine": "postgresql",
    "host": "127.0.0.1",
    "port": 5432,
    "database_name": "erp_db",
    "username": "analyst_ro",
    "password": "secret",
    "set_active": true
  }'
```

### 2. Detectar Todas las Tablas de la Base de Datos Conectada

```bash
curl http://127.0.0.1:8000/api/v1/connections/{connection_id}/tables
```
Devuelve el listado completo de tablas, cantidad de columnas, vista previa de campos y si cada tabla ya está vectorizada (`"is_vectorized": true/false`).

### 3. Vectorizar Selectivamente las Tablas Elegidas por el Usuario

```bash
curl -X POST http://127.0.0.1:8000/api/v1/connections/{connection_id}/vectorize \
  -H "Content-Type: application/json" \
  -d '{
    "tables": ["ordenes_produccion", "clientes", "inventario_bodega"]
  }'
```

### 4. Conversar con la Base de Datos (Text-to-SQL + RAG)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Muéstrame las últimas 5 órdenes de producción y su estado",
    "connection_id": "{connection_id}"
  }'
```

### 5. Descargar el Resultado en Excel (`.xlsx`)

Si la respuesta incluye `"has_tabular_data": true` y un `"dataset_id"`, puedes descargar el archivo Excel estilizado en cualquier momento:

```bash
curl -O -J http://127.0.0.1:8000/api/v1/export/excel/{dataset_id}
```

---

## 🧪 Ejecución de Pruebas Automatizadas

El proyecto cuenta con **32 pruebas automatizadas** (unitarias, de contrato y de integración extremo a extremo):

```powershell
.\.venv\Scripts\pytest.exe tests/ -v
```

---

## 🤝 Contribución Open-Source

¡Las contribuciones son bienvenidas!
1. Haz un *Fork* del repositorio.
2. Crea una rama para tu funcionalidad (`git checkout -b feat/nueva-funcionalidad`).
3. Asegúrate de que todas las pruebas pasen (`pytest tests/`).
4. Envía un *Pull Request*.

---

## 📄 Licencia

Distribuido bajo la licencia **MIT**. Libre para uso personal, académico y empresarial.
