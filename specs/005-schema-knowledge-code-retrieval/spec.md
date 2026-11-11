# Feature Specification: Conocimiento como Código (YAML) y Recuperación Semántica Híbrida de Esquema

**Feature Branch**: `005-schema-knowledge-code-retrieval`  
**Created**: 2026-11-11  
**Status**: Draft Specification  
**Input**: Requerimientos del usuario para transformar el aprendizaje de DataMind AI en dos pilares fundamentales:
1. **Conocimiento como código para desarrolladores**: Archivos YAML versionados en git (`knowledge/<conexión>/relations.yaml`, `examples.yaml`, `glossary.yaml`) con CLI idempotente (`python -m app.cli.load_knowledge --connection X [--check]`), validación semántica contra `synced_tables`, validación con `sqlglot` y `EXPLAIN`, upsert por hash SHA256 de contenido y estado de origen confiable (`status = 'verified'`, `scope = 'global'`).
2. **Recuperación semántica híbrida de esquema**: Documentos de tabla enriquecidos (descripciones, alias, sinónimos, comentarios de columnas), indexación de valores categóricos distintos (cardinalidad $\le 200$, sin datos sensibles), búsqueda híbrida (vectorial con `nomic-embed-text` + léxica trigramas/fulltext) con filtro estricto por `connection_id`, `status` y `scope`, expansión relacional de 1 salto y un harness de evaluación automatizado (`recall@k`) sobre 30 preguntas de negocio.

---

## 1. User Scenarios & Testing *(mandatory)*

### User Story 1 - Gestión de Conocimiento como Código Versionado en Git (Priority: P1)

Como ingeniero de software o arquitecto de datos del proyecto, quiero definir las relaciones complejas (`JOIN`), ejemplos representativos (Few-Shot SQL) y el glosario de términos de negocio en archivos YAML versionados en el repositorio (`knowledge/<conexión>/`), para que cualquier ajuste en la lógica de negocio se gestione mediante Pull Requests, revisiones de código y despliegues reproducibles sin depender de formularios manuales propensos a error.

**Why this priority**: Es la base de reproducibilidad y confiabilidad. Permite a los programadores documentar el modelo de datos formalmente y cargar conocimiento verificado y global en un solo comando idempotente.

**Independent Test**:
1. Crear o editar `knowledge/demo_manrique/relations.yaml` con una unión `inventario_partes.id_parte_maquina = hop.parte_maquina.id_parte_maquina`.
2. Ejecutar `python -m app.cli.load_knowledge --connection demo_manrique --check` (dry-run): verificar que valide tablas y columnas contra `synced_tables` y reporte lo que crearía sin modificar la base de datos.
3. Ejecutar `python -m app.cli.load_knowledge --connection demo_manrique`: verificar inserción idempotente con `status = 'verified'`, `scope = 'global'` y registro en `knowledge_audit_logs`.
4. Ejecutar el comando una segunda vez: verificar que reporte 0 duplicados y no altere los embeddings existentes (upsert por hash de contenido).
5. Agregar una unión hacia una tabla o columna inexistente: verificar que el comando falle antes de escribir con código de salida $\ne 0$ indicando el error exacto.

**Acceptance Scenarios**:
1. **Given** un archivo YAML con una consulta SQL de ejemplo en `examples.yaml`, **When** el comando de carga se ejecuta, **Then** valida sintácticamente el SQL con `sqlglot` (exigiendo estrictamente `SELECT`), valida opcionalmente con `EXPLAIN` en la base de datos de la conexión activa, calcula el hash SHA-256 del contenido, genera el embedding con prefijo `search_document:` y persiste la tupla como `status: 'verified'`, `scope: 'global'`.
2. **Given** un archivo YAML con una unión a una tabla que no existe en `synced_tables`, **When** se ejecuta el CLI, **Then** el proceso se detiene con error descriptivo y no genera basura en la base de datos.
3. **Given** la bandera `--check`, **When** se invoca el CLI, **Then** realiza todas las validaciones sintácticas y de esquema emitiendo el plan de ejecución sin realizar escrituras ni llamadas de embedding a Ollama.

---

### User Story 2 - Recuperación Semántica de Esquema con Valores Categóricos Distintos (Priority: P1)

Como usuario que realiza consultas en el chat utilizando nombres coloquiales de entidades o valores particulares (ej: *"¿cuántos perros hay?"* o *"muéstrame repuestos usados tipo looper"*), quiero que el recuperador de esquema identifique la tabla correcta (`animal.especie = 'perro'` o `hop.parte_maquina.nombre ILIKE '%looper%'`), incluso cuando el término no aparece en el nombre de la tabla ni de la columna.

**Why this priority**: Resuelve la mayor brecha de los sistemas Text-to-SQL: el usuario pregunta por los *datos* (valores), no por los *metadatos* (nombres de tablas). Indexar valores categóricos de baja cardinalidad permite enlazar el lenguaje del usuario con el filtro exacto en SQL.

