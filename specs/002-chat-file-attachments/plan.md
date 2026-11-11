# Implementation Plan: Adjuntos de Archivos en Chat con Conexión Efímera y Recuperación Segura

**Especificación de Referencia**: `specs/002-chat-file-attachments/spec.md`  
**Fecha**: 2026-11-11  

---

## 1. Technical Stack & Arquitectura

- **Frontend**:
  - Laravel 12 Blade (`index.blade.php`, `candidate_chip.blade.php`).
  - JavaScript SPA Modular (`chat_stream.js`): Control de ciclo de vida con `ActiveJobStore`, `viewedStreamId`, hidratación síncrona/asíncrona desde base de datos (`loadConversationSession()`), `escapeHtml()` estricto para prevención de XSS.
- **Backend**:
  - FastAPI (`app/api/v1/routers/attachments.py`, `app/use_cases/query_attachment.py`, `app/use_cases/ask_chat.py`).
  - PostgreSQL 17 + `pgvector` (`chat_attachments`, `chat_messages.metadata`, `query_datasets`).
- **Motores Analíticos en CPU Local (Sin GPU)**:
  - **DuckDB 2.0.0**: Base de datos SQL en memoria sandboxed (`enable_external_access = false`, `max_memory = '256MB'`, `threads = 2`).
  - **Polars 2.1.0 + Calamine Engine**: Lector de hojas de cálculo Excel (`.xlsx`, `.xls`) con carga completa en memoria (hasta 50,000 filas).
  - **PyMuPDF (`fitz`)**: Extractor ultrarrápido de texto por bloques, páginas y metadatos para archivos `.pdf`.
  - **python-docx 1.2.0**: Extractor de párrafos y títulos estructurados para documentos Word `.docx`.
  - **sqlglot**: Guardarraíl sintáctico (dialecto DuckDB: estrictamente `SELECT`, `LIMIT 500` forzado, bloqueo de llamadas de filesystem).

---

## 2. Respeto al Ciclo de Vida del Chat (Parte 1)

El renderizado de adjuntos debe funcionar de forma idéntica en ambos caminos de ejecución:

```
[Usuario adjunta archivo] ──> Chip previo sobre textarea (#attachedFilesContainer)
                                      │
                         [Envío de Mensaje POST /chat/stream]
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
   [CAMINO 1: EN VIVO]                                [CAMINO 2: HISTORIAL BD]
- ActiveJobStore registra job.attachments           - GET /chat/sessions/{id}
- appendUserMessage(text, activeAttachments)        - loadConversationSession(sessionId)
- Chip renderizado ENCIMA de la burbuja user        - msg.metadata.attachments parseado
- Limpieza inmediata del textarea                   - appendUserMessage(msg.content, msgAttachments)
- viewedStreamId acoplado síncronamente             - Tarjeta renderizada ENCIMA de la burbuja user
```

---

## 3. Fases Secuenciales de Implementación

### FASE 1: Subida Previa y Chip Interactivo sobre el Textarea
**Objetivo**: Garantizar la carga previa asíncrona, validación perimetral y previsualización de chips.
- Componente en Blade: `#attachedFilesContainer` sobre `#promptInput`.
- Estados del chip: `procesando` (spinner), `listo` (badge de tamaño, icono y botón `x`), `error` (borde rojo y tooltip explicativo).
- Invocación de `POST /api/v1/chat/attachments` retornando `attachment_id`, nombre original, peso y MIME real.
- Botón quitar (`x`): llama a `DELETE /api/v1/chat/attachments/{id}` y deselecciona de `activeAttachments`.

### FASE 2: Persistencia y Renderizado de Tarjeta ENCIMA del Mensaje (En Vivo + Hidratación)
**Objetivo**: Garantizar que el archivo enviado quede vinculado al mensaje y sobreviva a recargas.
- Envío de `attachment_ids` a `/chat/stream`.
- Guardado en PostgreSQL en `chat_messages.metadata` bajo `attachments: [{id, name, size_bytes, mime_type, status}]`.
- Modificación de `appendUserMessage(text, attachments)` en `chat_stream.js`:
  - Renderiza una tarjeta estilizada **arriba** de la burbuja del usuario.
  - Escapado estricto anti-XSS (`escapeHtml(name)`).
  - Al hidratar en `loadConversationSession()`, recupera `msg.metadata.attachments` y renderiza la tarjeta en el historial pasado.

### FASE 3: Conexión Efímera para Tabulares (CSV/TSV y XLSX con Polars Calamine)
**Objetivo**: Tratar archivos tabulares como una fuente introspeccionada efímera bajo DuckDB.
- Montaje de vista temporal en DuckDB en memoria.
- Generación de entrada sintética de esquema (`db_schema`) anunciada al LLM.
- Validación con `SQLGuardrail` (solo `SELECT`, `LIMIT 500`).
- Si produce filas, emisión del evento SSE `dataset` para habilitar el Constructor de Gráficos y la descarga en Excel (`/chat/export/{dataset_id}`).
- Destrucción de la sesión en memoria al concluir la consulta o expirar TTL.

### FASE 4: Documentos No Estructurados (PDF con PyMuPDF y DOCX con python-docx)
**Objetivo**: Extraer texto por páginas y párrafos con citas exactas y guardarraíl de contenido no confiable.
- Integración de `PyMuPDF` (`fitz`) para PDFs nativos y `python-docx` para documentos Word.
- Particionado con `TextChunker` indexando `seccion` (`"Página X"` / `"Título"`) y `contenido`.
- Guardarraíl de Prompt:
  `<<<CONTENIDO_DOCUMENTO_NO_CONFIABLE>>> ... <<<FIN_DOCUMENTO>>>`.
- El modelo responde con citas explícitas (`[Página X]`).
- Prohibición terminante de promover contenido de documentos a conocimiento global sin curación humana.

### FASE 5: Pruebas de Seguridad y Benchmarking de Rendimiento en CPU
**Objetivo**: Certificar la resiliencia y el cumplimiento estricto de recursos.
- **Suite de Pruebas de Seguridad (`test_attachment_security.py`)**:
  - Detección y rechazo de Zip-Bombs (compresión > 100:1 o > 50 MB descomprimido con HTTP 413).
  - Bloqueo de macros maliciosas (`.xlsm` desautorizado o neutralizado).
  - Detección de Magic Bytes falsificados (ej: `.exe` renombrado a `.pdf` o `.xlsx`).
  - Saneamiento de inyección de fórmulas (`=`, `+`, `-`, `@`).
- **Benchmark de Rendimiento (`tools/benchmark_attachments.py`)**:
  - Medición de RAM inicial, pico y delta con 50,000 registros.
  - Verificación de que el pico de RAM delta no supere los **256 MB**.
  - Registro de resultados en `specs/002-chat-file-attachments/benchmarks.md`.
