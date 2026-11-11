# Feature Specification: Humanización de Datos, Enmascaramiento de Seguridad y Resolución Directa de Consultas

**Feature Branch**: `007-humanized-business-lens`  
**Created**: 2026-11-11  
**Status**: Draft Specification  

---

## 1. Contexto y Problema

Durante las pruebas con usuarios reales (ej. consulta *"¿Qué usuarios hay creados actualmente?"*), se identificaron tres fallas críticas de experiencia y seguridad:

1. **Aclaraciones Innecesarias ante Preguntas Claras**:  
   La IA no reconoció que *"usuarios"* se refería directamente a la entidad `users`, abriendo un diálogo de aclaración redundante entre `users`, `company_user` y `companies`. Si la pregunta coincide de forma inequívoca con la entidad principal (lema o raíz singular/plural), la consulta debe resolverse de inmediato sin interrumpir al usuario.
2. **Fuga de Metadatos y Nombres Crudos de Base de Datos**:  
   El asistente expone nombres físicos de tablas (`users`, `companies`, `demo_manrique`), alias técnicos (`user_name`, `company_name`) y detalles internos que un colaborador de producción o negocio no conoce ni debe ver por motivos de seguridad y confidencialidad.
3. **Exposición de Campos Sensibles en Consultas Generadas**:  
   El generador SQL proyectó columnas críticas como contraseñas (`user_password`), tokens de sesión (`remember_token`) y credenciales de servicios (`gotify_pass`, `gotify_app_token`), lo cual viola las directivas de seguridad corporativa.
4. **Despliegue Forzado de Constructores de Gráficos**:  
   Para una simple pregunta de listado/conteo, el sistema forzó un módulo de selección de Eje X y Eje Y, abrumando al usuario con herramientas analíticas innecesarias.

---

## 2. Historias de Usuario y Escenarios de Aceptación *(mandatory)*

### User Story 1 - Resolución Directa de Consultas Inequívocas (Priority: P1)
Como usuario de DataMind AI, cuando formulo una pregunta evidente sobre una entidad del sistema (ej: *"¿Qué usuarios hay creados actualmente?"*, *"dime los clientes"* o *"lista de productos"*), quiero que el asistente responda de inmediato con la información solicitada sin pedir aclaraciones innecesarias, para obtener agilidad y fluidez en mis consultas diarias.

**Acceptance Criteria**:
- **AC-1.1**: Si el lema o raíz léxica de las palabras clave del usuario coincide unívocamente con el nombre o etiqueta de negocio de una tabla sincronizada (ej: `usuarios` $\leftrightarrow$ `users`), el sistema DEBE proceder directamente a la generación de SQL sin solicitar aclaración.
- **AC-1.2**: Solo se activa la aclaración si existen dos entidades del mismo nivel jerárquico en conflicto semántico real (ej: `clientes_nacionales` vs `clientes_exportacion`).

---

### User Story 2 - Humanización de Entidades y Columnas (Priority: P1)
Como colaborador operativo o directivo sin conocimientos técnicos de programación, quiero que las respuestas del asistente, los mensajes y las tablas muestren nombres claros en español de negocios (ej: *"Nombre del Usuario"*, *"Correo"*, *"Empresa Asignada"* en lugar de `user_name`, `user_email`, `companies.name`), y que nunca me hable con tecnicismos como nombres de tablas o esquemas de bases de datos.

**Acceptance Criteria**:
- **AC-2.1**: Toda columna proyectada en la tabla interactiva y en el dataset DEBE ser formateada automáticamente a un título legible en español (removiendo prefijos como `user_`, `tbl_`, guiones bajos y aplicando capitalización adecuada o mapeo desde el diccionario).
- **AC-2.2**: El texto generado por el LLM en la síntesis conversacional tiene **prohibido** mencionar nombres de tablas crudas (ej. *"de la tabla users"* $\rightarrow$ *"del catálogo de usuarios"*).
- **AC-2.3**: Las opciones de aclaración (cuando sean estrictamente necesarias) deben mostrar etiquetas humanas y descripciones funcionales, ocultando la estructura física de la base de datos.

