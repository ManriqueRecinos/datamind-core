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

---

## Fase 11: Renderizado de Vista Previa Markdown en Tiempo Real (IA y Usuario) (`DataMind Rich Markdown`)

**Objetivo**: Renderizar tanto las respuestas en streaming del asistente IA como las preguntas enviadas por el usuario en formato **Vista Previa de Markdown** (encabezados, negritas, cursivas, listas, citas, tablas Markdown y bloques de código con botón de copiado), manteniendo la arquitectura 100% local (Cero CDNs) y protección contra XSS.

- [x] T072 [P] Agregar estilos tipográficos `.markdown-body`, `.markdown-ai` y `.markdown-user` (encabezados, listas, tablas, bloques de código y citas) en `public/css/global_styles/globales.css` y `resources/css/global_styles/globales.css`
- [x] T073 [P] Actualizar el campo de entrada en `resources/views/chat/index.blade.php` a un `<textarea>` auto-ajustable con soporte multilínea (`Enter` para enviar, `Shift+Enter` para salto de línea) e indicador de soporte Markdown
- [x] T074 Implementar el motor local seguro de parseo y vista previa Markdown (`renderMarkdownPreview`) con soporte de streaming progresivo y botón de copiado de código en `public/js/chat_stream.js` (aplicado tanto a `appendUserMessage` como a los eventos SSE `token`)
- [x] T075 Optimizar el prompt de síntesis en `app/use_cases/ask_chat.py` para estructurar las respuestas con formato Markdown limpio y legible
- [x] T076 Compilar assets con Vite (`npm run build`), ejecutar suites de pruebas (`pytest` y `php artisan test`), e incrementar la versión a `1.0.4` en `README.md` y `AGENTS.md`

---

## Fase 12: Autenticación de Usuarios e Historial de Conversaciones por Usuario (`DataMind Auth & Chat History`)

**Objetivo**: Implementar un sistema de Login y Registro de usuarios en `datamind-studio` y persistir/recuperar en `datamind-core` el historial completo de conversaciones (`chat_sessions` y `chat_messages`) aislado por cada usuario autenticado (`user_id`), permitiendo cambiar entre conversaciones pasadas, restaurar sus mensajes con Vista Previa Markdown y tablas DataTables, o eliminarlas.

- [x] T077 Actualizar `AskChatUseCase` (`app/use_cases/ask_chat.py`) para guardar tanto el mensaje del usuario (`role="user"`) como la respuesta del asistente (`role="assistant"`), actualizar `updated_at` de la sesión e inyectar memoria conversacional de los últimos mensajes de la sesión
- [x] T078 [P] Crear esquemas Pydantic (`ChatSessionSummary`, `ChatMessageItem`, `ChatSessionDetailResponse`) en `app/api/v1/schemas/chat.py` y caso de uso/endpoints `GET /api/v1/chat/sessions`, `GET /api/v1/chat/sessions/{session_id}` y `DELETE /api/v1/chat/sessions/{session_id}` filtrados por `user_id` en `app/api/v1/routers/chat.py`
- [x] T079 [P] Crear `AuthController.php` (Login, Registro y Logout), vista `resources/views/auth/login.blade.php` con la paleta DataMind, y usuario inicial en `database/seeders/DatabaseSeeder.php` en `datamind-studio`
- [x] T080 Ampliar `FastApiClient.php`, `ChatController.php` y `routes/web.php` (proteger rutas con middleware `auth`, pasar `Auth::id()` como `user_id` y exponer endpoints locales `/chat/sessions`, `/chat/sessions/{sessionId}`)
- [x] T081 Actualizar `resources/views/chat/index.blade.php` y `public/js/chat_stream.js` para mostrar el perfil del usuario autenticado, botón de cerrar sesión, panel lateral **"Mis Conversaciones"** con carga dinámica de historial (renderizado en Vista Previa Markdown + tablas interactivas) y eliminación de sesiones
- [x] T082 Ejecutar migraciones/seeders en SQLite local (`php artisan migrate --seed`), escribir pruebas de autenticación e historial en `pytest` y `php artisan test`, compilar Vite (`npm run build`) e incrementar versión a `1.0.5`

---

## Fase 13: Generación Interactiva de Gráficos Detallados y Selector Visual de Campos (`DataMind Visual Analytics`)

