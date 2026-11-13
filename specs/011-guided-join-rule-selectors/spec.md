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

---

## 7. Ampliación (pedida el 2026-11-13): Columna Foránea como selectpicker + Constructor de Consultas Grandes

### 7.1 Columna Foránea como selectpicker
El campo "Columna Foránea" ya es un `<select>` dependiente de la Tabla Origen (implementado en esta feature). Esta ampliación lo mantiene como requisito formal: **nunca texto libre**; siempre un selectpicker alimentado con las columnas reales de la tabla vectorizada elegida (FK primero, luego `*_id`).

### 7.2 Constructor de consultas grandes ("Consulta Enorme")
En el mismo apartado de enseñanza se añade una plantilla **"Consulta compuesta"** para armar consultas con muchas tablas, de dos maneras que se pueden combinar:

**A) Constructor visual (selectpickers)**
- Tabla base (selector paginado 10 en 10, igual que Tabla Origen).
- Lista repetible de **uniones**: tipo (`INNER JOIN`, `LEFT JOIN`, `RIGHT JOIN`, `FULL JOIN`, `CROSS JOIN`) + tabla (selector) + columna izquierda (selector) + columna derecha (selector). Al elegir la columna foránea se sugiere la tabla destino y la condición `ON`.
- Selección de columnas a mostrar (con alias), filtros `WHERE` (columna + operador + valor), `GROUP BY`/agregados, `ORDER BY` y `LIMIT`.
- **Bloques `UNION` / `UNION ALL`**: se pueden agregar varias consultas (cada una con su propio constructor) unidas entre sí; se valida que tengan el mismo número de columnas.
- Vista previa del SQL generado en tiempo real, resaltado y editable.

**B) Script SQL → estructura**
- Cuadro para pegar un `SELECT` largo (con `JOIN`, `LEFT/INNER`, `UNION`, subconsultas, CTEs `WITH`).
- El backend lo **parsea con `sqlglot`** (ya usado en `SQLGuardrail`) y lo convierte al mismo modelo visual (tablas, uniones, columnas, filtros), de modo que se pueda revisar/ajustar con selectpickers y volver a generar el SQL.
- Si una parte no se puede representar visualmente, se conserva como "bloque SQL crudo" sin perderla.

### 7.3 Requisitos funcionales adicionales
- FR-6: Modelo intermedio JSON (`query_blueprint`): `{base, joins[{type,table,left,right}], select[], where[], group_by[], order_by[], limit, unions[]}` como fuente única entre constructor visual y script SQL.
- FR-7: Endpoint `POST /training/query-blueprint/parse` (SQL → blueprint) y `POST /training/query-blueprint/compile` (blueprint → SQL por dialecto PostgreSQL/MariaDB).
- FR-8: Validación de seguridad: solo `SELECT`/`WITH`/`UNION`; se rechaza `INSERT/UPDATE/DELETE/DDL` (reutilizar `SQLGuardrail`); límite razonable de uniones/tablas (p. ej. 30) para no generar consultas inejecutables.
- FR-9: Validación contra el esquema: todas las tablas y columnas deben existir y estar vectorizadas; las que no, se marcan en rojo antes de guardar.
- FR-10: Al guardar se crea una regla `sql_example` verificada (SQL + título + explicación) vectorizada en pgvector, con el blueprint en `metadata` para poder reabrirla y editarla después.
- FR-11: Probar sin guardar: botón "Ejecutar con LIMIT 20" sobre la conexión (solo lectura) para comprobar que el SQL funciona antes de enseñarlo a la IA.

### 7.4 Criterios de aceptación adicionales
- Armar `users → role_user → roles` con dos `INNER JOIN` desde selectpickers y obtener el SQL correcto.
- Cambiar un join a `LEFT JOIN` regenera el SQL sin perder el resto.
- Pegar un script con `LEFT JOIN`, `INNER JOIN` y `UNION ALL` lo convierte al constructor y, al compilarlo de vuelta, produce SQL equivalente (misma estructura al reparsearlo).
- Un script con `DELETE` o `DROP` es rechazado con mensaje claro.
- Una tabla no vectorizada dentro del script se señala antes de guardar.

### 7.5 Riesgos
- Consultas muy grandes pueden ser lentas en la base remota: la prueba usa `LIMIT` y timeout corto.
- SQL con construcciones exóticas (funciones propias, window functions complejas) puede no mapear al modelo visual: se conserva como bloque crudo.
- Diferencias de dialecto (PostgreSQL vs MariaDB): compilar siempre con el dialecto de la conexión elegida.
- Alcance grande: se recomienda implementarlo como **fase 2** de la feature 011, después de validar los selectores básicos.
