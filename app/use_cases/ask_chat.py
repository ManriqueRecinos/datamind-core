"""Caso de uso principal para orquestar la conversación de chat (RAG + Text-to-SQL)."""

from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid
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
from app.use_cases.intent_classifier import IntentClassifier
from app.use_cases.manage_connections import ManageConnectionsUseCase


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
                    return db_session.id
            except Exception:
                pass

        new_session = ChatSessionModel(
            user_id=user_id,
            title=prompt[:40] + ("..." if len(prompt) > 40 else "")
        )
        self.session.add(new_session)
        await self.session.flush()
        return new_session.id

    async def execute_sync(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        user_id: str = "user",
        connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Ejecuta la respuesta completa síncrona."""
        start_time = time.time()
        s_id = await self._get_or_create_session(session_id, user_id, prompt)

        # 1. Clasificar intención
        intent = IntentClassifier.classify(prompt)
        generated_sql = None
        dataset_id = None
        row_count = 0
        has_tabular_data = False
        columns_list = []
        preview_rows = []
        message_text = ""

        if intent == "general_chat":
            message_text = await self.ollama.generate_completion(
                prompt=prompt,
                system_prompt="Eres DataMind AI, un asistente de inteligencia artificial para análisis de bases de datos y procesos corporativos. Responde con un tono cálido, educado, profesional y en español."
            )

        elif intent == "process_qa":
            # RAG de Procesos en pgvector
            query_vec = await self.ollama.generate_embedding(prompt)
            chunks = await self.vector_repo.search_similar(query_vec, top_k=3, category="process_manual")
            context = "\n---\n".join([c.chunk_text for c in chunks]) if chunks else "No se encontró información específica en los manuales."

            sys_prompt = (
                "Eres un asistente de procesos corporativos. Responde a la pregunta del usuario utilizando "
                "el siguiente contexto de manuales y procedimientos. Si no tienes la información, indícalo "
                "con amabilidad sin inventar datos. Redacta en español formal y claro.\n\n"
                f"CONTEXTO DE PROCESOS:\n{context}"
            )
            message_text = await self.ollama.generate_completion(prompt=prompt, system_prompt=sys_prompt)

        elif intent == "data_query":
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

            # 1. Recuperar esquemas relevantes en pgvector filtrando por connection_id
            query_vec = await self.ollama.generate_embedding(prompt)
            schema_chunks = await self.vector_repo.search_similar(
                query_vec,
                top_k=5,
                category="db_schema",
                connection_id=target_conn_id
            )
            if not schema_chunks and target_conn_id:
                # Fallback a esquemas generales si la conexión aún no tenía filtro específico
                schema_chunks = await self.vector_repo.search_similar(query_vec, top_k=5, category="db_schema")

            schema_context = "\n".join([c.chunk_text for c in schema_chunks]) if schema_chunks else (
                "Tabla: orders (id, customer_id, order_code, status, created_at)\n"
                "Tabla: customers (id, name, email)\n"
                "Tabla: products (id, sku, name, stock)"
            )

            sql_prompt = (
                f"Eres un experto en SQL para {engine_title} conectado a la base de datos `{db_name}` ({conn_label}). "
                f"Escribe ÚNICAMENTE una consulta SQL SELECT válida para {engine_title} "
                f"que responda a la solicitud del usuario, sin explicaciones ni markdown.\n"
                f"ESQUEMAS DE TABLAS VECTORIZADOS DISPONIBLES EN `{db_name}`:\n{schema_context}\n\n"
                f"REGLAS:\n"
                f"- Usa únicamente las tablas y columnas listadas en los esquemas.\n"
                f"- Si el usuario pregunta si tienes conocimiento de una tabla o qué datos contiene, genera una consulta SELECT sencilla como `SELECT * FROM <tabla> LIMIT 5;`.\n"
                f"- Respeta estrictamente la sintaxis de {engine_title}.\n\n"
                f"SOLICITUD: {prompt}\n"
                f"CONSULTA SQL:"
            )
            raw_sql = await self.ollama.generate_completion(prompt=sql_prompt)
            is_valid, safe_sql, error_msg = self.guardrail.validate_and_sanitize(raw_sql, dialect=sql_dialect)

            if not is_valid:
                message_text = f"No pude formular una consulta segura para obtener esos datos: {error_msg}"
            else:
                generated_sql = safe_sql
                try:
                    rows = await db_adapter.execute_query(safe_sql)
                    row_count = len(rows)

                    if row_count > 0:
                        has_tabular_data = True
                        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
                        columns_list = list(rows[0].keys())
                        preview_rows = rows[:10]

                        # Guardar dataset en caché para botón de Excel
                        dataset_model = QueryDatasetModel(
                            dataset_id=dataset_id,
                            session_id=s_id,
                            sql_executed=safe_sql,
                            columns=columns_list,
                            rows=rows,
                            row_count=row_count,
                            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.settings.dataset_cache_ttl_hours)
                        )
                        self.session.add(dataset_model)

                        # Síntesis humanizada
                        sample_preview = json.dumps(rows[:5], ensure_ascii=False)
                        synthesis_prompt = (
                            f"Se ejecutó una consulta en la base de datos {engine_title} `{db_name}` ({conn_label}).\n"
                            f"Pregunta del usuario: {prompt}\n"
                            f"Consulta SQL ejecutada: {safe_sql}\n"
                            f"Total registros encontrados: {row_count}.\n"
                            f"Muestra de datos (primeros 5): {sample_preview}\n\n"
                            f"Redacta una respuesta humanizada, profesional, clara y en español, "
                            f"indicando con amabilidad que sí se tiene conocimiento de la tabla o datos y resumiendo los hallazgos principales."
                        )
                        message_text = await self.ollama.generate_completion(prompt=synthesis_prompt)
                    else:
                        message_text = f"Se consultó la base de datos `{db_name}` ({engine_title}) pero no se encontraron registros que coincidan con los criterios solicitados."
                except Exception as e:
                    message_text = f"Ocurrió un inconveniente al consultar la base de datos `{db_name}`: {str(e)}"

        latency = int((time.time() - start_time) * 1000)

        # Guardar mensaje en el historial
        msg_model = ChatMessageModel(
            session_id=s_id,
            role="assistant",
            content=message_text,
            intent=intent,
            generated_sql=generated_sql,
            dataset_id=dataset_id,
            latency_ms=latency
        )
        self.session.add(msg_model)
        await self.session.commit()

        return {
            "session_id": str(s_id),
            "message": message_text,
            "intent": intent,
            "has_tabular_data": has_tabular_data,
            "dataset_id": dataset_id,
            "row_count": row_count if has_tabular_data else None,
            "generated_sql": generated_sql,
            "columns": columns_list if has_tabular_data else None,
            "preview_rows": preview_rows if has_tabular_data else None,
            "latency_ms": latency
        }