**Objetivo**: Permitir que cuando el usuario solicite un gráfico (o al obtener datos tabulares de cualquier base de datos), la IA oriente al usuario sobre qué campos puede graficar y despliegue un **Constructor Visual de Gráficos súper sencillo e intuitivo** con `Chart.js` local (Cero CDNs), donde el usuario elija con un clic el tipo de gráfico (Barras, Líneas, Dona/Pastel, Barras Horizontales), el campo del Eje X, la métrica del Eje Y y la función de agregación (`Conteo`, `Suma`, `Promedio`, `Valor Directo`), con descarga en imagen PNG.

- [x] T083 Actualizar `IntentClassifier` (`app/use_cases/intent_classifier.py`) y `AskChatUseCase` (`app/use_cases/ask_chat.py`) para detectar solicitudes de gráficos (`wants_chart`), analizar las columnas del resultado (`dimension_columns` vs `metric_columns`), sugerir configuración inicial de gráfico (`chart_config`) y hacer que la IA pregunte/sugiera amablemente en Markdown sobre qué campos disponibles desea enfocar la gráfica
- [x] T084 [P] Agregar endpoint `GET /api/v1/export/dataset/{dataset_id}` en `app/api/v1/routers/export.py` (y su proxy `/chat/dataset/{datasetId}` en Laravel `ChatController.php` + `FastApiClient.php`) para obtener las filas completas cacheadas del dataset al construir/recalcular gráficos interactivos
- [x] T085 Incluir `chart.umd.min.js` local en `resources/views/chat/index.blade.php` y construir en `public/js/chat_stream.js` el **Constructor Interactivo de Gráficos (`renderChartBuilderSection`)** con chips rápidos de campos, selector de tipo de gráfico (`bar`, `line`, `doughnut`, `pie`, `horizontalBar`), selector de Eje X, operación (`COUNT`, `SUM`, `AVG`, `RAW`), Eje Y y botón de descarga PNG
- [x] T086 Validar extremo a extremo con pruebas automatizadas en `pytest` y `php artisan test`, recompilar Vite (`npm run build`) y actualizar documentación (`v1.0.5`)

---

## Fase 14: Descubrimiento Relacional de Campos (`JOIN`) y Flujo Guiado en 2 Pasos para Gráficos (`Option A Clarification`)

**Objetivo**: Implementar la **Opción A** clarificada por el usuario: cuando el usuario pide revisar datos cruzados entre dos o más tablas o solicita un gráfico sin especificar qué campos exactos usar en los ejes (ej. *"revísame el estado del rollo vinculado con otra tabla"*), la IA debe primero cruzar las tablas (`JOIN`), analizar las columnas resultantes, **preguntarle al usuario con qué campos desea crear el gráfico** mostrando un **Asistente Visual de Selección de Campos (Paso 1)** sin dibujar el gráfico prematuramente, y generar el gráfico exacto en cuanto el usuario elija/confirme los campos (por clic en **`[ ✨ Generar Gráfico ]`**, **`[ 💬 Pedirle a la IA ]`** o respondiendo en el chat).

- [x] T087 Actualizar `AskChatUseCase._generate_sql()` y `AskChatUseCase.analyze_columns_for_chart()` en `app/use_cases/ask_chat.py` para optimizar consultas `JOIN` multi-tabla, detectar si el prompt del usuario ya especificó los campos exactos o si requiere selección guiada (`needs_field_selection: bool`), extraer ejemplos reales por columna (`column_samples`) y soportar respuestas de seguimiento en el chat (cuando el usuario responde con qué campos quiere el gráfico)
- [x] T088 Actualizar el prompt de síntesis de `AskChatUseCase.execute_sync()` en `app/use_cases/ask_chat.py` para que cuando `needs_field_selection=True` la IA explique el cruce de tablas, liste en Markdown las columnas candidatas (Categorías vs Métricas) y pregunte explícitamente al usuario con cuáles campos desea generar la gráfica
- [x] T089 Actualizar `renderDatasetSection()` y `setupInteractiveChartBuilder()` en `D:\Laravel\Supertex AI\public\js\chat_stream.js` para implementar el flujo de 2 etapas (**Paso 1: Asistente de Selección de Campos** con tarjetas de columnas + muestras y botones **`[ ✨ Generar Gráfico Ahora ]`** / **`[ 💬 Confirmar Campos con la IA ]`**, y **Paso 2: Lienzo del Gráfico Generado** con `Chart.js`)
- [x] T090 Escribir pruebas unitarias en `tests/unit/test_intent_classifier.py` y `tests/contract/test_chat_router.py` verificando `needs_field_selection` (solicitud ambigua vs solicitud con campos explícitos), compilar Vite (`npm run build`), ejecutar `pytest` y `php artisan test`, e incrementar versión a `1.0.6`

---

