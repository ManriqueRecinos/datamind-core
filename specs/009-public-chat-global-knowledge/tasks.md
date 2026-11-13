# Tasks: 009-public-chat-global-knowledge

## Phase 1: Setup & Public Routing (Laravel)
- [ ] Task 1.1: Reconfigurar rutas raíz y chat en `routes/web.php`
  - Apuntar `GET /` directamente a `ChatController@index` (con nombre `home`).
  - Mover `GET /chat`, `POST /chat/send`, `POST /chat/stream` y `GET /chat/dataset/{id}` fuera del grupo `middleware(['auth'])`.
  - Mantener `/hub` protegido bajo `middleware(['auth'])`.

- [ ] Task 1.2: Adaptar `ChatController.php` para invitados y autenticados
  - En `index()`: si el usuario es invitado, pasar `chatSessions` vacío o sesiones locales sin consultar la BD de usuarios privados.
  - En `send()` y `stream()`: si `Auth::guest()`, asignar `user_id = 'guest_user'`, `user_role = 'guest'` y permisos vacíos `[]`.
  - Asegurar que no intente asociar a una conexión específica si el usuario no tiene permisos o no ha iniciado sesión.

## Phase 2: Interfaz de Usuario y Selector de Conocimiento (Blade / JS)
- [ ] Task 2.1: Adaptar selector de base de datos en `resources/views/chat/index.blade.php`
  - Añadir la opción fija `<option value="global">Conocimiento Global (Todas las Bases & Conceptos)</option>` como primera opción por defecto.
  - Si el usuario es invitado (`@guest`):
    - Fijar el select en `value="global"` y deshabilitar opciones privadas.
    - Mostrar en la cabecera un badge informativo: *"Modo Libre: Conocimiento Global & Conceptual"* con enlace rápido a *"Iniciar Sesión para consultar bases privadas"*.
  - Si el usuario está autenticado (`@auth`):
    - Habilitar la selección entre *"Conocimiento Global"* y las bases de datos registradas (`SUMAIE`, etc.).

- [ ] Task 2.2: Ajustes en Navbar y Layout (`resources/views/layouts/app.blade.php`)
  - Verificar que el sidebar y el navbar se rendericen con gracia para usuarios invitados (mostrando botón "Iniciar Sesión" en lugar del menú de usuario vacío).

## Phase 3: RAG Global y Soporte sin Conexión en Backend (FastAPI / python-db)
- [ ] Task 3.1: Actualizar `app/use_cases/ask_chat.py` para `connection_id = None | 'global'`
  - Cuando `connection_id` sea nulo o `'global'`:
    - Omitir la carga de una conexión SQL específica (`self.conn_manager.get_connection`).
    - Realizar búsqueda semántica vectorial amplia: documentos ingeridos (`knowledge_documents`), reglas aprendidas (`knowledge_rules`) y definiciones de esquemas de todas las bases vectorizadas.
    - Si la consulta es conceptual o informativa, sintetizar la respuesta desde el contexto recuperado sin requerir adaptador SQL.
    - Si la consulta exige estrictamente datos vivos de tablas (ej: "dame los registros de la tabla X"), responder amablemente explicando que para consultar registros en vivo de una base específica debe seleccionar la conexión correspondiente o iniciar sesión.

- [ ] Task 3.2: Actualizar `app/use_cases/intent_classifier.py`
  - Asegurar que consultas en modo global sin conexión se clasifiquen como `concept_query` o `rag_document` para que no se fuercen a Text-to-SQL vacío.

## Phase 4: Verificación y Pruebas
- [ ] Task 4.1: Pruebas automatizadas en FastAPI (`pytest`)
  - Ejecutar tests de clasificación y RAG con `connection_id=None` para asegurar que responda correctamente.
- [ ] Task 4.2: Prueba manual de navegación en Laravel
  - Probar `curl http://127.0.0.1:8085/` (debe responder 200 con la vista de Chat).
  - Verificar que al iniciar sesión aparezcan las conexiones específicas y el historial de sesiones.
