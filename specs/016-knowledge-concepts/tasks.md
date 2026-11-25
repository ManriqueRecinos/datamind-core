# Tasks: Clasificación de Aprendizajes por Concepto

**Plan**: `specs/016-knowledge-concepts/plan.md`

---

## Phase 1: Backend (`d:\Python\python-db`)

- [ ] **T001** Crear `KnowledgeConceptModel` (`knowledge_concepts`: `id`, `short_name`, `long_name`, `description`, `created_at`) en `app/infrastructure/database/models.py` y asegurar creación de tabla.
- [ ] **T002** Agregar endpoints `GET /api/v1/knowledge/concepts` y `POST /api/v1/knowledge/concepts` (vectorizando el concepto en chunks vía `IngestKnowledgeUseCase`) en `app/api/v1/routers/knowledge.py`.
- [ ] **T003** Aceptar `concept_id` opcional al crear aprendizajes en `knowledge.py` e inyectar `concept_id`, `concept_short_name` y `concept_long_name` en `metadata`.

---

## Phase 2: Frontend (`d:\Laravel\Supertex AI`)

- [ ] **T004** Agregar rutas `GET /training/concepts` y `POST /training/concepts` en `routes/web.php`, `TrainingController.php` y `FastApiClient.php`.
- [ ] **T005** Agregar SelectPicker de **Concepto**, botón **"Crear nuevo"** y modal `#modalCreateConcept` en la vista de `/training` y su JS (`training_manager.js` / `training_view.js`).
- [ ] **T006** Actualizar la versión en `README.md` y `AGENTS.md` de `Supertex AI` (`1.0.8` → `1.0.9`).
