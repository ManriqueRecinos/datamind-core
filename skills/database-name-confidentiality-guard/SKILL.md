---
name: database-name-confidentiality-guard
description: Regla crítica de confidencialidad y seguridad que prohíbe estrictamente que el asistente de IA mencione o exponga nombres físicos de bases de datos (como bd_suma o enterprise_rag), nombres de tablas, columnas técnicas o sentencias SQL en cualquier respuesta al usuario.
---

# Guardrail Crítico: Confidencialidad de Nombres de Bases de Datos y Esquemas

## Regla Inquebrantable (CRITICAL MUST)

Bajo **ninguna circunstancia** el asistente de IA (`DataMind AI` / `Supertex AI`) ni los mensajes de error o fallback del backend pueden mostrar, citar o mencionar al usuario final:

1. **Nombres físicos de bases de datos** (por ejemplo: `bd_suma`, `enterprise_rag`, o el valor de `db_name` / `database_name` de la conexión activa).
2. **Nombres de motores o servidores de base de datos** (por ejemplo: `MariaDB`, `MySQL`, `PostgreSQL`, puertos o IPs).
3. **Nombres físicos de tablas o columnas técnicas** (por ejemplo: `tabla op`, `cantidad_tallas_pedidas_op`, `id_op`, `id_paquete`).
4. **Fragmentos o sentencias SQL** en el cuerpo conversacional.

## Aplicación en el Sistema (`d:\Python\python-db`)

- **En prompts del LLM (`ask_chat.py`)**: Todo prompt de síntesis o de respuesta conceptual (`process_qa` y `data_query`) debe incluir la directiva explícita prohibiendo mencionar `db_name` y exigiendo referirse a la fuente de datos únicamente como **"el sistema"** o **"los registros operativos"**.
- **En mensajes de fallback/error (`ask_chat.py`)**: Cuando una consulta no arroje resultados o agote los intentos de auto-reparación (`sql_repair_exhausted`), el mensaje al usuario jamás debe interpolar `{db_name}` ni `{table_name}`.
- **Sanitización Post-Generación (Hard Filter)**: Antes de persistir y retornar `message_text` al usuario, se debe aplicar un reemplazo por expresión regular que sustituya cualquier aparición accidental de `db_name` (o identificadores conocidos como `bd_suma` y `enterprise_rag`) por `"el sistema"`.
