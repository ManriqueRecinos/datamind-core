# Research & Decisiones Técnicas: Conocimiento como Código y Recuperación Híbrida de Esquema

**Feature**: `specs/005-schema-knowledge-code-retrieval`  
**Fecha**: 2026-11-11  

---

## 1. Comparativa A: Valores Distintos Indexados al Sincronizar vs. Consultados en Vivo

### Enfoque 1: Indexación de Valores al Sincronizar (Elegido)
- **Mecanismo**: Durante la sincronización o carga de conocimiento, se extraen los valores únicos de columnas categóricas explícitamente listadas (`SELECT DISTINCT columna FROM tabla LIMIT 200`) y se generan chunks vectorizados con `nomic-embed-text` (`"En la tabla '{t}', la columna '{c}' tiene el valor '{v}'"`).
- **Ventajas**:
  - **Latencia predecible y ultra-rápida en runtime**: Cero consultas adicionales a la base de datos externa durante la formulación de la pregunta del usuario.
  - **Match Semántico Profundo**: Preguntas con sinónimos o jerga ("chuchos", "caninos") encuentran "perro" mediante similitud coseno antes de generar el SQL.
  - **Aislamiento**: No satura la base de datos transaccional con `DISTINCT` pesados durante las horas pico de producción.
- **Desventajas**:
  - Requiere re-indexación si los valores categóricos cambian con frecuencia (mitigado porque se restringe a catálogos maestros y estados estables).

### Enfoque 2: Consulta de Valores en Vivo (Descartado)
- **Mecanismo**: Al recibir la pregunta, el LLM o un extractor de entidades identifica posibles valores y lanza consultas `ILIKE` o `DISTINCT` sobre las tablas de la base remota.
- **Por qué se descarta**:
  - Agrega entre 500 ms y 2.5 s de latencia previa a la generación de la respuesta.
  - Provoca contención de bloqueos e I/O innecesario en bases de producción.
  - Si el usuario comete un error ortográfico o usa un sinónimo, el `ILIKE` en vivo falla.

**Decisión**: Indexación offline de valores categóricos controlada por lista blanca estricta con cardinalidad máxima de 200 valores.

---

## 2. Comparativa B: `pg_trgm` (Trigramas) vs. Full-Text Search de PostgreSQL

### Opción 1: `pg_trgm` (Extension de Trigramas) (Elegido para Esquemas)
- **Mecanismo**: Descompone las cadenas en secuencias de 3 caracteres contiguos. Utiliza índices GIN/GiST y la función `similarity(texto, query)`.
- **Ventajas para Esquemas y Metadatos**:
  - **Tolerancia a Errores Tipográficos y Variaciones**: Si el usuario escribe `"inventario_parte"` o `"repuetos"`, trigramas lo empareja con `inventario_partes` y `repuestos`.
  - **Substrings y Nombres Compuestos**: Excelente para identificadores técnicos como `id_parte_maquina`, `pm_codigo`, `uy128gas`.
  - **Sin dependencia de diccionario de idioma**: Los nombres de tablas y columnas suelen ser mezclas técnicas que los parsers de lenguaje natural (snowball stemmer) mutilan erróneamente.
- **Desventajas**:
  - Consumo de almacenamiento ligeramente superior en el índice GIN.

### Opción 2: Full-Text Search (`to_tsvector` / `to_tsquery`)
- **Mecanismo**: Análisis léxico con reducción morfológica (stemming) y diccionario de stopwords en español.
- **Por qué no es ideal para metadatos SQL**:
  - Las palabras clave técnicas y nombres de columnas (ej. `cod_sub_tipo_maq`) son tratados como palabras desconocidas o descompuestas erróneamente.
  - Cero tolerancia a typos (si falta una letra, el match es 0).

**Decisión**: Utilizar `pg_trgm` sobre los campos de contenido, nombres y alias, complementado con operadores `ILIKE` indexados.

---

## 3. Comparativa C: Algoritmo de Fusión por Reciprocal Rank Fusion (RRF)

Para fusionar la lista de tablas/reglas recuperadas por la rama vectorial (similitud semántica densa) y la rama léxica (`pg_trgm`), se adopta **Reciprocal Rank Fusion (RRF)**:

$$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + rank_m(d)}$$

Donde:
- $M = \{\text{Vectorial}, \text{Léxica}\}$
- $rank_m(d)$ es la posición (1-based) del documento $d$ en la lista ordenada del método $m$. Si no aparece en la lista, $rank_m(d) = \infty$.
- $k = 60$ (constante empírica estándar de Cormack et al. que penaliza suavemente las posiciones bajas).

**Por qué RRF supera a la suma ponderada de scores (Weighted Score)**:
- Los scores de similitud coseno (valores entre 0.0 y 1.0) y los puntajes de similitud de trigramas no comparten la misma distribución de probabilidad ni escala.
- Normalizar scores (min-max o z-score) es sensible a outliers y requiere calibrar coeficientes arbitrarios ($\alpha \cdot S_{vec} + \beta \cdot S_{lex}$).
- RRF opera puramente sobre el **orden relativo (ranking)**, siendo completamente agnóstico a la escala numérica de cada motor y sumamente robusto.
