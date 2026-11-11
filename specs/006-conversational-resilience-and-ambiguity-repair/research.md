# Research & Decisiones Técnicas: Resiliencia Conversacional y Reparación de Consultas

**Feature**: `specs/006-conversational-resilience-and-ambiguity-repair`  
**Fecha**: 2026-11-11  

---

## 1. Evaluación de Costo de Reintentos con `qwen2.5:3b` en CPU y Análisis de Modelo Especializado

### Análisis de Rendimiento de `qwen2.5:3b` en CPU Local
- **Velocidad de Inferencia en CPU (Intel Core i7/Xeon)**:
  - Generación de Text-to-SQL (prompt corto + salida estructurada $\sim 40$ tokens): **1.2 a 2.4 segundos**.
  - Si el primer intento falla, un reintento enfocado exclusivamente en corregir el nombre de una columna o un `JOIN` con un prompt conciso toma en promedio **1.5 segundos**.
  - **Costo total acumulado de 2 reintentos**: $\approx 3.0$ a $4.5$ segundos de CPU adicionales. Esto se mantiene cómodamente dentro del presupuesto interactivo del usuario sin activar timeouts de socket.

### ¿Conviene un Modelo más Grande (ej: `qwen2.5:7b` o `14b`) solo para la Reparación?
- **Evaluación**:
  1. **Consumo de Memoria RAM**: Cargar un modelo de 7B o 14B en paralelo en Ollama requiere entre 5.5 GB y 10 GB adicionales de memoria RAM en el host. En un entorno de CPU compartida sin GPU, esto generaría contención severa de memoria y riesgo de swapping (desaceleración de 10x).
  2. **Latencia de Conmutación de Modelos (Model Cold-Swap)**: Si Ollama no tiene cargado el modelo más grande en memoria, descargarlo y cambiar de modelo tarda entre 4 y 8 segundos en disco/CPU solo para la carga inicial.
  3. **Capacidad de Corrección de `qwen2.5:3b`**: Dado que el mensaje de error de PostgreSQL/MySQL es determinista (ej: `no existe la columna «id_parte»`), el modelo de 3B posee capacidad de sobra para mapear `id_parte` a `id_parte_maquina` cuando se le proporciona el error exacto junto con el esquema focalizado.

**Decisión**: **Mantener `qwen2.5:3b` para todo el pipeline**, incluyendo los reintentos de reparación. Para maximizar su precisión en el reintento, el prompt de reparación no le pide volver a pensar toda la lógica de negocio; solo le pide sustituir el identificador que arrojó el error.

---

## 2. Definición del Umbral de Aclaración Calibrado

Utilizando los datos del harness de evaluación de recuperación semántica (feature 005) y las pruebas de similitud con `nomic-embed-text`:

1. **Rango de Similitud Coseno de Recuperación**:
   - Consultas con alta certeza semántica: Score $\ge 0.74$.
   - Consultas con ambigüedad o jerga no mapeada: Score entre $0.58$ y $0.68$.
   - Consultas totalmente ajenas al dominio: Score $< 0.55$.

2. **Criterios Deterministas para Activar Aclaración**:
   - **Criterio A (Puntaje Bajo)**: Si la mejor coincidencia vectorial tiene un score de similitud coseno $< 0.65$ (`CONFIDENCE_THRESHOLD_MIN = 0.65`).
   - **Criterio B (Empate Técnico / Colisión)**: Si la diferencia entre el Score de la primera tabla y el Score de la segunda tabla es menor al $4\%$ ($\Delta Score \le 0.04$) y ambas superan $0.68$.
   - **Criterio C (Múltiples Tablas del Mismo Dominio)**: Si la pregunta menciona una palabra clave ambigua (ej: "cliente" coincidiendo simultáneamente con `clientes_nacionales` y `clientes_extranjeros`).

**Comportamiento**: En cualquiera de estos tres casos, el motor inhibe la llamada a `generate_completion` de SQL y transiciona directamente a emitir un evento SSE `clarification_request`.
