# Tasks: Artefactos Visuales Bajo Demanda, Extracción Robusta de SQL y Grafo Completo de Seguridad RBAC

**Feature**: `specs/008-demand-visual-artifacts/spec.md`  
**Plan**: `specs/008-demand-visual-artifacts/plan.md`  

---

## Task Overview & Progress Tracking

| ID | Task | Subtasks | Status |
| :--- | :--- | :--- | :--- |
| **TASK-008-01** | **Extractor Resiliente de Bloques SQL (`SQLGuardrail`)** | Extraer bloques markdown ````sql```` o buscar inicio de `SELECT` aislando texto conversacional de Ollama | [x] Completed |
| **TASK-008-02** | **Lemas y Triggers de RBAC (`data_humanizer.py` e `intent_classifier.py`)** | Agregar soporte para roles, permisos, ecosistemas e interfaces en lemas y clasificador | [x] Completed |
| **TASK-008-03** | **Recuperación Completa de Grafo RBAC (`vector_repository.py`)** | Asegurar que RAG inyecte tablas puente intermedias (`role_user`, etc.) cuando la conexión es compacta | [x] Completed |
| **TASK-008-04** | **Activación Estricta Bajo Demanda de Artefactos Visuales (Backend y Frontend)** | Limitar el despliegue del Data Table y gráficos a peticiones explícitas (`dame la data`, `tabla`, etc.) | [x] Completed |
| **TASK-008-05** | **Pruebas y Verificación en Vivo** | Ejecución de suite de tests y validación de la consulta multi-tabla con Ollama | [x] Completed |

---

## Detailed Task Breakdown

### TASK-008-01: Extractor Resiliente de Bloques SQL (`SQLGuardrail`)
- [x] **01.1**: En `app/infrastructure/llm/sql_guardrail.py`, crear método helper `extract_sql_query(raw_text: str) -> str`:
  - Buscar bloques delimitados por ````sql ... ```` o ```` ... ```` en cualquier parte del texto.
  - Si no hay bloques de código, buscar la primera aparición de palabras clave `SELECT` hasta el punto y coma `;` o fin de texto.
  - Retornar únicamente la sentencia SQL limpia.
- [x] **01.2**: Integrar en `validate_and_sanitize()` antes del parser `sqlglot`.

### TASK-008-02: Lemas y Triggers de RBAC (`data_humanizer.py` e `intent_classifier.py`)
- [x] **02.1**: En `app/infrastructure/analytics/data_humanizer.py`:
  - Añadir en `ENTITY_LEMMA_MAP`:
    - `rol`, `roles`, `role` $\rightarrow$ `roles`
    - `permiso`, `permisos`, `permission`, `permissions` $\rightarrow$ `permissions`
    - `ecosistema`, `ecosistemas`, `ecosystem`, `ecosystems` $\rightarrow$ `ecosystems`
    - `interfaz`, `interfaces`, `interface` $\rightarrow$ `interfaces`
  - Añadir etiquetas en `BUSINESS_COLUMN_DICTIONARY` para `role_name`, `interface_name`, `permission_name`, etc.
- [x] **02.2**: En `app/use_cases/intent_classifier.py`:
  - Agregar patrones en `SQL_TRIGGER_PATTERNS`:
    - `r"\brol(es)?\b"`, `r"\bpermiso[s]?\b"`, `r"\becosistema[s]?\b"`, `r"\binterfa(z|ces)\b"`.
  - En `TABLE_TRIGGER_PATTERNS`:
    - Añadir soporte explícito para `r"\bdame\s+la\s+data\b"`, `r"\bdata\s+de\b"`, `r"\bexportar\s+a\s+excel\b"`.

### TASK-008-03: Recuperación Completa de Grafo RBAC (`vector_repository.py`)
- [x] **03.1**: En `VectorRepository.search_schema_with_relations()`:
  - Si el total de tablas de esquema en la base para la conexión es $\le 15$ tablas (como en `demo_manrique` que tiene 11), devolver todos los esquemas de la base para que la IA disponga del grafo relacional completo sin pérdida de tablas intermedias.
  - Si son más de 15 tablas, realizar la búsqueda por similitud vectorial + lemas léxicos en ambas direcciones (origen y destino de `foreign_keys`).

### TASK-008-04: Activación Estricta Bajo Demanda de Artefactos Visuales (Backend y Frontend)
- [x] **04.1**: En `AskChatUseCase`:
  - Enviar `wants_table` en el payload de `dataset` (`has_tabular_data` siempre es `True` en base de datos si hay filas, pero `wants_table: bool` indica si el usuario pidió verla explícitamente).
- [x] **04.2**: En `public/js/chat_stream.js`:
  - En `handleJobSSEEvent()` y al cargar el historial, evaluar si `dataset.wants_table` es `true` (o si `msg.wants_table` es `true`).
  - Si `wants_table` es `false`, renderizar únicamente una tarjeta ejecutiva compacta o botón colapsable discreto (*"Ver datos sin procesar"*) en lugar de expandir la tabla y gráficos de golpe.

### TASK-008-05: Pruebas y Verificación en Vivo
- [x] **05.1**: Ejecutar suite de pruebas unitarias (`pytest`).
- [x] **05.2**: Probar en vivo la consulta de los roles, interfaces y permisos de `Administrador` en `HOP` con Ollama.
