"""Repositorio para almacenamiento y búsqueda por similitud en PostgreSQL con pgvector."""

from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities import DocumentChunk
from app.infrastructure.database.models import (
    KnowledgeDocumentModel,
    KnowledgeVectorChunkModel,
)


class VectorRepository:
    """Implementa operaciones de persistencia y búsqueda vectorial usando pgvector."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(
        self,
        title: str,
        category: str,
        department: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> KnowledgeDocumentModel:
        """Crea el registro maestro del documento."""
        doc = KnowledgeDocumentModel(
            title=title,
            category=category,
            department=department,
            content=content,
            metadata_=metadata or {}
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def save_chunks(
        self, document_id: uuid.UUID, chunks: List[DocumentChunk]
    ) -> List[KnowledgeVectorChunkModel]:
        """Inserta los fragmentos vectorizados asociados al documento."""
        chunk_models = []
        for idx, chunk in enumerate(chunks):
            chunk_model = KnowledgeVectorChunkModel(
                document_id=document_id,
                chunk_index=idx,
                chunk_text=chunk.chunk_text,
                embedding=chunk.embedding,
                metadata_=chunk.metadata
            )
            chunk_models.append(chunk_model)
            self.session.add(chunk_model)

        await self.session.commit()
        return chunk_models

    async def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 4,
        category: Optional[str] = None,
        connection_id: Optional[str] = None
    ) -> List[DocumentChunk]:
        """Realiza búsqueda semántica por distancia coseno usando el índice HNSW de pgvector."""
        # En pgvector, cosine_distance genera la distancia (menor es más similar)
        distance = KnowledgeVectorChunkModel.embedding.cosine_distance(query_embedding)
        query = select(
            KnowledgeVectorChunkModel,
            distance.label("distance")
        ).order_by(distance).limit(top_k)

        if category or connection_id:
            query = query.join(KnowledgeDocumentModel)
            if category:
                query = query.filter(KnowledgeDocumentModel.category == category)
            if connection_id:
                query = query.filter(
                    KnowledgeDocumentModel.metadata_["connection_id"].astext == str(connection_id)
                )

        result = await self.session.execute(query)
        rows = result.all()

        results: List[DocumentChunk] = []
        for row in rows:
            chunk_model = row[0]
            dist = float(row[1])
            # Similitud coseno normalizada: 1.0 - distancia
            similarity = round(max(0.0, 1.0 - dist), 4)

            results.append(
                DocumentChunk(
                    id=str(chunk_model.id),
                    document_id=str(chunk_model.document_id),
                    chunk_index=chunk_model.chunk_index,
                    chunk_text=chunk_model.chunk_text,
                    metadata=chunk_model.metadata_ or {},
                    similarity_score=similarity
                )
            )

        return results

    async def delete_schema_documents(
        self,
        connection_id: str,
        table_names: Optional[List[str]] = None
    ) -> int:
        """Elimina documentos de esquema previos de una conexión (o tablas específicas) para evitar duplicados."""
        stmt = select(KnowledgeDocumentModel.id).filter(
            KnowledgeDocumentModel.category == "db_schema",
            KnowledgeDocumentModel.metadata_["connection_id"].astext == str(connection_id)
        )
        if table_names:
            stmt = stmt.filter(
                KnowledgeDocumentModel.metadata_["table_name"].astext.in_(table_names)
            )
        res = await self.session.execute(stmt)
        doc_ids = [r[0] for r in res.all()]
        if not doc_ids:
            return 0

        await self.session.execute(
            delete(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id.in_(doc_ids))
        )
        await self.session.commit()
        return len(doc_ids)
