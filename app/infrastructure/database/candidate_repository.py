"""Repositorio de acceso a datos para candidatos de conocimiento implícito y auditoría inmutable."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import (
    KnowledgeVectorChunkModel,
    KnowledgeDocumentModel,
    KnowledgeAuditLogModel
)
from app.infrastructure.llm.ollama_adapter import OllamaAdapter


class CandidateRepository:
    """Gestiona el ciclo de vida, autorización y auditoría de candidatos de conocimiento."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_candidates(
        self,
        user_id: str,
        user_role: str,
        user_permissions: List[str],
        connection_id: Optional[str] = None,
        scope: Optional[str] = None,
        status: Optional[str] = None,
        proposed_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Lista reglas candidatas aplicando control de acceso:
        - Si no es admin/super-admin ni tiene manage-knowledge: fuerza scope=user y user_id.
        - Si es admin o tiene permiso: puede ver propuestas globales (proposed_only) o de cualquier usuario.
        """
        is_admin = (user_role in ("super-admin", "admin")) or ("manage-knowledge" in user_permissions)

        stmt = select(KnowledgeVectorChunkModel, KnowledgeDocumentModel).join(
            KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id
        )

        conditions = []

        if connection_id:
            try:
                conn_uuid = uuid.UUID(str(connection_id))
                conditions.append(KnowledgeVectorChunkModel.connection_id == conn_uuid)
            except ValueError:
                pass

        if proposed_only:
            conditions.append(KnowledgeVectorChunkModel.proposed_global_at.isnot(None))
            conditions.append(KnowledgeVectorChunkModel.status == "candidate")
        elif status:
            conditions.append(KnowledgeVectorChunkModel.status == status)

        if not is_admin:
            # Usuarios regulares solo ven sus candidatos
            conditions.append(KnowledgeVectorChunkModel.user_id == user_id)
            conditions.append(KnowledgeVectorChunkModel.scope == "user")
        else:
            if scope:
                conditions.append(KnowledgeVectorChunkModel.scope == scope)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(desc(KnowledgeVectorChunkModel.created_at)).limit(100)

        result = await self.session.execute(stmt)
        rows = result.all()

        items = []
        for chunk, doc in rows:
            items.append({
                "id": str(chunk.id),
                "title": doc.title,
                "content": chunk.chunk_text,
                "knowledge_type": doc.category,
                "status": chunk.status,
                "scope": chunk.scope,
                "user_id": chunk.user_id,
                "target_entity": chunk.target_entity,
                "target_column": chunk.target_column,
                "prescriptive_condition": chunk.prescriptive_condition,
                "trigger_signal": chunk.trigger_signal,
                "version": chunk.version,
                "confirmed_at": chunk.confirmed_at.isoformat() if chunk.confirmed_at else None,
                "proposed_global_at": chunk.proposed_global_at.isoformat() if chunk.proposed_global_at else None,
                "conflict_with_id": str(chunk.conflict_with_id) if chunk.conflict_with_id else None,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
            })
        return items

    async def confirm_user_candidate(self, candidate_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        El usuario autor confirma una regla candidata para su propio uso exclusivo.
        Si la regla estaba en estado 'conflict', en una sola transacción atómica:
        - Si el conflicto es con una regla global: rechaza con PermissionError (solo admin puede resolverlo).
        - Si el conflicto es con una regla del mismo usuario: la regla previa pasa a 'rolled_back'
          y la nueva pasa a 'candidate'.
        Actualiza confirmed_at = NOW() y registra en auditoría.
        """
        try:
            cand_uuid = uuid.UUID(candidate_id)
        except ValueError:
            return None

        stmt = select(KnowledgeVectorChunkModel, KnowledgeDocumentModel).join(
            KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id
        ).where(KnowledgeVectorChunkModel.id == cand_uuid)

        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        chunk, doc = row
        if chunk.user_id != user_id:
            raise PermissionError("No eres el autor de esta regla candidata.")

        # Manejo de resolución de conflicto
        if chunk.status == "conflict" and chunk.conflict_with_id:
            # Buscar la regla en conflicto
            conflict_stmt = select(KnowledgeVectorChunkModel).where(KnowledgeVectorChunkModel.id == chunk.conflict_with_id)
            c_res = await self.session.execute(conflict_stmt)
            conflicted_rule = c_res.scalar_one_or_none()

            if conflicted_rule:
                if conflicted_rule.scope == "global":
                    raise PermissionError(
                        "Esta regla entra en conflicto con una directiva corporativa global. Solo un administrador puede resolver este conflicto."
                    )
                if conflicted_rule.scope == "user" and conflicted_rule.user_id == user_id:
                    # En una sola transacción atómica: anterior -> rolled_back, nueva -> candidate
                    prev_conflicted_state = {
                        "status": conflicted_rule.status,
                        "scope": conflicted_rule.scope,
                        "version": conflicted_rule.version
                    }
                    conflicted_rule.status = "rolled_back"
                    conflicted_rule.version = (conflicted_rule.version or 1) + 1
                    
                    audit_prev = KnowledgeAuditLogModel(
                        rule_id=conflicted_rule.id,
                        action="rolled_back",
                        actor_id=user_id,
                        actor_role="user",
                        source_session_id=chunk.source_session_id,
                        previous_state=prev_conflicted_state,
                        new_state={"status": "rolled_back", "scope": conflicted_rule.scope, "version": conflicted_rule.version},
                        reason=f"Regla anterior reemplazada por confirmación de nuevo candidato {chunk.id}"
                    )
                    self.session.add(audit_prev)

        prev_state = {
            "status": chunk.status,
            "scope": chunk.scope,
            "confirmed_at": chunk.confirmed_at.isoformat() if chunk.confirmed_at else None
        }

        chunk.confirmed_at = datetime.now(timezone.utc)
        chunk.status = "candidate"  # Pasa/permanece como candidata activa personal
        chunk.scope = "user"
        chunk.conflict_with_id = None

        new_state = {
            "status": chunk.status,
            "scope": chunk.scope,
            "confirmed_at": chunk.confirmed_at.isoformat()
        }

        audit = KnowledgeAuditLogModel(
            rule_id=chunk.id,
            action="confirmed_user",
            actor_id=user_id,
            actor_role="user",
            source_session_id=chunk.source_session_id,
            previous_state=prev_state,
            new_state=new_state,
            reason="Confirmada por el usuario para su uso exclusivo"
        )
        self.session.add(audit)
        await self.session.commit()

        return {
            "id": str(chunk.id),
            "status": chunk.status,
            "scope": chunk.scope,
            "confirmed_at": chunk.confirmed_at.isoformat()
        }

    async def propose_global_candidate(self, candidate_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        El usuario autor postula la regla candidata para que sea evaluada corporativamente.
        Actualiza proposed_global_at = NOW() y registra en auditoría.
        """
        try:
            cand_uuid = uuid.UUID(candidate_id)
        except ValueError:
            return None

        stmt = select(KnowledgeVectorChunkModel, KnowledgeDocumentModel).join(
            KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id
        ).where(KnowledgeVectorChunkModel.id == cand_uuid)

        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        chunk, doc = row
        if chunk.user_id != user_id:
            raise PermissionError("Solo el autor puede postular esta regla a revisión global.")

        prev_state = {
            "proposed_global_at": chunk.proposed_global_at.isoformat() if chunk.proposed_global_at else None
        }

        chunk.proposed_global_at = datetime.now(timezone.utc)

        new_state = {
            "proposed_global_at": chunk.proposed_global_at.isoformat()
        }

        audit = KnowledgeAuditLogModel(
            rule_id=chunk.id,
            action="proposed_global",
            actor_id=user_id,
            actor_role="user",
            source_session_id=chunk.source_session_id,
            previous_state=prev_state,
            new_state=new_state,
            reason="Postulada por el autor para revisión corporativa global"
        )
        self.session.add(audit)
        await self.session.commit()

        return {
            "id": str(chunk.id),
            "proposed_global_at": chunk.proposed_global_at.isoformat()
        }

    async def promote_global_candidate(
        self,
        candidate_id: str,
        admin_user_id: str,
        user_role: str,
        user_permissions: List[str],
        edited_content: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Promueve una regla a verified y scope=global.
        Exclusivo de administradores con rol admin/super-admin o permiso manage-knowledge.
        Revalida colisión global previa: si existe otra con la misma tupla y condición distinta, lanza 409 Conflict.
        """
        is_admin = (user_role in ("super-admin", "admin")) or ("manage-knowledge" in user_permissions)
        if not is_admin:
            raise PermissionError("Solo un administrador puede promover reglas a nivel corporativo global.")

        try:
            cand_uuid = uuid.UUID(candidate_id)
        except ValueError:
            raise ValueError("ID de candidato inválido")

        stmt = select(KnowledgeVectorChunkModel, KnowledgeDocumentModel).join(
            KnowledgeDocumentModel, KnowledgeVectorChunkModel.document_id == KnowledgeDocumentModel.id
        ).where(KnowledgeVectorChunkModel.id == cand_uuid)

        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            raise FileNotFoundError("Candidato no encontrado")

        chunk, doc = row

        # Revalidar si ya existe otra regla global con la misma tupla y condición distinta
        if chunk.connection_id and chunk.target_entity and chunk.target_column and chunk.prescriptive_condition:
            dup_check = select(KnowledgeVectorChunkModel).where(
                KnowledgeVectorChunkModel.connection_id == chunk.connection_id,
                KnowledgeVectorChunkModel.target_entity == chunk.target_entity,
                KnowledgeVectorChunkModel.target_column == chunk.target_column,
                KnowledgeVectorChunkModel.scope == "global",
                KnowledgeVectorChunkModel.status == "verified",
                KnowledgeVectorChunkModel.id != chunk.id
            )
            dup_res = await self.session.execute(dup_check)
            existing_global = dup_res.scalars().first()
            if existing_global and existing_global.prescriptive_condition != chunk.prescriptive_condition:
                raise ValueError(
                    f"Conflicto 409: Ya existe una regla global activa para {chunk.target_entity}.{chunk.target_column} "
                    f"con condición distinta ('{existing_global.prescriptive_condition}'). Resuelve el conflicto antes de promover."
                )

        prev_state = {
            "status": chunk.status,
            "scope": chunk.scope,
            "version": chunk.version,
            "content": chunk.chunk_text
        }

        new_content = (edited_content or chunk.chunk_text).strip()

        # Re-vectorizar con prefijo search_document:
        ollama = OllamaAdapter(model="nomic-embed-text")
        new_embedding = await ollama.embed_query(f"search_document: {new_content}")

        chunk.chunk_text = new_content
        chunk.embedding = new_embedding
        chunk.scope = "global"
        chunk.status = "verified"
        chunk.version = (chunk.version or 1) + 1

        new_state = {
            "status": chunk.status,
            "scope": chunk.scope,
            "version": chunk.version,
            "content": chunk.chunk_text
        }

        audit = KnowledgeAuditLogModel(
            rule_id=chunk.id,
            action="promoted_global",
            actor_id=admin_user_id,
            actor_role=user_role,
            source_session_id=chunk.source_session_id,
            previous_state=prev_state,
            new_state=new_state,
            reason=reason or "Aprobada y promovida por el administrador"
        )
        self.session.add(audit)
        await self.session.commit()

        return {
            "id": str(chunk.id),
            "status": chunk.status,
            "scope": chunk.scope,
            "version": chunk.version
        }

    async def reject_candidate(
        self,
        candidate_id: str,
        actor_id: str,
        actor_role: str,
        user_permissions: List[str],
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Descarta un candidato. Si es de scope global, requiere rol de administrador.
        """
        is_admin = (actor_role in ("super-admin", "admin")) or ("manage-knowledge" in user_permissions)

        try:
            cand_uuid = uuid.UUID(candidate_id)
        except ValueError:
            raise ValueError("ID de candidato inválido")

        stmt = select(KnowledgeVectorChunkModel).where(KnowledgeVectorChunkModel.id == cand_uuid)
        result = await self.session.execute(stmt)
        chunk = result.scalar_one_or_none()
        if not chunk:
            raise FileNotFoundError("Candidato no encontrado")

        if chunk.scope == "global" and not is_admin:
            raise PermissionError("Solo un administrador puede descartar o rechazar reglas globales.")
        if chunk.scope == "user" and chunk.user_id != actor_id and not is_admin:
            raise PermissionError("No tienes permisos para descartar este candidato.")

        prev_state = {"status": chunk.status}
        chunk.status = "rejected"
        new_state = {"status": chunk.status}

        audit = KnowledgeAuditLogModel(
            rule_id=chunk.id,
            action="rejected",
            actor_id=actor_id,
            actor_role=actor_role,
            source_session_id=chunk.source_session_id,
            previous_state=prev_state,
            new_state=new_state,
            reason=reason or "Candidato rechazado"
        )
        self.session.add(audit)
        await self.session.commit()

        return {"id": str(chunk.id), "status": chunk.status}

    async def rollback_candidate(
        self,
        candidate_id: str,
        actor_id: str,
        actor_role: str,
        user_permissions: List[str],
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Revierte una regla. Si es de scope global, exige rol de administrador.
        Restaura previous_state desde knowledge_audit_logs si existe o muta a rolled_back.
        """
        is_admin = (actor_role in ("super-admin", "admin")) or ("manage-knowledge" in user_permissions)

        try:
            cand_uuid = uuid.UUID(candidate_id)
        except ValueError:
            raise ValueError("ID de candidato inválido")

        stmt = select(KnowledgeVectorChunkModel).where(KnowledgeVectorChunkModel.id == cand_uuid)
        result = await self.session.execute(stmt)
        chunk = result.scalar_one_or_none()
        if not chunk:
            raise FileNotFoundError("Regla no encontrada")

        if chunk.scope == "global" and not is_admin:
            raise PermissionError("Solo un administrador puede revertir reglas de alcance global.")
        if chunk.scope == "user" and chunk.user_id != actor_id and not is_admin:
            raise PermissionError("No tienes permisos para revertir este candidato.")

        prev_state = {
            "status": chunk.status,
            "content": chunk.chunk_text,
            "version": chunk.version
        }

        # Buscar última auditoría con previous_state restaurable
        audit_stmt = select(KnowledgeAuditLogModel).where(
            KnowledgeAuditLogModel.rule_id == chunk.id,
            KnowledgeAuditLogModel.previous_state.isnot(None)
        ).order_by(desc(KnowledgeAuditLogModel.created_at))

        audit_res = await self.session.execute(audit_stmt)
        last_audit = audit_res.scalars().first()

        if last_audit and last_audit.previous_state:
            # Restaurar estado previo
            chunk.status = last_audit.previous_state.get("status", "rolled_back")
            if "content" in last_audit.previous_state:
                chunk.chunk_text = last_audit.previous_state["content"]
                ollama = OllamaAdapter(model="nomic-embed-text")
                chunk.embedding = await ollama.embed_query(f"search_document: {chunk.chunk_text}")
        else:
            chunk.status = "rolled_back"

        chunk.version = (chunk.version or 1) + 1
        new_state = {
            "status": chunk.status,
            "content": chunk.chunk_text,
            "version": chunk.version
        }

        audit = KnowledgeAuditLogModel(
            rule_id=chunk.id,
            action="rolled_back",
            actor_id=actor_id,
            actor_role=actor_role,
            source_session_id=chunk.source_session_id,
            previous_state=prev_state,
            new_state=new_state,
            reason=reason or "Regla revertida a versión anterior"
        )
        self.session.add(audit)
        await self.session.commit()

        return {"id": str(chunk.id), "status": chunk.status, "version": chunk.version}
