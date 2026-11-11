# Tareas de Implementación: Adjuntos de Archivos en Chat y Analítica Local en CPU (Fase 1 Tabular)

**Especificación**: `specs/002-chat-file-attachments`  
**Plan de Referencia**: `specs/002-chat-file-attachments/plan.md`  
**Modelo de Datos**: `specs/002-chat-file-attachments/data-model.md`  
**Contratos**: `specs/002-chat-file-attachments/contracts/`

---

## FASE 1: Modelo de Datos, Almacenamiento y Endpoints de Carga en FastAPI

**Propósito**: Crear la infraestructura de persistencia, validación de tipo MIME real, límites perimetrales y endpoints de subida para archivos tabulares (CSV, TSV, XLSX).

- [x] **T101**: [P] Crear migración SQL en `D:\Python\python-db\migrations\005_create_chat_attachments.sql`.
  - Crear tabla `chat_attachments`:
    - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
    - `session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE`
    - `user_id VARCHAR(100) NOT NULL`
    - `filename VARCHAR(255) NOT NULL`
    - `original_name VARCHAR(255) NOT NULL`
    - `mime_type VARCHAR(100) NOT NULL`
    - `file_size_bytes BIGINT NOT NULL`
    - `storage_path TEXT NOT NULL`
    - `schema_preview JSONB NOT NULL DEFAULT '{}'`
    - `row_count INTEGER NULL`
    - `status VARCHAR(30) NOT NULL DEFAULT 'ready'`
    - `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL`
  - Crear índices por `(session_id, user_id)` y `created_at`.
  - Definir modelo SQLAlchemy `ChatAttachmentModel` en `D:\Python\python-db\app\infrastructure\database\models.py`.

- [x] **T102**: [P] Implementar esquemas Pydantic V2 de adjuntos en `D:\Python\python-db\app\api\v1\schemas\attachments.py`.
  - `AttachmentUploadResponse`: `id`, `filename`, `mime_type`, `file_size_bytes`, `row_count`, `columns`, `sample_rows`.
  - `AttachmentSummarySchema`: metadatos básicos y estado del archivo.

- [x] **T103**: Implementar servicio de validación de seguridad de archivos en `D:\Python\python-db\app\infrastructure\security\file_security_validator.py`.
  - Detección de tipo MIME real mediante Magic Bytes (`python-magic` o lectura de cabecera hexadecimal de 8 bytes).
  - Verificación contra Zip-Bombs para archivos XLSX (tasa de compresión > 100:1 o tamaño descomprimido > 50 MB rechazado con `413 Payload Too Large`).
  - Límite perimetral estricto: tamaño máximo 15 MB por archivo.
  - Saneamiento anti-fórmulas en celdas de Excel (`=`, `+`, `-`, `@` forzados a texto plano sin ejecución).

- [x] **T104**: Implementar motor de analítica local de archivos en `D:\Python\python-db\app\infrastructure\analytics\attachment_analytics_engine.py`.
  - Inicializar DuckDB en memoria con flags de sandbox: `enable_external_access = false`, `max_memory = '256MB'`, `threads = 2`.
  - Carga en streaming de CSV/TSV mediante `read_csv_auto()`.
  - Carga de XLSX mediante `polars.read_excel(engine="calamine")` validando $\le 50,000$ filas, registrando el DataFrame en la sesión DuckDB.
  - Inferencia y formateo del esquema: lista de columnas, tipos normalizados (`TEXT`, `INTEGER`, `DECIMAL`, `DATE`) y muestra de las primeras 5 filas.

- [x] **T105**: Implementar router de endpoints de subida y gestión en `D:\Python\python-db\app\api\v1\routers\attachments.py`.
  - `POST /api/v1/chat/attachments`:
    - Recibe `file: UploadFile = File(...)`, `session_id: str = Form(...)`, `user_id: str = Form(...)`.
    - Valida cuota de máximo 3 archivos adjuntos por sesión.
    - Ejecuta validaciones de seguridad (T103).
    - Procesa el esquema con `AttachmentAnalyticsEngine` (T104).
    - Almacena el archivo en disco (`storage/attachments/{session_id}/...`) y persiste el registro en PostgreSQL.
    - Retorna `AttachmentUploadResponse`.
  - `DELETE /api/v1/chat/attachments/{attachment_id}`:
    - Valida titularidad del usuario.
    - Elimina el archivo de disco y remueve el registro en BD.
  - Registrar el nuevo router en `D:\Python\python-db\app\main.py`.

---

## FASE 2: Integración de Consultas sobre Archivos en el Chat (FastAPI)

**Propósito**: Permitir que el usuario haga preguntas sobre sus archivos adjuntos, ejecutando consultas SQL en sandbox sobre DuckDB con streaming SSE.

