# 📌 REQUERIMIENTOS Y STACK TECNOLÓGICO DETALLADO (REQUERIMENTS.MD)

> **Proyecto**: AI Chatbot Service con RAG Local, PostgreSQL (pgvector) y Text-to-SQL sobre MariaDB  
> **Fecha**: Noviembre 2026  
> **Versión**: 1.0.0  
> **Ambiente**: Desarrollo Local / Producción Híbrida  

---

## 1. Introducción y Alcance

Este documento especifica de forma exhaustiva los **Requerimientos Funcionales (RF)**, **Requerimientos No Funcionales (RNF)** y la **Matriz Detallada del Stack Tecnológico** (herramientas, servicios, bibliotecas, drivers y parámetros de configuración) requeridos para el desarrollo, despliegue y mantenimiento del sistema.

El proyecto articula un microservicio de inteligencia artificial en **Python (FastAPI)** que opera con modelos locales (**Ollama**) y una base de datos vectorial (**PostgreSQL 17 + pgvector**), consumido por una aplicación web empresarial en **Laravel 11** para responder preguntas sobre procesos y extraer datos en tiempo real de una base externa en **MariaDB**, con exportación manual a **Excel (.xlsx)**.

---

## 2. Requerimientos Funcionales (RF)

### RF-01: Ingesta y Vectorización de Documentación de Procesos (RAG)
- **RF-01.1**: El sistema debe proveer un endpoint para recibir documentos de texto (manuales de procesos, políticas internas, flujos de trabajo) con metadatos asociados (departamento, categoría, autor, versión).
- **RF-01.2**: El sistema debe dividir el texto en fragmentos (*chunks*) deterministas de longitud configurable (típicamente 500-800 caracteres) con solapamiento (*overlap* de 50-100 caracteres) para mantener la continuidad contextual.
- **RF-01.3**: Cada fragmento debe ser vectorizado localmente mediante el modelo de embeddings `nomic-embed-text` (vector de 768 dimensiones).
- **RF-01.4**: Los vectores y sus metadatos deben almacenarse en PostgreSQL en una tabla con extensión `pgvector` e índice **HNSW**.

### RF-02: Mapeo y Sincronización del Esquema de MariaDB
- **RF-02.1**: El sistema debe permitir la sincronización e indexación semántica del diccionario de datos de MariaDB (nombres de tablas, tipos de columnas, claves foráneas, comentarios y descripciones operativas).
- **RF-02.2**: Ante una pregunta del usuario, el sistema debe recuperar de forma semántica únicamente las tablas relevantes (Top 3-5), evitando inyectar esquemas masivos completos en la ventana de contexto del LLM.

### RF-03: Chat Conversacional con Respuestas Humanizadas y Streaming
- **RF-03.1**: El usuario debe interactuar a través de una interfaz de chat web moderna.
- **RF-03.2**: Las respuestas del asistente deben ser redactadas en un tono profesional, cálido y humanizado en español, organizadas mediante formato Markdown (encabezados, listas de puntos, tablas comparativas y cifras destacadas).
- **RF-03.3**: La generación debe transmitirse en tiempo real al navegador mediante **Server-Sent Events (SSE)**, logrando el efecto de escritura fluida (mecanografía).

### RF-04: Consultas en Lenguaje Natural a MariaDB (Text-to-SQL Seguro)
- **RF-04.1**: El sistema debe clasificar si la intención del usuario es procedural (pregunta de proceso) o analítica/cuantitativa (datos numéricos o registros de MariaDB).
- **RF-04.2**: Para intenciones analíticas, el LLM local (`qwen2.5:7b`) debe traducir la pregunta a una consulta SQL compatible con dialecto MySQL/MariaDB.
- **RF-04.3**: La consulta generada debe ser ejecutada en MariaDB en modo lectura y sus resultados crudos deben ser interpretados por la IA para redactar la explicación humanizada.

### RF-05: Generación Manual y Bajo Demanda de Reportes Excel ("Botón Generar Excel")
- **RF-05.1**: Si la respuesta del chat involucra registros o datos tabulares de MariaDB, los resultados crudos deben guardarse en una memoria temporal (caché de datasets) con un identificador único (`dataset_id`) y una caducidad automática (TTL de 2 horas).
- **RF-05.2**: La interfaz de chat debe mostrar de manera **condicional** un botón dedicado al pie de la respuesta:  
  `[ 📊 Generar reporte Excel (.xlsx) ]`.