**Independent Test**:
1. Dada una base de datos con tablas `carro`, `animal` y `sexo`, donde `animal` tiene la columna `especie` con valores `['perro', 'gato', 'caballo']`.
2. Indexar los valores categóricos mediante configuración explícita.
3. Formular la consulta *"dime cuántos perros hay"*.
4. Verificar que el recuperador de esquema traiga en el top de contexto a la tabla `animal` y mediante la expansión de 1 salto a la tabla `sexo` (si existe FK), descartando `carro`.

**Acceptance Scenarios**:
1. **Given** una columna categórica configurada explícitamente con cardinalidad $\le 200$, **When** se sincronizan valores, **Then** se generan fragmentos vectorizados del tipo `Valor '{valor}' en {tabla}.{columna}`, con prefijo `search_document:`.
2. **Given** columnas con datos sensibles (correos, contraseñas, nombres de personas, tarjetas, teléfonos), **When** se ejecuta la indexación de valores, **Then** el sistema aplica un filtro de seguridad estricto que prohíbe terminantemente indexar columnas que no estén autorizadas explícitamente en una lista blanca.

---

### User Story 3 - Búsqueda Híbrida (Vectorial + Léxica) con Expansión Relacional de 1 Salto (Priority: P2)

Como motor de Text-to-SQL, quiero que la recuperación de tablas y reglas combine similitud semántica de embeddings densos con coincidencia léxica exacta/trigramas (`pg_trgm` o tsvector), fusionando los rankings mediante Reciprocal Rank Fusion (RRF), para garantizar alta precisión cuando el usuario mencione nombres técnicos exactos y alta cobertura cuando use perífrasis o conceptos difusos.

**Why this priority**: Los embeddings fallan ante códigos exactos o acrónimos (`pm.codigo`, `UY 128 GAS`), mientras que la búsqueda léxica falla ante lenguaje natural interpretativo. La combinación híbrida maximiza el `recall@k`.

**Independent Test**:
1. Realizar una búsqueda con código técnico exacto (ej. `"UY 128 GAS"`).
2. Realizar una búsqueda conceptual (ej. `"costura de elásticos y dobladillos"`).
3. Verificar que en ambos casos las tablas y directivas correctas aparezcan dentro del top 6 de contexto.

**Acceptance Scenarios**:
1. **Given** una consulta que contiene el nombre exacto de una tabla o columna, **When** se ejecuta la búsqueda híbrida, **Then** la rama léxica le otorga una alta ponderación evitando que un embedding difuso la relegue.
2. **Given** una tabla recuperada en el top ranking, **When** el motor detecta relaciones de clave foránea predefinidas en `relations.yaml`, **Then** incluye automáticamente las tablas a 1 salto de distancia en el esquema de contexto si el presupuesto de tokens lo permite.

---

### User Story 4 - Harness de Evaluación Automatizado y Medición de `Recall@k` (Priority: P3)

Como equipo de ingeniería, quiero un conjunto de pruebas de evaluación automatizado (`tests/fixtures/schema_retrieval_eval.json`) con al menos 30 preguntas de negocio representativas y las tablas/columnas esperadas, ejecutable por CLI, que reporte métricas de `recall@k` (específicamente `recall@6`), para medir objetivamente la mejora de recuperación semántica antes y después de aplicar los cambios.

**Why this priority**: Evita regresiones a ciegas y proporciona una métrica empírica irrefutable del impacto de las mejoras en el sistema.

**Independent Test**:
1. Ejecutar el harness de evaluación: `python -m app.cli.eval_retrieval --k 6`.
2. Verificar que se evalúen las 30 preguntas del dataset de prueba y se imprima la tabla con aciertos, fallos y el porcentaje global de `recall@6`.

**Acceptance Scenarios**:
1. **Given** el archivo `tests/fixtures/schema_retrieval_eval.json` poblado con 30 casos reales en español, **When** se corre la evaluación, **Then** compara las tablas recuperadas por el pipeline híbrido contra las tablas esperadas y computa el `recall@6`.
2. **Given** la incorporación del conocimiento como código y valores categóricos, **When** se compara el resultado contra el baseline léxico puro, **Then** el `recall@6` muestra una mejora cuantitativa medible.

---

## 2. Requirements *(mandatory)*

### Functional Requirements

- **FR-001 (Estructura de Archivos de Conocimiento en Git)**:
  - El sistema DEBE soportar la lectura de archivos YAML bajo la ruta canónica `knowledge/<connection_slug>/`:
    - `relations.yaml`: Definición de claves foráneas y uniones lógicas (`source_table.source_column = target_table.target_column`, indicando `label_column` y descripción).
    - `examples.yaml`: Pares de preguntas en lenguaje natural y su consulta SQL `SELECT` verificada asociada.
    - `glossary.yaml`: Sinónimos y términos de negocio mapeados a tablas, columnas o expresiones de filtro.
