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
