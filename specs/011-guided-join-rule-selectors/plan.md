# Implementation Plan: 011-guided-join-rule-selectors

## Hallazgos del código actual
- `GET /api/v1/connections` ya devuelve `synced_tables` (lista de nombres vectorizados) → la lista paginada de tablas **no requiere introspección**: se pagina en Laravel sobre ese arreglo.
- Las columnas/FK solo salen de `GET /api/v1/connections/{id}/tables` (introspección completa, pesada). Se llamará **una vez por conexión y se cacheará** (10 min); cada selector de columnas se sirve desde esa caché.
- Formulario: campos de texto `#trainSourceTable`, `#trainSourceCol`, `#trainTargetTable`, `#trainLabelCol` en `resources/views/training/index.blade.php`, lógica en `public/js/training_view.js` (y duplicada en `training_manager.js` + modal `chat/partials/training-center-modal.blade.php`). El payload `source_table/source_column/target_table/label_column` no cambia → **FastAPI intacto**.

## Cambios (solo Laravel / Supertex AI)
1. **`TrainingController`** (2 métodos nuevos, rutas bajo `training.`):
   - `vectorizedTables(Request)` → `GET /training/vectorized-tables?connection_id&page&per_page=10&search`: toma `synced_tables` de la conexión, filtra por nombre (contiene, case-insensitive), pagina de 10 en 10, devuelve `{data:[{table_name}], page, has_more, total}`.
   - `tableColumns(Request)` → `GET /training/vectorized-tables/columns?connection_id&table`: lee la respuesta cacheada de `getConnectionTables` (`Cache::remember("training.tables.{id}", 600, …)`), devuelve `{columns:[{name,type,is_fk,references}], primary_key, label_suggestion}`; 404 claro si la tabla no está vectorizada.
2. **`routes/web.php`**: ambas rutas en el grupo `training` (solo lectura; protegidas igual que el resto de `/training`).
3. **Componente JS compartido `public/js/table_picker.js`**: selector con búsqueda (debounce 300 ms), lista de 10, botón "Cargar más", estados cargando/vacío/error. Usado por Tabla Origen y Tabla Maestra.
4. **Vista `training/index.blade.php`**: sustituir los 4 `<input>` por: picker de Tabla Origen, `<select>` de Columna Foránea (deshabilitado hasta elegir tabla), picker de Tabla Maestra, `<select>` de Campo Legible. Mantener los mismos `id` para no tocar la lógica de guardado.
5. **`training_view.js`**: encadenar eventos (origen → columnas; columna con FK → preselecciona maestra y su PK; maestra → columnas legibles con `name/nombre/descripcion` preseleccionado); reset total de los selectores tras guardar y al cambiar de conexión; validar los 4 valores antes de enviar.
6. **Modal heredado** (`training-center-modal` + `training_manager.js`): reutilizar el mismo componente para no tener dos formularios distintos.

## Verificación
- Pest/PHPUnit (o `php artisan route:list` + peticiones reales): paginación (página 1 = 10, página 3 = 8 de 28), búsqueda solo por nombre, tabla no vectorizada → 404.
- Prueba manual con SUMAIE: `role_user` → columna `role_id` → sugiere `roles`; guardar crea la regla `custom_relation` igual que hoy.

## Riesgos
- Primera carga de columnas lenta (introspección remota): mitigado con caché y spinner; invalidar caché al vectorizar/editar la conexión.
- `synced_tables` puede venir con minúsculas/schema; normalizar al comparar.
- Sin tablas vectorizadas: mostrar enlace a `/connections/explorer`.
