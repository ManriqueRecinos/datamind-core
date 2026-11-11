# Implementation Plan: Centro de Entrenamiento IA Simplificado y Fix de Binder Error en Adjuntos

**Feature**: `specs/004-simplified-training-center/spec.md`  
**Goal**: Reparar la discrepancia de columnas en el motor analítico de documentos DuckDB y rediseñar el modal del Centro de Entrenamiento en Laravel para que sea completamente intuitivo y asistido por listas desplegables.

---

## Technical Stack & Architecture

- **Backend**: FastAPI (`app/use_cases/query_attachment.py`, `app/infrastructure/analytics/attachment_analytics_engine.py`, `app/api/v1/routers/knowledge.py`).
- **Analítica Local**: DuckDB en memoria (`parrafo_id`, `seccion`, `contenido`), Polars Calamine, pypdf, python-docx.
- **Frontend**: Laravel 12 Blade (`training-center-modal.blade.php`), JavaScript (`connections_manager.js`, `chat_stream.js`).
- **Persistencia**: PostgreSQL 17 + `pgvector` (`knowledge_documents`, `knowledge_vector_chunks`, `knowledge_audit_logs`).

---

## Fases de Ejecución

### Fase 1: Reparación del Error de DuckDB (`Binder Error`)
1. En `app/use_cases/query_attachment.py`:
   - Modificar la creación del DataFrame en Polars para documentos `.pdf` y `.docx`:
     - Incluir columna `seccion` con valor de la página o encabezado (ej: `"Página 1"`, `"Párrafo 1"`).
     - Incluir columna `contenido` con el texto limpio.
     - Incluir columna `parrafo_id` con el índice correlativo.
2. En `app/infrastructure/analytics/attachment_analytics_engine.py`:
   - Alinear la definición del esquema anunciado en `inspect_file` para reflejar exactamente `parrafo_id`, `seccion`, `contenido`.
3. Actualizar y ejecutar suite de tests: `tests/unit/test_document_attachments.py`.

### Fase 2: Rediseño Visual del Centro de Entrenamiento IA (Laravel Blade)
1. Reemplazar inputs de texto manual (`trainSourceTable`, `trainSourceCol`, etc.) por selectores asistidos `<select>` que carguen las tablas y columnas reales de la conexión activa.
2. Agregar un asistente visual guiado de 3 pasos:
   - **Paso A: Relación entre Tablas**:
     - *¿Qué tabla tiene el dato?* (Selector de tabla origen, ej: `inventario_partes`).
     - *¿Con qué tabla se une?* (Selector de tabla destino, ej: `hop.parte_maquina`).
     - *¿Qué campo identifica la relación?* (Selector de FK / PK).
     - *¿Qué nombre legible debe mostrar la IA al usuario?* (ej: `nombre` o `descripcion`).
   - **Paso B: Diccionario de Códigos y Estados**:
     - *Tabla y Columna* (Selectores).
     - *Valor numérico o código* (ej: `A` o `1`).
     - *Significado real para el negocio* (ej: `"Activo para producción"`).
   - **Paso C: Consultas de Ejemplo (Few-Shot)**:
     - Editor con botón de validación de sintaxis antes de guardar.
   - **Paso D: Subida de Manuales y Documentos**:
     - Botón directo para arrastrar o subir un PDF/Word/Markdown y guardarlo automáticamente en `pgvector`.
3. Generador dinámico de directiva explicativa en tiempo real.

### Fase 3: Conexión Frontend-Backend y Verificación Integral
1. Integrar llamadas a la API de FastAPI para listar esquemas y guardar directivas.
2. Ejecutar prueba integral con el documento de arquitectura de repuestos y verificar que ya no ocurra ningún error de columna inexistente.
