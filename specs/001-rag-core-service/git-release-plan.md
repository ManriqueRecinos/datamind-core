# Plan Maestro de Desvinculación Empresarial, Sanitización Open-Source y Reinicialización de Repositorios (`git-release-plan.md`)

**Fecha**: 2026-11-09  
**Autor Git**: `ManriqueRecinos` (`manrique.recinos23@gmail.com`)  
**Repositorios Destino**:
- **Python Backend**: `https://github.com/ManriqueRecinos/datamind-core.git`
- **Laravel Frontend**: `https://github.com/ManriqueRecinos/datamind-studio.git`

---

## 🎯 1. Objetivo del Plan

Desvincular **al 100%** ambos proyectos de cualquier dato, nombre, tabla, IP, puerto no estándar o dominio de la empresa actual para publicarlos como una herramienta **Open-Source genérica (`DataMind Core` + `DataMind Studio`)**, eliminando por completo el historial `.git` previo y recreando ambos repositorios desde cero con una secuencia limpia de commits (`commit` ➔ `push`).

---

## 🧹 2. Matriz de Auditoría y Limpieza de Datos Sensibles / Empresariales

Se han auditado todos los archivos de ambos proyectos y se reemplazarán las siguientes categorías de información:

| Categoría | Estado de Sanitización | Estándar Open-Source Aplicado (`DataMind`) |
| :--- | :--- | :--- |
| **Marca / Nombre** | Sanitizado al 100% | `DataMind`, `DataMind AI`, `DataMind Studio`, `--datamind-*`, `datamind-core` |
| **URLs de Repositorio** | Sanitizado al 100% | `https://github.com/ManriqueRecinos/datamind-studio.git` y `datamind-core.git` |
| **Nombre de Base de Datos** | Sanitizado al 100% | `analytics_db` / `target_database` (en docs, ejemplos y placeholders) |
| **Tablas de Ejemplo** | Sanitizado al 100% | `orders`, `customers`, `products`, `inventory_movements` (esquema universal de ejemplo) |
| **IPs y Subredes** | Sanitizado al 100% | `127.0.0.1` o `db.example.local` |
| **Puertos Estándar** | Sanitizado al 100% | Estándares oficiales: `3306` (MariaDB/MySQL) y `5432` (PostgreSQL) en código, `.env.example` y README |
| **Tokens y Contraseñas Ejemplo** | Sanitizado al 100% | `datamind_api_secret_token_2026`, `readonly_password` |
| **Archivos Descargados (`.xlsx`)** | Sanitizado al 100% | `datamind_report_{id}.xlsx` / `"DataMind AI - Reporte Analítico"` |
| **Datos Demo en `routes/web.php`** | Sanitizado al 100% | Recursos de TI / Analítica de Datos (`'Servidor Nodo GPU'`, `'Cluster PostgreSQL'`, códigos `'DM-001'`) |

---

## 🛠️ 3. Archivos Exactos a Modificar por Proyecto

### 3.1 En `D:\Python\python-db` (`datamind-core`)
1. **`app/main.py`**: Cambiar título a `"DataMind Core - Local AI RAG & Text-to-SQL Engine"` y `"service": "datamind-core"`.
2. **`app/core/config.py`**: Cambiar `api_key` default a `"datamind_api_secret_token_2026"` y `postgres_port` default a `5432`.
3. **`.env.example`**: Usar puertos estándar (`5432`, `3306`), `127.0.0.1`, `analytics_db` y credenciales genéricas.
4. **`app/use_cases/ask_chat.py`**: Reemplazar el fallback de tablas por ejemplos universales (`orders`, `customers`, `products`).
5. **`app/infrastructure/export/excel_generator.py` y `app/use_cases/export_excel.py`**: Cambiar nombre del reporte a `datamind_report_{timestamp}.xlsx` y encabezado a `"DataMind AI - Reporte Analítico de Datos"`.
6. **`tests/` (`test_chat_router.py`, `test_connections_router.py`, `test_quickstart_scenarios.py`, `test_config.py`, `test_excel_generator.py`, `test_logging.py`)**: Usar casos de prueba 100% genéricos (`orders`, `datamind_report_`).
7. **Documentación (`README.md`, `PLAN.md`, `REQUERIMENTS.MD`, `specs/001-rag-core-service/*`)**: Estandarizar toda referencia bajo la marca `DataMind`.

### 3.2 En `datamind-studio` (Frontend Laravel 13)
1. **`public/css/global_styles/globales.css` y `resources/css/global_styles/globales.css` y `resources/css/app.css`**:
   - Renombrar todas las variables CSS a `--datamind-*` y clases `.btn-datamind-*` / `.badge-datamind` / `.bg-datamind-*`.
2. **`resources/views/chat/index.blade.php`**:
   - Cambiar branding a **`DATAMIND AI`**, sugerencias rápidas a consultas SQL universales (`"¿Qué tablas están disponibles en la base de datos?"`, `"Muestra los últimos 5 registros..."`) y clases CSS a `datamind-*`.