- **RF-05.3**: Si la pregunta fue puramente conceptual o conversacional (sin datos tabulares), el botón **no** debe aparecer.
- **RF-05.4**: Al presionar el botón, el sistema debe generar al vuelo y descargar en el navegador un archivo binario `.xlsx` estilizado con `openpyxl`:
  - Membrete superior con título del proceso, fecha y hora de emisión.
  - Fila de cabecera con relleno de color corporativo (azul marino), texto en blanco y negrita.
  - Filtros automáticos (*AutoFilter*) en todas las columnas.
  - Ancho de columnas calculado automáticamente según la longitud del texto.
  - Tipado de celdas formateado (fechas `YYYY-MM-DD`, moneda `\$#,##0.00`, números enteros o decimales con dos dígitos).
- **RF-05.5**: La generación de Excel no debe volver a consultar a la IA ni a MariaDB; debe nutrirse directamente del dataset en caché.

### RF-06: Gestión de Sesiones y Trazabilidad
- **RF-06.1**: El sistema debe mantener sesiones de chat independientes para que el usuario pueda tener conversaciones con contexto multi-turno.
- **RF-06.2**: Cada interacción debe registrar latencia, tokens aproximados y la consulta SQL ejecutada (para propósitos de auditoría interna).

---

## 3. Requerimientos No Funcionales (RNF)

### RNF-01: Rendimiento y Eficiencia de Hardware
- **RNF-01.1**: El consumo de memoria RAM de los modelos de IA en reposo e inferencia no debe exceder los **6.0 GB**, garantizando que queden más de 10 GB de RAM libres para el sistema operativo Windows, PostgreSQL, MariaDB y los servicios web en una máquina de 16 GB.
- **RNF-01.2**: El tiempo hasta el primer token en streaming (*Time-To-First-Token* o TTFT) no debe superar los **1.5 segundos** en el procesador Intel Core i5-14500T.
- **RNF-01.3**: La búsqueda de similitud vectorial en `pgvector` mediante índice HNSW debe resolver en menos de **25 milisegundos**.
- **RNF-01.4**: La generación del archivo Excel bajo demanda para consultas de hasta 500 filas debe demorar menos de **400 milisegundos**.

### RNF-02: Seguridad y Guardrails SQL para MariaDB
- **RNF-02.1**: **Privilegios Mínimos**: Las credenciales de conexión asignadas al servicio en MariaDB deben tener estrictamente permisos de `SELECT` sobre las tablas o vistas designadas.
- **RNF-02.2**: **Validación AST**: Toda sentencia SQL generada por el LLM debe ser analizada a nivel sintáctico mediante `sqlglot` antes de ser enviada al motor de base de datos. Se rechazará cualquier consulta que contenga operaciones de mutación (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `RENAME`, `GRANT`).
- **RNF-02.3**: **Límite de Registros Forzado**: Toda consulta debe tener forzada una cláusula `LIMIT 500` (si la consulta no la tiene o si el valor generado supera 500, se sobreescribirá a 500).
- **RNF-02.4**: **Timeout de Ejecución**: Las consultas a MariaDB se abortarán automáticamente si tardan más de **5.0 segundos**, evitando bloqueos o lecturas de tablas completas (*full table scans*).

### RNF-03: Arquitectura, Mantenibilidad y Clean Code
- **RNF-03.1**: El backend en Python debe respetar **Clean Architecture / Arquitectura Hexagonal**, organizando el código en 4 capas estrictas: `domain` (entidades y contratos puros), `use_cases` (lógica de negocio), `infrastructure` (adaptadores externos: Ollama, PostgreSQL, MariaDB, openpyxl) y `api` (controladores FastAPI).
- **RNF-03.2**: La lógica de dominio no debe depender de FastAPI, SQLAlchemy ni Ollama; debe interactuar a través de interfaces abstractas (`typing.Protocol` o `abc.ABC`).
- **RNF-03.3**: Tipado estricto al 100% mediante **Pydantic V2** en todos los modelos de entrada, salida y configuración.

### RNF-04: Concurrencia y Asincronismo de Extremo a Extremo
- **RNF-04.1**: Todas las rutas y operaciones I/O en FastAPI deben declararse como `async def`.
- **RNF-04.2**: Las conexiones de red a PostgreSQL (`asyncpg`), MariaDB (`aiomysql`) y Ollama (`httpx.AsyncClient`) deben ser asíncronas no bloqueantes para no congelar el bucle de eventos de Uvicorn.

