"""Pruebas unitarias de autorización, contratos y modelos de candidatos de conocimiento (Fase 1)."""

import pytest
import uuid
from app.api.v1.schemas.knowledge import (
    KnowledgeCandidateItem,
    KnowledgeCandidatesResponse,
    PromoteCandidateRequest,
    RejectCandidateRequest,
    RollbackCandidateRequest,
)


def test_knowledge_candidate_schema_serialization():
    item = KnowledgeCandidateItem(
        id=str(uuid.uuid4()),
        title="Filtro de Estado",
        content="Para la tabla factura_lineas, estado debe cumplir: estado = 'A'",
        knowledge_type="schema_correction",
        status="candidate",
        scope="user",
        user_id="user_1",
        target_entity="factura_lineas",
        target_column="estado",
        prescriptive_condition="estado = 'A'",
        trigger_signal="user_correction",
        version=1,
        created_at="2026-03-11T15:00:00Z"
    )
    response = KnowledgeCandidatesResponse(total=1, candidates=[item])
    assert response.total == 1
    assert response.candidates[0].target_entity == "factura_lineas"
    assert response.candidates[0].prescriptive_condition == "estado = 'A'"
    assert response.candidates[0].scope == "user"


def test_candidate_requests_payloads():
    p_req = PromoteCandidateRequest(edited_content="Contenido refinado", reason="Validado por contabilidad")
    assert p_req.edited_content == "Contenido refinado"

    r_req = RejectCandidateRequest(reason="Regla no aplicable")
    assert r_req.reason == "Regla no aplicable"

    rb_req = RollbackCandidateRequest(reason="Generaba sesgos")
    assert rb_req.reason == "Generaba sesgos"
