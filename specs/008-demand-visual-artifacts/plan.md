# Plan: Artefactos Visuales Bajo Demanda, Extracción Robusta de SQL y Grafo Completo de Seguridad RBAC

**Feature**: `specs/008-demand-visual-artifacts/spec.md`  
**Fecha**: 2026-11-11  

---

## 1. Arquitectura Técnica y Módulos a Modificar

1. **`app/infrastructure/llm/sql_guardrail.py`**:
   - Extractor regex para bloques ````sql ... ```` o detección de inicio con `SELECT` cuando el modelo incluye texto explicativo.
2. **`app/infrastructure/analytics/data_humanizer.py`**:
   - Incorporación de lemas y traducciones de negocio para `roles`, `permissions`, `ecosystems`, `interfaces`, `role_user`, etc.
3. **`app/use_cases/intent_classifier.py`**:
   - Ampliación de `SQL_TRIGGER_PATTERNS` para reconocer preguntas sobre roles, permisos y accesos como consultas de datos (`data_query`).
   - Refinamiento de `detect_output_format()` para activar `wants_table` únicamente con frases imperativas explícitas como `"dame la data"`, `"muéstrame la tabla"`, `"genera tabla"`, `"exportar a excel"`.
4. **`app/infrastructure/database/vector_repository.py`**:
   - Mejora de `search_schema_with_relations()` para conexiones con $\le 15$ tablas vectorizadas o coincidencia de entidades RBAC, garantizando que el grafo incluya las tablas puente intermedias.
5. **`app/use_cases/ask_chat.py` y `public/js/chat_stream.js`**:
   - Control del flag `wants_table` en el evento SSE `dataset` y en la respuesta JSON para que la tabla interactiva se muestre sólo si el usuario la demandó.
