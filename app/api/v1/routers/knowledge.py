"""Endpoints REST para la gestión del conocimiento y búsqueda vectorial en pgvector."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.schemas.knowledge import (
    ChunkResultItem,
    IngestKnowledgeRequest,
    IngestKnowledgeResponse,
    SearchKnowledgeRequest,
    SearchKnowledgeResponse,
    SchemaSyncRequest,
    SchemaSyncResponse,
)
from app.infrastructure.database.postgres_adapter import get_db_session
from app.infrastructure.database.vector_repository import VectorRepository
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.use_cases.ingest_knowledge import IngestKnowledgeUseCase
from app.use_cases.sync_schema import SyncSchemaUseCase
from app.use_cases.sync_schema import SyncSchemaUseCase

router = APIRouter(prefix="/knowledge", tags=["Knowledge & RAG"])


@router.post(
    "/schema-sync",
    summary="Sincronizar e indexar el catálogo de tablas de MariaDB en pgvector"
)
async def sync_mariadb_schema(
    session: AsyncSession = Depends(get_db_session)
):
    """Lee las tablas y columnas de MariaDB y las almacena vectorizadas para el agente Text-to-SQL."""
    try:
        use_case = SyncSchemaUseCase(session)
        result = await use_case.execute()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la sincronización de esquema de MariaDB: {str(e)}"
        )


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