---

## 4. Matriz Exhaustiva del Stack Tecnológico

### 4.1 Entorno de Hardware Base (Detectado)
- **CPU**: Intel Core i5-14500T (14 núcleos: 6 Performance Cores + 8 Efficient Cores, 20 hilos lógicos, arquitectura Raptor Lake).
- **RAM**: 16 GB DDR4/DDR5.
- **GPU**: Intel UHD Graphics 770 Integrada (aceleración por CPU AVX2 para modelos locales).
- **Almacenamiento**: SSD NVMe.
- **Sistema Operativo**: Windows 11 Pro / Home.

---

### 4.2 Motor de Inteligencia Artificial Local (Inferencia & Embeddings)

| Componente | Software / Modelo | Versión / Variante | Rol y Justificación |
| :--- | :--- | :--- | :--- |
| **Motor Servidor** | **Ollama** | Última versión Windows | Motor de ejecución local de modelos de código abierto basado en `llama.cpp`. Ofrece API REST local en puerto `11434` y excelente optimización de CPU AVX2. |
| **Modelo LLM de Inferencia** | **`qwen2.5:3b-instruct`** | Cuantización `Q4_K_M` (~1.9 GB RAM) | Modelo ultraliviano de alta velocidad (30-45 tokens/s en CPU), excelente comprensión del español y capacidad para generar consultas SQL estructuradas sin saturar memoria. |
| **Modelo LLM Opcional** | **`qwen2.5:7b-instruct`** | Cuantización `Q4_K_M` (~4.7 GB RAM) | Variante de mayor capacidad si se requiere escalar razonamientos más complejos. |
| **Modelo de Embeddings** | **`nomic-embed-text`** | 768 dimensiones (~275 MB RAM) | Modelo local de embeddings de alta resolución con ventana de 8,192 tokens. Convierte textos de procesos en vectores de coma flotante. |

---

### 4.3 Bases de Datos y Almacenamiento

| Capa | Motor de Base de Datos | Versión / Extensiones | Propósito y Configuración |
| :--- | :--- | :--- | :--- |
| **Base Vectorial & Memoria** | **PostgreSQL** | 17.x con extensión **`pgvector`** | Almacena fragmentos de manuales de procesos y diccionario de tablas en columnas `vector(768)`. Indexado con **HNSW** (`vector_cosine_ops`) y búsqueda híbrida con `tsvector` en español. |
| **Base Operativa Externa** | **MariaDB** | 10.4+ / 11.x (XAMPP o Remota) | Base de datos corporativa que contiene los registros de procesos reales de la empresa. Conexión de solo lectura. |

---

### 4.4 Backend / Microservicio de IA (Python)

| Biblioteca / Paquete | Versión Recomendada | Propósito en el Proyecto |
| :--- | :--- | :--- |
| **`python`** | 3.11.x – 3.13.x | Entorno de ejecución principal de alto rendimiento. |
| **`fastapi`** | >= 0.115.0 | Framework web asíncrono para construir la API REST y los endpoints SSE. |
| **`uvicorn[standard]`** | >= 0.32.0 | Servidor ASGI asíncrono de alto rendimiento con soporte para WebSockets y SSE. |
| **`pydantic`** | >= 2.9.0 | Validación de datos en tiempo de ejecución, esquemas de entrada y contratos estrictos. |
| **`pydantic-settings`** | >= 2.6.0 | Gestión centralizada de variables de entorno desde archivos `.env`. |
| **`sqlalchemy`** | >= 2.0.36 | ORM moderno con soporte nativo para consultas asíncronas (`AsyncSession`). |
| **`asyncpg`** | >= 0.30.0 | Driver asíncrono de máximo rendimiento para PostgreSQL. |
| **`pgvector`** | >= 0.3.6 | Biblioteca oficial de integración de pgvector con SQLAlchemy y asyncpg. |
| **`aiomysql`** | >= 0.2.0 | Driver asíncrono no bloqueante para consultas a MariaDB/MySQL. |
| **`sqlglot`** | >= 25.26.0 | Parser y transpilador de SQL para análisis del árbol sintáctico (AST) y guardrails de seguridad. |
| **`openpyxl`** | >= 3.1.5 | Generación programática de hojas de cálculo de Excel (`.xlsx`) con estilos profesionales. |
| **`httpx`** | >= 0.27.2 | Cliente HTTP asíncrono para comunicarse con la API de Ollama y recibir tokens por streaming. |
| **`pytest`** | >= 8.3.0 | Framework de pruebas unitarias y funcionales. |
| **`pytest-asyncio`** | >= 0.24.0 | Extensión para ejecutar pruebas asíncronas de corrutinas en pytest. |
| **`pytest-mock`** | >= 3.14.0 | Creación de mocks y espías para aislar Ollama y las bases de datos en los tests. |

