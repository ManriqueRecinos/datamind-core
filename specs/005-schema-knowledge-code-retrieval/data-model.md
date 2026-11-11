# Data Model: Chunks de Valores Categóricos y Conocimiento como Código

**Especificación**: `specs/005-schema-knowledge-code-retrieval`  
**Base de Datos**: PostgreSQL 17 + `pgvector`  

---

## 1. Extensiones al Modelo de Datos (`knowledge_vector_chunks`)

La tabla existente `knowledge_vector_chunks` aloja los nuevos chunks de valores categóricos (`trigger_signal = 'categorical_value'`), garantizando compatibilidad retroactiva total con el esquema de Fases 1 a 4:

### Definición de Columnas para Chunks de Valores:
- `id`: UUID (Clave Primaria).
- `document_id`: UUID (FK a `knowledge_documents` padre de la conexión).
- `connection_id`: UUID (FK estricta a `database_connections`).
- `chunk_index`: INTEGER.
- `chunk_text`: TEXT (Formato estandarizado: `"En la tabla '{target_entity}', la columna '{target_column}' tiene el valor categórico '{valor}'"`).
- `embedding`: VECTOR(768) (Generado con `nomic-embed-text` usando prefijo `search_document:`).
- `status`: VARCHAR(30) NOT NULL DEFAULT `'verified'`.
- `scope`: VARCHAR(20) NOT NULL DEFAULT `'global'`.
- `user_id`: VARCHAR(100) NULL DEFAULT `'system'`.
- `target_entity`: VARCHAR(100) NOT NULL (Nombre de la tabla, ej: `animal` o `inventario_partes`).
- `target_column`: VARCHAR(100) NOT NULL (Nombre de la columna, ej: `especie` o `es_usado`).
- `trigger_signal`: VARCHAR(50) NOT NULL DEFAULT `'categorical_value'` (o `'code_yaml'` para los archivos YAML).
- `prescriptive_condition`: VARCHAR(250) NULL (Condición SQL exacta asociada, ej: `especie = 'perro'`).
- `metadata`: JSONB con el payload enriquecido de seguridad y gobernanza:
  ```json
  {
    "category": "categorical_value",
    "target_entity": "animal",
    "target_column": "especie",
    "categorical_value": "perro",
    "cardinality": 3,
    "is_sensitive": false,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "source_file": "knowledge/demo_manrique/glossary.yaml"
  }
  ```

---

## 2. Restricciones y Reglas de Integridad

1. **Bandera de Sensibilidad (`is_sensitive`)**:
   - `is_sensitive = false` es obligatorio para persistir.
   - Si la columna coincide con patrones de datos personales (`nombre`, `correo`, `email`, `telefono`, `cedula`, `dpi`, `password`, `token`, `tarjeta`, `direccion`), el pipeline de carga aborta la inclusión de la columna.
2. **Límite de Cardinalidad**:
   - Se valida mediante `COUNT(DISTINCT columna) <= 200`. Si excede 200 valores únicos, se rechaza la indexación de esa columna para evitar saturar el espacio vectorial.
3. **Unicidad e Idempotencia (Upsert)**:
   - Se utiliza el hash SHA-256 de `(connection_id, target_entity, target_column, valor)` almacenado en `metadata->>'sha256'`.
   - Si el hash coincide, no se regenera el embedding ni se duplica la fila.
