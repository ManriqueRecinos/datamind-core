"""Repositorio para gestionar términos no entendidos y ambigüedades en PostgreSQL."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import UnresolvedQueryTermModel


class UnresolvedQueryTermRepository:
    """Acceso a datos para la tabla unresolved_query_terms."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_term(
        self,
        session_id: uuid.UUID,
        user_id: str,
        prompt: str,
        extracted_term: str,
        failure_reason: str = "ambiguous_candidates",
        connection_id: Optional[uuid.UUID] = None,
        candidate_tables: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None
    ) -> UnresolvedQueryTermModel:
        """Registra un nuevo término o consulta no entendida / fallida."""
        record = UnresolvedQueryTermModel(
            connection_id=connection_id,
            session_id=session_id,
            user_id=user_id,
            prompt=prompt,
            extracted_term=extracted_term,
            failure_reason=failure_reason,
            candidate_tables=candidate_tables or [],
            error_message=error_message,
            status="pending"
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_terms(
        self,
        connection_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[UnresolvedQueryTermModel]:
        """Obtiene la lista de términos con filtros opcionales."""
        stmt = select(UnresolvedQueryTermModel).order_by(desc(UnresolvedQueryTermModel.created_at))
        if connection_id:
            stmt = stmt.where(UnresolvedQueryTermModel.connection_id == connection_id)
        if status:
            stmt = stmt.where(UnresolvedQueryTermModel.status == status)

        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_term(
        self,
        term_id: uuid.UUID,
        resolved_target: str,
        resolved_by: str,
        status: str = "resolved"
    ) -> Optional[UnresolvedQueryTermModel]:
        """Marca un término como resuelto o descartado."""
        record = await self.session.get(UnresolvedQueryTermModel, term_id)
        if not record:
            return None

        record.status = status
        record.resolved_target = resolved_target
        record.resolved_by = resolved_by
        record.resolved_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(record)
        return record
