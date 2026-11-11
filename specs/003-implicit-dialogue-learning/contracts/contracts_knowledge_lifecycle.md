# Contratos de API: Ciclo de Vida de Candidatos de Conocimiento

**Servicio**: FastAPI (`python-db`) ↔ Cliente Web (`Laravel 12 / chat_stream.js`)

**Principio de Autorización**:
- FastAPI valida la API Key de servicio (`Authorization: Bearer <API_KEY>`).
- Laravel inyecta de forma segura el usuario autenticado:
  - `X-User-Id: <string>` (ej. `user_1`)
  - `X-User-Role: <string>` (ej. `super-admin`, `admin`, `analyst`)
  - `X-User-Permissions: <comma-separated-strings>` (ej. `manage-knowledge`)

---

## 1. GET /api/v1/knowledge/candidates

Lista reglas candidatas y conflictos filtrados por titularidad y permisos.

- **Query Params**:
  - `scope`: `user` (por defecto) o `global`.
  - `status`: `candidate`, `conflict`, `verified`.
  - `proposed_only`: `true` | `false` (para el panel administrativo de curación).
  - `connection_id`: UUID de la base de datos conectada.

### Comportamiento de Autorización
- Si `X-User-Role` no es `admin`/`super-admin` ni posee `manage-knowledge`, la consulta forzará automáticamente `user_id = X-User-Id` y `scope = 'user'`.

### Respuesta `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "7b8e1a2c-4f5d-4e9b-8a1c-3e2d1f0a9b8c",
      "knowledge_type": "schema_correction",
      "title": "Filtro de Estado Activo en Facturas",
      "content": "Para la tabla `factura_lineas`, la columna `estado` debe cumplir: estado = 'A'.",
      "target_entity": "factura_lineas",
      "target_column": "estado",
      "prescriptive_condition": "estado = 'A'",
      "status": "candidate",
      "scope": "user",
      "trigger_signal": "user_correction",
      "version": 1,
      "source_session_id": "8b9826a4-c241-4c12-9c9e-52f01fdfba10",
      "conflict_with_id": null,
      "confirmed_at": null,
      "proposed_global_at": "2026-03-11T15:25:00Z",
      "created_at": "2026-03-11T15:20:00Z"
    }
  ]
}
```

---

## 2. POST /api/v1/knowledge/candidates/{id}/confirm-user

El usuario autor confirma la regla para su propio uso exclusivo (`scope: user`).

- **Headers**:
  - `X-User-Id: <string>`
- **Efecto Persistente**:
  - `confirmed_at = NOW()`
  - La regla se mantiene en `scope: user`, `status: candidate`.

---

## 3. POST /api/v1/knowledge/candidates/{id}/propose-global

El usuario autor postula la regla a revisión corporativa.

- **Headers**:
  - `X-User-Id: <string>`
- **Efecto Persistente**:
  - `proposed_global_at = NOW()`

---

## 4. POST /api/v1/knowledge/candidates/{id}/promote-global

Un **administrador** aprueba la promoción a conocimiento corporativo global.

- **Headers**:
  - `X-User-Role: <string>` (debe ser `admin`/`super-admin` o permiso `manage-knowledge`).
- **Efecto Persistente**:
  - `scope: global`, `status: verified`, `version = version + 1`.
  - Re-sanitización y re-vectorización en `nomic-embed-text` (`search_document: `).

---

## 5. POST /api/v1/knowledge/candidates/{id}/reject

Descarta una regla candidata o corporativa.

- **Autorización**:
  - Si la regla tiene `scope: user`: permitido al autor (`user_id == X-User-Id`) o a un admin.
  - Si la regla tiene `scope: global`: **ESTRICTAMENTE RESERVADO A ADMINISTRADORES** (`403 Forbidden` a usuarios regulares).
- **Efecto**:
  - `status = 'rejected'`, purga de memoria vectorial.

---

## 6. POST /api/v1/knowledge/candidates/{id}/rollback

Revierte una regla activa a su versión previa o la desactiva.

- **Autorización**:
  - Si `scope: global`: **SOLO ADMINISTRADORES**.
- **Comportamiento**:
  - Si existe un `previous_state` en `knowledge_audit_logs`, restaura los atributos previos y re-vectoriza.
  - Si no existe estado anterior, muta a `status = 'rolled_back'`.

---

## 7. Persistencia y Exposición de `rules_applied` en Contratos de Chat

En `POST /chat/stream` y `GET /chat/sessions/{id}`:
- **Evento SSE `done`**:
  ```http
  event: done
  data: {"status": "completed", "session_id": "...", "rules_applied": [{"id": "...", "title": "Filtro de Estado Activo"}]}
  ```
- **GET /chat/sessions/{id}**:
  Cada mensaje con rol `assistant` devuelve su array de reglas aplicadas:
  ```json
  {
    "id": "msg_uuid",
    "role": "assistant",
    "content": "...",
    "metadata": {
      "rules_applied": [
        {"id": "7b8e1a2c-4f5d-4e9b-8a1c-3e2d1f0a9b8c", "title": "Filtro de Estado Activo"}
      ]
    }
  }
  ```