3. **`resources/views/connections/index.blade.php` y `public/js/connections_manager.js`**:
   - Cambiar placeholders (`"Ej: ERP Ventas / Analytics DB"`, `"127.0.0.1"`, `"analytics_db"`), puertos estándar (`3306`, `5432`), y usar clases `datamind-*`.
4. **`resources/views/welcome.blade.php`, `resources/views/components/data-table.blade.php` y `routes/web.php`**:
   - Usar un catálogo genérico de **DataMind Studio** (`DM-001`, módulos de datos y analítica).
5. **`app/Services/FastApiClient.php`, `app/Http/Controllers/ChatController.php`, `config/services.php`, `.env.example`**:
   - Token por defecto `datamind_api_secret_token_2026` y archivo `datamind_report_{datasetId}.xlsx`.
6. **`README.md`, `AGENTS.md`, `CLAUDE.md` y `tests/Feature/ChatTest.php`**:
   - Actualizar toda la documentación y pruebas a **DataMind Studio**.

---

## 🔍 4. Compuerta de Verificación Cero Rastro (`Zero-Trace Gate`)

Antes de ejecutar `git init`, correremos un comando de auditoría automática en ambos directorios para verificar que el resultado sea **estrictamente 0 coincidencias** de datos propietarios en todos los archivos rastreables por Git.

---

## 🚀 5. Reinicialización de Git desde Cero y Secuencia de Commits (`Commit & Push`)

### Paso Previo en Ambos Proyectos:
Eliminar por completo el directorio `.git` (`Remove-Item -Recurse -Force .git`) para destruir cualquier historial previo, ejecutar `git init`, configurar:
```powershell
git config user.name "ManriqueRecinos"
git config user.email "manrique.recinos23@gmail.com"
git branch -M main
```

### 🐍 5.1 Secuencia de Commits en `datamind-core` (`https://github.com/ManriqueRecinos/datamind-core.git`)

| # | Archivos | Mensaje de Commit | Push |
| :-: | :--- | :--- | :--- |
| **1** | `.gitignore`, `.env.example`, `requirements.txt`, `pytest.ini`, `PLAN.md`, `REQUERIMENTS.MD`, `.specify/`, `specs/`, `.agents/`, `skills/` | `chore(setup): initialize project configuration, dependencies and speckit specifications` | `git push -u origin main --force` |
| **2** | `app/core/*`, `app/domain/*` | `feat(domain): add core settings, structured logging with masking and domain entities` | `git push origin main` |
| **3** | `app/infrastructure/__init__.py`, `app/infrastructure/database/*` | `feat(database): implement async pgvector HNSW repository and dynamic multi-db adapters` | `git push origin main` |
| **4** | `app/infrastructure/llm/*`, `app/infrastructure/parsers/*`, `app/infrastructure/export/*` | `feat(infrastructure): add Ollama client, sqlglot AST guardrail, text chunker and Excel generator` | `git push origin main` |
| **5** | `app/use_cases/*` | `feat(use-cases): implement RAG ingestion, dynamic connection manager, hybrid chat and Excel export` | `git push origin main` |
| **6** | `app/api/*`, `app/main.py` | `feat(api): expose FastAPI v1 REST endpoints, connection manager and SSE streaming pipeline` | `git push origin main` |
| **7** | `tests/*`, `README.md` | `test(suite): add comprehensive unit, contract and integration test suites with open-source docs` | `git push origin main` |

---

### 🌐 5.2 Secuencia de Commits en `datamind-studio` (`https://github.com/ManriqueRecinos/datamind-studio.git`)

| # | Versión | Archivos | Mensaje de Commit | Push |
| :-: | :---: | :--- | :--- | :--- |
| **1** | `v1.0.0` | Base Laravel 13, `config/`, `bootstrap/`, plugins locales `public/`, `.gitignore`, `.env.example` | `chore(scaffold): initialize Laravel 13 offline-ready base template (v1.0.0)` | `git push -u origin main --force` |
| **2** | `v1.0.1` | `app/Services/FastApiClient.php`, `app/Http/Controllers/ChatController.php`, `app/Http/Controllers/DatabaseConnectionController.php`, `routes/` | `feat(backend): add FastApiClient service, Chat and DatabaseConnection controllers (v1.0.1)` | `git push origin main` |
| **3** | `v1.0.2` | `globales.css`, `resources/css/app.css`, `chat_stream.js`, `connections_manager.js`, `resources/views/*` | `feat(ui): implement DataMind global color palette, chat streaming view and schema explorer (v1.0.2)` | `git push origin main` |
| **4** | `v1.0.3` | `tests/*`, `phpunit.xml`, `README.md`, `AGENTS.md`, `CLAUDE.md` | `test(suite): add feature tests and comprehensive open-source README documentation (v1.0.3)` | `git push origin main` |
