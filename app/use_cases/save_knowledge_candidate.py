"""Caso de uso para persistir candidatos de conocimiento con lock determinista y detección de conflictos."""

import hashlib
import logging
from typing import Optional, Dict, Any
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import sqlglot

from app.infrastructure.database.models import (
    KnowledgeDocumentModel,
    KnowledgeVectorChunkModel,
    KnowledgeAuditLogModel
)
from app.infrastructure.llm.ollama_adapter import OllamaAdapter

logger = logging.getLogger("save_knowledge_candidate")


class SaveKnowledgeCandidateUseCase:
    """
    Guarda un candidato garantizando control de concurrencia mediante pg_advisory_xact_lock
    sobre (connection_id, target_entity, target_column), detección de colisiones contra reglas
    globales verificadas o reglas del mismo usuario, y gestión de estados 'conflict'.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _compute_lock_key(connection_id: str, target_entity: str, target_column: str) -> int:
        raw = f"{connection_id}:{target_entity.lower()}:{target_column.lower()}"
        # Convertir los primeros 8 bytes de md5 a entero de 64 bits con signo para pg_advisory_xact_lock(bigint)
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
        val = int(digest, 16)
        # Convertir a signed 64-bit int
        if val >= 2**63:
            val -= 2**64
        return val

    async def execute(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
        connection_id: Any,
        title: str,
        knowledge_type: str,
        content: str,
        target_entity: str,
        target_column: str,
        prescriptive_condition: str,
        trigger_signal: str = "user_correction",
        dialect: str = "mysql"
    ) -> Optional[Dict[str, Any]]:
        """
        Adquiere el lock de la tupla y almacena el candidato manejando posibles conflictos.
        """
        conn_str = str(connection_id)
        lock_key = self._compute_lock_key(conn_str, target_entity, target_column)

        # 1. Adquirir pg_advisory_xact_lock para evitar carreras entre workers en background
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

        # 2. Consultar reglas existentes de esa tupla ÚNICAMENTE:
        #    a) Reglas globales verificadas (scope='global' AND status='verified')
        #    b) Reglas del MISMO usuario (scope='user' AND user_id=:user_id)
        stmt = (
            select(KnowledgeVectorChunkModel)
            .where(
                KnowledgeVectorChunkModel.connection_id == connection_id,
                KnowledgeVectorChunkModel.target_entity.ilike(target_entity),
                KnowledgeVectorChunkModel.target_column.ilike(target_column),
                KnowledgeVectorChunkModel.status.in_(["candidate", "verified"]),
                (
                    (KnowledgeVectorChunkModel.scope == "global") & (KnowledgeVectorChunkModel.status == "verified")
                ) | (
                    (KnowledgeVectorChunkModel.scope == "user") & (KnowledgeVectorChunkModel.user_id == user_id)
                )
            )
            .order_by(KnowledgeVectorChunkModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        existing_rules = result.scalars().all()

        # Parsear condición entrante con sqlglot para comparación en AST normalizado
        try:
            incoming_ast = sqlglot.parse_one(prescriptive_condition, read=dialect)
            incoming_norm = incoming_ast.sql(dialect=dialect)
        except Exception:
            incoming_norm = prescriptive_condition.strip()

        status = "candidate"
        conflict_with_id = None

        for rule in existing_rules:
            if not rule.prescriptive_condition:
                continue
            try:
                exist_ast = sqlglot.parse_one(rule.prescriptive_condition, read=dialect)
                exist_norm = exist_ast.sql(dialect=dialect)
            except Exception:
                exist_norm = rule.prescriptive_condition.strip()

            # Si la condición normalizada es idéntica: no duplicar
            if exist_norm == incoming_norm:
                logger.info(f"Regla idéntica existente ({rule.id}). Descartando inserción.")
                return {
                    "id": str(rule.id),
                    "status": rule.status,
                    "scope": rule.scope,
                    "duplicated": True
                }

            # Condición difiere en la misma tupla -> Conflicto detectado
            status = "conflict"
            conflict_with_id = rule.id
            break  # Tomamos la regla en conflicto más reciente

        # 3. Crear contenedor de documento
        doc = KnowledgeDocumentModel(
            title=title,
            category=knowledge_type,
            department="Aprendizaje Diálogo",
            content=content,
            metadata_={
                "connection_id": conn_str,
                "user_id": user_id,
                "target_entity": target_entity,
                "target_column": target_column,
                "trigger_signal": trigger_signal
            }
        )
        self.session.add(doc)
        await self.session.flush()

        # 4. Vectorizar con prefijo search_document:
        ollama = OllamaAdapter(model="nomic-embed-text")
        embedding = await ollama.embed_query(f"search_document: {content}")

        chunk = KnowledgeVectorChunkModel(
            document_id=doc.id,
            chunk_index=0,
            chunk_text=content,
            embedding=embedding,
            connection_id=connection_id,
            status=status,
            scope="user",
            user_id=user_id,
            target_entity=target_entity,
            target_column=target_column,
            prescriptive_condition=incoming_norm,
            trigger_signal=trigger_signal,
            source_session_id=session_id,
            source_message_id=message_id,
            conflict_with_id=conflict_with_id,
            version=1,
            embedding_model="nomic-embed-text"
        )
        self.session.add(chunk)
        await self.session.flush()

        # 5. Registro de auditoría
        audit = KnowledgeAuditLogModel(
            rule_id=chunk.id,
            action="detected_candidate" if status == "candidate" else "conflict_detected",
            actor_id="SYSTEM_BACKGROUND_WORKER",
            actor_role="system",
            source_session_id=session_id,
            previous_state=None,
            new_state={
                "status": status,
                "scope": "user",
                "target_entity": target_entity,
                "target_column": target_column,
                "prescriptive_condition": incoming_norm,
                "conflict_with_id": str(conflict_with_id) if conflict_with_id else None
            },
            reason=f"Regla detectada ({status}) con condición '{incoming_norm}'"
        )
        self.session.add(audit)
        await self.session.commit()

        logger.info(f"Candidato persistido: {chunk.id} [status={status}] para {user_id}")
        return {
            "id": str(chunk.id),
            "title": doc.title,
            "status": status,
            "scope": "user",
            "conflict_with_id": str(conflict_with_id) if conflict_with_id else None
        }
