"""Caso de uso para particionar, vectorizar e ingestar documentos de procesos en pgvector."""

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.domain.entities import DocumentChunk
from app.infrastructure.database.vector_repository import VectorRepository
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.parsers.text_chunker import TextChunker


class IngestKnowledgeUseCase:
    """Orquestador para el procesamiento e indexación de conocimiento empresarial."""

    def __init__(self, session: AsyncSession, ollama: Optional[OllamaAdapter] = None):
        settings = get_settings()
        self.session = session
        self.repository = VectorRepository(session)
        self.ollama = ollama or OllamaAdapter()
        self.chunker = TextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )

    async def execute(
        self,
        title: str,
        category: str,
        department: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ejecuta el flujo completo de partición, cálculo de embeddings e inserción."""
        # 1. Crear registro maestro del documento
        doc_record = await self.repository.create_document(
            title=title,
            category=category,
            department=department,
            content=content,
            metadata=metadata
        )

        # 2. Particionar texto en fragmentos
        raw_chunks = self.chunker.split_text(content)
        if not raw_chunks:
            return {
                "document_id": str(doc_record.id),
                "title": title,
                "chunks_created": 0,
                "status": "empty_content"
            }

        # 3. Vectorizar cada fragmento con nomic-embed-text
        chunks_to_insert: List[DocumentChunk] = []
        for idx, text in enumerate(raw_chunks):
            embedding = await self.ollama.generate_embedding(text)
            chunks_to_insert.append(
                DocumentChunk(
                    document_id=str(doc_record.id),
                    chunk_index=idx,
                    chunk_text=text,
                    embedding=embedding,
                    metadata={"department": department, "category": category, **(metadata or {})}
                )
            )

        # 4. Guardar en PostgreSQL 17 con pgvector
        saved_chunks = await self.repository.save_chunks(doc_record.id, chunks_to_insert)

        return {
            "document_id": str(doc_record.id),
            "title": title,
            "category": category,
            "department": department,
            "chunks_created": len(saved_chunks),
            "status": "indexed"
        }
