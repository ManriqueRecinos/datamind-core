# Data Model & Esquemas: Resiliencia, Ambigüedad y Cola de Términos

**Especificación**: `specs/006-conversational-resilience-and-ambiguity-repair`  
**Base de Datos**: PostgreSQL 17  

---

## 1. Tabla de Términos No Entendidos (`unresolved_query_terms`)

```sql
CREATE TABLE IF NOT EXISTS unresolved_query_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id UUID NOT NULL REFERENCES database_connections(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    prompt TEXT NOT NULL,
    extracted_term VARCHAR(150) NOT NULL,
    candidate_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolved_target VARCHAR(150) NULL,
    resolved_by VARCHAR(100) NULL,
    resolved_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT chk_unresolved_status CHECK (
        status IN ('pending', 'resolved', 'ignored')
    )
);

CREATE INDEX IF NOT EXISTS idx_uqt_conn_status ON unresolved_query_terms(connection_id, status);
CREATE INDEX IF NOT EXISTS idx_uqt_created_at ON unresolved_query_terms(created_at DESC);
```

---

## 2. Esquema del Evento SSE de Aclaración (`clarification_request`)

Emitido hacia el frontend cuando la certeza es baja o hay colisión:

```json
{
  "event": "clarification",
  "data": {
    "type": "clarification_request",
    "question": "Para darte un resultado exacto, ¿a cuál de las siguientes tablas te refieres?",
    "extracted_term": "repuestos",
    "options": [
      {
        "id": "inventario_repuestos.inventario_partes",
        "label": "Inventario de Repuestos Físicos (Bodega)",
        "description": "Stock físico, costos, existencias y ubicaciones en estante"
      },
      {
        "id": "hop.parte_maquina",
        "label": "Catálogo de Ingeniería HOP (Especificaciones)",
        "description": "Número de parte del fabricante y compatibilidad con máquinas"
      }
    ],
    "original_prompt": "¿Cuántos repuestos tenemos activos?"
  }
}
```

---

## 3. Integración con Candidatos de Conocimiento (`knowledge_vector_chunks`)

Al responder el usuario la aclaración:
- `target_entity`: La tabla elegida por el usuario (ej: `inventario_repuestos.inventario_partes`).
- `target_column`: La columna principal de búsqueda o nombre.
- `trigger_signal`: `'clarification_resolved'`.
- `status`: `'candidate'`.
- `scope`: `'user'`.
- `user_id`: El identificador del usuario autenticado.
- `prescriptive_condition`: Condición o sinónimo asociado.
- Registro inmutable en `knowledge_audit_logs`.
