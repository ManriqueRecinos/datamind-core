# Research & Technical Decisions: Chat File Attachments & Local CPU Analytics

**Feature**: `002-chat-file-attachments`  
**Estado**: Validado y Alineado con Arquitectura Local CPU

---

## 1. Motores de Procesamiento Tabular en CPU

### DuckDB para CSV / TSV (Streaming Real)
- **Por qué DuckDB**: DuckDB es un motor SQL columnar embebido de alto rendimiento en C++ que opera dentro del proceso de Python. Implementa lectura en streaming real mediante `read_csv_auto()`, permitiendo proyectar, filtrar y agregar datos directamente sin cargar todo el archivo en la memoria del runtime de Python.
- **Gestión de Memoria y Concurrencia**:
  - DuckDB permite configurar topes estrictos de memoria por conexión: `SET max_memory = '256MB';` y `SET threads = 2;`.
  - Soporta creación de vistas virtuales sin costo de copia en RAM: `CREATE VIEW session_tab AS SELECT * FROM read_csv_auto('/path/to/file.csv');`.
- **Aislamiento**: Cada sesión/usuario puede operar con una conexión aislada (`duckdb.connect(':memory:')`), garantizando que las tablas temporales y alias no se filtren entre distintas sesiones del chat.

### Polars con Motor Calamine para XLSX / XLS (Lectura Completa con Límites)
- **Aclaración Arquitectónica Fundamental sobre XLSX**:
  - A diferencia de CSV/TSV, un archivo `.xlsx` es un contenedor comprimido ZIP que almacena múltiples documentos XML (`sheet1.xml`, `sharedStrings.xml`, `styles.xml`).
  - **No existe streaming lineal real en XLSX**: Para reconstruir las filas, el descompresor debe cargar y parsear las cadenas compartidas (`sharedStrings.xml`) y el árbol de celdas. Prometer streaming sobre XLSX induciría a error arquitectónico.
- **Solución con Polars + Calamine**:
  - `calamine` es una biblioteca nativa en Rust compilada para Python (`fastexcel` / `polars[calamine]`) que lee hojas Excel con un consumo de RAM y latencia drásticamente menores que `openpyxl` o `pandas`.
  - **Flujo de Ejecución**:
    1. Polars lee la hoja de cálculo con el motor `calamine`: `df = pl.read_excel(file_path, sheet_name=sheet, engine="calamine")`.
    2. Se validan las filas en memoria (`len(df) <= MAX_ROWS`).
    3. Para consultas SQL en lenguaje natural, el DataFrame de Polars se registra transparentemente en la conexión DuckDB de la sesión (`conn.register('session_excel_tab', df)`), permitiendo ejecutar las mismas consultas SQL unificadas que sobre CSV.

---

## 2. Validación Perimetral de Seguridad & MIME Real

El sistema no confía en la extensión del archivo ni en el encabezado `Content-Type` enviado por el navegador cliente:
1. **Magic Bytes (MIME Real con `python-magic` / inspección binaria)**:
   - CSV / TSV: Validación de texto plano / UTF-8 / ASCII; detección de caracteres binarios o nulos (`\0`) que denoten ejecutables encubiertos.
   - XLSX: Verificación de firma ZIP PK (`50 4B 03 04`) y presencia obligatoria de la estructura OpenXML (`[Content_Types].xml`, `xl/workbook.xml`).
   - XLS: Verificación de estructura OLE2 / Compound File Binary (`D0 CF 11 E0 A1 B1 1A E1`).
2. **Mitigación de Riesgos Específicos**:
   - **Zip Bombs (Decompression Bombs)**: Al abrir un XLSX/XLS, se inspecciona el tamaño descomprimido declarado en las cabeceras del zip antes de extraer. Si el ratio de compresión excede 100:1 o el tamaño descomprimido estimado supera 50 MB, el archivo es rechazado de inmediato.
   - **Macros y Fórmulas Maliciosas (CSV / Excel Injection)**:
     - El procesamiento se realiza a nivel de datos puros. No se evalúan macros de VBA.
     - Si el archivo contiene celdas que inician con `=`, `+`, `-`, `@`, `|`, no se interpretan como comandos DDE ni ejecutables del sistema operativo; DuckDB y Polars las tratan estrictamente como cadenas de texto plano (`VARCHAR`).
   - **Path Traversal**: El archivo físico se almacena en el disco del servidor con un nombre generado aleatoriamente (`uuid4().hex`) en un directorio aislado con permisos restringidos (`chmod 0700`), sin usar el nombre original proporcionado por el usuario.

---

## 3. Sandbox de Solo Lectura para SQL Generado sobre los Datos

Cuando el usuario formula una pregunta en lenguaje natural, el LLM local (`qwen2.5:3b`) genera una consulta SQL dirigida a la vista temporal del archivo:
- **Inspección AST y Guardarraíles de Consulta**:
  - Se utiliza `sqlglot` para validar que la consulta generada sea única y exclusivamente una sentencia `SELECT`.
  - Se prohíben estrictamente cláusulas o comandos destructivos o de acceso al sistema: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `COPY`, `ATTACH`, `DETACH`, `PRAGMA`, `INSTALL`, `LOAD`.
- **Restricciones DuckDB en Ejecución**:
  - DuckDB se configura con sandboxing interno para deshabilitar acceso a disco no autorizado desde SQL:
    ```sql
    SET enable_external_access = false;
    ```
  - Timeout de ejecución estricto (e.g. 3.0 segundos) en el hilo de análisis para evitar bucles o productos cartesianos infinitos.
  - Inyección forzada de cláusula `LIMIT 500` si la consulta no define un límite superior.

---

## 4. Política de Retención y Recolección de Basura (Garbage Collection)

1. **Almacenamiento Temporal Organizado**:
   - Estructura en disco: `storage/app/attachments/{user_id}/{session_id}/{attachment_id}.dat`.
2. **Ciclo de Limpieza Síncrona**:
   - Cuando el usuario elimina una conversación en Laravel, el endpoint `DELETE /chat/sessions/{id}` notifica al backend FastAPI para purgar el directorio `storage/app/attachments/{user_id}/{session_id}/` y cerrar las conexiones en memoria.
3. **Tarea Recurrente de Limpieza Asíncrona (Cron / Scheduler)**:
   - Un script programado ejecuta periódicamente (e.g. cada hora) la eliminación de archivos con `created_at` superior a 48 horas o asociados a sesiones marcadas como inactivas/expiradas.

---

## 5. Plan de Benchmarking con Archivos Reales de Supertex

Queda prohibido asumir cifras teóricas. Se ejecutará una batería de benchmarks automatizada:
1. **Dimensiones de Archivos de Prueba**:
   - *Pequeño*: 1,000 filas, 10 columnas (~150 KB).
   - *Mediano*: 15,000 filas, 25 columnas (~3 MB).
   - *Límite*: 50,000 filas, 40 columnas (~12 MB).
2. **Métricas a Capturar en Hardware CPU**:
   - Tiempo de inferencia de esquema y carga en memoria (ms).
   - Consumo pico de RAM (RSS antes vs. RSS durante vs. RSS después de garbage collection con `tracemalloc` o `psutil`).
   - Latencia de inferencia de consulta SQL con `qwen2.5:3b` en CPU.
   - Tiempo de ejecución de consulta analítica en DuckDB / Polars.
