"""Endpoints REST para la gestión del conocimiento, Centro de Entrenamiento IA y búsqueda vectorial en pgvector."""

from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.schemas.knowledge import (
    ChunkResultItem,
    IngestKnowledgeRequest,
    IngestKnowledgeResponse,
    SearchKnowledgeRequest,
    SearchKnowledgeResponse,
    SchemaSyncRequest,
    SchemaSyncResponse,
    TrainKnowledgeRequest,
    KnowledgeCandidateItem,
    KnowledgeCandidatesResponse,
    PromoteCandidateRequest,
    RejectCandidateRequest,
    RollbackCandidateRequest,
    UnresolvedQueryTermItem,
    UnresolvedTermsResponse,
    ResolveUnresolvedTermRequest,
)
from app.infrastructure.database.models import KnowledgeDocumentModel
from app.infrastructure.database.postgres_adapter import get_db_session
from app.infrastructure.database.vector_repository import VectorRepository
from app.infrastructure.database.candidate_repository import CandidateRepository
from app.infrastructure.database.repositories.unresolved_terms_repository import UnresolvedQueryTermRepository
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.llm.sql_guardrail import SQLGuardrail
from app.use_cases.ingest_knowledge import IngestKnowledgeUseCase
from app.use_cases.manage_connections import ManageConnectionsUseCase
from app.use_cases.sync_schema import SyncSchemaUseCase

router = APIRouter(prefix="/knowledge", tags=["Knowledge & RAG"])


@router.get(
    "/rules",
    summary="Listar cápsulas de aprendizaje enseñadas a la IA (Relaciones, Reglas, Fórmulas y Ejemplos SQL)"
)
async def list_trained_rules(
    connection_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session)
):
    """Devuelve todas las reglas, relaciones manuales, fórmulas y ejemplos SQL aprendidos en pgvector."""
    repo = VectorRepository(session)
    items = await repo.list_learned_rules(connection_id=connection_id)
    return {
        "total": len(items),
        "rules": items
    }


