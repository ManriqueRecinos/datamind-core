# Quickstart: Chat File Attachments & Local CPU Analytics

**Guía de Verificación y Flujo Operativo**

---

## 1. Requisitos Previos y Dependencias Python

Instalar dependencias necesarias en el entorno virtual de `python-db`:

```powershell
Set-Location "D:\Python\python-db"
.\.venv\Scripts\pip.exe install duckdb polars fastexcel sqlglot python-magic-bin
```

---

## 2. Flujo de Prueba de Carga de Archivo (Fase 1)

1. **Subida de Archivo CSV de Prueba**:
   Enviar una petición multipart/form-data a FastAPI:
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/chat/attachments/upload" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: 00000000-0000-0000-0000-000000000001" \
     -F "file=@tests/fixtures/ventas_supertex_sample.csv" \
     -F "session_id=8b9826a4-c241-4c12-9c9e-52f01fdfba10"
   ```
   *Respuesta esperada*: `201 Created` con esquema inferido de columnas y tipos.

2. **Consulta en Lenguaje Natural sobre el Archivo**:
   Enviar consulta a través de `POST /chat/stream`:
   ```json
   {
     "prompt": "Calcula el total de ventas agrupado por categoría en el archivo adjunto",
     "session_id": "8b9826a4-c241-4c12-9c9e-52f01fdfba10",
     "attachment_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"]
   }
   ```
   *Comportamiento esperado*: DuckDB ejecuta la consulta SQL generada en su conexión en memoria y devuelve los tokens SSE con la explicación y el dataset de resultados.

---

## 3. Verificación de Guardarraíles y Seguridad

1. **Intento de Zip Bomb / Archivo > 15 MB**:
   - Subir un archivo de 20 MB.
   - *Resultado esperado*: Rechazo `422 Unprocessable Entity` con mensaje explícito.
2. **Inyección de SQL Malicioso**:
   - Simular un prompt que intente forzar un `DROP TABLE` o `COPY`.
   - *Resultado esperado*: `sqlglot` bloquea la consulta y rechaza la ejecución antes de tocar DuckDB.
3. **Aislamiento Multi-Usuario**:
   - Intentar consultar el archivo desde otra sesión con un `session_id` diferente.
   - *Resultado esperado*: Error `404 Not Found` (archivo no visible en la sesión actual).