---

### 4.5 Frontend / Aplicación Web de Usuario (DataMind Studio - Laravel 13)

El frontend se desarrolla sobre la arquitectura local de **DataMind Studio**:
- **Repositorio Base Git**: `https://github.com/ManriqueRecinos/datamind-studio.git`
- **Directorio Local en el Proyecto**: `datamind-studio/`
- **Nombre**: DataMind Studio - Laravel 13 (Versión `1.0.0`)
- **Filosofía de Arquitectura**: **Full Local (Offline Ready / Cero CDNs)** — Todas las librerías CSS, JavaScript, iconos y fuentes están empaquetadas localmente, permitiendo operar sin conexión a internet ni dependencias externas.

#### Matriz de Componentes del Frontend DataMind Studio:

| Tecnología / Componente | Versión / Estado | Rol en el Proyecto |
| :--- | :--- | :--- |
| **Repositorio Base** | `datamind-studio.git` | Interfaz web oficial de DataMind Studio. |
| **Laravel Framework** | `^13.36` (PHP 8.3+ / 8.5+) | Núcleo MVC para autenticación, control de accesos, gestión de sesiones y comunicación API. |
| **Tailwind CSS** | `^4.0` (Vite 8) | Motor de estilos moderno y reactivo para la interfaz del chat y tarjetas. |
| **jQuery** | `3.6.0` (Local) | Manipulación DOM y soporte para plugins de tablas. |
| **DataTables** | `1.13` (Local) | Tablas dinámicas interactivas con paginación, ordenamiento y scroll interno. |
| **SweetAlert2** | `v11.x` (Local) | Diálogos modales y confirmaciones visuales para descargas y acciones críticas. |
| **Toastr** | `v2.x` (Local) | Notificaciones emergentes (ej. "Descarga de Excel iniciada", "Error de conexión"). |
| **Font Awesome** | `v7.x` (Local `webfonts/`) | Iconografía vectorial (iconos de chat, Excel, base de datos, engranajes). |
| **Axios** | `Minified` (Local) | Cliente HTTP asíncrono para llamadas a la API de FastAPI y consumo de streams. |
| **Select2** | `v4.x` (Local) | Selectores con búsqueda para filtrar procesos, departamentos o categorías. |
| **Chart.js** | `UMD` (Local) | Gráficas analíticas embebidas en el chat cuando la consulta incluya métricas. |
| **Pusher JS** | `Minified` (Local) | Soporte para WebSockets y eventos en vivo. |

#### Componente Nativo DataTables (`<x-data-table>`)
La plantilla incluye el componente Blade `<x-data-table>` con estilos Tailwind CSS, el cual se utilizará para renderizar vistas previas interactivas de los datos devueltos por MariaDB/PostgreSQL en el chat:
- Selector de longitud: `5` (por defecto), `10`, `20`, `50`, `100` y `Todos`.
- Scroll vertical suave (`scrollY="240px"`) con altura estática.
- Botón superior de exportación y barra inferior de acciones.

#### Regla Estricta de Versionado Semántico para Commits (DataMind Studio)
El versionado del proyecto en este repositorio sigue una progresión numérica secuencial decimal de 3 dígitos (`MAJOR.MINOR.PATCH`):
- **Versión Inicial**: `1.0.0`
- **Por cada commit**: Se incrementa en `0.0.1` (`1.0.1`, `1.0.2`, ..., `1.0.9`).
- **Al llegar a `x.x.9`**: El siguiente commit pasa a la siguiente décima (`1.0.9` ➔ `1.1.0`).
- **Ciclo continuo**: `1.1.0` ➔ `1.1.1` ➔ ... ➔ `1.1.9` ➔ `1.2.0`, etc.

---

## 5. Especificación de Dependencias de Python (`requirements.txt`)

