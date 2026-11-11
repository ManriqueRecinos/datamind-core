# Checklist de Calidad y Validación: Humanización de Datos y Seguridad

**Feature**: `specs/007-humanized-business-lens`  
**Fecha de Creación**: 2026-11-11  

---

## 1. Experiencia de Usuario y Desambiguación Inequívoca
- [x] **CHK-001**: Las preguntas con lemas o plurales claros en español (ej. *"usuarios"*, *"empresas"*, *"repuestos"*) se resuelven en el primer turno sin emitir tarjeta de aclaración.
- [x] **CHK-002**: Las opciones de aclaración solo se activan cuando existe un empate técnico real ($\Delta \le 0.04$) entre entidades no unívocas.
- [x] **CHK-003**: Si se presenta una aclaración, las opciones muestran descripciones de negocio y no nombres crudos de tablas técnicas.

## 2. Seguridad Corporativa y Privacidad de Datos
- [x] **CHK-004**: Ninguna consulta SQL proyecta columnas de contraseñas (`password`, `user_password`).
- [x] **CHK-005**: Las columnas que contienen tokens de autenticación (`remember_token`, `api_token`, `gotify_app_token`) son purgadas por el backend antes de emitir datasets.
- [x] **CHK-006**: Ninguna credencial secreta o hash queda registrada en la base de datos `query_datasets` en caché.
- [x] **CHK-007**: Los archivos de exportación a Excel no contienen contraseñas ni tokens de sesión.

## 3. Humanización y Ocultamiento de Metadatos Físicos
- [x] **CHK-008**: Los encabezados de las tablas interactivas en la UI muestran etiquetas en español (ej: *"Nombre de Usuario"*, *"Correo Electrónico"*, *"Empresa Asignada"*).
- [x] **CHK-009**: El asistente no menciona nombres físicos de tablas (`users`, `companies`, `company_user`) en su respuesta redactada.
- [x] **CHK-010**: El asistente no expone nombres de bases de datos o instancias de conexión en el diálogo con el usuario.

## 4. Visualización y Gráficos
- [x] **CHK-011**: Las consultas de listados informativos simples no despliegan el selector de Eje X / Eje Y innecesariamente.
- [x] **CHK-012**: El constructor de gráficos se reserva exclusivamente para solicitudes explícitas de graficación o agregaciones numéricas comparables.

## 5. Pruebas y Robustez
- [x] **CHK-013**: La suite de pruebas unitarias `tests/unit/test_data_humanizer.py` pasa al 100%.
- [x] **CHK-014**: El microservicio FastAPI arranca limpio sin excepciones de sintaxis ni importaciones circulares.
