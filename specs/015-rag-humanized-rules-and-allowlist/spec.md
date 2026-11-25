# Feature Specification: Respuestas Humanizadas, Reglas Dinámicas y Allowlist por Vectorización

**Feature Branch**: `015-rag-humanized-rules-and-allowlist`  
**Created**: 2026-11-24  
**Status**: Draft

## Overview & Executive Summary

Actualmente, el asistente RAG + Text-to-SQL puede llegar a mencionar nombres técnicos de tablas y columnas en sus respuestas (ej. *"según la tabla `cant_rollo` y `nom_rollo = rol-1`"*), carece de un mecanismo ágil para editar reglas/alias de negocio de forma continua, y necesita restringir estrictamente el acceso SQL únicamente a las tablas, funciones y procedimientos almacenados que hayan sido vectorizados.

Esta especificación define tres pilares:
1. **Respuestas 100% humanizadas:** Prohibir en el *system prompt* y en la síntesis final la exposición de nombres internos de tablas, columnas o esquemas SQL al usuario final.
2. **Reglas, Alias y Límites Dinámicos (Skills de Negocio):** Permitir crear, editar y eliminar continuamente instrucciones, alias de campos (ej. `nom_rollo` → *"nombre del rollo"*) y límites de respuesta desde el Centro de Aprendizaje, inyectándolos en el contexto RAG.
3. **Allowlist Estricta por Vectorización:** Aunque la base de datos conectada tenga cientos de tablas (ej. 450+ en `bd_suma`), el motor SQL solo podrá consultar las tablas, funciones y procedimientos almacenados explícitamente vectorizados/habilitados.

---

## User Scenarios & Testing

### User Story 1 - Respuestas Humanizadas sin Jerga Técnica (Priority: P1)
Como usuario final del chat, quiero recibir respuestas naturales en lenguaje de negocio sin ver nombres de tablas (`cant_rollo`) ni columnas (`nom_rollo`), para entender la información fácilmente sin exponer la estructura interna de la base de datos.

**Acceptance Scenarios**:
1. **Given** una consulta sobre `"cuántos rollos hay de rol-1"`, **When** el modelo sintetiza la respuesta tras ejecutar el SQL, **Then** responde en lenguaje natural (ej. *"Hay 2 rollos registrados para rol-1"*) sin mencionar nombres de tablas, columnas ni cláusulas SQL.

---

### User Story 2 - Gestión Continua de Reglas, Alias y Límites (Priority: P1)
Como administrador, quiero agregar, modificar y eliminar reglas de negocio, alias de columnas y límites de respuesta desde el Centro de Aprendizaje, para ajustar el comportamiento del modelo sin tocar código.

**Acceptance Scenarios**:
1. **Given** el Centro de Aprendizaje, **When** el administrador crea o edita una regla/alias (ej. *"Cuando pregunten por rollos, responder en unidades y no mostrar IDs internos"*), **Then** la regla se vectoriza/actualiza en `pgvector` y se aplica en las siguientes consultas del chat.

---

### User Story 3 - Allowlist Estricta de Tablas y Rutinas Vectorizadas (Priority: P1)
Como administrador de seguridad/datos, quiero que la IA solo pueda consultar las tablas, funciones y procedimientos almacenados que están vectorizados en la conexión, bloqueando cualquier acceso a las demás tablas de la BD (ej. las 450+ tablas de `bd_suma`).

**Acceptance Scenarios**:
1. **Given** una conexión con 450 tablas donde solo 10 están vectorizadas, **When** el modelo genera un SQL que referencia una tabla no vectorizada, **Then** `SQLGuardrail` / `execute_sql_tool` rechaza la consulta antes de ejecutarla.
2. **Given** rutinas vectorizadas en `pgvector`, **When** el usuario pregunta algo que requiere una función o procedimiento permitido, **Then** solo se permiten las rutinas incluidas en la allowlist de la conexión.

---

## Functional Requirements

- **FR-001**: Inyectar en el *system prompt* de síntesis la regla estricta de no revelar nombres de tablas, columnas, esquemas ni SQL crudo al usuario final.
- **FR-002**: Soportar CRUD (crear, editar, eliminar) de reglas/instrucciones/alias de negocio en el módulo de conocimiento (`category="business_rule"` / `"field_alias"`), actualizando su vector en `pgvector`.
- **FR-003**: Extraer la lista de tablas y rutinas vectorizadas de la conexión (`synced_tables` + rutinas vectorizadas) y pasarla como `allowed_tables` / `allowed_routines` a `SQLGuardrail` y `execute_sql_tool`.
- **FR-004**: Rechazar cualquier consulta SQL que haga referencia a tablas o rutinas fuera de la allowlist antes de enviarla a MariaDB/PostgreSQL.
