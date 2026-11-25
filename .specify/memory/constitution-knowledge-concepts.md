# Constitución: Clasificación de Aprendizajes por Concepto (Dominios RAG)

**Versión**: 1.0.0 | **Fecha**: 2026-11-25  
**Aplica a**: `d:\Python\python-db` (Backend FastAPI + pgvector) y `d:\Laravel\Supertex AI` (Frontend Centro de Aprendizaje)

---

## 1. Principio de Taxonomía Semántica (Conceptos)

Todo aprendizaje registrado en el Centro de Aprendizaje (reglas de negocio, códigos/estados, ejemplos SQL, consultas compuestas) debe poder asociarse a un **Concepto** de negocio:
- **`nombre_corto`**: Identificador breve y único (ej. `SEG`, `PROD`, `INV`, `CAL`).
- **`nombre_largo`**: Nombre legible del dominio (ej. `Seguridad y Permisos`, `Control de Producción`).
- **`descripcion`**: Explicación semántica de qué abarca el concepto y cuándo aplica.

---

## 2. Vectorización y Chunking de Conceptos

1. **Indexación en `pgvector`**:
   - Cada concepto creado o actualizado debe particionarse en chunks (`TextChunker`) y vectorizarse con `nomic-embed-text` bajo la categoría `concept_definition`.
2. **Metadatos en Aprendizajes**:
   - Cada regla o ejemplo SQL asociado a un concepto debe incluir `concept_id`, `concept_short_name` y `concept_long_name` en sus metadatos (`metadata_`) y en el texto indexado, permitiendo que el RAG filtre o priorice el dominio correcto según la pregunta del usuario.

---

## 3. Experiencia de Usuario en `/training` (`Supertex AI`)

1. **SelectPicker de Concepto**:
   - En el formulario de **Nueva Regla**, mostrar un selector (`Select2` / `selectpicker` local, sin CDNs) con todos los conceptos disponibles.
2. **Creación Rápida en Modal**:
   - Junto al selector, incluir un botón **"+ Nuevo Concepto"** que abra un modal para registrar `nombre_corto`, `nombre_largo` y `descripcion` sin salir del flujo de creación de la regla, seleccionando automáticamente el concepto recién creado.
3. **Control de Versiones (`Supertex AI`)**:
   - Todo cambio en `Supertex AI` debe incrementar la versión en `README.md` y `AGENTS.md` según el protocolo del proyecto.
