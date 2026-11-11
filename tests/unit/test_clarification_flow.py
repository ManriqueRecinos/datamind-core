"""Pruebas unitarias para el flujo de detección de ambigüedad, aclaración y cola de términos."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.infrastructure.database.models import UnresolvedQueryTermModel
from app.infrastructure.database.repositories.unresolved_terms_repository import UnresolvedQueryTermRepository


@pytest.mark.asyncio
async def test_unresolved_terms_repository():
    """Valida la creación y resolución de términos en la cola de unresolved_query_terms."""
    mock_session = AsyncMock()

    # Mock de get para retornar un modelo simulado
    dummy_term = UnresolvedQueryTermModel(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        user_id="user_test",
        prompt="dime repuestos",
        extracted_term="repuestos",
        failure_reason="ambiguous_candidates",
        status="pending"
    )
    mock_session.get.return_value = dummy_term

    repo = UnresolvedQueryTermRepository(mock_session)

    # 1. Crear término
    created = await repo.create_term(
        session_id=dummy_term.session_id,
        user_id="user_test",
        prompt="dime repuestos",
        extracted_term="repuestos",
        failure_reason="ambiguous_candidates",
        candidate_tables=[{"id": "inventario_partes", "label": "Inventario de partes"}]
    )

    mock_session.add.assert_called_once()
    assert mock_session.commit.called

    # 2. Resolver término
    resolved = await repo.resolve_term(
        term_id=dummy_term.id,
        resolved_target="inventario_partes",
        resolved_by="admin_test",
        status="resolved"
    )

    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.resolved_target == "inventario_partes"
    assert resolved.resolved_by == "admin_test"
    assert resolved.resolved_at is not None
