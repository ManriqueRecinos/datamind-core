# Implementation Plan: Humanización de Datos, Seguridad y Resolución Directa de Consultas

**Especificación**: `specs/007-humanized-business-lens/spec.md`  
**Research de Referencia**: `specs/007-humanized-business-lens/research.md`  

---

## Technical Stack & Architecture

- **Backend**: FastAPI, SQLAlchemy 2.0 Async, Pydantic V2.
- **Seguridad**: Regex-based sensitive data purifier y `SQLGuardrail` anti-proyección.
- **Analytics & Humanizer**: `app/infrastructure/analytics/data_humanizer.py`.
- **Frontend**: Laravel 12 Blade (`chat_stream.js`): visualización de etiquetas humanas y filtrado visual.

---

## Fases de Implementación Secuenciales

### FASE 1: Filtro de Desambiguación Inequívoca y Lematización en Español
- En `app/use_cases/ask_chat.py`:
  - Implementar normalización y extracción de lemas de las tablas sincronizadas de la conexión activa.
  - Mapear plurales y singulares (`usuarios` $\rightarrow$ `users`, `empresas` $\rightarrow$ `companies`, `repuestos` $\rightarrow$ `repuestos`, `clientes` $\rightarrow$ `clientes`/`customers`).
  - Si el usuario menciona inequívocamente la entidad raíz principal, **desactivar la aclaración** y proceder directamente a la generación de SQL.

### FASE 2: Purga Estricta de Columnas Sensibles (Seguridad Corporativa)
- En `app/infrastructure/llm/sql_guardrail.py` y `app/use_cases/ask_chat.py`:
  - Inyectar instrucción negativa obligatoria en el prompt SQL: prohibido proyectar `password`, `remember_token`, `gotify_*`, `secret`, `hash`.
  - Crear interceptor de seguridad en el backend: antes de persistir o transmitir cualquier fila de datos, purgar todas las claves que coincidan con la lista negra de datos sensibles.

### FASE 3: Módulo de Humanización de Encabezados (`DataHumanizer`)
- Crear `app/infrastructure/analytics/data_humanizer.py`:
  - Mapeo de términos de negocio para columnas comunes.
  - Transformación heurística de nombres técnicos a etiquetas ejecutivas con formato de título en español.
  - Aplicar en la respuesta de `AskChatUseCase` para que `columns` y las filas del dataset contengan nombres humanos.

### FASE 4: Refactorización de la Síntesis Conversacional (Cero Fuga Técnica)
- En `AskChatUseCase`:
  - Ajustar el prompt de síntesis del LLM (`qwen2.5:3b`):
    - Prohibir terminantemente mencionar nombres de tablas (`users`, `companies`), motores o nombres de base de datos.
    - Exigir tono ejecutivo de negocios (ej. *"Actualmente se encuentran registrados **5 usuarios** en el sistema..."*).

### FASE 5: Prudencia en Gráficos y Pruebas Automatizadas
- En `analyze_columns_for_chart`:
  - Desactivar la forzatura de gráficos en consultas de listado puro de entidades que carecen de métricas numéricas acumulativas.
- Desarrollar pruebas unitarias en `tests/unit/test_data_humanizer.py` y `test_sensitive_data_masking.py`.