@router.post(
    "/train",
    status_code=status.HTTP_201_CREATED,
    summary="Enseñar y vectorizar una relación JOIN, regla de negocio, fórmula o SQL de ejemplo"
)
async def train_knowledge_capsule(
    payload: TrainKnowledgeRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Valida, previene duplicados, vectoriza en pgvector y vincula la cápsula de aprendizaje
    al grafo relacional de la conexión activa.
    """
    allowed_categories = {"custom_relation", "business_rule", "kpi_formula", "sql_example"}
    category = payload.category if payload.category in allowed_categories else "business_rule"

    conn_manager = ManageConnectionsUseCase(session)
    active_conn = await conn_manager.get_active_or_target_connection(payload.connection_id)
    target_conn_id = str(active_conn.id) if active_conn else payload.connection_id
    dept_name = active_conn.name if active_conn else "Entrenamiento IA"

    # Validar seguridad si es un ejemplo SQL (CHK011: solo SELECT permitido mediante sqlglot)
    if category == "sql_example" or payload.sql_query:
        sql_to_check = (payload.sql_query or payload.content).strip()
        guardrail = SQLGuardrail(max_limit=500)
        is_valid, safe_sql, err_msg = guardrail.validate_and_sanitize(sql_to_check)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El ejemplo SQL debe ser una consulta SELECT válida de solo lectura: {err_msg}"
            )

    # Construir texto enriquecido y metadatos
    related_tables = []
    join_hint = ""
    enriched_content = payload.content.strip()

    if category == "custom_relation" and payload.source_table and payload.target_table:
        src_t = payload.source_table.strip()
        src_col = (payload.source_column or "id").strip()
        tgt_t = payload.target_table.strip()
        tgt_col = (payload.target_column or "id").strip()
        lbl_col = (payload.label_column or "nombre").strip()
        related_tables = [src_t, tgt_t]
        join_hint = (
            f"JOIN {tgt_t} ON {src_t}.{src_col} = {tgt_t}.{tgt_col} "
            f"(mostrar siempre {tgt_t}.{lbl_col} en vez de {src_col})"
        )
        enriched_content = (
            f"RELACIÓN OBLIGATORIA ENSEÑADA POR EL USUARIO: La tabla `{src_t}` se relaciona con `{tgt_t}` "
            f"uniendo `{src_t}.{src_col} = {tgt_t}.{tgt_col}`. "
            f"REGLA: Nunca muestres `{src_col}` crudo; haz siempre `JOIN {tgt_t} ON {src_t}.{src_col} = {tgt_t}.{tgt_col}` "
            f"y selecciona `{tgt_t}.{lbl_col}`.\nDetalle: {payload.content}"
        )
    elif category == "sql_example" and payload.sql_query:
        enriched_content = (
            f"EJEMPLO SQL DE ORO (FEW-SHOT) ENSEÑADO POR EL USUARIO:\n"
            f"Pregunta / Caso: {payload.title} - {payload.content}\n"
            f"Consulta SQL Verificada:\n{payload.sql_query.strip()}"
        )

    # Prevenir duplicados por título y categoría (CHK014)
    dup_stmt = select(KnowledgeDocumentModel.id).where(
        KnowledgeDocumentModel.category == category,
        KnowledgeDocumentModel.title == payload.title
    )
    existing_ids = [r[0] for r in (await session.execute(dup_stmt)).all()]
    if existing_ids:
        await session.execute(
            delete(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id.in_(existing_ids))
        )
        await session.commit()

    ingest_uc = IngestKnowledgeUseCase(session)
    metadata = {
        "connection_id": target_conn_id,
        "source_table": payload.source_table,
        "source_column": payload.source_column,
        "target_table": payload.target_table,
        "target_column": payload.target_column,
        "label_column": payload.label_column,
        "related_tables": related_tables,
        "join_hint": join_hint,
        "sql_query": payload.sql_query,
        "taught_by": "user"
    }

    result = await ingest_uc.execute(
        title=payload.title,
        category=category,
        department=dept_name,
        content=enriched_content,
        metadata=metadata
    )

    # Si es una relación manual, inyectarla también en los esquemas de las tablas en pgvector
    repo = VectorRepository(session)
    schema_updated = 0
    if category == "custom_relation" and payload.source_table and payload.target_table:
        schema_updated = await repo.attach_custom_relation_to_schema_docs(
            source_table=payload.source_table,
            target_table=payload.target_table,
            join_hint=join_hint,
            connection_id=target_conn_id
        )

    return {
        **result,
        "join_hint": join_hint,
        "schema_docs_linked": schema_updated
    }


@router.delete(
    "/rules/{document_id}",
    summary="Eliminar una regla o cápsula de entrenamiento de pgvector"
)
async def delete_trained_rule(
    document_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    repo = VectorRepository(session)
    deleted = await repo.delete_learned_rule(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la regla especificada."
        )
    return {"status": "deleted", "document_id": document_id}


@router.post(
    "/ingest",
    response_model=IngestKnowledgeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingestar y vectorizar un manual o documento de proceso"
)
async def ingest_knowledge(
    payload: IngestKnowledgeRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Particiona el documento, calcula embeddings en Ollama y almacena los vectores en PostgreSQL 17."""
    try:
        use_case = IngestKnowledgeUseCase(session)
        result = await use_case.execute(
            title=payload.title,
            category=payload.category,
            department=payload.department,
            content=payload.content,
            metadata=payload.metadata
        )
        return IngestKnowledgeResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la ingesta vectorial: {str(e)}"
        )


