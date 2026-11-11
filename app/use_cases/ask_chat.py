"""Caso de uso principal para orquestar la conversación de chat (RAG + Text-to-SQL)."""

from datetime import datetime, timedelta, timezone
import json
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.domain.entities import QueryDataset
from app.infrastructure.database.models import (
    ChatMessageModel,
    ChatSessionModel,
    QueryDatasetModel,
)
from app.infrastructure.database.dynamic_db_adapter import DynamicDBAdapter
from app.infrastructure.database.mariadb_adapter import MariaDBAdapter
from app.infrastructure.database.vector_repository import VectorRepository
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.llm.sql_guardrail import SQLGuardrail
from app.use_cases.ingest_knowledge import IngestKnowledgeUseCase
from app.use_cases.intent_classifier import IntentClassifier, remove_accents
from app.use_cases.manage_connections import ManageConnectionsUseCase
from app.use_cases.sql_repair_agent import SqlRepairAgent
from app.infrastructure.database.repositories.unresolved_terms_repository import UnresolvedQueryTermRepository
from app.infrastructure.analytics.data_humanizer import DataHumanizer
from app.core.telemetry_resilience import resilience_metrics


class AskChatUseCase:
    """Orquestador integral del Chat: RAG vectorial, Text-to-SQL seguro y síntesis en español."""

    def __init__(self, session: AsyncSession, ollama: Optional[OllamaAdapter] = None):
        self.session = session
        self.ollama = ollama or OllamaAdapter()
        self.vector_repo = VectorRepository(session)
        self.mariadb = MariaDBAdapter()
        self.conn_manager = ManageConnectionsUseCase(session)
        self.guardrail = SQLGuardrail(max_limit=500)
        self.settings = get_settings()

    async def _get_or_create_session(self, session_id: Optional[str], user_id: str, prompt: str) -> uuid.UUID:
        """Obtiene o inicializa una sesión de chat."""
        if session_id:
            try:
                parsed_id = uuid.UUID(session_id)
                db_session = await self.session.get(ChatSessionModel, parsed_id)
                if db_session:
                    db_session.updated_at = datetime.now(timezone.utc)
                    return db_session.id
            except Exception:
                pass

        new_session = ChatSessionModel(
            user_id=user_id,
            title=prompt[:55] + ("..." if len(prompt) > 55 else "")
        )
        self.session.add(new_session)
        await self.session.commit()
        return new_session.id

    @staticmethod
    def analyze_columns_for_chart(
        columns: List[str],
        rows: List[Dict[str, Any]],
        wants_chart: bool = False,
        wants_table: bool = False,
        preferred_type: str = "bar",
        prompt: str = "",
        force_ready: bool = False
    ) -> Dict[str, Any]:
        """
        Analiza los tipos de datos de las columnas, extrae muestras reales por columna,
        sugiere dimensiones (Eje X) y métricas numéricas (Eje Y), y determina si la IA
        debe preguntar primero al usuario con qué campos desea construir el gráfico
        (needs_field_selection = True) o si el usuario ya especificó los campos exactos.
        """
        dimension_cols: List[str] = []
        metric_cols: List[str] = []
        fk_id_cols: List[str] = []
        column_samples: Dict[str, Dict[str, str]] = {}
        sample_rows = rows[:25]

        for col in columns:
            col_lower = col.lower()
            is_id_like = (
                col_lower == "id"
                or col_lower.endswith("_id")
                or col_lower.startswith("id_")
                or col_lower.startswith("fk_")
                or col_lower.endswith("_fk")
            )
            non_null_vals = [
                r.get(col) for r in sample_rows
                if r.get(col) is not None and str(r.get(col)).strip() != ""
            ]
            first_sample = str(non_null_vals[0])[:32] if non_null_vals else "N/A"

            if not non_null_vals:
                if is_id_like:
                    fk_id_cols.append(col)
                    column_samples[col] = {"kind": "foreign_key", "sample": first_sample}
                else:
                    dimension_cols.append(col)
                    column_samples[col] = {"kind": "category", "sample": first_sample}
                continue

            numeric_hits = 0
            for val in non_null_vals:
                if isinstance(val, bool):
                    continue
                if isinstance(val, (int, float)):
                    numeric_hits += 1
                else:
                    try:
                        float(str(val).replace(",", ""))
                        numeric_hits += 1
                    except Exception:
                        pass

            is_mostly_numeric = (numeric_hits / len(non_null_vals)) >= 0.8

            if is_id_like:
                fk_id_cols.append(col)
                column_samples[col] = {"kind": "foreign_key", "sample": first_sample}
            elif is_mostly_numeric:
                metric_cols.append(col)
                column_samples[col] = {"kind": "metric", "sample": first_sample}
            else:
                dimension_cols.append(col)
                column_samples[col] = {"kind": "category", "sample": first_sample}

        # Si no hay ninguna columna descriptiva y solo vinieron IDs, usar los IDs como fallback
        if not dimension_cols and fk_id_cols:
            dimension_cols = list(fk_id_cols)
        elif not dimension_cols and columns:
            dimension_cols = [columns[0]]

        default_x = dimension_cols[0] if dimension_cols else (columns[0] if columns else "")
        # Priorizar columnas descriptivas humanas (nombre, empresa, estado, departamento, tipo) sobre códigos o fechas
        for d_col in dimension_cols:
            if re.search(r"\b(nombre|name|razon_social|empresa|cliente|estado|status|departamento|proceso|tipo|categoria)\b", d_col.lower().replace("_", " ")):
                default_x = d_col
                break

        default_y = metric_cols[0] if metric_cols else ""
        default_agg = "SUM" if default_y else "COUNT"

        # Detectar si el prompt del usuario ya menciona explícitamente columnas del dataset
        matched_dims: List[str] = []
        matched_metrics: List[str] = []
        norm_prompt = remove_accents((prompt or "").lower())

        if norm_prompt:
            for col in columns:
                norm_col = remove_accents(col.lower())
                # Soportar coincidencia por nombre exacto de columna (con guiones bajos o espacios)
                col_tokens = [norm_col, norm_col.replace("_", " ")]
                for tok in col_tokens:
                    if len(tok) >= 3 and re.search(rf"\b{re.escape(tok)}\b", norm_prompt):
                        if col in metric_cols:
                            if col not in matched_metrics:
                                matched_metrics.append(col)
                        else:
                            if col not in matched_dims:
                                matched_dims.append(col)
                        break

        if matched_dims:
            default_x = matched_dims[0]
        if matched_metrics:
            default_y = matched_metrics[0]
            default_agg = "SUM"

        if re.search(r"\b(conteo|contar|cantidad\s+de\s+registros|count)\b", norm_prompt):
            default_agg = "COUNT"
        elif re.search(r"\b(promedio|media|avg)\b", norm_prompt) and default_y:
            default_agg = "AVG"
        elif re.search(r"\b(suma|sumar|total|sum)\b", norm_prompt) and default_y:
            default_agg = "SUM"

        explicit_axis_syntax = bool(
            re.search(
                r"\b(eje\s+[xy]|agrupad[oa]\s+por|agrupar\s+por|en\s+base\s+a\s+los?\s+campos?|con\s+los?\s+campos?)\b",
                norm_prompt
            )
        )
        has_explicit_fields = (
            force_ready
            or (len(matched_dims) >= 1 and (len(matched_metrics) >= 1 or explicit_axis_syntax))
            or (len(matched_dims) >= 2)
        )

        # Opción A: Si el usuario pidió gráfico (o hay varias columnas candidatas) y NO especificó
        # los campos exactos a graficar, activar needs_field_selection = True para que la IA le pregunte primero
        needs_field_selection = bool(
            wants_chart and len(columns) > 2 and not has_explicit_fields
        )

        return {
            "wants_chart": wants_chart,
            "wants_table": wants_table,
            "output_mode": (
                "both" if (wants_chart and wants_table)
                else ("chart" if wants_chart else ("table" if wants_table else "text_only"))
            ),
            "needs_field_selection": needs_field_selection,
            "chart_type": preferred_type or "bar",
            "suggested_type": preferred_type or "bar",
            "x_field": default_x,
            "suggested_x": default_x,
            "y_field": default_y,
            "suggested_y": default_y,
            "aggregation": default_agg,
            "suggested_agg": default_agg,
            "dimension_columns": dimension_cols,
            "metric_columns": metric_cols,
            "foreign_key_columns": fk_id_cols,
            "column_samples": column_samples,
            "all_columns": columns
        }

    async def execute_sync(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        user_id: str = "user",
        connection_id: Optional[str] = None,
        user_role: str = "user",
        user_permissions: Optional[List[str]] = None,
        retry_message_id: Optional[str] = None,
        attachment_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Ejecuta la respuesta completa síncrona evaluando políticas, roles RBAC y reintento sin duplicación."""
        start_time = time.time()
        s_id = await self._get_or_create_session(session_id, user_id, prompt)
        perms = user_permissions or []

        # GUARDRAIL RBAC IA: Comprobar acciones restringidas según el rol y permisos
        is_super_admin = (user_role == "super-admin")
        lower_prompt = prompt.lower()

        # 1. Intento de entrenamiento / enseñanza sin permiso 'chat.train'
        if ("enséñale" in lower_prompt or "aprende" in lower_prompt or "regla" in lower_prompt) and not is_super_admin:
            if "chat.train" not in perms and perms:
                return {
                    "session_id": str(s_id),
                    "message": f"Acción restringida: Tu rol actual ('{user_role}') no tiene autorización para registrar reglas de conocimiento o entrenar el modelo RAG.",
                    "intent": "general_chat",
                    "has_tabular_data": False,
                    "dataset_id": None,
                    "row_count": 0,
                    "generated_sql": None,
                    "columns": [],
                    "preview_rows": [],
                    "chart_config": None,
                    "latency_ms": int((time.time() - start_time) * 1000)
                }

        # 2. Intento de consulta directa a bases de datos sin permiso 'chat.use'
        if not is_super_admin and perms and "chat.use" not in perms:
            return {
                "session_id": str(s_id),
                "message": f"Acceso restringido: Tu perfil ('{user_role}') no cuenta con privilegios para consultar el motor analítico.",
                "intent": "general_chat",
                "has_tabular_data": False,
                "dataset_id": None,
                "row_count": 0,
                "generated_sql": None,
                "columns": [],
                "preview_rows": [],
                "chart_config": None,
                "latency_ms": int((time.time() - start_time) * 1000)
            }

        # 1. Clasificar intención y detectar explícitamente qué formato solicitó el usuario
        intent = IntentClassifier.classify(prompt)
        output_fmt = IntentClassifier.detect_output_format(prompt)
        wants_chart = bool(output_fmt["wants_chart"])
        wants_table = bool(output_fmt["wants_table"])
        preferred_chart_type = str(output_fmt["preferred_chart_type"])
        generated_sql = None
        dataset_id = None
        row_count = 0
        has_tabular_data = False
        columns_list = []
        preview_rows = []
        chart_config = None
        rules_applied = []
        clarification_payload = None
        message_text = ""

        # Obtener el turno previo del asistente y su SQL (si existieron) para contexto del detector
        prev_asst_stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == s_id, ChatMessageModel.role == "assistant")
            .order_by(ChatMessageModel.created_at.desc())
            .limit(1)
        )
        prev_asst_msg = (await self.session.execute(prev_asst_stmt)).scalars().first()
        prev_asst_content = prev_asst_msg.content if prev_asst_msg else None
        prev_asst_sql = prev_asst_msg.generated_sql if prev_asst_msg else None

        # Verificar si en la misma sesión existe un dataset reciente y el usuario está respondiendo
        # con qué campos crear el gráfico (flujo conversacional en 2 pasos — Opción A)
        prev_ds_stmt = (
            select(QueryDatasetModel)
            .where(QueryDatasetModel.session_id == s_id)
            .order_by(QueryDatasetModel.created_at.desc())
            .limit(1)
        )
        last_dataset = (await self.session.execute(prev_ds_stmt)).scalars().first()
        reused_previous_dataset = False

        if intent != "teach_knowledge" and last_dataset and last_dataset.columns and last_dataset.rows:
            norm_p = remove_accents(prompt.lower())
            matched_prev_cols = [
                c for c in last_dataset.columns
                if len(c) >= 3 and (
                    re.search(rf"\b{re.escape(remove_accents(c.lower()))}\b", norm_p)
                    or re.search(rf"\b{re.escape(remove_accents(c.lower()).replace('_', ' '))}\b", norm_p)
                )
            ]
            is_followup_chart_confirmation = bool(
                matched_prev_cols and (
                    wants_chart
                    or re.search(
                        r"\b(usa(r|ndo)?|con\s+(el|los|la|las)?\s*campo[s]?|agrupa(r|do|ndo)?\s+por|eje\s+[xy]|grafica(r|lo)?|haz(lo|me)?)\b",
                        norm_p
                    )
                )
            )
            if is_followup_chart_confirmation:
                intent = "data_query"
                wants_chart = True
                reused_previous_dataset = True

        # Detección de resolución de aclaración rápida (formato /clarify <target_entity>)
        if prompt.strip().startswith("/clarify "):
            clarified_target = prompt.strip().replace("/clarify ", "", 1).strip()
            resilience_metrics.inc_clarifications_resolved()
            try:
                # Guardar como candidato personal scope='user', status='candidate'
                active_c = await self.conn_manager.get_active_or_target_connection(connection_id)
                target_c_id = active_c.id if active_c else None
                ingest_uc = IngestKnowledgeUseCase(self.session, ollama=self.ollama)
                cand_doc = await ingest_uc.execute(
                    title=f"Sinónimo aclarado: {clarified_target}",
                    category="business_rule",
                    department=active_c.name if active_c else "Aclaraciones",
                    content=f"El término aclarado corresponde a la tabla `{clarified_target}`.",
                    metadata={
                        "connection_id": str(target_c_id) if target_c_id else None,
                        "target_entity": clarified_target,
                        "trigger_signal": "clarification_resolved",
                        "status": "candidate",
                        "scope": "user",
                        "user_id": user_id
                    }
                )
            except Exception as cand_err:
                pass
            prompt = f"Consulta la tabla {clarified_target}"

        # Gestión de Persistencia del Mensaje del Usuario: Reintento o Mensaje Nuevo
        reused_user_msg = None
        if retry_message_id:
            try:
                parsed_retry_id = uuid.UUID(retry_message_id)
                existing_msg = await self.session.get(ChatMessageModel, parsed_retry_id)
                if not existing_msg:
                    raise ValueError(f"El mensaje a reintentar '{retry_message_id}' no existe.")
                if existing_msg.session_id != s_id:
                    raise ValueError("El mensaje a reintentar no pertenece a la sesión activa.")
                if existing_msg.role != "user":
                    raise ValueError("Solo se pueden reintentar mensajes emitidos por el usuario.")

                # Verificar que no exista ya una respuesta de rol 'assistant' posterior en esta sesión
                later_assist_stmt = (
                    select(ChatMessageModel)
                    .where(
                        ChatMessageModel.session_id == s_id,
                        ChatMessageModel.role == "assistant",
                        ChatMessageModel.created_at >= existing_msg.created_at
                    )
                )
                existing_assistant = (await self.session.execute(later_assist_stmt)).scalars().first()
                if existing_assistant:
                    raise ValueError("Este mensaje ya cuenta con una respuesta generada en la sesión.")

                existing_msg.content = prompt
                existing_msg.intent = intent
                reused_user_msg = existing_msg
                await self.session.commit()
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Error validando reintento de mensaje: {str(e)}")

        user_msg_id = None
        if not reused_user_msg:
            # Guardar el nuevo mensaje del usuario en la sesión con commit inmediato
            user_msg_model = ChatMessageModel(
                session_id=s_id,
                role="user",
                content=prompt,
                intent=intent
            )
            self.session.add(user_msg_model)
            await self.session.commit()
            user_msg_id = str(user_msg_model.id)
        else:
            user_msg_id = str(reused_user_msg.id)

        if intent == "teach_knowledge":
            # El usuario le está enseñando una regla, relación JOIN, diccionario o fórmula directamente en el chat
            capsule = IntentClassifier.extract_teaching_capsule(prompt)
            active_conn = await self.conn_manager.get_active_or_target_connection(connection_id)
            target_conn_id = str(active_conn.id) if active_conn else connection_id
            dept_name = active_conn.name if active_conn else "Entrenamiento IA"

            cat = capsule["category"]
            title = capsule["title"]
            src_t = capsule.get("source_table") or ""
            src_c = capsule.get("source_column") or ""
            tgt_t = capsule.get("target_table") or ""
            tgt_c = capsule.get("target_column") or "id"
            lbl_c = capsule.get("label_column") or "name"
            join_hint = capsule.get("join_hint") or ""
            rel_tables = capsule.get("related_tables") or []

            if cat == "custom_relation" and src_t and tgt_t:
                enriched_text = (
                    f"RELACIÓN OBLIGATORIA ENSEÑADA POR EL USUARIO: La tabla `{src_t}` se relaciona con `{tgt_t}` "
                    f"uniendo `{src_t}.{src_c} = {tgt_t}.{tgt_c}`. "
                    f"REGLA: Cuando se pidan datos o gráficos, nunca muestres `{src_c}` crudo; haz siempre "
                    f"`JOIN {tgt_t} ON {src_t}.{src_c} = {tgt_t}.{tgt_c}` y selecciona `{tgt_t}.{lbl_c}`.\n"
                    f"Instrucción original del usuario: {prompt}"
                )
            else:
                enriched_text = f"REGLA DE NEGOCIO ENSEÑADA POR EL USUARIO:\n{prompt}"

            ingest_uc = IngestKnowledgeUseCase(self.session, ollama=self.ollama)
            saved_doc = await ingest_uc.execute(
                title=title,
                category=cat,
                department=dept_name,
                content=enriched_text,
                metadata={
                    "connection_id": target_conn_id,
                    "source_table": src_t,
                    "source_column": src_c,
                    "target_table": tgt_t,
                    "target_column": tgt_c,
                    "label_column": lbl_c,
                    "related_tables": rel_tables,
                    "join_hint": join_hint,
                    "taught_via": "chat"
                }
            )

            if cat == "custom_relation" and src_t and tgt_t:
                await self.vector_repo.attach_custom_relation_to_schema_docs(
                    source_table=src_t,
                    target_table=tgt_t,
                    join_hint=join_hint,
                    connection_id=target_conn_id
                )
                message_text = (
                    f"### 🧠 ¡Relación entre Tablas Aprendida y Vectorizada!\n\n"
                    f"He guardado esta regla relacional en mi memoria vectorial (`pgvector`) para la conexión **{dept_name}** y no ejecuté ninguna consulta ni gráfico innecesario:\n\n"
                    f"- **Tabla Origen**: `{src_t}` (columna llave foránea: `{src_c}`)\n"
                    f"- **Tabla Maestra**: `{tgt_t}` (columna llave primaria: `{tgt_c}`)\n"
                    f"- **Condición `JOIN` aprendida**: `JOIN {tgt_t} ON {src_t}.{src_c} = {tgt_t}.{tgt_c}`\n"
                    f"- **Etiqueta legible obligatoria**: Mostrar siempre `{tgt_t}.{lbl_c}` en lugar de `{src_c}`.\n\n"
                    f"A partir de ahora, cuando me pidas una consulta, una tabla o un gráfico sobre `{src_t}` y `{tgt_t}`, aplicaré automáticamente este `JOIN`."
                )
            else:
                message_text = (
                    f"### 🧠 ¡Nuevo Conocimiento Aprendido y Vectorizado!\n\n"
                    f"He registrado tu enseñanza en mi base de conocimiento vectorial (`pgvector`) bajo la categoría **`{cat}`**:\n\n"
                    f"- **Regla guardada**: *{prompt}*\n"
                    f"- **ID de Cápsula**: `{saved_doc.get('document_id', 'ok')[:8]}`\n\n"
                    f"La tendré en cuenta automáticamente cuando me pidas consultas, tablas o gráficos relacionados."
                )

        elif intent == "general_chat":
            message_text = await self.ollama.generate_completion(
                prompt=prompt,
                system_prompt=(
                    "Eres DataMind AI, un asistente de inteligencia artificial para análisis de bases de datos "
                    "y procesos corporativos. Responde con un tono cálido, educado, profesional y en español, "
                    "utilizando formato Markdown estructurado (encabezados `###`, listas con viñetas `-` y **negritas** para conceptos clave)."
                )
            )

        elif intent == "process_qa":
            # RAG de Procesos en pgvector
            query_vec = await self.ollama.generate_embedding(prompt)
            chunks = await self.vector_repo.search_similar(query_vec, top_k=3, category="process_manual")
            context = "\n---\n".join([c.chunk_text for c in chunks]) if chunks else "No se encontró información específica en los manuales."

            sys_prompt = (
                "Eres un asistente de procesos corporativos. Responde a la pregunta del usuario utilizando "
                "el siguiente contexto de manuales y procedimientos. Si no tienes la información, indícalo "
                "con amabilidad sin inventar datos. Redacta en español formal y claro, estructurando la respuesta "
                "en Markdown (encabezados `###`, viñetas `-`, **negritas** y código en línea `como_este`).\n\n"
                f"CONTEXTO DE PROCESOS:\n{context}"
            )
            message_text = await self.ollama.generate_completion(prompt=prompt, system_prompt=sys_prompt)

        elif intent == "data_query":
            # 0. Si la petición incluye archivos adjuntos cargados en la sesión, consultar DuckDB localmente
            if attachment_ids:
                from app.use_cases.query_attachment import QueryAttachmentUseCase
                query_att_uc = QueryAttachmentUseCase(self.session, ollama=self.ollama)
                attached_records = await query_att_uc.get_attachments(attachment_ids)
                if attached_records:
                    message_text, generated_sql, rows, row_count = await query_att_uc.generate_and_execute_query(
                        prompt=prompt,
                        attachments=attached_records
                    )
                    if row_count > 0:
                        has_tabular_data = True
                        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
                        columns_list = list(rows[0].keys())
                        preview_rows = rows[:10]
                        chart_config = self.analyze_columns_for_chart(
                            columns=columns_list,
                            rows=rows,
                            wants_chart=wants_chart,
                            preferred_type=preferred_chart_type,
                            prompt=prompt,
                            force_ready=False
                        )
                        dataset_model = QueryDatasetModel(
                            dataset_id=dataset_id,
                            session_id=s_id,
                            sql_executed=generated_sql or "SELECT * FROM attachment",
                            columns=columns_list,
                            rows=rows,
                            row_count=row_count,
                            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.settings.dataset_cache_ttl_hours)
                        )
                        self.session.add(dataset_model)
                        await self.session.commit()
            elif reused_previous_dataset and last_dataset:
                # Paso 2 del flujo Opción A: el usuario respondió en el chat indicando con qué campos crear el gráfico
                has_tabular_data = True
                dataset_id = last_dataset.dataset_id
                generated_sql = last_dataset.sql_executed
                columns_list = list(last_dataset.columns or [])
                rows = list(last_dataset.rows or [])
                row_count = last_dataset.row_count or len(rows)
                preview_rows = rows[:10]

                chart_config = self.analyze_columns_for_chart(
                    columns=columns_list,
                    rows=rows,
                    wants_chart=True,
                    preferred_type=preferred_chart_type,
                    prompt=prompt,
                    force_ready=True
                )

                chosen_x = chart_config.get("x_field") or "categoría"
                chosen_y = chart_config.get("y_field") or "registros"
                chosen_agg = chart_config.get("aggregation") or "COUNT"
                chosen_type = chart_config.get("chart_type") or "bar"

                sample_preview = json.dumps(rows[:5], ensure_ascii=False)
                synthesis_prompt = (
                    f"El usuario confirmó con qué campos desea generar su gráfico sobre la consulta previa.\n"
                    f"Solicitud del usuario: {prompt}\n"
                    f"Configuración aplicada al gráfico: Tipo `{chosen_type}`, Eje X (Agrupación) = `{chosen_x}`, "
                    f"Operación = `{chosen_agg}`, Eje Y = `{chosen_y or 'Conteo de registros'}`.\n"
                    f"Total de registros analizados: {row_count}.\n"
                    f"Muestra de datos: {sample_preview}\n\n"
                    f"Redacta una respuesta ejecutiva y clara en Markdown confirmando que has generado el gráfico "
                    f"utilizando exactamente el campo `{chosen_x}` y la métrica `{chosen_agg}({chosen_y or 'registros'})`, "
                    f"destacando los puntos clave que se aprecian en la visualización."
                )
                message_text = await self.ollama.generate_completion(prompt=synthesis_prompt)
            else:
                # Text-to-SQL dinámico sobre la conexión activa o seleccionada
                active_conn = await self.conn_manager.get_active_or_target_connection(connection_id)
                target_conn_id = str(active_conn.id) if active_conn else None
                db_engine = active_conn.engine if active_conn else "mariadb"
                db_name = active_conn.database_name if active_conn else self.settings.mariadb_db
                conn_label = active_conn.name if active_conn else f"MariaDB ({db_name})"

                if active_conn:
                    db_adapter = DynamicDBAdapter(
                        engine=active_conn.engine,
                        host=active_conn.host,
                        port=active_conn.port,
                        database_name=active_conn.database_name,
                        username=active_conn.username,
                        password=active_conn.password,
                        timeout=self.settings.mariadb_timeout_seconds
                    )
                    sql_dialect = db_adapter.sqlglot_dialect
                    engine_title = "PostgreSQL" if db_adapter.is_postgres else "MariaDB/MySQL"
                else:
                    db_adapter = self.mariadb
                    sql_dialect = "mysql"
                    engine_title = "MariaDB/MySQL"

                # 1. Recuperar esquemas relevantes + tablas relacionadas (1-Hop Graph Expansion + Hybrid Search)
                query_vec = await self.ollama.generate_embedding(prompt)
                schema_chunks = await self.vector_repo.search_schema_with_relations(
                    query_embedding=query_vec,
                    prompt_text=prompt,
                    top_k=6,
                    connection_id=target_conn_id
                )

                # ==============================================================================
                # Feature 007: Detección de Entidad Inequívoca y Prevención de Falsa Aclaración
                # ==============================================================================
                is_ambiguous = False
                ambiguity_reason = None
                options_list = []

                # Obtener la lista de tablas sincronizadas reales de la conexión
                synced_tbls = active_conn.synced_tables if (active_conn and active_conn.synced_tables) else []
                is_unambiguous, unambiguous_target = DataHumanizer.resolve_unambiguous_entity(prompt, synced_tbls)

                if is_unambiguous and unambiguous_target:
                    # El usuario nombró de forma evidente la entidad (ej: 'usuarios' -> 'users')
                    is_ambiguous = False
                else:
                    # Verificar si el usuario mencionó explícitamente el nombre exacto de alguna tabla en el prompt
                    norm_prompt_lower = remove_accents((prompt or "").lower())
                    explicitly_named_tables = set()
                    if schema_chunks:
                        for ch in schema_chunks:
                            t_raw = str((ch.metadata or {}).get("table_name", "")).strip()
                            if t_raw and len(t_raw) >= 3:
                                t_norm = remove_accents(t_raw.lower())
                                if re.search(rf"\b{re.escape(t_norm)}\b", norm_prompt_lower):
                                    explicitly_named_tables.add(t_raw.lower())

                    # Si el usuario mencionó explícitamente una sola tabla unívoca, no hay ambigüedad
                    if len(explicitly_named_tables) == 1:
                        is_ambiguous = False
                    elif schema_chunks and len(schema_chunks) >= 1:
                        top_chunk = schema_chunks[0]
                        top_score = getattr(top_chunk, "similarity_score", 0.0) or 0.0

                        # 1. Confianza general baja (< 0.65) si no hay coincidencia léxica fuerte
                        if top_score < 0.65 and len(schema_chunks) >= 2 and not explicitly_named_tables:
                            is_ambiguous = True
                            ambiguity_reason = "low_retrieval_confidence"

                        # 2. Empate técnico entre los 2 mejores candidatos (delta <= 0.04)
                        elif len(schema_chunks) >= 2 and not explicitly_named_tables:
                            second_chunk = schema_chunks[1]
                            second_score = getattr(second_chunk, "similarity_score", 0.0) or 0.0
                            delta = abs(top_score - second_score)
                            
                            t1 = str((top_chunk.metadata or {}).get("table_name", "")).strip()
                            t2 = str((second_chunk.metadata or {}).get("table_name", "")).strip()

                            if delta <= 0.04 and t1 and t2 and t1.lower() != t2.lower():
                                is_ambiguous = True
                                ambiguity_reason = "ambiguous_candidates"

                    if is_ambiguous:
                        seen_opts = set()
                        for ch in schema_chunks[:3]:
                            t_n = str((ch.metadata or {}).get("table_name", "")).strip()
                            t_desc = str((ch.metadata or {}).get("description") or (ch.metadata or {}).get("table_comment") or f"Tabla {t_n}")
                            if t_n and t_n.lower() not in seen_opts:
                                seen_opts.add(t_n.lower())
                                options_list.append({
                                    "id": t_n,
                                    "label": t_n,
                                    "description": t_desc[:120]
                                })

                # Si es ambiguo y tenemos al menos 2 opciones reales, emitir aclaración en vez de generar SQL
                if is_ambiguous and len(options_list) >= 2:
                    resilience_metrics.inc_clarifications_requested()
                    clarification_payload = {
                        "type": "clarification_request",
                        "question": "Para darte un resultado exacto, ¿a cuál de las siguientes tablas te refieres?",
                        "extracted_term": prompt[:60],
                        "options": options_list,
                        "original_prompt": prompt
                    }

                    # Registrar término en la cola de términos no entendidos
                    try:
                        uqt_repo = UnresolvedQueryTermRepository(self.session)
                        conn_u = uuid.UUID(target_conn_id) if target_conn_id else None
                        await uqt_repo.create_term(
                            session_id=s_id,
                            user_id=user_id,
                            prompt=prompt,
                            extracted_term=prompt[:60],
                            failure_reason=ambiguity_reason or "ambiguous_candidates",
                            connection_id=conn_u,
                            candidate_tables=options_list
                        )
                    except Exception as uqt_err:
                        pass

                    options_md = "\n".join([f"- **`{opt['label']}`**: {opt['description']}" for opt in options_list])
                    message_text = (
                        f"Para responderte con total precisión, por favor aclárame a cuál de estas entidades te refieres:\n\n"
                        f"{options_md}\n\n"
                        f"*(Puedes hacer clic en una de las opciones interactivas que aparecen a continuación para continuar automáticamente)*"
                    )
                else:
                    # 2. Recuperar reglas de negocio, relaciones manuales, fórmulas y ejemplos SQL aprendidos del usuario
                    learned_rule_chunks = await self.vector_repo.search_learned_rules(
                        query_embedding=query_vec,
                        prompt_text=prompt,
                        top_k=5,
                        connection_id=target_conn_id
                    )

                    # 2.1 Recuperación de directivas aprendidas dinámicamente si el feature flag está activo
                    dynamic_rules: List[Dict[str, Any]] = []
                    dynamic_rules_applied: List[Dict[str, Any]] = []
                    dynamic_rules_block = ""
                    if self.settings.enable_dynamic_knowledge_injection:
                        try:
                            # Vectorizar usando el prefijo de búsqueda para queries
                            query_search_vec = await self.ollama.generate_embedding(f"search_query: {prompt}")
                            dynamic_rules = await self.vector_repo.search_dynamic_knowledge_rules(
                                query_embedding=query_search_vec,
                                user_id=user_id,
                                connection_id=target_conn_id,
                                top_k=self.settings.knowledge_top_k,
                                similarity_threshold=self.settings.knowledge_similarity_threshold
                            )
                            if dynamic_rules:
                                lines = []
                                for dr in dynamic_rules:
                                    dynamic_rules_applied.append({"id": dr["id"], "title": dr["title"]})
                                    lines.append(f"- Regla para `{dr['target_entity']}` (`{dr['target_column']}`): {dr['prescriptive_condition']}")
                                dynamic_rules_block = (
                                    "\n<<<DIRECTIVAS_APRENDIDAS>>>\n"
                                    + "\n".join(lines)
                                    + "\n<<<FIN_DIRECTIVAS>>>\n"
                                )
                                rules_applied = dynamic_rules_applied
                        except Exception as dyn_err:
                            logger.warning(f"Error recuperando directivas dinámicas: {str(dyn_err)}")

                    # Extraer pistas explícitas de JOIN aprendidas en los metadatos vectoriales
                    learned_joins: List[str] = []
                    for ch in schema_chunks:
                        for jh in (ch.metadata or {}).get("join_hints", []) or []:
                            if jh not in learned_joins:
                                learned_joins.append(jh)
                    for r_ch in learned_rule_chunks:
                        jh_custom = (r_ch.metadata or {}).get("join_hint")
                        if jh_custom and jh_custom not in learned_joins:
                            learned_joins.insert(0, jh_custom)

                    joins_summary = (
                        "\nRELACIONES Y JOINS APRENDIDOS EN EL GRAFO VECTORIAL:\n"
                        + "\n".join([f"- {j}" for j in learned_joins[:12]])
                        if learned_joins else ""
                    )

                    rules_summary = (
                        "\nREGLAS DE NEGOCIO, DICCIONARIO Y EJEMPLOS SQL ENSEÑADOS POR EL USUARIO (PRIORIDAD MÁXIMA):\n"
                        + "\n".join([f"- {rc.chunk_text}" for rc in learned_rule_chunks])
                        if learned_rule_chunks else ""
                    )

                    schema_context = "\n\n".join([c.chunk_text for c in schema_chunks]) if schema_chunks else (
                        "Tabla: orders (id, customer_id, order_code, status, created_at)\n"
                        "Tabla: customers (id, name, email)\n"
                        "Tabla: products (id, sku, name, stock)"
                    )

                    sql_prompt = (
                        f"Eres un analista de datos de negocios experto en {engine_title} para la base de datos `{db_name}` ({conn_label}). "
                        f"Escribe ÚNICAMENTE una consulta SQL SELECT válida para {engine_title} "
                        f"que responda a la solicitud del usuario, sin explicaciones ni markdown.\n"
                        f"ESQUEMAS DE TABLAS Y RELACIONES VECTORIZADOS DISPONIBLES EN `{db_name}`:\n{schema_context}{joins_summary}{rules_summary}{dynamic_rules_block}\n\n"
                        f"REGLAS OBLIGATORIAS DE ANÁLISIS RELACIONAL Y GRÁFICOS:\n"
                        f"- Usa únicamente las tablas y columnas listadas en los esquemas.\n"
                        f"- PROHIBICIÓN ESTRICTA DE SEGURIDAD: NUNCA incluyas en el SELECT columnas que almacenen contraseñas, tokens de autenticación o secretos (ej: password, remember_token, gotify_pass, gotify_app_token, api_token, secret, hash, salt).\n"
                        f"- SOPORTE MULTI-ESQUEMA: Si la tabla contiene prefijo de esquema (ej: `produccion.ordenes`, `inventario.items`, `hop.registro`), SIEMPRE califica el nombre completo en `FROM` y `JOIN` con su esquema exacto (ej. `FROM produccion.ordenes`). Para tablas del esquema `public`, puedes usar `public.tabla` o `tabla`.\n"
                        f"- APLICA ESTRICTAMENTE las REGLAS DE NEGOCIO, DICCIONARIO Y EJEMPLOS SQL ENSEÑADOS POR EL USUARIO si aparecen arriba.\n"
                        f"- SI EXISTEN <<<DIRECTIVAS_APRENDIDAS>>>, APLÍCALAS DE FORMA OBLIGATORIA Y PRIORITARIA en las cláusulas WHERE y filtros correspondientes.\n"
                        f"- REGLA DE ORO DE RELACIONES (`JOIN`): Cuando una tabla tenga columnas de relación como `id_empresa`, `empresa_id`, `current_company_id`, `id_cliente`, `id_rollo`, `id_orden`, etc., ese ID por sí solo NO dice el nombre real. SIEMPRE realiza el `INNER JOIN` o `LEFT JOIN` hacia la tabla relacionada (por ejemplo `JOIN empresa ON usuario.id_empresa = empresa.id` o `JOIN companies ON users.current_company_id = companies.id`) e incluye en el `SELECT` las columnas descriptivas reales de la tabla maestra con un alias claro (ej. `companies.name AS empresa_nombre`).\n"
                        f"- Si el usuario menciona dos o más tablas o entidades vinculadas/relacionadas, realiza el `JOIN` correspondiente e incluye en el `SELECT` las columnas descriptivas (nombres, estados, tipos, fechas) y numéricas (cantidades, pesos, totales) de ambas tablas para poder analizarlas y graficarlas con datos exactos.\n"
                        f"- Si el usuario pide un gráfico o análisis sin especificar una sola columna, selecciona múltiples columnas relevantes de las tablas involucradas (en lugar de un simple `COUNT(*)` de 1 sola fila) para que el usuario pueda elegir con qué campos construir su gráfico.\n"
                        f"- Si el usuario pregunta si tienes conocimiento de una tabla o qué datos contiene, genera una consulta SELECT sencilla como `SELECT * FROM <tabla> LIMIT 20;`.\n"
                        f"- Respeta estrictamente la sintaxis de {engine_title}.\n\n"
                        f"SOLICITUD: {prompt}\n"
                        f"CONSULTA SQL:"
                    )
                    raw_sql = await self.ollama.generate_completion(
                        prompt=sql_prompt,
                        max_tokens=300,
                        temperature=0.0
                    )
                    # Validar SQL inicial o pasar por reparación si el guardrail o el modelo fallaron
                    repair_agent = SqlRepairAgent(ollama=self.ollama, guardrail=self.guardrail)
                    is_valid, safe_sql, error_msg = self.guardrail.validate_and_sanitize(raw_sql, dialect=sql_dialect)

                    sql_to_execute = safe_sql if is_valid else None
                    execution_success = False
                    last_error_details = error_msg if not is_valid else None
                    attempts_done = 0
                    max_repair_attempts = 2

                    # Bucle de Auto-Reparación (Self-Healing Loop)
                    while attempts_done <= max_repair_attempts:
                        if sql_to_execute:
                            try:
                                rows = await db_adapter.execute_query(sql_to_execute)
                                execution_success = True
                                generated_sql = sql_to_execute
                                if attempts_done > 0:
                                    resilience_metrics.inc_repair_success()
                                break
                            except Exception as exec_err:
                                last_error_details = str(exec_err)
                                attempts_done += 1
                                if attempts_done <= max_repair_attempts:
                                    resilience_metrics.inc_repair_attempts()
                                    rep_ok, repaired_sql, rep_err = await repair_agent.attempt_repair(
                                        original_prompt=prompt,
                                        failed_sql=sql_to_execute,
                                        error_details=last_error_details,
                                        schema_context=schema_context,
                                        dialect=sql_dialect,
                                        engine_title=engine_title
                                    )
                                    if rep_ok and repaired_sql:
                                        sql_to_execute = repaired_sql
                                    else:
                                        last_error_details = rep_err or "Guardrail rechazó la corrección"
                                        sql_to_execute = None
                        else:
                            attempts_done += 1
                            if attempts_done <= max_repair_attempts:
                                resilience_metrics.inc_repair_attempts()
                                rep_ok, repaired_sql, rep_err = await repair_agent.attempt_repair(
                                    original_prompt=prompt,
                                    failed_sql=raw_sql,
                                    error_details=last_error_details or "Sintaxis o instrucción no válida",
                                    schema_context=schema_context,
                                    dialect=sql_dialect,
                                    engine_title=engine_title
                                )
                                if rep_ok and repaired_sql:
                                    sql_to_execute = repaired_sql
                                else:
                                    last_error_details = rep_err or "No se pudo generar un SQL seguro"

                    if not execution_success:
                        resilience_metrics.inc_repair_exhausted()
                        # Registrar en cola de términos no entendidos
                        try:
                            uqt_repo = UnresolvedQueryTermRepository(self.session)
                            conn_u = uuid.UUID(target_conn_id) if target_conn_id else None
                            await uqt_repo.create_term(
                                session_id=s_id,
                                user_id=user_id,
                                prompt=prompt,
                                extracted_term=prompt[:60],
                                failure_reason="sql_repair_exhausted",
                                connection_id=conn_u,
                                error_message=last_error_details
                            )
                        except Exception:
                            pass

                        message_text = (
                            f"He analizado los esquemas de la base de datos `{db_name}`, pero no pude generar una consulta "
                            f"exacta para responder a tu solicitud sin ambigüedades.\n\n"
                            f"💡 **Sugerencia**: Intenta especificar con mayor claridad el nombre de la tabla o columnas que deseas consultar "
                            f"(ejemplo: *\"muéstrame los primeros 10 registros de la tabla {schema_chunks[0].metadata.get('table_name', 'principal') if schema_chunks else 'principal'}\"*)."
                        )
                    else:
                        row_count = len(rows)

                        if row_count > 0:
                            has_tabular_data = True
                            dataset_id = f"ds_{uuid.uuid4().hex[:12]}"

                            # Feature 007: Purgar datos sensibles y humanizar columnas para negocio
                            raw_columns = list(rows[0].keys())
                            human_cols, sanitized_rows, _ = DataHumanizer.sanitize_and_humanize(raw_columns, rows)
                            columns_list = human_cols
                            preview_rows = sanitized_rows[:10]

                            # Guardar dataset en caché para botón de Excel y Constructor de Gráficos (limpio y sin passwords)
                            dataset_model = QueryDatasetModel(
                                dataset_id=dataset_id,
                                session_id=s_id,
                                sql_executed=generated_sql,
                                columns=columns_list,
                                rows=sanitized_rows,
                                row_count=row_count,
                                expires_at=datetime.now(timezone.utc) + timedelta(hours=self.settings.dataset_cache_ttl_hours)
                            )
                            self.session.add(dataset_model)
                            await self.session.commit()

                            # Analizar columnas y determinar si requiere selección guiada de campos (Opción A)
                            chart_config = self.analyze_columns_for_chart(
                                columns=columns_list,
                                rows=sanitized_rows,
                                wants_chart=wants_chart,
                                wants_table=wants_table,
                                preferred_type=preferred_chart_type,
                                prompt=prompt
                            )

                            sample_preview = json.dumps(sanitized_rows[:5], ensure_ascii=False)
                            chart_instruction = ""
                            dims_str = ", ".join([f"`{c}`" for c in chart_config["dimension_columns"][:8]]) or "ninguna"
                            metrics_str = ", ".join([f"`{c}`" for c in chart_config["metric_columns"][:8]]) or "conteo de registros (`COUNT`)"

                            if chart_config.get("needs_field_selection") and wants_chart:
                                chart_instruction = (
                                    f"\nIMPORTANTE (FLUJO GUIADO DE GRÁFICOS):\n"
                                    f"- Ya analizaste los registros, obteniendo los siguientes campos:\n"
                                    f"  * **Campos de Agrupación (Eje X)**: {dims_str}\n"
                                    f"  * **Métricas Numéricas (Eje Y)**: {metrics_str}\n"
                                    f"- Pregúntale amablemente al usuario con cuáles de estos campos desea generar el gráfico."
                                )
                            elif wants_chart:
                                chart_instruction = (
                                    f"\nIMPORTANTE (GRÁFICO GENERADO):\n"
                                    f"- Confirma que has generado el gráfico con el campo `{chart_config['x_field']}` en el Eje X "
                                    f"y `{chart_config['aggregation']}({chart_config['y_field'] or 'registros'})` en el Eje Y."
                                )

                            synthesis_prompt = (
                                f"Eres un asistente corporativo de análisis empresarial que habla en español claro, profesional y de negocios.\n"
                                f"Pregunta del colaborador: {prompt}\n"
                                f"Total de registros recuperados: {row_count}.\n"
                                f"Muestra representativa de los datos de negocio: {sample_preview}\n\n"
                                f"DIRECTIVAS ESTRICTAS DE COMUNICACIÓN CON EL USUARIO:\n"
                                f"1. Habla 100% en términos humanos de procesos y negocios. NUNCA menciones nombres físicos de tablas (como 'users', 'company_user', 'companies', 'hop'), ni nombres de base de datos, ni la sentencia SQL ejecutada.\n"
                                f"2. Refiérete a los datos como 'los usuarios registrados', 'las empresas asociadas' o 'la información consultada'.\n"
                                f"3. Redacta una respuesta ejecutiva, amable y directa de máximo 2 párrafos concisos destacando los puntos más importantes.{chart_instruction}"
                            )
                            try:
                                message_text = await self.ollama.generate_completion(
                                    prompt=synthesis_prompt,
                                    max_tokens=220,
                                    temperature=0.2
                                )
                            except Exception as synth_err:
                                message_text = (
                                    f"Se consultó exitosamente la base de datos `{db_name}` y se recuperaron **{row_count} registros** "
                                    f"mediante la consulta SQL ejecutada.\n\n"
                                    f"Puedes explorar los datos completos en la tabla interactiva de abajo o exportarlos directamente a Excel (.xlsx)."
                                )
                        else:
                            message_text = f"Se consultó la base de datos `{db_name}` ({engine_title}) pero no se encontraron registros que coincidan con los criterios solicitados."

        latency = int((time.time() - start_time) * 1000)

        # Guardar mensaje en el historial con metadata_ incluyendo rules_applied
        msg_metadata = {}
        if rules_applied:
            msg_metadata["rules_applied"] = rules_applied

        msg_model = ChatMessageModel(
            session_id=s_id,
            role="assistant",
            content=message_text,
            intent=intent,
            generated_sql=generated_sql,
            dataset_id=dataset_id,
            latency_ms=latency,
            metadata_=msg_metadata
        )
        self.session.add(msg_model)
        await self.session.commit()

        return {
            "session_id": str(s_id),
            "message_id": str(msg_model.id),
            "user_message_id": user_msg_id,
            "previous_assistant_message": prev_asst_content,
            "previous_sql": prev_asst_sql,
            "message": message_text,
            "intent": intent,
            "has_tabular_data": has_tabular_data,
            "dataset_id": dataset_id,
            "row_count": row_count if has_tabular_data else None,
            "generated_sql": generated_sql,
            "columns": columns_list if has_tabular_data else None,
            "preview_rows": preview_rows if has_tabular_data else None,
            "chart_config": chart_config if has_tabular_data else None,
            "clarification": clarification_payload,
            "latency_ms": latency,
            "rules_applied": rules_applied
        }

    async def list_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Lista todas las sesiones de conversación pertenecientes a un usuario."""
        stmt = (
            select(
                ChatSessionModel,
                func.count(ChatMessageModel.id).label("msg_count")
            )
            .outerjoin(ChatMessageModel, ChatMessageModel.session_id == ChatSessionModel.id)
            .where(ChatSessionModel.user_id == user_id)
            .group_by(ChatSessionModel.id)
            .order_by(ChatSessionModel.updated_at.desc())
            .limit(50)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "id": str(sess.id),
                "user_id": sess.user_id,
                "title": sess.title,
                "created_at": sess.created_at.isoformat() if sess.created_at else "",
                "updated_at": (sess.updated_at or sess.created_at).isoformat() if (sess.updated_at or sess.created_at) else "",
                "message_count": int(msg_count or 0)
            }
            for sess, msg_count in rows
        ]

    async def get_session_detail(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtiene una sesión de chat y todos sus mensajes hidratados con datasets y chart_config."""
        try:
            parsed_id = uuid.UUID(session_id)
        except Exception:
            return None

        sess = await self.session.get(ChatSessionModel, parsed_id)
        if not sess:
            return None
        if user_id and sess.user_id != user_id:
            return None

        msg_stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == parsed_id)
            .order_by(ChatMessageModel.created_at.asc())
        )
        messages = (await self.session.execute(msg_stmt)).scalars().all()

        hydrated_messages = []
        for m in messages:
            has_tabular = False
            row_count = None
            columns = None
            preview_rows = None
            chart_config = None
            msg_meta = m.metadata_ or {}
            rules_applied = msg_meta.get("rules_applied", [])

            if m.dataset_id:
                ds = await self.session.get(QueryDatasetModel, m.dataset_id)
                if ds and ds.rows:
                    has_tabular = True
                    row_count = ds.row_count
                    columns = ds.columns
                    preview_rows = ds.rows[:10]
                    wants_chart, pref_type = IntentClassifier.detect_chart_request(m.content or "")
                    chart_config = self.analyze_columns_for_chart(
                        columns=ds.columns,
                        rows=ds.rows,
                        wants_chart=wants_chart,
                        preferred_type=pref_type
                    )

            hydrated_messages.append({
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "generated_sql": m.generated_sql,
                "dataset_id": m.dataset_id,
                "has_tabular_data": has_tabular,
                "row_count": row_count,
                "columns": columns,
                "preview_rows": preview_rows,
                "chart_config": chart_config,
                "latency_ms": m.latency_ms,
                "metadata": msg_meta,
                "rules_applied": rules_applied,
                "created_at": m.created_at.isoformat() if m.created_at else ""
            })

        return {
            "id": str(sess.id),
            "user_id": sess.user_id,
            "title": sess.title,
            "created_at": sess.created_at.isoformat() if sess.created_at else "",
            "updated_at": (sess.updated_at or sess.created_at).isoformat() if (sess.updated_at or sess.created_at) else "",
            "messages": hydrated_messages
        }

    async def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """Elimina una sesión conversacional verificando su propietario."""
        try:
            parsed_id = uuid.UUID(session_id)
        except Exception:
            return False

        sess = await self.session.get(ChatSessionModel, parsed_id)
        if not sess:
            return False
        if user_id and sess.user_id != user_id:
            return False

        await self.session.delete(sess)
        await self.session.commit()
        return True
