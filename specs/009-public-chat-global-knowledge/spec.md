# Feature Specification: 009-public-chat-global-knowledge

## 1. Overview & Business Problem
Al levantar el servidor web de Laravel (`php artisan serve`), la ruta raíz (`/`) actualmente dirige al Hub de Ecosistemas o exige login para interactuar con la IA. El objetivo es que la consola de Chat sea el punto de entrada principal e inmediato tanto para usuarios anónimos (invitados) como para usuarios autenticados, estableciendo dos alcances cognitivos claros:

1. **Modo Libre / Invitado (Sin Iniciar Sesión)**:
   - Acceso inmediato en `/` y `/chat`.
   - Consulta transversal y holística del **Conocimiento Global**: conceptos, glosario de términos, documentos vectorizados (PDF, Excel, manuales, guías), relaciones entre entidades y reglas generales aprendidas.
   - Sin selector de base de datos específica (actúa sobre el pool de conocimiento global de pgvector sin mutaciones SQL directas).
   - Historial de chat en memoria o local.

2. **Modo Autenticado (Con Sesión Iniciada)**:
   - Mantiene todo el conocimiento global del modo libre.
   - **Capacidad Exclusiva**: Permite asociar el chat a una **conexión específica** (ej: SUMAIE `demo_manrique` u otras registradas) para ejecutar Text-to-SQL, consultar tablas y registros privados en vivo, y generar data tables/gráficos.
   - Persistencia de historial por usuario en base de datos.
   - Acceso a navegación de ecosistemas (`/hub`), conexiones y vectorización según permisos.

## 2. User Stories & Acceptance Criteria

### US-1: Acceso Directo al Chat sin Autenticación
- **Dado** un usuario que navega a `http://127.0.0.1:8085/` o `http://127.0.0.1:8085/chat` sin haber iniciado sesión.
- **Cuando** carga la página.
- **Entonces** debe visualizar directamente la interfaz del Chat DataMind AI lista para escribir, sin ser redirigido a `/login` ni a `/hub`.
- **Y** el selector de base de datos debe mostrar *"Conocimiento Global / Todas las Bases"* o estar fijado en modo general.

### US-2: RAG Global sin Conexión Forzada en Backend (FastAPI)
- **Dado** un prompt enviado desde el chat sin `connection_id` o con `connection_id = null`.
- **Cuando** la API procesa la consulta en `AskChatUseCase`.
- **Entonces** no debe fallar exigiendo una conexión de BD.
- **Y** debe recuperar embeddings globales de `knowledge_documents` (PDF/Excel), `business_rules` y el grafo conceptual de todas las tablas vectorizadas para responder conceptual y contextualmente.

### US-3: Chat Específico con Sesión Iniciada
- **Dado** un usuario con sesión iniciada.
- **Cuando** está en `/chat`.
- **Entonces** puede seleccionar libremente una base de datos específica del dropdown (ej: SUMAIE) para hacer consultas directas a los datos y tablas de esa conexión, o seleccionar *"Conocimiento Global"*.
- **Y** sus sesiones quedan guardadas en `chat_sessions` asociadas a su `user_id`.
