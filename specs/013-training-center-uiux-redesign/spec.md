# Feature Specification: Rediseño Integral UI/UX del Centro de Aprendizaje & Memoria de la IA

**Feature Branch**: `013-training-center-uiux-redesign`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "eres un experto en UI/UX, vas a corregir esa vista de Centro de Aprendizaje & Memoria de la IA para que sea mas intuitiva y facil de usar, con colores casi similares pero bien hechos y visualmente agradables"

## Overview & Executive Summary
El Centro de Aprendizaje & Memoria de la IA (`/training`) es el núcleo donde administradores y usuarios enseñan a la IA el modelo mental de su negocio: relaciones foráneas, reglas de estados, ejemplos SQL de oro, fórmulas de cálculo, consultas compuestas con múltiples uniones y documentos procesados.

La vista actual sufre de fricciones de usabilidad y consistencia estética:
1. **Jerarquía visual plana y ruido cognitivo**: Tarjetas de tipos de enseñanza densas y con bordes pesados que saturan la atención.
2. **Contrastes y colores heterogéneos**: Mezcla de tonos no balanceados (índigo oscuro, morados sin armonizar, fondos grises planos) que dificultan identificar acciones principales frente a secundarias o estados deshabilitados.
3. **Flujo de creación fragmentado**: El constructor de consultas compuestas y el formulario de reglas de 2 tablas conviven como bloques desconectados con diferentes patrones de diseño.
4. **Espaciado y alineación vertical**: Densidad excesiva en pantallas medianas y falta de respiración entre bloques de filtrado, galería de tarjetas y paneles de edición.

Este rediseño moderniza la experiencia basándose en un sistema visual corporativo cohesivo (paleta DataMind `#0476D9`, fondos en escala de grises refinada `slate-50/100/200/900`, acentos esmeralda/ámbar pulidos, bordes limpios y estados de foco perceptibles) con navegación fluida, feedback contextual y ergonomía de interacción superior.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Creación Guiada Intuitiva de Reglas y Relaciones (Priority: P1)
Como administrador de la base de datos, quiero un formulario claro, espacioso y organizado por pasos lógicos donde seleccionar el tipo de regla (JOIN simple, consulta compuesta, estados de negocio, ejemplo SQL o fórmula) y ver inmediatamente solo los controles relevantes con etiquetas y ayudas visuales legibles, para enseñar a la IA sin cometer errores ni confundirme entre campos técnicos.

**Why this priority**: Es la tarea principal y recurrente de la vista. Si la creación de reglas resulta confusa o visualmente pesada, los usuarios evitan documentar el sistema y la IA pierde precisión.

**Independent Test**: Puede probarse abriendo el modal/formulario de "Nueva Regla", alternando entre cada tipo de enseñanza y verificando que la interfaz cambie fluidamente con contrastes óptimos (mínimo ratio 4.5:1), selectpickers claros y estados activos distinguibles.

**Acceptance Scenarios**:
1. **Given** que el usuario hace clic en "Nueva Regla", **When** se despliega el panel, **Then** las categorías de enseñanza se muestran como tarjetas ergonómicas con iconos claros, badges de color armónico y un estado seleccionado destacado con borde perimetral sutil `#0476D9` y fondo suave.
2. **Given** que el usuario selecciona "Unir 2 Tablas (JOIN)", **When** interactúa con los selectores de origen y destino, **Then** los selectores de columnas y sugerencias de campos legibles tienen etiquetas descriptivas, placeholders amigables y estados deshabilitados comprensibles sin texto invisible.
3. **Given** que el usuario pulsa "Guardar y Vectorizar", **When** la petición se procesa, **Then** el botón muestra un estado de carga claro (spinner blanco sobre color corporativo) y tras el éxito se muestra un feedback visual positivo limpiando la vista ordenadamente.

---

### User Story 2 - Constructor de Consultas Compuestas Elegante y Estructurado (Priority: P1)
Como ingeniero de datos o analista, quiero construir consultas grandes (con múltiples JOINs, filtros WHERE por alias y proyecciones SELECT) dentro de un constructor visual limpio, donde cada fila de unión tenga contraste cromático profesional, separadores nítidos y selectpickers claros para alias y columnas, para inspeccionar y probar la consulta sin fatiga visual.

**Why this priority**: Es el flujo más avanzado y complejo de la herramienta. Requiere claridad cristalina en tipografía, badges de tipos de unión (`INNER`, `LEFT`, `RIGHT`) y bloques de condiciones para evitar errores sintácticos.

**Independent Test**: Puede probarse seleccionando "Consulta Compuesta (Builder)", agregando 2 uniones con alias, un filtro WHERE por columna, observando la vista previa en vivo y ejecutando la prueba de 20 registros con tabla de resultados perfectamente alineada.

**Acceptance Scenarios**:
1. **Given** el panel de Tablas Unificadas (JOINs), **When** se agrega una unión, **Then** la tarjeta de la unión tiene un contenedor blanco limpio con borde `slate-200`, selector de tipo de JOIN con etiqueta destacada y selector de alias/columna en contraste óptimo con el texto.
2. **Given** la condición ON o los filtros WHERE, **When** el usuario selecciona un alias, **Then** el selectpicker de columnas asociado se habilita dinámicamente con texto en negro/gris oscuro legible y badges de tipo de dato (`varchar`, `int`, `[FK]`).
3. **Given** la vista previa de SQL compilado en vivo, **When** se generan las cláusulas, **Then** el bloque de código utiliza una tipografía monoespaciada legible sobre fondo oscuro elegante (`slate-950`) con colores sintácticos de alto contraste (texto esmeralda `#34D399` y palabras clave destacadas).

---