- [x] **T201**: Implementar caso de uso `QueryAttachmentUseCase` en `D:\Python\python-db\app\use_cases\query_attachment.py`.
  - Cargar las vistas temporales en DuckDB a partir de los `attachment_ids` provistos.
  - Formatear el contexto del esquema de los archivos para el prompt del LLM (`qwen2.5:3b`).
  - Prompt estructurado que instruye generar consultas SQL compatibles con DuckDB referenciando los nombres de las vistas creadas (e.g. `SELECT * FROM archivo_ventas WHERE ...`).

- [x] **T202**: Integrar guardarraíl y ejecución de DuckDB en `D:\Python\python-db\app\use_cases\ask_chat.py`.
  - Si la petición incluye `attachment_ids`:
    - Validar sintácticamente el SQL con `sqlglot` usando dialecto DuckDB: exigir exclusivamente `SELECT`, prohibir llamadas a funciones de sistema, forzar `LIMIT 500`.
    - Ejecutar en DuckDB con timeout de 3.0 segundos.
    - Si genera resultados tabulares, persistir en `query_datasets` para habilitar el botón de Excel y gráficos.
  - Enriquecer `ChatRequest` en `D:\Python\python-db\app\api\v1\schemas\chat.py` para aceptar `attachment_ids: Optional[List[str]] = None`.

---

## FASE 3: Interfaz de Usuario en Laravel (Clip de Adjunto y Experiencia de Chat)

**Propósito**: Proveer el botón interactivo de adjuntar archivo (clip 📎), drag-and-drop, chips de estado y vinculación en el envío de mensajes.

- [x] **T301**: Actualizar cliente de Laravel en `D:\Laravel\Supertex AI\app\Services\FastApiClient.php`.
  - Implementar método `uploadAttachment(UploadedFile $file, string $sessionId, string $userId)`.
  - Implementar método `deleteAttachment(string $attachmentId, string $userId)`.
  - Modificar `streamChat()` para propagar el array opcional `attachment_ids`.

- [x] **T302**: Crear endpoints en Laravel en `D:\Laravel\Supertex AI\app\Http\Controllers\ChatController.php`.
  - `POST /chat/attachments`: Valida el archivo (`max:15360`, mimes: `csv,txt,xlsx,xls`), delega la subida a FastAPI y retorna JSON.
  - `DELETE /chat/attachments/{id}`: Delega la eliminación a FastAPI y retorna JSON.
  - Registrar las rutas en `D:\Laravel\Supertex AI\routes\web.php`.

- [x] **T303**: Diseñar componente visual en `D:\Laravel\Supertex AI\resources\views\chat\index.blade.php`.
  - Agregar botón con icono de clip (`<button id="btnAttachFile" type="button"><i class="fa-solid fa-paperclip"></i></button>`) en la barra inferior junto al textarea.
  - Agregar input oculto `<input type="file" id="fileAttachmentInput" accept=".csv,.tsv,.xlsx,.xls" class="hidden">`.
  - Contenedor de previsualización de chips de adjuntos (`<div id="attachedFilesContainer" class="flex flex-wrap gap-2 mb-2"></div>`) encima del textarea.

- [x] **T304**: Implementar interactividad en `D:\Laravel\Supertex AI\public\js\chat_stream.js`.
  - Manejo de evento clic en `#btnAttachFile` y apertura del selector de archivos.
  - Subida asíncrona inmediata con spinner de carga.
  - Renderizado del chip de archivo cargado: icono de tipo (Excel/CSV), nombre truncado, peso, badge de número de filas/columnas y botón de remover (`x`).
  - Inclusión de los IDs de adjuntos activos en el payload JSON enviado a `POST /chat/stream`.
  - Limpieza de adjuntos al resetear o cambiar de sesión.

---

## FASE 4: Benchmarking y Pruebas con Archivos Reales

**Propósito**: Validar consumo de memoria RAM (pico vs reposo), latencia y resiliencia ante archivos reales de Supertex.

- [x] **T401**: Crear suite de tests de seguridad y análisis tabular en `D:\Python\python-db\tests\unit\test_attachment_analytics.py`.
  - Test de rechazo de Zip-Bomb en XLSX.
  - Test de bloqueo de inyecciones por fórmulas (`=CMD|...`).
  - Test de consulta DuckDB con límite y timeout.
  - Test de lectura streaming CSV y Calamine XLSX.

- [x] **T402**: Script de benchmarking de RAM y latencia en `D:\Python\python-db\tools\benchmark_attachments.py`.
  - Medir RAM antes, durante y después con `tracemalloc` y `psutil`.
  - Validar que el pico de RAM no exceda 256 MB por sesión.
  - Registrar resultados en `D:\Python\python-db\specs\002-chat-file-attachments\benchmarks.md`.
