"""Caso de uso para revertir y restaurar una directiva de conocimiento a su estado previo."""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.candidate_repository import CandidateRepository

logger = logging.getLogger("rollback_candidate")


class RollbackCandidateUseCase:
    """
    Ejecuta el rollback restaurando el estado previo desde knowledge_audit_logs si existe,
    re-vectorizando el contenido anterior con nomic-embed-text o mutando a 'rolled_back'.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CandidateRepository(session)

    async def execute(
        self,
        candidate_id: str,
        actor_id: str,
        actor_role: str,
        user_permissions: list[str],
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.repo.rollback_candidate(
            candidate_id=candidate_id,
            actor_id=actor_id,
            actor_role=actor_role,
            user_permissions=user_permissions,
            reason=reason
        )