### User Story 3 - Exploración y Gestión Ágil de la Galería de Aprendizajes (Priority: P2)
Como usuario que consulta la memoria de la IA, quiero navegar la galería de tarjetas existentes con un buscador instantáneo, filtros de categoría visuales con contadores y tarjetas tipo "bento" limpias que indiquen claramente la categoría, fecha, conexión y un extracto legible del conocimiento aprendido, para auditar o eliminar reglas rápidamente.

**Why this priority**: Permite supervisar la salud del conocimiento adquirido por la IA y editar/revisar reglas anteriores sin perderse entre cientos de registros.

**Independent Test**: Puede probarse filtrando por categoría, buscando por texto en tiempo real, abriendo el modal de detalle de una regla y utilizando el botón de "Abrir en Constructor" para retomar una consulta.

**Acceptance Scenarios**:
1. **Given** la galería de tarjetas de aprendizaje, **When** el usuario escribe en el buscador o cambia la categoría, **Then** las tarjetas se filtran en tiempo real sin parpadeos visuales ni desconfiguración del grid.
2. **Given** una tarjeta de regla de tipo consulta compuesta en la galería, **When** el usuario hace clic para ver su detalle, **Then** se abre un modal con tipografía jerárquica, bloque SQL formateado y botón primario para abrirla directamente en el constructor visual.

---

### Edge Cases
- ¿Qué ocurre si la base de datos vinculada no tiene tablas vectorizadas? Se muestra un estado vacío instructivo con ilustración/icono suave y un botón de llamada a la acción directo a `/connections/explorer`.
- ¿Qué ocurre si la pantalla es reducida (tablets o laptops de 1366x768)? El sidebar y el panel central deben hacer scroll independiente sin desbordamiento horizontal y las tarjetas de tipo de regla deben reorganizarse fluidamente a 2 o 3 columnas sin colapsar textos.
- ¿Qué ocurre si una consulta SQL importada tiene nombres de tablas o alias excesivamente largos? Los badges y selectpickers deben truncar con elipsis (`truncate`) y mostrar tooltip nativo para preservar la alineación del layout.

---

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: La vista MUST unificar la paleta de colores cromática bajo las variables del sistema DataMind:
  - Color Primario Interactivo: `#0476D9` (DataMind Blue).
  - Fondos de Contenedor: `#FFFFFF` (tarjetas), `#F8FAFC` (fondos de bloque `slate-50`), `#F1F5F9` (`slate-100` para subpaneles).
  - Tipografía y Contraste: Texto principal `#0F172A` (`slate-900`), texto secundario `#475569` (`slate-600`), bordes consistentes `#CBD5E1` (`slate-300`) y `#E2E8F0` (`slate-200`).
  - Acentos funcionales: Éxito/Ejecución `#059669` (`emerald-600`), Advertencias/Filtros `#D97706` (`amber-600`), Uniones `#4F46E5` (`indigo-600` ajustado para alto contraste sobre blanco).
- **FR-002**: El selector de categorías de regla MUST presentarse con tarjetas ergonómicas con micro-interacciones hover claras, radio de foco accesible y badge indicador de categoría activa sin colores estridentes.
- **FR-003**: En el Constructor de Consultas Compuestas, cada paso numérico (`1. Tabla Base`, `2. Tablas Unificadas`, `3. Columnas`, `4. Filtros`, `5. Uniones`) MUST tener una barra de título uniforme con su número en badge con fondo corporativo, título en negrita legible y botón de acción con icono alineado.
- **FR-004**: Los selectpickers de alias y columnas en cascada MUST ofrecer estados visuales consistentes:
  - Estado inicial deshabilitado con fondo `slate-100`, borde `slate-200` y texto placeholder gris medio.
  - Estado activo con fondo blanco puro, borde `slate-300`, texto negro nítido y anillo de foco `ring-2 ring-datamind-primary/20`.
- **FR-005**: La sección de vista previa de SQL y salida del Dry Run MUST tener cabeceras claras, scrollbars personalizados discretos y tablas de resultados con filas alternadas (`even:bg-slate-50/50`) y cabeceras fijas.
- **FR-006**: La barra de filtrado y búsqueda de la galería MUST mantener altura consistente, inputs alineados con iconos embebidos a la izquierda y contadores numéricos actualizados en tiempo real.
- **FR-007**: El modal de "Ingest (Subir Archivo)" y el modal de "Detalle de Regla" MUST compartir la misma estructura de diseño: encabezado con icono temático, cuerpo estructurado en bloques de lectura descansada y footer con botones alineados a la derecha.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes
- **SC-001**: El ratio de contraste de todos los textos y botones frente a sus fondos de contenedor supera el estándar de accesibilidad WCAG AA (mínimo 4.5:1 para texto normal y 3:1 para controles/botones).
- **SC-002**: Los usuarios completan la configuración de una regla compuesta con múltiples uniones y filtros en menos de 90 segundos gracias a la claridad de los selectores en cascada.
- **SC-003**: Cero elementos visuales con texto truncado ilegible o colores no armonizados reportados en resoluciones desde 1280px hasta 4K.
- **SC-004**: Tiempo de respuesta visual y transición entre pestañas y selectores inferior a 100 ms sin layout shifts (CLS < 0.05).

---

## Assumptions
- Los usuarios utilizan navegadores modernos con soporte para flexbox, CSS grid y variables CSS nativas de Tailwind CSS.
- El diseño mantiene la filosofía monolítica recta y corporativa de DataMind Studio (`rounded-none`, sobriedad industrial de software empresarial).
- Las conexiones a bases de datos y la vectorización continúan siendo provistas por los microservicios existentes de Laravel y FastAPI.
