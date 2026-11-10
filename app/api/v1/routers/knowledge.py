"""Endpoints REST para la gestión del conocimiento, Centro de Entrenamiento IA y búsqueda vectorial en pgvector."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
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
)
from app.infrastructure.database.models import KnowledgeDocumentModel
from app.infrastructure.database.postgres_adapter import get_db_session
from app.infrastructure.database.vector_repository import VectorRepository
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
