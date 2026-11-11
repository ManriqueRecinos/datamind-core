import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.use_cases.save_knowledge_candidate import SaveKnowledgeCandidateUseCase
from app.use_cases.rollback_candidate import RollbackCandidateUseCase
from app.infrastructure.database.models import KnowledgeVectorChunkModel, KnowledgeDocumentModel


@pytest.mark.asyncio
async def test_save_knowledge_candidate_duplicate_normalization():
    session = AsyncMock()
    # Mock lock
    session.execute = AsyncMock()
    
    # Simular que ya existe una regla con condición idéntica
    existing_rule = MagicMock(spec=KnowledgeVectorChunkModel)
    existing_rule.id = uuid.uuid4()
    existing_rule.status = "candidate"
    existing_rule.scope = "user"
    existing_rule.prescriptive_condition = "estado = 'A'"
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [existing_rule]
    session.execute.side_effect = [MagicMock(), mock_res]

    use_case = SaveKnowledgeCandidateUseCase(session)
    res = await use_case.execute(
        user_id="user_123",
        session_id=str(uuid.uuid4()),
        message_id=str(uuid.uuid4()),
        connection_id=uuid.uuid4(),
        title="Filtro facturas",
        knowledge_type="business_rule",
        content="Para facturas filtra por estado = 'A'",
        target_entity="facturas",
        target_column="estado",
        prescriptive_condition="estado = 'A'",
        dialect="mysql"
    )

    assert res["duplicated"] is True
    assert res["id"] == str(existing_rule.id)


@pytest.mark.asyncio
async def test_save_knowledge_candidate_detects_conflict():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    
    # Simular regla existente con condición distinta
    existing_rule = MagicMock(spec=KnowledgeVectorChunkModel)
    existing_rule.id = uuid.uuid4()
    existing_rule.status = "candidate"
    existing_rule.scope = "user"
    existing_rule.prescriptive_condition = "estado = 'B'"
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [existing_rule]
    session.execute.side_effect = [MagicMock(), mock_res]

    with patch("app.use_cases.save_knowledge_candidate.OllamaAdapter") as mock_ollama_cls:
        mock_ollama = MagicMock()
        mock_ollama.embed_query = AsyncMock(return_value=[0.1] * 768)
        mock_ollama_cls.return_value = mock_ollama

        use_case = SaveKnowledgeCandidateUseCase(session)
        res = await use_case.execute(
            user_id="user_123",
            session_id=str(uuid.uuid4()),
            message_id=str(uuid.uuid4()),
            connection_id=uuid.uuid4(),
            title="Filtro facturas",
            knowledge_type="business_rule",
            content="Para facturas filtra por estado = 'A'",
            target_entity="facturas",
            target_column="estado",
            prescriptive_condition="estado = 'A'",
            dialect="mysql"
        )

        assert res["status"] == "conflict"
        assert res["conflict_with_id"] == str(existing_rule.id)


@pytest.mark.asyncio
async def test_rollback_candidate_use_case():
    session = AsyncMock()
    use_case = RollbackCandidateUseCase(session)
    use_case.repo.rollback_candidate = AsyncMock(return_value={"id": "abc", "status": "rolled_back", "version": 2})

    res = await use_case.execute(
        candidate_id=str(uuid.uuid4()),
        actor_id="user_123",
        actor_role="user",
        user_permissions=["view-dashboard"],
        reason="Corrección errónea"
    )

    assert res["status"] == "rolled_back"
    assert res["version"] == 2
