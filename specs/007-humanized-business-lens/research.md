# Research & Technical Decisions: Humanización, Seguridad y Desambiguación

**Feature**: `specs/007-humanized-business-lens`

---

## 1. Detección Léxica de Entidades Raíz vs Aclaración
- **Problema**: El vector similarity de nomic-embed-text dispersa semánticamente términos genéricos como "usuarios" entre `users`, `company_user` y `companies`.
- **Decisión**: Antes de evaluar el umbral de aclaración ($0.65$ o $\Delta \le 0.04$), aplicar una regla de lematización y coincidencia de nombres de tablas. Si las palabras clave del prompt normalizado contienen la raíz de una sola tabla sincronizada (`usuario` / `usuarios` $\rightarrow$ `users`, `cliente` / `clientes` $\rightarrow$ `customers` o `clientes`, `empresa` / `empresas` $\rightarrow$ `companies`), se asigna automáticamente como la tabla de enfoque principal y se desactiva la bandera de ambigüedad.

---

## 2. Purgado y Lista Negra de Columnas Sensibles
- **Problema**: `SELECT *` o selecciones automáticas exponen campos que nunca deben ser visibles para usuarios (`password`, `remember_token`, `gotify_pass`, etc.).
- **Decisión**:
  1. En el prompt de generación SQL, inyectar una regla estricta de exclusión:
     `"NUNCA selecciones columnas que contengan contraseñas, tokens de sesión o secretos (ej: password, remember_token, api_token, gotify_pass, secret, hash)."`
  2. En el backend (`AskChatUseCase` y `DataHumanizer`), aplicar un filtro posterior sobre el diccionario de filas:
     Cualquier columna cuyo nombre coincida con la expresión regular `(?i)(password|passwd|pass|token|secret|hash|salt|remember_token)` es purgada del dataset antes de almacenarlo y enviarlo al frontend.

---

## 3. Humanización de Encabezados (DataHumanizer)
- **Problema**: Las columnas aparecen con nombres técnicos de BD (`user_name`, `user_username`, `company_description`).
- **Decisión**:
  Implementar `DataHumanizer` en `app/infrastructure/analytics/data_humanizer.py` con dos niveles:
  1. **Diccionario de términos conocidos**:
     - `name` / `user_name` $\rightarrow$ *"Nombre"*
     - `username` / `user_username` $\rightarrow$ *"Usuario"*
     - `email` / `user_email` $\rightarrow$ *"Correo Electrónico"*
     - `created_at` / `user_created_at` $\rightarrow$ *"Fecha de Registro"*
     - `updated_at` $\rightarrow$ *"Última Actualización"*
     - `company_name` $\rightarrow$ *"Empresa Asignada"*
     - `description` $\rightarrow$ *"Descripción"*
     - `status` $\rightarrow$ *"Estado"*
  2. **Regla heurística de fallback**:
     - Remover prefijos comunes (`tbl_`, `col_`, `id_`, `user_`, `company_`).
     - Reemplazar guiones bajos por espacios y aplicar `title()` (ej: `fecha_ingreso` $\rightarrow$ *"Fecha Ingreso"*).

---

## 4. Ocultamiento de Metadatos Físicos en la Síntesis Conversacional
- **Problema**: El asistente redacta: *"La consulta SQL devolvió registros de la tabla users de la base de datos demo_manrique..."*.
- **Decisión**:
  Modificar el system prompt del sintetizador en `AskChatUseCase`:
  - Instrucción explícita: `"Habla en términos de negocio corporativo en español. NUNCA menciones nombres físicos de tablas (como 'users' o 'companies'), ni nombres técnicos de bases de datos. Di en su lugar 'los usuarios registrados', 'las empresas asociadas' o 'la información consultada'."`

---

## 5. Prudencia en la Activación de Gráficos
- **Problema**: Desplegar el Constructor de Gráficos para un listado de usuarios abruma al usuario.
- **Decisión**:
  En `analyze_columns_for_chart`:
  - Solo activar `needs_field_selection = True` si:
    a) El usuario lo pidió explícitamente (`wants_chart = True`), O
    b) Hay al menos 1 dimensión categórica y 1 métrica numérica agregable, Y la consulta no es un simple listado de entidades (`SELECT name, email FROM ...`).
