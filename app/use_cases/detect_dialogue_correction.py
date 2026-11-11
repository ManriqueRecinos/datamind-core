"""Caso de uso de filtrado rápido y orquestación del detector de correcciones en background."""

import logging
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import (
    KnowledgeVectorChunkModel,
    KnowledgeDocumentModel,
    KnowledgeAuditLogModel,
    DatabaseConnectionModel
)
from app.infrastructure.llm.dialogue_correction_detector import DialogueCorrectionDetector
from app.infrastructure.llm.inference_concurrency_manager import InferenceConcurrencyManager
from app.infrastructure.llm.ollama_adapter import OllamaAdapter

logger = logging.getLogger("detect_correction_use_case")


class DetectDialogueCorrectionUseCase:
    """
    1. Aplica filtro previo barato en memoria (< 1 ms).
    2. Si pasa, verifica si Ollama está ocupado.
    3. Invoca al detector con límite de 120 tokens.
    4. Guarda el candidato con status='candidate', scope='user'.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.concurrency_manager = InferenceConcurrencyManager.get_instance()
        self.detector = DialogueCorrectionDetector()

    def quick_filter(
        self,
        user_message: str,
        previous_sql: Optional[str],
        synced_tables: List[Dict[str, Any]]
    ) -> bool:
        """
        Filtro previo barato (< 1 ms):
        1. Debe haber existido una consulta SQL en el turno previo.
        2. El mensaje del usuario debe contener al menos un token coincidente con nombres
           de tablas o columnas registradas en synced_tables.
        """
        if not previous_sql or not previous_sql.strip():
            return False

        if not user_message or len(user_message.strip()) < 8:
            return False

        msg_lower = user_message.lower()

        # Recopilar identificadores de catálogo
        catalog_tokens = set()
        for t in synced_tables:
            t_name = (t.get("name") or t.get("table_name") or "").lower()
            if t_name:
                catalog_tokens.add(t_name)
            for c in t.get("columns", []):
                if isinstance(c, dict):
                    c_name = (c.get("name") or "").lower()
                    if len(c_name) >= 3:
                        catalog_tokens.add(c_name)

        # Buscar coincidencia exacta por palabra (word boundaries)
        for token in catalog_tokens:
            if re.search(r'\b' + re.escape(token) + r'\b', msg_lower):
                return True

        return False

    async def execute(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
        connection_id: Optional[str],
        user_message: str,
        previous_assistant_message: Optional[str],
        previous_sql: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Orquesta la detección en background."""
        if not connection_id:
            return None

        # 1. Obtener la conexión y su catálogo
        stmt = select(DatabaseConnectionModel).where(DatabaseConnectionModel.id == connection_id)
        res = await self.session.execute(stmt)
        conn_model = res.scalar_one_or_none()
        if not conn_model:
            return None

        synced_tables = conn_model.synced_tables or []
        dialect = "mysql" if conn_model.engine in ("mariadb", "mysql") else "postgres"

        # 2. Filtro previo barato (< 1 ms)
        if not self.quick_filter(user_message, previous_sql, synced_tables):
            return None

        # 3. Control de concurrencia: si Ollama está ocupado con consultas interactivas, no competir
        if self.concurrency_manager.is_ollama_busy():
            logger.info("Detector omitido: Ollama ocupado atendiendo consultas interactivas de usuario.")
            return None

        # 4. Inferencia con DialogueCorrectionDetector
        detection = await self.detector.detect_correction(
            user_message=user_message,
            previous_assistant_message=previous_assistant_message,
            previous_sql=previous_sql,
            synced_tables=synced_tables,
            dialect=dialect
        )

        if not detection:
            return None

        # 5. Persistir como candidato utilizando SaveKnowledgeCandidateUseCase (con locks y detección de conflictos)
        from app.use_cases.save_knowledge_candidate import SaveKnowledgeCandidateUseCase
        save_use_case = SaveKnowledgeCandidateUseCase(self.session)
        result = await save_use_case.execute(
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            connection_id=conn_model.id,
            title=detection["title"],
            knowledge_type=detection["knowledge_type"],
            content=detection["content"],
            target_entity=detection["target_entity"],
            target_column=detection["target_column"],
            prescriptive_condition=detection["prescriptive_condition"],
            trigger_signal="user_correction",
            dialect=dialect
        )
        return result
