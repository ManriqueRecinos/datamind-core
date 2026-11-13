# Feature Specification: 011-guided-join-rule-selectors

## 1. Problema
En el Centro de Aprendizaje (`/training`), la plantilla **Relaciones JOIN** pide escribir a mano cuatro campos de texto: Tabla Origen, Columna Foránea, Tabla Maestra y Campo Legible. Es fácil equivocarse con nombres de tablas/columnas y la IA aprende una relación inválida.

## 2. Objetivo
Reemplazar esos campos de texto por selectores alimentados con las **tablas ya vectorizadas** de la conexión elegida, con carga paginada de 10 en 10 para no sobrecargar el servidor.

## 3. Comportamiento esperado
1. **Conexión**: el selector de base de datos del formulario define de qué conexión salen las tablas.
2. **Tabla Origen**: selector con búsqueda, lista solo tablas vectorizadas (`synced_tables`), 10 por página con "Cargar más" / scroll infinito y búsqueda en servidor por nombre de tabla.
3. **Columna Foránea**: se habilita al elegir la tabla origen; carga las columnas de esa tabla (se sugieren primero las que terminan en `_id` o son llave foránea).
4. **Tabla Maestra**: mismo selector paginado (10 en 10) de tablas vectorizadas.
5. **Campo Legible**: se habilita al elegir la tabla maestra; lista sus columnas, preseleccionando `name`/`nombre`/`descripcion` si existen.
6. **Autocompletado**: si la columna elegida tiene una FK real hacia una tabla vectorizada, se preselecciona la Tabla Maestra y su llave primaria.
7. El payload enviado (`source_table`, `source_column`, `target_table`, `label_column`) no cambia, por lo que el backend FastAPI sigue igual.
8. Validación: no se puede guardar si faltan los 4 valores o si origen = maestra sin confirmar.

## 4. Requisitos funcionales
- FR-1: `GET /training/vectorized-tables?connection_id=&page=&per_page=10&search=` → `{data:[{table_name, schema_name, columns_count}], has_more}`.
- FR-2: `GET /training/vectorized-tables/columns?connection_id=&table=` → `{columns:[{name,type,is_fk,references}], primary_key}`; cacheado en Laravel (p. ej. 10 min) para no reintrospectar la base remota en cada clic.
- FR-3: Los selectores muestran estados de carga, vacío ("No hay tablas vectorizadas") y error.
- FR-4: Respetar el reset total del formulario tras guardar (regla previa) incluyendo los selectores.
- FR-5: Solo lectura sobre la base remota; sin escrituras.

## 5. Criterios de aceptación
- Con SUMAIE (28 tablas vectorizadas) se ven 10 tablas, y "Cargar más" trae las siguientes 10.
- Buscar `user` filtra por nombre de tabla únicamente.
- Elegir `role_user` → columnas de `role_user`; elegir `role_id` → sugiere `roles`.
- Guardar crea la misma regla `custom_relation` que hoy.

## 6. Notas y riesgos
- La introspección de columnas es lo costoso: por eso se pide por tabla y bajo demanda, no todo de golpe.
- Si la conexión no tiene tablas vectorizadas, se muestra un enlace a "Esquemas y Tablas" para vectorizar.
- Aplica a la vista `/training` y al modal heredado `chat.partials.training-center-modal`, que debería compartir el mismo componente.
