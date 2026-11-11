# Research & Technical Decisions: Implicit Dialogue Learning

**Feature**: `003-implicit-dialogue-learning`  
**Estado**: Especificaciones de Diseño y Decisiones Técnicas Corregidas

---

## 1. Detector de Correcciones: Filtro Barato + LLM con Contexto Enriquecido

### Arquitectura de Detección en Dos Etapas
1. **Etapa 1: Filtro Heurístico Previo (< 1 ms)**:
   - Antes de despertar al LLM o despachar tareas pesadas en CPU, el mensaje del usuario se evalúa contra una lista de marcadores prescriptivos en español:
     `{"no", "usa", "utiliza", "cambia", "filtra por", "tabla", "columna", "no es", "debe ser", "en lugar de", "reemplaza", "estado"}`.
   - Si el mensaje no contiene ningún marcador de corrección o es una frase trivial ("gracias", "ok", "hola", "genera el reporte"), el pipeline finaliza de inmediato.
2. **Etapa 2: LLM en Background con Validación de Esquema y Salida Estructurada**:
   - **Contexto que recibe**:
     - Turno previo del asistente (incluyendo el `generated_sql` si existió).
     - Turno del usuario con la presunta corrección.
     - Lista de tablas y columnas válidas de la conexión activa (`synced_tables`).
   - **Salida Estructurada (Pydantic)**:
     ```json
     {
       "has_correction": true,
       "knowledge_type": "schema_correction",
       "target_entity": "factura_lineas",
       "target_column": "estado",
       "prescriptive_condition": "estado = 'A'",
       "explanation": "Filtrar únicamente facturas activas"
     }
     ```
   - **Control de Confianza**: Se elimina la dependencia ciega de un campo `confidence` inventado por el modelo. En su lugar, el sistema aplica **validación determinista**:
     1. Comprueba si `target_entity` y `target_column` existen en el catálogo de la base de datos conectada.
     2. Si no coinciden con tablas reales, el candidato se rechaza automáticamente.
     3. El texto que se almacenará no es el texto libre del usuario, sino una plantilla sintetizada y controlada:
        `"Para la tabla `{target_entity}`, la columna `{target_column}` debe cumplir: {prescriptive_condition}."`

---

## 2. Gestión de Latencia de CPU y Concurrencia con Ollama

- En un servidor que procesa inferencias en CPU sin GPU, una tarea en background que invoque a Ollama al mismo tiempo que el usuario formula su siguiente pregunta causaría una contención grave de núcleos.
- **Estrategia de Mitigación**:
  1. Se monitorea el estado del bucle de inferencia: la tarea en background se encola con baja prioridad y solo se ejecuta si Ollama está ocioso o tras un retardo prudencial (e.g. 1.5 s tras emitir `done`).
  2. Si el usuario envía una nueva pregunta mientras el detector está corriendo, la consulta del usuario tiene prioridad absoluta de CPU.
  3. **Criterio de Aceptación Medible**: La latencia del turno siguiente del usuario no debe degradarse en más de un 15% respecto al promedio de respuesta en frío.

---

## 3. Modelo de Embeddings: Prefijos de Nomic y Calibración Empírica

- **Modelo Actual**: `nomic-embed-text` (dimensión 768).
- **Manejo de Prefijos Obligatorio de Nomic**:
  - Para indexar fragmentos de conocimiento: se debe anteponer el prefijo `search_document: `.
  - Para realizar consultas de similitud (query): se debe anteponer el prefijo `search_query: `.
  - Ignorar estos prefijos reduce la correlación semántica del modelo hasta en un 30%.
- **Calibración del Umbral**:
  - El umbral preliminar de 0.75 se calibrará utilizando el **Set Dorado de 30 frases** para encontrar el valor que maximice F1-Score sin admitir ruido léxico.
- **Sesión de Base de Datos en Background**:
  - El background task nunca debe reusar la sesión `AsyncSession` del request HTTP (que se cierra al terminar la petición). Se instancia explícitamente `async with async_session_factory() as session:`.

---

## 4. Detección de Contradicciones y Rollback Seguro

- **Orden de Flujo**: La detección de contradicciones y el mecanismo de rollback se ubican en **Fase 3**, antes de habilitar la inyección masiva en el prompt.
- **Algoritmo de Colisión Semántica**:
  1. Cuando un nuevo candidato es aprobado o activado, se ejecuta una búsqueda vectorial sobre las reglas existentes con el mismo `connection_id` y `target_entity`.
  2. Si existe una regla con similitud $\ge 0.82$, se ejecuta una comparación lógica rápida. Si son incompatibles (e.g., directiva previa: `estado = 1`, directiva nueva: `estado = 'A'`), la nueva regla pasa a estado `conflict`, se enlaza `conflict_with_id` y se notifica al usuario sin inyectarse en el prompt.
- **Purga en Rollback**: Al hacer rollback, la regla pasa a `rolled_back` y se invalidan las cachés locales de reglas en memoria para que el siguiente turno no la recupere.

---

## 5. Señales del Servidor para Minería de Ejemplos SQL

- Se rechazan métodos basados en feedback de texto informal ("gracias", "excelente").
- La captura de candidatos `sql_example` se dispara **en el servidor** dentro del controlador que procesa la exportación a Excel:
  1. `GET /chat/export/excel?dataset_id=...`
  2. El servidor valida que el `dataset_id` exista y pertenezca al usuario autenticado.
  3. Se recupera el SQL ejecutado asociado al dataset y se valida mediante `sqlglot` que sea estrictamente un `SELECT`.
  4. Se crea el candidato en segundo plano con `trigger_signal = 'excel_export'`.

---

## 6. Alcance Delimitado (Lo que queda fuera de alcance)

- **Script de migración a `multilingual-e5-small`**: Queda fuera de alcance en esta fase. Se deja la columna `embedding_model` en la tabla para garantizar la trazabilidad y extensibilidad futura.
- **Dashboard analítico complejo de métricas**: Queda fuera de alcance; se implementará una vista SQL administrativa estándar (`v_knowledge_candidates_stats`) para consultar totales, aprobaciones y rechazos.