---

### User Story 3 - Enmascaramiento y Lista Negra de Campos Sensibles (Priority: P1)
Como oficial de seguridad y administrador del sistema, quiero garantizar que ninguna consulta generada por la IA incluya jamás contraseñas, hashes, tokens de autenticación o secretos en las respuestas al usuario, tanto en la sentencia SQL como en los datos devueltos.

**Acceptance Criteria**:
- **AC-3.1**: `SQLGuardrail` y el prompt del generador SQL deben aplicar una **lista negra estricta** (`password`, `pass`, `token`, `secret`, `hash`, `salt`, `remember_token`, `auth`, `private_key`).
- **AC-3.2**: Si por alguna razón la base de datos devuelve una columna sensible, el backend DEBE filtrarla y eliminarla del dataset antes de registrarlo en caché o enviarlo al frontend.
- **AC-3.3**: Cero (0%) credenciales, hashes o tokens deben ser visibles en el chat o en las exportaciones de Excel.

---

### User Story 4 - Activación Condicional y Prudente de Gráficos (Priority: P2)
Como usuario que realiza consultas informativas o de inventario, no quiero que aparezca un constructor de gráficos si mi consulta no involucra una métrica temporal o de distribución, recibiendo únicamente un resumen ejecutivo y una tabla limpia.

**Acceptance Criteria**:
- **AC-4.1**: El Asistente de Selección de Campos y el gráfico solo deben mostrarse si el usuario pidió explícitamente un gráfico (*"grafica"*, *"gráfico"*, *"diagrama"*) o si la consulta contiene una agrupación natural por fecha o categoría con métricas numéricas comparables.
- **AC-4.2**: Para consultas de listado directo (ej: *"quiénes son"*, *"qué usuarios hay"*, *"mostrar datos"*), el asistente debe limitarse a la síntesis ejecutiva y la vista previa tabular.

---

## 3. Requisitos Funcionales y Técnicos

- **FR-001 (Humanizador de Encabezados de Datos)**:
  - Crear servicio `DataHumanizer` en `app/infrastructure/analytics/data_humanizer.py`.
  - Convierte nombres de columnas técnicas (`user_name`, `created_at`, `current_company_id`) a etiquetas empresariales legibles (*"Nombre de Usuario"*, *"Fecha de Registro"*, *"Empresa"*).
- **FR-002 (Purga de Columnas Sensibles en Backend)**:
  - En `SQLGuardrail`, instruir al LLM a no proyectar columnas protegidas.
  - En `QueryDatasetModel` y en la serialización del chat, filtrar cualquier clave presente en `SENSITIVE_COLUMN_PATTERNS`.
- **FR-003 (Directiva Anti-Exposición de Nombres Físicos en Síntesis)**:
  - El system prompt del sintetizador en `AskChatUseCase` debe prohibir explícitamente frases como *"de la tabla <nombre>"* o *"en la base de datos <nombre>"*, reemplazándolas por lenguaje natural corporativo.
- **FR-004 (Filtro de Desambiguación Inequívoca)**:
  - Previo a evaluar umbrales de aclaración, verificar si el prompt contiene lemas que coinciden al 100% con la entidad principal. Si es así, saltar la aclaración.

---

## 4. Criterios de Éxito

- **SC-001**: 0% de campos sensibles (`password`, `token`, etc.) expuestos en datasets, tablas o texto de respuesta.
- **SC-002**: 0 menciones de nombres de tablas crudas con sintaxis técnica (`users`, `company_user`) en las respuestas de cara al usuario.
- **SC-003**: 100% de consultas unívocas sobre entidades sincronizadas se responden directamente sin pedir aclaraciones innecesarias.
- **SC-004**: Encabezados de tablas presentados con formato legible y humano en la interfaz web.
