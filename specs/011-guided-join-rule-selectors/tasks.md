# Tasks: 011-guided-join-rule-selectors

Repositorio: `D:\Laravel\Supertex AI` (FastAPI no cambia).

## Fase 1: Backend Laravel
- [x] T001 `TrainingController::vectorizedTables`: leer `synced_tables` de la conexión (`listConnections`), normalizar a minúsculas, filtrar por nombre (contiene), paginar de 10 en 10; devolver `{data, page, has_more, total}`.
- [x] T002 `TrainingController::tableColumns`: `Cache::remember("training.tables.{id}", 600, getConnectionTables)`; devolver `{columns:[{name,type,is_fk,references}], primary_key, label_suggestion}`; 404 si la tabla no está vectorizada.
- [x] T003 `routes/web.php`: `GET /training/vectorized-tables` y `GET /training/vectorized-tables/columns` en el grupo `training` (nombres `training.tables` y `training.columns`).
- [x] T004 Invalidar la caché `training.tables.{id}` al vectorizar, actualizar o eliminar una conexión (`DatabaseConnectionController`).

## Fase 2: Componente JS
- [x] T005 `public/js/table_picker.js`: selector con búsqueda (debounce 300 ms), 10 por página, botón "Cargar más", estados cargando/vacío/error, API `init(el,{connectionId,onSelect})` y `reset()`.

## Fase 3: Vista `/training`
- [x] T006 `training/index.blade.php`: reemplazar `#trainSourceTable` y `#trainTargetTable` por contenedores del picker, y `#trainSourceCol` y `#trainLabelCol` por `<select>` deshabilitados al inicio (mantener los mismos `id` para el guardado).
- [x] T007 `training_view.js`: encadenar origen → columnas; columna con FK → preselecciona maestra y su PK; maestra → columnas legibles con `name/nombre/descripcion` preseleccionado.
- [x] T008 `training_view.js`: reset total de los 4 selectores al guardar y al cambiar de conexión; validar que los 4 valores existan antes de enviar; enlace a `/connections/explorer` si no hay tablas vectorizadas.

## Fase 4: Modal heredado
- [x] T009 `chat/partials/training-center-modal.blade.php` y `training_manager.js`: reutilizar `table_picker.js` y la misma lógica encadenada.

## Fase 5: Verificación
- [x] T010 Pruebas de los endpoints: 28 tablas → página 1 = 10, página 3 = 8; búsqueda solo por nombre; tabla no vectorizada → 404.
- [ ] T011 Prueba manual con SUMAIE: `role_user` → `role_id` → sugiere `roles`; guardar crea la misma regla `custom_relation` de hoy.
- [ ] T012 Commit en `D:\Laravel\Supertex AI`.

## Dependencias
T001–T003 → T005 → T006–T008 → T009 → T010–T012. T004 es paralelizable con T005.

---

# FASE 2: Constructor de Consultas Grandes

Repos: FastAPI `D:\Python\python-db` (backend) y Laravel `D:\Laravel\Supertex AI` (proxy + UI).

## 2a. Backend FastAPI (python-db)
- [ ] T020 `app/domain/query_blueprint.py`: modelos Pydantic (`Blueprint`, `JoinSpec`, `UnionSpec`, `SelectItem`, `WhereItem`) con validación: tipos de join (`INNER|LEFT|RIGHT|FULL|CROSS`), máx. 30 tablas y 10 uniones.
- [ ] T021 `app/use_cases/query_blueprint.py::compile`: blueprint -> SQL con el constructor de `sqlglot` (select/from/join/where/group/order/limit/union), dialecto `postgres` o `mysql`.
- [ ] T022 `parse`: SQL -> blueprint recorriendo el AST (`exp.Select`, `exp.Join` side/kind, `exp.Union`, `exp.With`); lo no mapeable pasa a `raw_blocks`.
- [ ] T023 `validate`: comprobar que tablas y columnas existen y están vectorizadas (usar `synced_tables` + introspección); devolver la lista de elementos inválidos; verificar mismo número de columnas entre bloques `UNION`.
- [ ] T024 `dry_run`: pasar por `SQLGuardrail.validate_and_sanitize` (solo `SELECT/WITH/UNION`), forzar `LIMIT 20`, timeout corto, solo lectura.
- [ ] T025 `app/api/v1/routers/query_blueprint.py`: `POST /query-blueprint/{parse|compile|validate|dry-run}`; registrar en `api_router`.
- [ ] T026 `tests/unit/test_query_blueprint.py`: ida y vuelta SQL -> blueprint -> SQL; LEFT/INNER/RIGHT/FULL; `UNION ALL`; CTE -> `raw_blocks`; rechazo de `DELETE/DROP`; tabla no vectorizada marcada; límites de tamaño.

## 2b. Proxy Laravel + constructor visual
- [ ] T030 `FastApiClient`: `parseBlueprint`, `compileBlueprint`, `validateBlueprint`, `dryRunBlueprint`.
- [ ] T031 `TrainingController`: 4 acciones proxy y rutas `POST /training/query-blueprint/{parse|compile|validate|dry-run}`.
- [ ] T032 `public/js/query_builder.js`: estado del blueprint en memoria, tabla base con `TablePicker`.
- [ ] T033 Filas repetibles de unión: tipo + tabla (`TablePicker`) + columna izquierda/derecha (selects desde `/training/vectorized-tables/columns`); una columna FK autocompleta tabla destino y `ON`.
- [ ] T034 Selección de columnas con alias, filtros `WHERE`, `ORDER BY` y `LIMIT`.
- [ ] T035 Vista previa del SQL en vivo (debounce 300 ms, llama a `compile`) y botón "Probar (LIMIT 20)" con resultado en tabla.
- [ ] T036 `training/index.blade.php`: nueva plantilla "Consulta compuesta" con pestañas Constructor / Script SQL (la pestaña Script llega en 2c).

## 2c. UNION, script SQL y guardado
- [ ] T040 Bloques `UNION`/`UNION ALL` anidados, cada uno con su propio constructor y aviso si difiere el número de columnas.
- [ ] T041 Pestaña Script SQL: textarea -> "Convertir a constructor" (`parse`), rellena el constructor; elementos inválidos en rojo.
- [ ] T042 `raw_blocks`: mostrar los fragmentos no representables como bloque SQL editable que se conserva al compilar.
- [ ] T043 Guardar: crear regla `sql_example` con `sql_query` y `blueprint` en `metadata` (vía `/chat/training/train`); reabrir una regla del catálogo reconstruye el constructor.
- [ ] T044 Reset total del constructor al guardar y al cambiar de conexión.

## 2d. Pulido
- [ ] T050 Agregados y `GROUP BY` (COUNT/SUM/AVG/MIN/MAX) en el constructor.
- [ ] T051 Alias de tablas automáticos y mensajes de error claros por cada regla de validación.
- [ ] T052 Prueba con SUMAIE: `users -> role_user -> roles` con dos `INNER JOIN`; cambiar uno a `LEFT JOIN`; script con `LEFT`, `INNER` y `UNION ALL` ida y vuelta; script con `DELETE` rechazado.
- [ ] T053 Commits en ambos repos y actualización de este archivo.

## Dependencias
T020 -> T021, T022 -> T023, T024 -> T025 -> T026 -> T030, T031 -> T032 -> T033 -> T034 -> T035 -> T036 -> T040 -> T041 -> T042 -> T043 -> T044 -> T050 -> T051 -> T052 -> T053. T021 y T022 son paralelizables.
