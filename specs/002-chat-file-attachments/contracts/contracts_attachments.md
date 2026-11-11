# Contratos de API: Adjuntos de Chat & Inferencia Tabular

**Versión**: 1.0.0  
**Servicio**: FastAPI (`python-db`) ↔ Cliente Web (`Laravel 12 / chat_stream.js`)

---

## 1. POST /api/v1/chat/attachments/upload

Carga y parseo inicial de un archivo adjunto para una sesión de chat.

- **Content-Type**: `multipart/form-data`
- **Headers**:
  - `Authorization: Bearer <API_KEY>`
  - `X-User-Id: <UUID>`

### Parámetros Form-Data
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | `UploadFile` (Binary) | Sí | Archivo tabular (`.csv`, `.tsv`, `.xlsx`, `.xls`). |
| `session_id` | `UUID` | Sí | ID de la sesión de chat a la que pertenece el adjunto. |
| `selected_sheet` | `string` | No | Nombre de la hoja de cálculo (para Excel). Si no se envía, toma la primera hoja. |

### Respuestas

#### `201 Created`
```json
{
  "success": true,
  "data": {
    "attachment_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "session_id": "8b9826a4-c241-4c12-9c9e-52f01fdfba10",
    "filename_original": "inventario_telas_marzo.xlsx",
    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "file_size_bytes": 1048576,
    "row_count": 12500,
    "column_count": 6,
    "sheet_names": ["Inventario_Almacen", "Precios_Vigentes"],
    "active_sheet": "Inventario_Almacen",
    "schema_metadata": {
      "columns": [
        {"name": "codigo_rollo", "type": "VARCHAR"},
        {"name": "tipo_tela", "type": "VARCHAR"},
        {"name": "metros_disponibles", "type": "DOUBLE"},
        {"name": "costo_metro", "type": "DOUBLE"},
        {"name": "almacen", "type": "VARCHAR"},
        {"name": "fecha_ingreso", "type": "DATE"}
      ],
      "sample_rows": [
        {
          "codigo_rollo": "ROL-001",
          "tipo_tela": "Algodón 100%",
          "metros_disponibles": 120.5,
          "costo_metro": 8.75,
          "almacen": "Planta 1",
          "fecha_ingreso": "2026-02-15"
        }
      ]
    },
    "expires_at": "2026-03-13T15:00:00Z"
  }
}
```

#### `400 Bad Request / 422 Unprocessable Entity` (Validaciones Perimetrales)
```json
{
  "detail": "El archivo excede el límite máximo de filas permitido (máximo: 50,000, detectadas: 78,400).",
  "code": "FILE_LIMIT_EXCEEDED",
  "timestamp": "2026-03-11T15:00:00Z"
}
```

#### `415 Unsupported Media Type` (MIME Inválido)
```json
{
  "detail": "Tipo de archivo no permitido. Solo se aceptan archivos tabulares .csv, .tsv, .xlsx y .xls (MIME detectado: image/png).",
  "code": "INVALID_MIME_TYPE",
  "timestamp": "2026-03-11T15:00:00Z"
}
```

---

## 2. GET /api/v1/chat/sessions/{session_id}/attachments

Lista todos los archivos adjuntos activos de una sesión.

### Respuestas
#### `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "attachment_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "filename_original": "inventario_telas_marzo.xlsx",
      "file_size_bytes": 1048576,
      "row_count": 12500,
      "column_count": 6,
      "created_at": "2026-03-11T14:30:00Z"
    }
  ]
}
```

---

## 3. DELETE /api/v1/chat/attachments/{attachment_id}

Elimina manualmente un archivo adjunto antes de que expire.

### Respuestas
#### `200 OK`
```json
{
  "success": true,
  "message": "Archivo adjunto eliminado correctamente."
}
```

---

## 4. Modificación de POST /chat/stream para Consulta sobre Archivos

El contrato existente de streaming SSE (`POST /api/v1/chat/stream`) se amplía con el campo opcional `attachment_ids`:

```json
{
  "prompt": "¿Cuáles son los 5 tipos de tela con más metros disponibles en el archivo de inventario?",
  "session_id": "8b9826a4-c241-4c12-9c9e-52f01fdfba10",
  "attachment_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"]
}
```

El flujo SSE continúa utilizando los eventos estándar (`session`, `token`, `dataset`, `done`, `error`) con el resultado analítico computado en DuckDB.
