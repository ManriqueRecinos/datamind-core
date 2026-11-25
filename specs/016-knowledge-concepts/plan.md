# Implementation Plan: Clasificación de Aprendizajes por Concepto

**Branch**: `016-knowledge-concepts` | **Date**: 2026-11-25  
**Constitution**: `.specify/memory/constitution-knowledge-concepts.md`

## Summary

Implementar la taxonomía de **Conceptos** (`nombre_corto`, `nombre_largo`, `descripcion`) para clasificar los aprendizajes en el Centro de Aprendizaje (`/training`), vectorizando cada concepto en chunks dentro de `pgvector` y vinculándolo en los metadatos de cada regla o ejemplo SQL.

---

## Phase 1: Backend (`d:\Python\python-db` - FastAPI + PostgreSQL)

1. **Modelo de Datos (`app/infrastructure/database/models.py`)**:
   - Agregar `KnowledgeConceptModel` (`knowledge_concepts`: `id`, `short_name` único, `long_name`, `description`, `created_at`).
2. **Endpoints en `app/api/v1/routers/knowledge.py`**:
   - `GET /api/v1/knowledge/concepts`: lista todos los conceptos ordenados por `long_name`.
   - `POST /api/v1/knowledge/concepts`: crea el concepto en PostgreSQL y lo vectoriza en chunks mediante `IngestKnowledgeUseCase` (`category="concept_definition"`).
   - En los endpoints de creación de conocimiento/reglas, aceptar `concept_id` opcional e inyectar `concept_id`, `concept_short_name` y `concept_long_name` en `metadata` y en el texto a vectorizar.

---

## Phase 2: Frontend (`d:\Laravel\Supertex AI` - `/training`)

1. **Rutas y Controlador (`routes/web.php`, `TrainingController.php`, `FastApiClient.php`)**:
   - Exponer `GET /training/concepts` y `POST /training/concepts` hacia FastAPI.
2. **Vista y JS (`/training`)**:
   - Agregar SelectPicker de **Concepto** en el formulario de **Nueva Regla** junto al botón **"Crear nuevo"**.
   - Agregar modal `#modalCreateConcept` (`nombre_corto`, `nombre_largo`, `descripcion`) que crea el concepto vía AJAX y lo selecciona automáticamente en el SelectPicker.
   - Mostrar badge del concepto en cada tarjeta de la galería.
3. **Control de Versiones**:
   - Actualizar `README.md` y `AGENTS.md` de `Supertex AI` (`1.0.8` → `1.0.9`).