El archivo de dependencias exacto para el entorno virtual de Python es el siguiente:

```text
# Web Framework & ASGI
fastapi>=0.115.0
uvicorn[standard]>=0.32.0

# Type Validation & Settings
pydantic>=2.9.0
pydantic-settings>=2.6.0

# Database & Vector Engine
sqlalchemy>=2.0.36
asyncpg>=0.30.0
pgvector>=0.3.6
aiomysql>=0.2.0

# SQL Guardrails & AST Security
sqlglot>=25.26.0

# Document & Spreadsheet Export
openpyxl>=3.1.5

# HTTP Client (Async Ollama communication)
httpx>=0.27.2

# Testing
pytest>=8.3.0
pytest-asyncio>=0.24.0
pytest-mock>=3.14.0
```

---

## 6. Variables de Entorno y Configuración (`.env`)

El archivo `.env` del microservicio Python centraliza las conexiones y modelos:

```ini
# Configuración de Entorno
APP_ENV=development
APP_PORT=8000
API_KEY=secreto_bearer_token_para_comunicacion_con_laravel

# Motor Ollama Local
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen2.5:3b
EMBEDDING_MODEL=nomic-embed-text
OLLAMA_TIMEOUT_SECONDS=60.0

# Base de Datos PostgreSQL 17 + pgvector (Memoria y Vectores)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_contraseña_postgres
POSTGRES_DB=enterprise_rag
POSTGRES_POOL_SIZE=10

# Base de Datos MariaDB Externa (Solo Lectura - Procesos)
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=readonly_ai_user
MARIADB_PASSWORD=contraseña_segura_lectura
MARIADB_DB=empresa_procesos
MARIADB_MAX_ROWS=500
MARIADB_TIMEOUT_SECONDS=5.0

# Parámetros de Ingesta RAG
CHUNK_SIZE=600
CHUNK_OVERLAP=80
DATASET_CACHE_TTL_HOURS=2
```

---

## 7. Verificación de Cumplimiento de Objetivos

| Requerimiento Solicitado por el Usuario | Estado en este Diseño | Mecanismo de Implementación |
| :--- | :---: | :--- |
| **Aprender mediante IA local** | ✅ Cumplido | Ollama con `qwen2.5:7b` y `nomic-embed-text` ejecutándose en la CPU del sistema. |
| **PostgreSQL con pgvector para vectorizar** | ✅ Cumplido | PostgreSQL 17 local con índice HNSW y columnas `vector(768)` para manuales y esquemas. |
| **Chat que responda sobre base externa MariaDB** | ✅ Cumplido | Flujo Text-to-SQL asíncrono con `aiomysql`, recuperación previa de esquemas en pgvector y guardrail AST. |
| **Stack en Python (API) y Laravel (Consumo)** | ✅ Cumplido | FastAPI (microservicio de IA) + DataMind Studio (Laravel 13, Tailwind CSS v4, DataTables `<x-data-table>`, SweetAlert2, FontAwesome, Full Local / Cero CDNs). |
| **Respuestas humanizadas** | ✅ Cumplido | Prompt estructurado que sintetiza los datos en prosa natural y explicativa en español. |
| **Botón de Generar Excel manual tras la respuesta** | ✅ Cumplido | Los datos se guardan con `dataset_id`. Al final del mensaje aparece el botón condicional que descarga el `.xlsx` estilizado con `openpyxl`. |
| **Buenas prácticas, mantenibilidad y calidad** | ✅ Cumplido | Clean Architecture, Pydantic V2, AST SQL parser con `sqlglot`, concurrencia asíncrona y pruebas con Pytest. |

---

> 📄 **Documentos Relacionados**:
> - [**`PLAN.md` (Plan Maestro de Arquitectura y Flujos)**](file:///d:/Python/python-db/PLAN.md)
> - [**`specs/001-rag-core-service/spec.md` (Especificación SpecKit)**](file:///d:/Python/python-db/specs/001-rag-core-service/spec.md)
> - [**`specs/001-rag-core-service/data-model.md` (Esquemas de Base de Datos)**](file:///d:/Python/python-db/specs/001-rag-core-service/data-model.md)
> - [**`specs/001-rag-core-service/contracts/chat-api.yaml` (Contratos OpenAPI)**](file:///d:/Python/python-db/specs/001-rag-core-service/contracts/chat-api.yaml)