## Fase 15: Aprendizaje Relacional por Embeddings (`FK` + Heurísticas), Búsqueda Híbrida con Expansión de Grafo (`1-Hop`) y Resolución de Nombres Reales en Gráficos

**Objetivo**: Aplicar las skills `rag-engineer`, `embedding-strategies` y `hybrid-search-implementation` para que al vectorizar tablas en `pgvector`, la IA aprenda tanto las llaves foráneas explícitas (`FOREIGN KEY`) como las relaciones por convención (`id_empresa` ➔ `empresa.id`), recupere automáticamente las tablas vinculadas mediante búsqueda híbrida + expansión de grafo (`1-Hop Graph Expansion`), y genere consultas `JOIN` que traigan los nombres descriptivos reales (`empresa.nombre`) en lugar de IDs numéricos para el Asistente de Gráficos.

- [x] T091 Actualizar `DynamicDBAdapter` (`app/infrastructure/database/dynamic_db_adapter.py`) para extraer llaves foráneas explícitas (`INFORMATION_SCHEMA.KEY_COLUMN_USAGE` en MySQL/MariaDB y PostgreSQL) e inferir relaciones heurísticas (`id_<tabla>`, `<tabla>_id`) junto con las columnas descriptivas (`nombre`, `razon_social`, `descripcion`, `estado`) de la tabla referenciada
- [x] T092 Actualizar `ManageConnectionsUseCase.vectorize_selected_tables()` (`app/use_cases/manage_connections.py`) y `SyncSchemaDictionaryUseCase` (`app/use_cases/sync_schema_dictionary.py`) aplicando `embedding-strategies` para enriquecer el texto vectorizado con el bloque `RELACIONES Y JOINS APRENDIDOS` y almacenar `related_tables` y `join_hints` en `metadata_`
- [x] T093 [P] Implementar `search_schema_with_relations()` en `VectorRepository` (`app/infrastructure/database/vector_repository.py`) aplicando `hybrid-search-implementation` y `rag-engineer` (combinando similitud vectorial + coincidencia léxica de tablas + expansión automática `1-Hop` de las tablas listadas en `metadata_["related_tables"]`)
- [x] T094 Actualizar `AskChatUseCase` (`app/use_cases/ask_chat.py`) para usar `search_schema_with_relations()`, exigir en el prompt SQL la resolución de llaves foráneas (`id_empresa` ➔ `JOIN empresa` seleccionando el nombre descriptivo), y depriorizar columnas `id_*`/`*_id` crudas en `analyze_columns_for_chart()` cuando existen etiquetas descriptivas del `JOIN`
- [x] T095 [P] Mostrar las relaciones detectadas (`🔗 Relaciones`) en el explorador de tablas `public/js/connections_manager.js` y etiquetar las columnas relacionales en el Asistente de Selección de Campos de `public/js/chat_stream.js`
- [x] T096 Escribir pruebas unitarias de inferencia relacional (`usuario.id_empresa` ➔ `empresa.id` + `empresa.nombre`), búsqueda híbrida con expansión de grafo y filtrado de FKs en `pytest` y `php artisan test`, recompilar Vite (`npm run build`) e incrementar versión a `1.0.7`

---

## Fase 16: Centro de Entrenamiento IA ("🎓 Entrenar IA") y Currículo Práctico para Enseñarle a la IA (`v1.0.8`)

### Bloque A — Tareas Técnicas del Sistema (Para construir el módulo "🎓 Entrenar IA", Aprendizaje por Chat y Control de Formato Tabla/Gráfico)