- **FR-002 (Comando CLI Idempotente de Carga)**:
  - DEBE existir el comando `python -m app.cli.load_knowledge --connection <slug_or_id> [--check] [--explain]`:
    - Valida que la conexión exista en `database_connections`.
    - Valida que toda tabla y columna mencionada exista en `synced_tables` de esa conexión.
    - Valida toda consulta SQL en `examples.yaml` con `sqlglot` (restringido exclusivamente a sentencias `SELECT`).
    - Si se especifica `--explain`, ejecuta un `EXPLAIN` de la consulta contra la base de datos destino para asegurar validez de ejecución.
    - Si se especifica `--check`, realiza un simulacro (dry-run) sin invocar embeddings ni escribir en base de datos, retornando código de salida 0 si todo es válido o 1 si hay inconsistencias.
    - Calcula el hash SHA-256 de cada elemento y realiza upsert en `knowledge_vector_chunks` y `knowledge_documents` (no regenera embeddings si el hash no ha cambiado).
    - Asigna automáticamente `status = 'verified'`, `scope = 'global'` y `trigger_signal = 'code_yaml'`, registrando la operación en `knowledge_audit_logs`.
- **FR-003 (Enriquecimiento de Metadatos de Tabla)**:
  - Al vectorizar el esquema de una tabla, el documento textual DEBE incorporar:
    - Nombre de tabla y esquema.
    - Descripción o propósito de negocio (extraído de `glossary.yaml` o de comentarios SQL del motor).
    - Alias y sinónimos conocidos.
    - Lista de columnas con tipo de dato, indicación de PK/FK y comentarios de columna.
- **FR-004 (Indexación de Valores Categóricos de Baja Cardinalidad)**:
  - El sistema DEBE permitir indexar valores distintos para columnas categóricas explícitamente configuradas en el archivo YAML de la conexión (`categorical_columns`).
  - Límite perimetral: Máximo 200 valores distintos por columna. Si una columna excede 200 valores, se omite con una advertencia en el log.
  - Formato del chunk: `"En la tabla '{table}', la columna '{column}' tiene el valor '{value}'"`.
  - Protección estricta de privacidad: Queda terminantemente prohibido indexar columnas que contengan nombres propios, identificaciones personales, correos, contraseñas o datos financieros. Solo se indexan columnas declaradas explícitamente en la lista blanca de la conexión.
- **FR-005 (Búsqueda Híbrida con Fusión de Rangos RRF)**:
  - La recuperación semántica de esquema DEBE ejecutar dos ramas de búsqueda paralelas filtrando estrictamente por `connection_id`:
    1. **Rama Vectorial**: Búsqueda por similitud coseno con embeddings generados con prefijo `search_query:`.
    2. **Rama Léxica**: Búsqueda por coincidencia de texto completo o trigramas (`similarity()` o `ts_rank`).
  - Los resultados de ambas ramas DEBEN combinarse mediante el algoritmo **Reciprocal Rank Fusion (RRF)**:
    $$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + rank_m(d)}$$ (con constante $k = 60$).
- **FR-006 (Gobernanza y Aislamiento por Status y Scope)**:
  - Toda lectura y recuperación vectorial en `knowledge_vector_chunks` DEBE filtrar estrictamente por:
    - `connection_id = :conn_id`.
    - Reglas verificadas o activas: `status IN ('verified', 'candidate')` (excluyendo permanentemente `conflict`, `rejected`, `rolled_back`).
    - Alcance autorizado: `scope = 'global' OR (scope = 'user' AND user_id = :current_user)`.
- **FR-007 (Expansión Relacional de 1 Salto)**:
  - Tras seleccionar las top-$N$ tablas más relevantes mediante la búsqueda híbrida, el motor DEBE inspeccionar las relaciones declaradas en `relations.yaml` y anexar al contexto del esquema aquellas tablas secundarias vinculadas directamente a 1 salto de distancia que aporten claves foráneas necesarias para los `JOIN`.
- **FR-008 (Harness de Evaluación de Recuperación)**:
  - DEBE existir el archivo de pruebas `tests/fixtures/schema_retrieval_eval.json` con 30 preguntas de negocio en español y su lista de tablas y columnas esperadas.
  - DEBE existir el script ejecutable `python -m app.cli.eval_retrieval --k 6` que reporte el indicador `Recall@6`.

---

## 3. Success Criteria *(mandatory)*

- **SC-001 (Validación de Integridad en Carga de Código)**: El 100% de los intentos de cargar archivos YAML con tablas inexistentes, columnas no sincronizadas o consultas SQL con sintaxis no válida son rechazados por el CLI antes de cualquier persistencia.
- **SC-002 (Idempotencia y Eficiencia)**: Ejecutar el CLI de carga dos veces consecutivas sobre archivos YAML sin modificar toma menos de 1 segundo y realiza exactamente 0 llamadas de re-embedding a Ollama.
- **SC-003 (Recuperación por Valores)**: Con las tablas `carro`, `animal` y `sexo`, la pregunta *"dime cuántos perros hay"* posiciona a la tabla `animal` en el top 1 de tablas recuperadas.
- **SC-004 (Mejora Cuantitativa de Recall@6)**: La métrica de `Recall@6` evaluada sobre los 30 casos de `schema_retrieval_eval.json` alcanza o supera el **85%** de acierto en el top 6.
- **SC-005 (Aislamiento de Privacidad)**: Cero (0%) valores clasificados como datos personales o sensibles son indexados en la base de datos vectorial.
