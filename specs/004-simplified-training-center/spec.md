# Feature Specification: Centro de Entrenamiento IA Simplificado y Fix de Binder Error en Adjuntos Documentales

**Feature Branch**: `004-simplified-training-center`  
**Created**: 2026-11-11  
**Status**: Specification Refined  
**Input**: Usuario reporta que al adjuntar un documento e intentar que la IA aprenda sobre cómo se hace un repuesto (parte, aditamento, ayuda, aguja) falló la consulta en DuckDB con:
`Binder Error: Referenced column "seccion" not found in FROM clause! Candidate bindings: "contenido" LINE 1: ... contenido FROM repuestos WHERE contenido LIKE '%repuesto%' OR seccion LIKE '%repuesto%' LIMIT 500`.
Además, solicita rediseñar y simplificar radicalmente el **Centro de Entrenamiento de la IA** (`training-center-modal`) porque actualmente es confuso, técnico y difícil de usar al momento de agregar relaciones (FK/PK), consultas y reglas de negocio.

---

## 1. User Scenarios & Testing

### User Story 1 - Corrección de Binder Error en Consultas DuckDB sobre Documentos (Priority: P1)
Como usuario que adjunta un documento técnico (PDF o DOCX) en el chat, quiero que las consultas analíticas sobre el texto se ejecuten limpiamente sin errores de columnas faltantes (`seccion` vs `contenido`), para recibir respuestas fundamentadas en el documento sin fallos de compilación SQL en DuckDB.

**Por qué esta prioridad**: Es un bug bloqueante en tiempo de ejecución. El esquema anunciado al LLM para documentos incluía `seccion` y `contenido`, pero el DataFrame de Polars registrado en DuckDB solo contenía `parrafo_id` y `contenido`.

**Acceptance Scenarios**:
1. **Given** un archivo PDF o DOCX adjunto, **When** el motor de analítica monta la vista en DuckDB, **Then** las columnas registradas en el DataFrame (`seccion`, `contenido`, `parrafo_id`) coinciden de forma idéntica con el esquema anunciado en el prompt del LLM.
2. **Given** una pregunta del usuario sobre un documento adjunto, **When** el LLM genera SQL como `WHERE contenido LIKE '%...' OR seccion LIKE '%...'`, **Then** DuckDB ejecuta la consulta exitosamente y devuelve los párrafos coincidentes.

---

### User Story 2 - Centro de Entrenamiento IA Visual e Intuitivo (Priority: P1)
Como usuario operativo o analista, quiero una interfaz en el Centro de Entrenamiento que sea visual, simple y sin jerga técnica confusa (sin necesidad de escribir código SQL manual ni pelear con claves foráneas abstractas), donde pueda:
1. **Enlazar dos tablas visualmente**: Seleccionar "Tabla A" y "Tabla B" desde listas desplegables sincronizadas del catálogo, elegir el campo que las une y qué campo legible mostrar (ej: "mostrar `nombre` en vez de `id`").
2. **Enseñar sinónimos o estados**: Definir en un clic equivalencias (ej: "1 = Activo", "2 = Anulado").
3. **Cargar o pegar consultas de ejemplo**: Un área limpia para pegar una consulta funcional de SQL con botón de validación previa antes de guardar.
4. **Subir documentos maestros**: Una sección directa en el modal para subir guías técnicas o PDFs que la IA deba memorizar globalmente en la base de datos vectorial de la empresa.

**Acceptance Scenarios**:
1. **Given** el modal del Centro de Entrenamiento abierto, **When** el usuario selecciona la opción "Vincular Tablas", **Then** los campos de tabla y columna son desplegables poblados desde el catálogo sincronizado de la conexión activa, no inputs de texto libre propensos a errores tipográficos.
2. **Given** una regla guardada, **When** se vectoriza en `pgvector`, **Then** aparece de inmediato en la lista de conocimiento aprendido con opción de edición y prueba rápida en un clic.

---

## 2. Requirements & Guardrails

- **FR-001 (Consistencia de Columnas en DuckDB)**:
  - En `app/use_cases/query_attachment.py` y `app/infrastructure/analytics/attachment_analytics_engine.py`, toda vista temporal creada para documentos PDF/DOCX DEBE contener de forma consistente las columnas: `seccion VARCHAR`, `contenido VARCHAR` y `parrafo_id INTEGER`.
- **FR-002 (Simplificación del Modal de Entrenamiento en Laravel)**:
  - Rediseñar `resources/views/chat/partials/training-center-modal.blade.php`:
    - Tarjetas visuales de acción rápida con lenguaje no técnico ("Vincular 2 Tablas", "Explicar Códigos o Estados", "Ejemplo de Consulta", "Subir Documento o Manual").
    - Selectores dinámicos (`<select>`) para tablas y columnas basados en las tablas sincronizadas de la conexión seleccionada.
    - Previsualización en tiempo real de la directiva generada ("Cuando alguien pregunte por X, uniré con Y y mostraré Z").
- **FR-003 (Ingesta Documental Directa al Centro de Conocimiento)**:
  - Permitir desde el mismo modal de entrenamiento adjuntar un documento (`.md`, `.pdf`, `.docx`) para vectorizarlo como conocimiento permanente con `category = 'business_rule'` o `'process_qa'`.

---

## 3. Success Criteria

- **SC-001**: Cero errores `Binder Error` en DuckDB al formular preguntas sobre documentos PDF o DOCX adjuntos.
- **SC-002**: Reducción del tiempo y fricción para registrar una relación entre tablas en el Centro de Entrenamiento a menos de 30 segundos sin necesidad de escribir SQL a mano.
- **SC-003**: 100% de las pruebas automatizadas del repositorio continúan aprobadas.
