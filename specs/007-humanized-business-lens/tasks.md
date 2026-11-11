# Tasks: Humanización de Datos, Enmascaramiento de Seguridad y Resolución Directa de Consultas

**Feature**: `specs/007-humanized-business-lens/spec.md`  
**Plan**: `specs/007-humanized-business-lens/plan.md`  
**Research**: `specs/007-humanized-business-lens/research.md`  

---

## Task Overview & Progress Tracking

| ID | Task | Subtasks | Status |
| :--- | :--- | :--- | :--- |
| **TASK-007-01** | **Filtro de Desambiguación Inequívoca y Lematización** | Mapeo de lemas y plurales en español, resolución directa sin aclaraciones innecesarias en `ask_chat.py` | [x] Completed |
| **TASK-007-02** | **Purga Estricta y Lista Negra de Columnas Sensibles** | Restricción en prompt SQL y purga en backend de `password`, `token`, `secret`, `hash` | [x] Completed |
| **TASK-007-03** | **Servicio de Humanización de Encabezados (`DataHumanizer`)** | Creación de `data_humanizer.py` con diccionario corporativo y formateador automático de columnas | [x] Completed |
| **TASK-007-04** | **Síntesis Conversacional en Lenguaje Humano (Cero Fuga Técnica)** | Ajuste estricto del prompt de síntesis en `AskChatUseCase` prohibiendo nombres de tablas y bases de datos | [x] Completed |
| **TASK-007-05** | **Prudencia en Activación de Gráficos** | Desactivar la forzatura de gráficos en consultas de listado simple en `analyze_columns_for_chart` | [x] Completed |
| **TASK-007-06** | **Pruebas Automatizadas y Verificación en Vivo** | Creación de `test_data_humanizer.py` y `test_sensitive_data_masking.py`, validación con la consulta de usuarios | [x] Completed |

---

## Detailed Task Breakdown

### TASK-007-01: Filtro de Desambiguación Inequívoca y Lematización
- [x] **01.1**: En `app/use_cases/ask_chat.py`, crear función helper `resolve_unambiguous_entity(prompt, synced_tables)`:
  - Definir lematización y diccionario de plurales comunes en español:
    - `usuarios`, `usuario`, `users` $\rightarrow$ `users`
    - `empresas`, `empresa`, `companies` $\rightarrow$ `companies`
    - `repuestos`, `repuesto`, `partes`, `parte` $\rightarrow$ `repuestos` o `parte_maquina`
    - `clientes`, `cliente`, `customers` $\rightarrow$ `clientes` / `customers`
  - Comprobar si las palabras del prompt contienen una coincidencia lematizada exacta con una única tabla sincronizada.
- [x] **01.2**: Si existe una única entidad coincidente, desactivar la bandera `is_ambiguous` y priorizar su esquema en el contexto de generación SQL sin emitir el evento `clarification`.

### TASK-007-02: Purga Estricta y Lista Negra de Columnas Sensibles
- [x] **02.1**: En `app/infrastructure/llm/sql_guardrail.py` y el prompt del generador SQL de `AskChatUseCase`:
  - Instruir taxativamente: `"PROHIBICIÓN ESTRICTA: NUNCA incluyas en el SELECT columnas que almacenen contraseñas, tokens de autenticación o secretos (ej: password, remember_token, gotify_pass, gotify_token, api_token, secret, hash, salt)."`
- [x] **02.2**: En `AskChatUseCase`, implementar método `sanitize_row_data(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]`:
  - Definir patrón regex `r"(?i)(password|passwd|pass|token|secret|hash|salt|remember_token)"`.
  - Purgar de inmediato cualquier clave coincidente tanto en `columns` como en cada fila devuelta antes de guardar en `QueryDatasetModel` y enviar al frontend.

### TASK-007-03: Servicio de Humanización de Encabezados (`DataHumanizer`)
- [x] **03.1**: Crear `app/infrastructure/analytics/data_humanizer.py`:
  - Diccionario de etiquetas corporativas en español:
    - `id` / `user_id` $\rightarrow$ `"ID"`
    - `name` / `user_name` $\rightarrow$ `"Nombre del Usuario"`
    - `username` / `user_username` $\rightarrow$ `"Usuario"`
    - `email` / `user_email` $\rightarrow$ `"Correo Electrónico"`
    - `created_at` / `user_created_at` $\rightarrow$ `"Fecha de Creación"`
    - `updated_at` / `user_updated_at` $\rightarrow$ `"Última Actualización"`
    - `company_name` $\rightarrow$ `"Empresa Asignada"`
    - `company_description` $\rightarrow$ `"Descripción de la Empresa"`
    - `status` $\rightarrow$ `"Estado"`
  - Lógica de fallback: limpiar prefijos (`tbl_`, `user_`, `company_`), reemplazar `_` por espacio y aplicar `title()`.
- [x] **03.2**: Integrar `DataHumanizer.humanize_columns(columns)` y `DataHumanizer.humanize_rows(rows)` en `AskChatUseCase` para proyectar datos legibles en `preview_rows` y `columns`.

### TASK-007-04: Síntesis Conversacional en Lenguaje Humano (Cero Fuga Técnica)
- [x] **04.1**: Refactorizar el prompt de redacción de síntesis ejecutiva en `AskChatUseCase`:
  - Reemplazar la mención cruda de `Se ejecutó una consulta en la base de datos...` por:
    `"Eres un asistente ejecutivo de negocios. Redacta en español un resumen conciso y natural sobre los datos encontrados. NUNCA menciones nombres físicos de tablas (como 'users', 'company_user' o 'companies'), ni nombres de base de datos o sintaxis SQL. Habla en términos de negocio (ej: 'Actualmente se registran 5 usuarios en el sistema...')."`
- [x] **04.2**: Verificar que el texto devuelto al usuario sea cálido, profesional y comprensible para cualquier persona sin conocimientos técnicos.

### TASK-007-05: Prudencia en Activación de Gráficos
- [x] **05.1**: En `AskChatUseCase.analyze_columns_for_chart`:
  - Si la consulta es un listado puro de entidades (`SELECT ... FROM users`) y el usuario no usó palabras como *"grafica"*, *"gráfico"*, *"diagrama"* ni pidió agregaciones, establecer `needs_field_selection = False`.
  - Evitar que se despliegue el selector de Eje X / Eje Y innecesariamente.

### TASK-007-06: Pruebas Automatizadas y Verificación en Vivo
- [x] **06.1**: Crear `tests/unit/test_data_humanizer.py` evaluando la traducción de columnas técnicas a etiquetas de negocio y el fallback heurístico.
- [x] **06.2**: Crear `tests/unit/test_sensitive_data_masking.py` asegurando que columnas como `user_password` o `remember_token` sean purgadas al 100%.
- [x] **06.3**: Ejecutar pytest y validar el reinicio del servicio FastAPI.
