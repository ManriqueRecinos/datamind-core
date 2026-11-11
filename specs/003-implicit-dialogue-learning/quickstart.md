# Quickstart: Implicit Dialogue Learning & Candidate Lifecycle

---

## 1. Simulación de Detección, Inyección y Persistencia de `rules_applied`

1. **Consulta inicial que genera SQL**:
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/chat/stream" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: user_1" \
     -d '{
       "prompt": "¿Cuáles son las facturas recientes?",
       "session_id": "8b9826a4-c241-4c12-9c9e-52f01fdfba10",
       "connection_id": "c1a2b3c4-0000-0000-0000-000000000001"
     }'
   ```
2. **Usuario envía corrección mencionando tabla y columna del catálogo**:
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/chat/stream" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: user_1" \
     -d '{
       "prompt": "En la tabla factura_lineas, filtra siempre por estado = \"A\".",
       "session_id": "8b9826a4-c241-4c12-9c9e-52f01fdfba10",
       "connection_id": "c1a2b3c4-0000-0000-0000-000000000001"
     }'
   ```
   *Verificación*: El filtro previo valida que existió SQL en el turno previo y que `factura_lineas` y `estado` están en el catálogo. `prescriptive_condition` (`estado = 'A'`) es validada por `sqlglot`. El candidato se guarda con `status: 'candidate'`.

3. **Turno subsiguiente e Hidratación**:
   - Enviar una nueva consulta con `user_1`.
   - Comprobar que el SSE final emite `"rules_applied": [{"id": "...", "title": "..."}]`.
   - Llamar a `GET /api/v1/chat/sessions/8b9826a4-c241-4c12-9c9e-52f01fdfba10` y verificar que el mensaje del asistente contiene `metadata.rules_applied`.

---

## 2. Confirmación, Postulación y Promoción por Admin

1. **Usuario normal confirma para sí mismo**:
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/knowledge/candidates/{id}/confirm-user" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: user_1"
   ```
   *Verificación*: `confirmed_at` se actualiza con el timestamp actual.

2. **Usuario normal postula a global**:
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/knowledge/candidates/{id}/propose-global" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: user_1"
   ```
   *Verificación*: `proposed_global_at` se actualiza.

3. **Admin consulta postulaciones pendientes**:
   ```bash
   curl -X GET "http://127.0.0.1:8000/api/v1/knowledge/candidates?proposed_only=true" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: user_admin" \
     -H "X-User-Role: super-admin"
   ```

4. **Usuario normal intenta rechazar una regla global (debe fallar)**:
   ```bash
   curl -X POST "http://127.0.0.1:8000/api/v1/knowledge/candidates/{global_rule_id}/reject" \
     -H "Authorization: Bearer test_api_key" \
     -H "X-User-Id: user_1" \
     -H "X-User-Role: analyst"
   ```
   *Resultado esperado*: `403 Forbidden` ("Solo un administrador puede rechazar o revertir reglas globales").

---

## 3. Conflicto Determinista al Insertar

1. Con la regla activa `estado = 'A'`, enviar una nueva corrección: `"En la tabla factura_lineas, filtra por estado = 'P'"`.
2. *Verificación*: Al evaluar `(connection_id, factura_lineas, estado)`, la condición difiere. La regla nace directamente con `status: 'conflict'` y `conflict_with_id = <rule_id_anterior>`.

---

## 4. Borrado de Sesión con Auditoría Existente

1. Registrar candidatos y auditorías para la sesión `8b9826a4-c241-4c12-9c9e-52f01fdfba10`.
2. Ejecutar borrado de la sesión:
   ```bash
   curl -X DELETE "http://127.0.0.1:8000/api/v1/chat/sessions/8b9826a4-c241-4c12-9c9e-52f01fdfba10" \
     -H "Authorization: Bearer test_api_key"
   ```
3. *Verificación*:
   - La sesión se elimina exitosamente (`200 OK`).
   - El trigger anti-mutación de `knowledge_audit_logs` **no** se dispara porque la tabla de auditoría usa `source_session_id UUID` plano sin foreign key `ON DELETE SET NULL`.
   - Los registros de auditoría persisten inmutables en PostgreSQL.
