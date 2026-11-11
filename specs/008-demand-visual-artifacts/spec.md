# Spec: Artefactos Visuales Bajo Demanda, Extracción Robusta de SQL y Grafo Completo de Seguridad RBAC

**Feature Branch**: `008-demand-visual-artifacts`  
**Fecha**: 2026-11-11  
**Estado**: Especificado  

---

## 1. Contexto y Objetivos del Negocio

DataMind AI cuenta actualmente con un ecosistema de tablas relacionales vectorizadas en `pgvector` que incluye catálogos maestros de usuarios, empresas y un modelo RBAC completo (`users`, `roles`, `role_user`, `permissions`, `ecosystems`, `interfaces`, `role_ecosystem`, `role_interface`, `role_interface_permission`).

Para garantizar una experiencia de usuario (UX) corporativa intuitiva, no invasiva y de alta precisión:
1. **Artefactos Visuales Únicamente Bajo Demanda**:
   - Actualmente, cada vez que una consulta devuelve registros, el sistema despliega automáticamente una tabla de datos completa (`Data Table`), opciones de exportación (Excel, CSV) y configurador de gráficos, saturando la vista conversacional.
   - **Nuevo comportamiento**: La respuesta debe ser **100% narrativa en lenguaje de negocios, viñetas o tarjetas ejecutivas por defecto**. Los componentes visuales enriquecidos (`Data Table`, botón de descarga a Excel o gráficos) **únicamente deben renderizarse si el usuario los solicitó explícitamente** mediante instrucciones directas (ej: *"dame la data de..."*, *"muéstrame la tabla..."*, *"genera un gráfico..."*, *"exporta a excel..."*).
2. **Extracción Robusta de Consultas SQL (`SQLGuardrail`)**:
   - Los modelos LLM locales (como Ollama / Qwen) con frecuencia anteponen o posponen texto explicativo antes de su bloque de código (ej: *"Para responder a la solicitud, necesitamos realizar varias consultas... ```sql ... ```"*).
   - El guardrail debe extraer limpiamente el bloque SQL mediante expresiones regulares antes del análisis sintáctico con `sqlglot`, evitando falsos errores de sintaxis (`Invalid expression / Unexpected token`).
3. **Expansión del Grafo Relacional RBAC y Vocabulario de Negocio**:
   - Registrar en `ENTITY_LEMMA_MAP` y `SQL_TRIGGER_PATTERNS` las entidades y palabras clave: `rol`, `roles`, `permiso`, `permisos`, `ecosistema`, `ecosistemas`, `interfaz`, `interfaces`.
   - Cuando el usuario consulte entidades relacionadas por múltiples tablas intermedias, asegurar la recuperación de todas las tablas puente necesarias para construir los `JOINs` requeridos.

---

## 2. Requerimientos Funcionales

- **RF-008-01 (Detección Estricta de Demanda de Artefactos Visuales)**:
  - En `IntentClassifier.detect_output_format()`:
    - `wants_table` será `True` si y solo si el usuario pide explícitamente tablas o datos en bruto: `"dame la data"`, `"muéstrame la tabla"`, `"en formato tabular"`, `"exportar a excel"`, `"descargar datos"`.
    - `wants_chart` será `True` si y solo si el usuario pide gráficos o diagramas: `"gráfico"`, `"diagrama"`, `"gráfico de barras"`, etc.
    - Si el usuario solo hace una pregunta analítica o consultiva (*"¿Qué rol tiene X?"*, *"¿Qué roles existen?"*, *"Dime los usuarios de tal empresa"*), `output_mode` será `"text_only"`.
- **RF-008-02 (Respuesta Narrativa Ejecutiva vs Tabular)**:
  - En `AskChatUseCase`: si `wants_table` es `False` y `wants_chart` es `False`, el evento SSE `dataset` NO activará el renderizado de la tabla en el frontend, manteniendo el dataset en segundo plano para exportación voluntaria pero sin desplegar la tabla en la pantalla del chat.
  - La síntesis conversacional presentará viñetas claras, resúmenes y formato legible sin exponer nombres físicos de BD.
- **RF-008-03 (Parser y Extractor Resiliente en `SQLGuardrail`)**:
  - `SQLGuardrail.validate_and_sanitize()` debe implementar un extractor de bloques ````sql ... ```` o un extractor de primer bloque `SELECT ...` que descarte cualquier texto conversacional previo o posterior.
- **RF-008-04 (Cobertura Completa de RBAC en RAG)**:
  - Enriquecer `VectorRepository.search_schema_with_relations()` para que cuando el catálogo de tablas vectorizadas de la conexión sea compacto ($\le 15$ tablas), o cuando se detecten consultas de seguridad/permisos, incluya las tablas puente intermedias (`role_user`, `role_interface_permission`, `role_ecosystem`, `role_interface`).
  - Registrar lemas en `data_humanizer.py` y triggers en `intent_classifier.py` para `roles`, `permissions`, `ecosystems` e `interfaces`.
