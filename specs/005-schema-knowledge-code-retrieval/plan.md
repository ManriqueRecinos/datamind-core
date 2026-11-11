# Implementation Plan: Conocimiento como Código (YAML) y Recuperación Semántica Híbrida de Esquema

**Especificación**: `specs/005-schema-knowledge-code-retrieval/spec.md`  
**Research de Referencia**: `specs/005-schema-knowledge-code-retrieval/research.md`  
**Modelo de Datos**: `specs/005-schema-knowledge-code-retrieval/data-model.md`  
**Contratos**: `specs/005-schema-knowledge-code-retrieval/contracts/contracts_cli_and_yaml.md`  

---

## Technical Stack & Architecture

- **Backend**: FastAPI, SQLAlchemy 2.0 Async, Pydantic V2, Click / Typer / Argparse CLI.
- **Bases de Datos**: PostgreSQL 17 (`pgvector`, extensión `pg_trgm` para trigramas y similitud léxica).
- **Validadores de Sintaxis**: `sqlglot` (dialectos PostgreSQL / MySQL), PyYAML.
- **Modelos de IA**: Ollama con `nomic-embed-text` (prefijos `search_document:` y `search_query:`).
- **Algoritmo de Reranking**: Reciprocal Rank Fusion (RRF, $k = 60$).

---

## Fases de Implementación Secuenciales

### FASE 1: CLI de Carga de Conocimiento como Código y Validaciones Estrictas
**Objetivo**: Implementar el comando `load_knowledge` y los validadores de archivos YAML contra `synced_tables`.
- **Componentes**:
  - `app/cli/load_knowledge.py`: Entrypoint CLI con argumentos `--connection`, `--check` y `--explain`.
  - `app/infrastructure/knowledge/yaml_knowledge_parser.py`: Lector y validador de `relations.yaml`, `examples.yaml` y `glossary.yaml`.
  - Validación con `sqlglot` (solo `SELECT`, sin mutaciones) y verificación de existencia de tablas/columnas contra la tabla `database_connections.synced_tables`.
  - Upsert idempotente por hash SHA256 en `knowledge_vector_chunks` (`status = 'verified'`, `scope = 'global'`).
  - Registro de evento en `knowledge_audit_logs`.

### FASE 2: Enriquecimiento del Documento de Tabla para Text-to-SQL
**Objetivo**: Transformar el texto con el que se vectoriza cada tabla para incluir contexto semántico denso.
- **Componentes**:
  - `app/use_cases/sync_schema.py`: Modificar la plantilla de texto de cada tabla:
    - Nombre del esquema y tabla.
    - Descripción de negocio (desde `glossary.yaml` o comentarios SQL).
    - Sinónimos y alias conocidos.
    - Lista de columnas con tipo de dato, comentarios y relaciones de clave foránea conocidas.
  - Re-vectorización limpia de esquemas con prefijo `search_document:`.

### FASE 3: Chunks de Valores Categóricos de Baja Cardinalidad
**Objetivo**: Indexar valores de columnas categóricas para emparejar términos que no están en el nombre de la tabla.
- **Componentes**:
  - `app/infrastructure/knowledge/categorical_indexer.py`:
    - Introspección de valores únicos de columnas categóricas (`cardinality <= 200`).
    - Filtro de seguridad estricto que prohíbe columnas con nombres sospechosos de contener datos sensibles/personales.
    - Generación de chunks: `"En la tabla '{t}', la columna '{c}' tiene el valor '{v}'"` (`trigger_signal = 'categorical_value'`).
    - Inserción con `status = 'verified'`, `scope = 'global'`.

### FASE 4: Recuperación Híbrida (Vectorial + `pg_trgm`) y Expansión Relacional de 1 Salto
**Objetivo**: Motor de búsqueda híbrido con fusión RRF y expansión automática de tablas vinculadas por FK.
- **Componentes**:
  - Migración SQL para habilitar `CREATE EXTENSION IF NOT EXISTS pg_trgm;` e índice GIN sobre `knowledge_vector_chunks.chunk_text`.
  - `app/infrastructure/database/hybrid_schema_searcher.py`:
    - Consulta 1 (Vectorial): Similitud coseno con `nomic-embed-text` (`search_query:`).
    - Consulta 2 (Léxica): Búsqueda por trigramas con `similarity(chunk_text, :query)` o coincidencia exacta de identificadores.
    - Fusión RRF: Combina ambos rankings con $k=60$.
    - Filtro estricto por `connection_id`, `status IN ('verified', 'candidate')` y `scope IN ('global', 'user')`.
    - Expansión de 1 salto: Incorpora automáticamente tablas maestras/hijas conectadas por relaciones activas.

### FASE 5: Harness de Evaluación y Métricas `Recall@k`
**Objetivo**: Medir objetivamente la calidad de recuperación semántica sobre un set dorado de 30 consultas reales.
- **Componentes**:
  - `tests/fixtures/schema_retrieval_eval.json`: 30 preguntas de negocio con las tablas y columnas esperadas.
  - `app/cli/eval_retrieval.py`: Script evaluador que calcula `Recall@k` (específicamente `Recall@6`) reportando tabla comparativa de aciertos y precisión.
  - Pruebas unitarias en `tests/unit/test_yaml_knowledge_loader.py` y `test_hybrid_retrieval.py`.
