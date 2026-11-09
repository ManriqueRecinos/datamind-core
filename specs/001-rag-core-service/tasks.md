# Lista de Tareas: Servicio de Chat IA con RAG Local, pgvector y MariaDB (001-rag-core-service)

**Entrada**: Documentos de diseño desde `specs/001-rag-core-service/` (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`).  
**Idioma**: Español  
**Estrategia**: Desarrollo incremental por fases y User Stories independientes con Clean Architecture.

---

## Formato: `[ID] [P?] [Historia] Descripción`
- **[P]**: Tarea paralelizable (archivos independientes, sin dependencias cruzadas).
- **[USx]**: Historia de usuario a la que pertenece (US1, US2, US3, US4, US5).
- Rutas de archivo exactas en cada descripción.

---

## Fase 1: Configuración Inicial (Setup e Infraestructura Base)

**Propósito**: Inicialización de la estructura de código en Python y validación de variables de entorno.

- [x] T001 Inicializar entorno virtual Python y archivo de dependencias en `requirements.txt`
- [x] T002 Crear archivo de variables de entorno `.env` con credenciales de PostgreSQL 17 (puerto 5432), MariaDB y Ollama
- [x] T003 [P] Crear la estructura de directorios de Clean Architecture: `app/api/`, `app/core/`, `app/domain/`, `app/infrastructure/`, `app/use_cases/` y `tests/`
- [x] T004 [P] Implementar módulo de configuración y lectura tipada de variables de entorno con Pydantic Settings en `app/core/config.py`
- [x] T005 [P] Configurar sistema de logging estructurado en formato JSON con correlación de trazas en `app/core/logging.py`

---

## Fase 2: Fundamentos del Sistema (Prerrequisitos Bloqueantes)

**Propósito**: Capa de base de datos, conexión asíncrona a PostgreSQL 17, soporte de `pgvector` y cliente HTTP de Ollama.

**⚠️ CRÍTICO**: Ninguna historia de usuario puede comenzar hasta que esta fase esté completada.

- [x] T006 Crear entidades de dominio independientes de frameworks (`DocumentChunk`, `ChatMessage`, `QueryDataset`, `SqlQuery`) en `app/domain/entities.py`
- [x] T007 [P] Definir contratos e interfaces abstractas del dominio (`VectorStoreInterface`, `RelationalDbInterface`, `LLMClientInterface`) en `app/domain/interfaces.py`
- [x] T008 Configurar motor asíncrono de SQLAlchemy 2.0 y sesión para PostgreSQL en `app/infrastructure/database/postgres_adapter.py`
- [x] T009 Crear modelos ORM de SQLAlchemy para tablas `knowledge_documents`, `knowledge_vector_chunks` (con `Vector(768)` e índice HNSW), `chat_sessions`, `chat_messages` y `query_datasets` en `app/infrastructure/database/models.py`
- [x] T010 [P] Implementar cliente asíncrono para Ollama (`http://127.0.0.1:11434`) con soporte para embeddings (`nomic-embed-text`) y generación/streaming (`qwen2.5:3b`) en `app/infrastructure/llm/ollama_adapter.py`
- [x] T011 Configurar punto de entrada de FastAPI y endpoint de salud `GET /health` en `app/main.py`
- [x] T012 [P] Escribir prueba de integración para conexión a PostgreSQL 17 y activación de pgvector en `tests/integration/test_postgres_adapter.py`
- [x] T013 [P] Escribir prueba unitaria para el cliente de Ollama (con mock de httpx) en `tests/unit/test_ollama_adapter.py`

**Punto de Control**: La infraestructura base y los modelos de persistencia están listos y verificados.

---

## Fase 3: User Story 1 - Ingesta de Procesos Corporativos y Vectorización (Prioridad: P1) 🎯 MVP

**Objetivo**: Permitir la ingesta de manuales de procesos de la empresa, particionarlos con solapamiento, calcular embeddings con `nomic-embed-text` y almacenarlos en `pgvector`.

**Prueba Independiente**: Llamar a `POST /api/v1/knowledge/ingest` con un texto de prueba y verificar que se creen los fragmentos en `knowledge_vector_chunks` con vectores de 768 dimensiones.

- [x] T016 [P] [US1] Implementar algoritmo de particionado de texto recursivo con solapamiento (*overlap*) en `app/infrastructure/parsers/text_chunker.py`
- [x] T017 [US1] Implementar repositorio vectorial para inserción y búsqueda por similitud coseno en `app/infrastructure/database/vector_repository.py`
- [x] T018 [US1] Implementar caso de uso `IngestKnowledgeUseCase` en `app/use_cases/ingest_knowledge.py`
- [x] T019 [US1] Crear esquemas Pydantic V2 (`IngestRequest`, `IngestResponse`) en `app/api/v1/schemas/knowledge.py`
- [x] T020 [US1] Implementar router HTTP para ingesta de conocimiento en `app/api/v1/routers/knowledge.py`
- [x] T021 [US1] Registrar router de conocimiento en `app/api/v1/api.py`

**Punto de Control**: Se pueden ingestar documentos y manuales de procesos en `pgvector` y consultarlos semánticamente.

---

## Fase 4: User Story 4 - Guardrails de Seguridad y Conexión a MariaDB (Prioridad: P1)

**Objetivo**: Garantizar conexión segura de solo lectura a MariaDB externa y validar mediante AST (`sqlglot`) que toda consulta sea exclusivamente `SELECT` y con `LIMIT 500`.

**Prueba Independiente**: Ejecutar `sqlglot` contra consultas maliciosas (`DROP`, `DELETE`, `UPDATE`) y verificar que sean rechazadas; ejecutar una consulta válida contra MariaDB y verificar retorno de registros.

- [x] T024 [P] [US4] Implementar validador de árbol sintáctico (AST) con `sqlglot` para rechazar mutaciones e inyectar `LIMIT 500` en `app/infrastructure/llm/sql_guardrail.py`
- [x] T025 [US4] Implementar adaptador asíncrono de solo lectura para MariaDB con timeout de 5 segundos en `app/infrastructure/database/mariadb_adapter.py`
- [x] T026 [US4] Implementar caso de uso de sincronización del diccionario de datos de MariaDB (`SyncSchemaUseCase`) hacia `pgvector` en `app/use_cases/sync_schema.py`
- [x] T027 [US4] Crear endpoint `POST /api/v1/knowledge/schema-sync` en `app/api/v1/routers/knowledge.py`

**Punto de Control**: La conexión a MariaDB está blindada y los esquemas de las tablas están vectorizados.

---

## Fase 5: User Story 2 - Chat Conversacional con Text-to-SQL y Streaming SSE (Prioridad: P1)

**Objetivo**: Procesar preguntas en lenguaje natural del usuario, recuperar contexto de `pgvector`, generar consultas SQL seguras para MariaDB cuando corresponda, sintetizar respuestas humanizadas en español y emitirlas por streaming (SSE).

**Prueba Independiente**: Enviar una pregunta vía `POST /api/v1/chat/stream` y verificar que se reciba el flujo de eventos SSE (`token`, `dataset`, `done`).

- [x] T030 [P] [US2] Crear esquemas Pydantic V2 para solicitudes y respuestas del chat (`ChatRequest`, `ChatResponse`, `StreamEvent`) en `app/api/v1/schemas/chat.py`
- [x] T031 [US2] Implementar clasificador de intención del usuario (proceso conceptual vs. consulta analítica SQL) en `app/use_cases/intent_classifier.py`
- [x] T032 [US2] Implementar caso de uso principal `AskChatUseCase` en `app/use_cases/ask_chat.py` (orquesta pgvector -> Text-to-SQL -> MariaDB -> síntesis en español)
- [x] T033 [US2] Implementar generador asíncrono de eventos SSE (`session`, `token`, `dataset`, `done`, `error`) en `app/api/v1/streaming.py`
- [x] T034 [US2] Implementar endpoints `POST /api/v1/chat` (síncrono) y `POST /api/v1/chat/stream` (SSE) en `app/api/v1/routers/chat.py`
- [x] T035 [US2] Registrar router de chat en `app/api/v1/api.py`

**Punto de Control**: El chat responde con narrativa cálida y streaming, consultando MariaDB y vectorizando sesiones.

---

## Fase 6: User Story 3 - Generación Manual de Reportes en Excel (.xlsx) (Prioridad: P1)

**Objetivo**: Almacenar en caché temporal los resultados tabulares devueltos por MariaDB bajo un `dataset_id` y permitir al usuario descargar bajo demanda un archivo `.xlsx` estilizado con `openpyxl`.

**Prueba Independiente**: Solicitar la descarga a `GET /api/v1/export/excel/{dataset_id}` y verificar que el archivo generado sea un `.xlsx` válido con cabeceras formateadas y tipos de datos correctos.

- [x] T038 [P] [US3] Implementar generador de libros Excel con estilos corporativos (encabezado azul marino, negrita, auto-filtro, ajuste de columnas y formatos numéricos) en `app/infrastructure/export/excel_generator.py`
- [x] T039 [US3] Implementar repositorio de almacenamiento temporal de datasets (`QueryDatasetRepository`) con TTL de 2 horas en `app/infrastructure/database/dataset_repository.py`
- [x] T040 [US3] Implementar caso de uso `ExportExcelUseCase` en `app/use_cases/export_excel.py`
- [x] T041 [US3] Implementar endpoint de descarga de archivos `GET /api/v1/export/excel/{dataset_id}` con cabeceras `Content-Disposition` en `app/api/v1/routers/export.py`
- [x] T042 [US3] Registrar router de exportación en `app/api/v1/api.py`

**Punto de Control**: El botón de Excel puede descargar al vuelo el reporte estilizado en milisegundos sin re-consultar a la IA ni a MariaDB.

---

## Fase 7: User Story 5 - Frontend Web en DataMind Studio (Laravel 13) (Prioridad: P2)

**Objetivo**: Construir en `datamind-studio` la interfaz de chat en tiempo real consumiendo los eventos SSE de FastAPI, renderizando la vista previa de datos con el componente nativo `<x-data-table>` y el botón de descarga de Excel.

- [x] T043 [US5] Configurar cliente HTTP y variables de conexión a FastAPI en `config/services.php` y `.env` de Laravel
- [x] T044 [P] [US5] Crear servicio cliente de backend (`FastApiClient.php`) en `app/Services/`
- [x] T045 [P] [US5] Crear controlador de Chat (`ChatController.php`) en `app/Http/Controllers/`
- [x] T046 [US5] Crear script en JavaScript nativo local (`public/js/chat_stream.js`) para consumir el flujo SSE de `/api/v1/chat/stream` usando Axios/Fetch local
- [x] T047 [US5] Diseñar la vista Blade principal del Chat (`resources/views/chat/index.blade.php`) usando Tailwind CSS v4, Font Awesome y SweetAlert2 locales
- [x] T048 [US5] Integrar el componente `<x-data-table>` para mostrar la vista previa interactiva de registros de MariaDB dentro del mensaje del asistente
- [x] T049 [US5] Implementar botón dinámico de descarga `[ 📊 Generar Excel (.xlsx) ]` que invoca el endpoint de exportación y emite alerta Toastr de confirmación
- [x] T050 [US5] Incrementar la versión del commit en `README.md` y `AGENTS.md` siguiendo la regla decimal (`1.0.0` ➔ `1.0.1`)

---

## Fase 8: Pulido Final, Seguridad y Validación Extremo a Extremo

- [x] T051 [P] Ejecutar suite completa de pruebas unitarias y de contrato con `pytest` en Python
- [x] T052 Ejecutar los 4 escenarios de validación del documento `specs/001-rag-core-service/quickstart.md`
- [x] T053 [P] Documentar guía de despliegue y puesta en marcha final en `README.md`
- [x] T054 Realizar auditoría de seguridad para confirmar que no se expongan credenciales en logs ni en respuestas al usuario

---

## Fase 9: Sistema de Diseño Corporativo y Paleta Global DataMind (`#0476D9`, `#0468BF`, `#4B89BF`, `#99D0F2`, `#F2F2F2`)

**Objetivo**: Centralizar los 5 colores de la identidad visual en `globales.css` y `@theme` de Tailwind CSS v4, y optimizar los estilos de las vistas Blade, componente `<x-data-table>`, cliente de streaming JS y reportes Excel `.xlsx`.

- [x] T055 [P] Definir variables CSS (`:root`), variantes semánticas (RGB/alpha) y utilidades globales en `public/css/global_styles/globales.css`
- [x] T056 [P] Registrar tokens de tema de Tailwind CSS v4 (`@theme`) y fuente `@source` para JS en `resources/css/app.css`
- [x] T057 Actualizar vista principal del asistente `resources/views/chat/index.blade.php` usando la nueva paleta corporativa y clases globales
- [x] T058 Actualizar cliente SSE `public/js/chat_stream.js` (burbujas de usuario `#0476D9`, avatar AI `#0468BF`->`#4B89BF`, tablas preview y SweetAlert2)
- [x] T059 [P] Optimizar estilos del componente `<x-data-table>` en `resources/views/components/data-table.blade.php` y vista `welcome.blade.php`
- [x] T060 [P] Homologar la paleta de colores de reportes Excel (`#0468BF`, `#F2F2F2`, `#99D0F2`) en `app/infrastructure/export/excel_generator.py` y sus pruebas
- [x] T061 Compilar assets con Vite (`npm run build`), incrementar versión a `1.0.2` en `README.md` y `AGENTS.md` de Laravel, y ejecutar suites de pruebas (`pytest` y `php artisan test`)

---

## Fase 10: Gestor Dinámico Multi-Base de Datos y Vectorización Selectiva (`DataMind Universal`)

**Objetivo**: Permitir conectar cualquier base de datos PostgreSQL o MariaDB/MySQL mediante credenciales, probar la conexión, explorar todas las tablas detectadas y vectorizar selectivamente en `pgvector` las tablas elegidas por el usuario para que el Chat converse sobre esa base de datos.

- [x] T062 Crear modelo ORM `DatabaseConnectionModel` en `app/infrastructure/database/models.py`
- [x] T063 [P] Implementar adaptador universal `DynamicDBAdapter` (soporte `postgresql` con `asyncpg` y `mariadb`/`mysql` con `aiomysql`) en `app/infrastructure/database/dynamic_db_adapter.py`
- [x] T064 [P] Actualizar `SQLGuardrail` (`app/infrastructure/llm/sql_guardrail.py`) y `VectorRepository` (`app/infrastructure/database/vector_repository.py`) para soportar múltiples dialectos SQL (`mysql`, `postgres`) y filtrado e idempotencia por `connection_id`
- [x] T065 Implementar caso de uso `ManageConnectionsUseCase` (probar conexión, guardar, activar, listar tablas detectadas y vectorizar tablas seleccionadas) en `app/use_cases/manage_connections.py`
- [x] T066 Actualizar `AskChatUseCase` (`app/use_cases/ask_chat.py`) y esquemas/routers de chat para usar la conexión activa o el `connection_id` seleccionado
- [x] T067 Crear esquemas Pydantic (`app/api/v1/schemas/connections.py`) y router REST (`app/api/v1/routers/connections.py`) y registrarlo en `app/api/v1/api.py`
- [x] T068 Ampliar `FastApiClient.php`, crear `DatabaseConnectionController.php` y registrar rutas `/connections` en `datamind-studio`
- [x] T069 Crear vista interactiva `resources/views/connections/index.blade.php` y script `public/js/connections_manager.js` (formulario de credenciales, test de conexión, explorador de tablas con checkboxes y vectorización selectiva)
- [x] T070 Integrar selector de base de datos activa en `resources/views/chat/index.blade.php` y `public/js/chat_stream.js`
- [x] T071 Escribir pruebas automatizadas para conexiones dinámicas y vectorización selectiva en Python (`pytest`) y Laravel (`php artisan test`), recompilar assets y subir commits a GitHub
