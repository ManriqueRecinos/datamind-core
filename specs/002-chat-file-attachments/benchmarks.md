# Benchmark de Rendimiento: Analítica Local en CPU con DuckDB y Polars

**Fecha**: 2026-11-10  
**Especificación**: `specs/002-chat-file-attachments`  
**Entorno**: Windows 11, Python 3.13.14, DuckDB 2.0.0, Polars 2.1.0, PyArrow 26.0.1  

---

## 1. Parámetros del Test

- **Dataset Sintético**: 50,000 registros tabulares simulando catálogo e inventario de repuestos.
- **Tamaño de archivo en disco**: 1.68 MB (CSV).
- **Operaciones ejecutadas**:
  1. Detección y validación perimetral de tipo MIME y Magic Bytes.
  2. Inferencia de esquema (conteo total de filas, tipos normalizados, muestra de valores limpios).
  3. Carga en streaming y creación de vista temporal en DuckDB.
  4. Agregación analítica multivariable (`COUNT`, `SUM`, `AVG`, `GROUP BY`, `ORDER BY`).

---

## 2. Resultados Obtenidos

| Métrica | Valor Medido | Límite Máximo Permitido | Estado |
|---|---|---|---|
| **RAM Inicial del Proceso** | 68.38 MB | - | - |
| **RAM Pico del Proceso** | **166.86 MB** | 256.00 MB | ✅ **CUMPLE** |
| **Delta RAM Consumida** | **98.48 MB** | 256.00 MB | ✅ **CUMPLE (61% bajo el tope)** |
| **Pico Tracemalloc Interno** | 40.12 MB | - | ✅ Eficiente |
| **Tiempo Inferencia de Esquema** | **1.514 s** | 5.0 s | ✅ Óptimo |
| **Tiempo Consulta Analítica DuckDB** | **0.064 s** (64 ms) | 3.0 s | ✅ Ultrarrápido |

---

## 3. Conclusiones

- El procesamiento en CPU local mediante **DuckDB** y **Polars** demuestra una eficiencia extrema para volúmenes de 50,000 filas (solo 64 ms de ejecución de consulta).
- El consumo de memoria se mantiene cómodamente por debajo del umbral estricto de 256 MB por sesión, garantizando que el servidor de FastAPI no sufra degradación ni saturación al procesar archivos adjuntos de usuarios en paralelo.