- [x] T097 [P] Enriquecer la introspección de columnas en `DynamicDBAdapter` (`app/infrastructure/database/dynamic_db_adapter.py`) para extraer `COLUMN_COMMENT` (MySQL/MariaDB) y `col_description` (PostgreSQL), incorporando los comentarios de negocio de cada columna al documento semántico vectorizado en `pgvector`
- [x] T098 Actualizar `IntentClassifier` (`app/use_cases/intent_classifier.py`) para: (a) detectar la intención prioritaria `teach_knowledge` cuando el usuario le enseña una relación/regla en el chat (ej. *"La tabla users se relaciona con companies uniendo..."*), (b) ignorar menciones condicionales de gráficos (*"cuando el usuario pida gráficos..."*), y (c) detectar explícitamente qué formato pidió el usuario (`wants_chart`, `wants_table`) para no mostrar tablas ni gráficos no solicitados
- [x] T099 Crear los casos de uso y endpoints de entrenamiento en `app/api/v1/routers/knowledge.py` (`GET /api/v1/knowledge/rules`, `POST /api/v1/knowledge/train`, `DELETE /api/v1/knowledge/rules/{id}`) soportando las 4 cápsulas de aprendizaje (`custom_relation`, `business_rule`, `kpi_formula`, `sql_example` con validación `sqlglot` de solo lectura), prevención de duplicados y vinculación automática con `metadata_["related_tables"]`
- [x] T100 [P] Implementar `search_learned_rules()` en `VectorRepository` (`app/infrastructure/database/vector_repository.py`) y actualizar `AskChatUseCase` (`app/use_cases/ask_chat.py`) para: (a) procesar el intent `teach_knowledge` guardando y vectorizando automáticamente la enseñanza desde el chat (respondiendo con una confirmación de aprendizaje sin ejecutar SQL ni abrir gráficos/tablas), y (b) en cada `data_query` recuperar e inyectar en el prompt tanto `db_schema` (+ `1-Hop`) como las reglas y ejemplos aprendidos, incluyendo `wants_table` y `wants_chart` en la respuesta
- [x] T101 Construir en `datamind-studio` (Laravel) el **"🎓 Centro de Entrenamiento IA"** y actualizar `public/js/chat_stream.js` para: (a) mostrar la tabla interactiva (`DataTables`) o el gráfico **únicamente** cuando el usuario los haya pedido (`wants_table` / `wants_chart`, manteniendo botones compactos para abrirlos bajo demanda cuando solo pidió respuesta en texto), y (b) habilitar el panel interactivo `🎓 Entrenar IA` con las 4 plantillas guiadas, el currículo de 5 niveles y el botón *"🧠 Enseñar este SQL a la IA"*
- [x] T102 Escribir pruebas unitarias en `pytest` y `php artisan test` para `teach_knowledge` (incluyendo el caso exacto de `users.current_company_id = companies.id`), control de formato (`wants_chart` vs `wants_table` vs `text_only`), y el Centro de Entrenamiento IA; recompilar assets con Vite (`npm run build`) e incrementar la versión a `1.0.8`

### Bloque B — Tareas de Aprendizaje para el Usuario ("Currículo Práctico: Aprender a Enseñarle a la IA")

- [ ] T103 **[Nivel 1 - Alimentar el Mapa Relacional]**: Ir a `/connections`, identificar las **Parejas Maestra + Detalle** (ej. `companies` + `users`, `ordenes` + `rollos`, `clientes` + `facturas`) y vectorizarlas **juntas en el mismo lote**. Verificar en las tarjetas de tabla que aparezca el badge `🔗 JOIN: tabla.id_xxx -> maestra.id (nombre)`.
- [ ] T104 **[Nivel 2 - Enseñar Relaciones Directo en el Chat o en `🎓 Entrenar IA` (`custom_relation`)]**: Escribir en el chat o en el Centro de Entrenamiento una relación especial (ej. *"La tabla `users` se relaciona con la tabla `companies` uniendo `users.current_company_id = companies.id`. Cuando el usuario pida datos o gráficos por empresa, nunca muestres `current_company_id`; haz siempre `JOIN companies` y muestra `companies.name`."*) y verificar que la IA confirme que lo aprendió sin lanzar gráficos ni tablas.
- [ ] T105 **[Nivel 3 - Enseñar el Diccionario de Estados y Sinónimos (`business_rule`)]**: Documentar y enseñar a la IA qué significan los códigos numéricos o letras de tus tablas (ej. *"En la tabla `rollos`, `estado = 1` significa 'En Tejeduría', `estado = 2` significa 'Revisado' y `estado = 3` significa 'Despachado'"*) y los términos internos de tu empresa, para que los gráficos muestren etiquetas humanas en lugar de números `1, 2, 3`.
- [ ] T106 **[Nivel 4 - Enseñar Fórmulas e Indicadores (`kpi_formula`)]**: Enseñar a la IA cómo se calculan las métricas clave de tu operación (ej. *"% de Eficiencia"*, *"Kilos Netos = `peso_bruto - peso_tara`"*, *"Días de Atraso"*), indicando exactamente qué columnas se suman, restan o dividen.
- [ ] T107 **[Nivel 5 - Enseñar con el Ejemplo / Golden SQL (`sql_example`)]**: Crear o guardar desde el chat entre 3 y 5 **Consultas SQL de Oro (`SELECT ... JOIN`)** que crucen 2 o 3 tablas importantes de tu negocio. Probar pidiéndole a la IA: (a) una pregunta en texto, (b) *"hazme una tabla..."*, y (c) *"hazme un gráfico..."*.