@router.post(
    "/search",
    response_model=SearchKnowledgeResponse,
    summary="Búsqueda semántica por similitud en pgvector"
)
async def search_knowledge(
    payload: SearchKnowledgeRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Calcula el vector de la consulta y recupera los fragmentos más cercanos mediante el índice HNSW."""
    try:
        ollama = OllamaAdapter()
        query_embedding = await ollama.generate_embedding(payload.query)

        repo = VectorRepository(session)
        chunks = await repo.search_similar(
            query_embedding=query_embedding,
            top_k=payload.top_k,
            category=payload.category
        )

        results = [
            ChunkResultItem(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                chunk_text=c.chunk_text,
                similarity_score=c.similarity_score or 0.0,
                metadata=c.metadata
            )
            for c in chunks
        ]

        return SearchKnowledgeResponse(
            query=payload.query,
            total_results=len(results),
            results=results
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en la búsqueda semántica: {str(e)}"
        )


@router.post(
    "/schema-sync",
    response_model=SchemaSyncResponse,
    summary="Sincronizar e indexar el esquema de MariaDB en pgvector"
)
async def sync_schema(
    payload: Optional[SchemaSyncRequest] = None,
    session: AsyncSession = Depends(get_db_session)
):
    """Extrae las tablas y columnas de MariaDB e indexa su esquema en pgvector para Text-to-SQL."""
    try:
        use_case = SyncSchemaUseCase(session)
        table_filter = payload.tables if payload else None
        result = await use_case.execute(table_filter=table_filter)
        return SchemaSyncResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la sincronización del esquema: {str(e)}"
        )


# ==============================================================================
# Endpoints de Ciclo de Vida de Candidatos de Conocimiento Implícito (Fase 1)
# ==============================================================================

@router.get(
    "/candidates",
    response_model=KnowledgeCandidatesResponse,
    summary="Listar candidatos de conocimiento y propuestas pendientes"
)
async def list_candidates(
    connection_id: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    proposed_only: bool = Query(default=False),
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    x_user_role: str = Header(default="analyst", alias="X-User-Role"),
    x_user_permissions: Optional[str] = Header(default="", alias="X-User-Permissions"),
    session: AsyncSession = Depends(get_db_session)
):
    """Devuelve la lista de candidatos aplicando autorización RBAC estricta."""
    perms = [p.strip() for p in (x_user_permissions or "").split(",") if p.strip()]
    repo = CandidateRepository(session)
    items = await repo.list_candidates(
        user_id=x_user_id,
        user_role=x_user_role,
        user_permissions=perms,
        connection_id=connection_id,
        scope=scope,
        status=status_filter,
        proposed_only=proposed_only
    )
    return KnowledgeCandidatesResponse(total=len(items), candidates=items)


@router.post(
    "/candidates/{candidate_id}/confirm-user",
    summary="Confirmar regla candidata para uso exclusivo del usuario autor"
)
async def confirm_user_candidate(
    candidate_id: str,
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    session: AsyncSession = Depends(get_db_session)
):
    """El autor ratifica un candidato para su alcance personal (scope: user)."""
    repo = CandidateRepository(session)
    try:
        updated = await repo.confirm_user_candidate(candidate_id=candidate_id, user_id=x_user_id)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidato no encontrado.")
        return {"success": True, "message": "Regla confirmada para tu usuario.", "data": updated}
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.post(
    "/candidates/{candidate_id}/propose-global",
    summary="Postular regla candidata a revisión corporativa global"
)
async def propose_global_candidate(
    candidate_id: str,
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    session: AsyncSession = Depends(get_db_session)
):
    """El autor postula su regla personal para ser evaluada por un administrador."""
    repo = CandidateRepository(session)
    try:
        updated = await repo.propose_global_candidate(candidate_id=candidate_id, user_id=x_user_id)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidato no encontrado.")
        return {"success": True, "message": "Regla propuesta para revisión corporativa.", "data": updated}
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.post(
    "/candidates/{candidate_id}/promote-global",
    summary="Promover regla a conocimiento corporativo verificado (Exclusivo Administradores)"
)
async def promote_global_candidate(
    candidate_id: str,
    payload: Optional[PromoteCandidateRequest] = None,
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    x_user_role: str = Header(default="analyst", alias="X-User-Role"),
    x_user_permissions: Optional[str] = Header(default="", alias="X-User-Permissions"),
    session: AsyncSession = Depends(get_db_session)
):
    """Promueve una regla a scope global y status verified. Rechaza con 409 si colisiona con otra global."""
    perms = [p.strip() for p in (x_user_permissions or "").split(",") if p.strip()]
    repo = CandidateRepository(session)
    try:
        updated = await repo.promote_global_candidate(
            candidate_id=candidate_id,
            admin_user_id=x_user_id,
            user_role=x_user_role,
            user_permissions=perms,
            edited_content=payload.edited_content if payload else None,
            reason=payload.reason if payload else None
        )
        return {"success": True, "message": "Regla promovida exitosamente a global.", "data": updated}
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_409_CONFLICT if "409" in err_msg or "Conflicto" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)


@router.post(
    "/candidates/{candidate_id}/reject",
    summary="Descartar un candidato o regla"
)
async def reject_candidate(
    candidate_id: str,
    payload: Optional[RejectCandidateRequest] = None,
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    x_user_role: str = Header(default="analyst", alias="X-User-Role"),
    x_user_permissions: Optional[str] = Header(default="", alias="X-User-Permissions"),
    session: AsyncSession = Depends(get_db_session)
):
    """Descarta una regla. Reglas de scope global exigen rol de administrador."""
    perms = [p.strip() for p in (x_user_permissions or "").split(",") if p.strip()]
    repo = CandidateRepository(session)
    try:
        updated = await repo.reject_candidate(
            candidate_id=candidate_id,
            actor_id=x_user_id,
            actor_role=x_user_role,
            user_permissions=perms,
            reason=payload.reason if payload else None
        )
        return {"success": True, "message": "Candidato descartado.", "data": updated}
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))


@router.post(
    "/candidates/{candidate_id}/rollback",
    summary="Revertir una regla a su estado anterior o desactivarla"
)
async def rollback_candidate(
    candidate_id: str,
    payload: Optional[RollbackCandidateRequest] = None,
    x_user_id: str = Header(default="guest_user", alias="X-User-Id"),
    x_user_role: str = Header(default="analyst", alias="X-User-Role"),
    x_user_permissions: Optional[str] = Header(default="", alias="X-User-Permissions"),
    session: AsyncSession = Depends(get_db_session)
):
    """Revierte una regla restaurando su estado previo desde auditoría."""
    perms = [p.strip() for p in (x_user_permissions or "").split(",") if p.strip()]
    repo = CandidateRepository(session)
    try:
        updated = await repo.rollback_candidate(
            candidate_id=candidate_id,
            actor_id=x_user_id,
            actor_role=x_user_role,
            user_permissions=perms,
            reason=payload.reason if payload else None
        )
        return {"success": True, "message": "Regla revertida correctamente.", "data": updated}
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))


# ==============================================================================
# Endpoints de Cola de Términos No Entendidos y Ambigüedades (Feature 006)
# ==============================================================================

@router.get(
    "/unresolved-terms",
    response_model=UnresolvedTermsResponse,
    summary="Listar términos no entendidos, colisiones y fallos de consulta"
)
async def list_unresolved_terms(
    connection_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session)
):
    """Devuelve la cola de términos no entendidos para su revisión o conversión en glosario."""
    repo = UnresolvedQueryTermRepository(session)
    conn_uuid = None
    if connection_id:
        try:
            conn_uuid = uuid.UUID(connection_id)
        except ValueError:
            pass

    records = await repo.list_terms(
        connection_id=conn_uuid,
        status=status,
        limit=limit,
        offset=offset
    )
    items = [
        UnresolvedQueryTermItem(
            id=str(r.id),
            connection_id=str(r.connection_id) if r.connection_id else None,
            session_id=str(r.session_id),
            user_id=r.user_id,
            prompt=r.prompt,
            extracted_term=r.extracted_term,
            failure_reason=r.failure_reason,
            candidate_tables=r.candidate_tables or [],
            error_message=r.error_message,
            status=r.status,
            resolved_target=r.resolved_target,
            resolved_by=r.resolved_by,
            resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
            created_at=r.created_at.isoformat() if r.created_at else ""
        )
        for r in records
    ]
    return UnresolvedTermsResponse(total=len(items), items=items)


@router.post(
    "/unresolved-terms/{term_id}/resolve",
    summary="Resolver o descartar un término no entendido de la cola"
)
async def resolve_unresolved_term(
    term_id: str,
    payload: ResolveUnresolvedTermRequest,
    x_user_id: str = Header(default="admin", alias="X-User-Id"),
    session: AsyncSession = Depends(get_db_session)
):
    """Marca un término como resuelto o descartado asociándole la tabla de destino."""
    try:
        t_uuid = uuid.UUID(term_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de término inválido")

    repo = UnresolvedQueryTermRepository(session)
    updated = await repo.resolve_term(
        term_id=t_uuid,
        resolved_target=payload.resolved_target,
        resolved_by=x_user_id,
        status=payload.status
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Término no encontrado")

    return {
        "success": True,
        "message": f"Término marcado como {payload.status}.",
        "term_id": str(updated.id),
        "status": updated.status,
        "resolved_target": updated.resolved_target
    }
