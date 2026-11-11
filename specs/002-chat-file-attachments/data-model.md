# Data Model: Chat File Attachments

**Feature**: `002-chat-file-attachments`  
**Base de Datos**: PostgreSQL 17 (Metadatos persistentes) + DuckDB / Polars (Tablas analíticas en memoria)

---

## 1. Modelo Relacional en PostgreSQL (`chat_attachments`)

Almacena los metadatos persistentes de los archivos adjuntos cargados en las sesiones de chat.

```sql
CREATE TABLE IF NOT EXISTS chat_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    filename_original VARCHAR(255) NOT NULL,
    filename_storage VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_extension VARCHAR(10) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    row_count INTEGER NULL,
    column_count INTEGER NULL,
    sheet_names JSONB NULL, -- Para archivos Excel con múltiples hojas
    schema_metadata JSONB NOT NULL, -- Columnas, tipos inferidos (VARCHAR, BIGINT, DOUBLE, DATE, etc.) y sample
    status VARCHAR(30) NOT NULL DEFAULT 'uploaded', -- 'uploaded', 'ready', 'error'
    error_detail TEXT NULL,
    storage_path VARCHAR(500) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_chat_attachments_session_user ON chat_attachments(session_id, user_id);
CREATE INDEX idx_chat_attachments_expires ON chat_attachments(expires_at);
```

### Campos Clave de `schema_metadata` (JSONB)
```json
{
  "columns": [
    {
      "name": "id_producto",
      "type": "BIGINT",
      "nullable": false
    },
    {
      "name": "descripcion",
      "type": "VARCHAR",
      "nullable": true
    },
    {
      "name": "cantidad_unidades",
      "type": "BIGINT",
      "nullable": false
    },
    {
      "name": "precio_unitario",
      "type": "DOUBLE",
      "nullable": false
    },
    {
      "name": "fecha_produccion",
      "type": "DATE",
      "nullable": true
    }
  ],
  "sample_rows": [
    {"id_producto": 101, "descripcion": "Tela Algodón Premium", "cantidad_unidades": 500, "precio_unitario": 12.50, "fecha_produccion": "2026-03-01"}
  ],
  "summary_stats": {
    "total_rows": 12450,
    "total_columns": 5
  }
}
```

---

## 2. Modelos DuckDB en Memoria (Contexto Efímero de Sesión)

Para cada sesión activa que consulte archivos, se crea una vista o registro temporal en una instancia DuckDB aislada en memoria:

```sql
-- Para CSV / TSV (vistas virtuales en streaming):
CREATE VIEW view_att_<attachment_uuid_prefix> AS 
SELECT * FROM read_csv_auto('/absolute/path/to/storage/<user_id>/<session_id>/<attachment_id>.dat');

-- Para XLSX / XLS (registrado desde Polars DataFrame en memoria):
-- conn.register('view_att_<attachment_uuid_prefix>', polars_df)
```

**Regla de Naming**:
El alias de la tabla expuesto al LLM es sanitizado y humanizado (e.g. `datos_inventario` o `hoja_produccion`) para que el prompt del modelo genere consultas SQL naturales y precisas.

---

## 3. Relación con Mensajes de Chat (`chat_messages`)

El modelo existente `chat_messages` puede referenciar los archivos adjuntos que formaron parte de la interacción:
- Campo opcional en `metadata` (JSONB) de `chat_messages`:
  ```json
  {
    "attachment_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
    "query_executed_on_file": "SELECT sum(cantidad_unidades) FROM datos_inventario WHERE precio_unitario > 10.0"
  }
  ```
