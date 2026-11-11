import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.database.models import ChatSessionModel, ChatMessageModel, KnowledgeAuditLogModel, KnowledgeVectorChunkModel
from app.use_cases.ask_chat import AskChatUseCase


@pytest.mark.asyncio
async def test_session_deletion_preserves_audit_and_candidates():
    """
    Verifica que al eliminar una sesión de chat, los candidatos en knowledge_vector_chunks
    y los registros en knowledge_audit_logs persisten intactos y no se borran en cascada.
    """
    session = AsyncMock()
    session_id = uuid.uuid4()
    user_id = "user_test_123"

    mock_chat_session = MagicMock(spec=ChatSessionModel)
    mock_chat_session.id = session_id
    mock_chat_session.user_id = user_id

    # Simular get session
    session.get.return_value = mock_chat_session
    session.delete = AsyncMock()
    session.commit = AsyncMock()

    use_case = AskChatUseCase(session)
    deleted = await use_case.delete_session(str(session_id), user_id=user_id)

    assert deleted is True
    session.delete.assert_called_once_with(mock_chat_session)
    session.commit.assert_called_once()
