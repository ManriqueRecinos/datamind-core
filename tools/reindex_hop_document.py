import asyncio
import os
import sys
import uuid

# Asegurar path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.database.postgres_adapter import AsyncSessionLocal
from app.infrastructure.database.models import KnowledgeDocumentModel, KnowledgeVectorChunkModel
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.parsers.text_chunker import TextChunker
from sqlalchemy import delete


async def reindex_hop_catalog():
    file_path = r"c:\Users\mrecinos\Downloads\plan_repuestos_catalogo_hop.md"
    print(f"[*] Leyendo documento actualizado: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    connection_id = uuid.UUID("8629a50c-7351-4cda-bc97-967be6637c7e")
    doc_id = uuid.UUID("71405c16-e053-402e-b0c5-64a9ab25a10d")

    ollama = OllamaAdapter()
    chunker = TextChunker(chunk_size=600, chunk_overlap=100)
    raw_chunks = chunker.split_text(content)
    print(f"[*] Texto dividido en {len(raw_chunks)} fragmentos.")

    async with AsyncSessionLocal() as session:
        # 1. Purgar chunks viejos del documento
        print(f"[*] Eliminando chunks previos de doc_id: {doc_id}...")
        await session.execute(
            delete(KnowledgeVectorChunkModel).where(KnowledgeVectorChunkModel.document_id == doc_id)
        )
        
        # 2. Actualizar contenido del documento padre
        doc = await session.get(KnowledgeDocumentModel, doc_id)
        if doc:
            doc.content = content
            doc.title = "Arquitectura Relacional Catálogo HOP e Inventario de Repuestos (Actualizado)"
            session.add(doc)
        else:
            doc = KnowledgeDocumentModel(
                id=doc_id,
                title="Arquitectura Relacional Catálogo HOP e Inventario de Repuestos (Actualizado)",
                category="business_rule",
                department="Mantenimiento",
                content=content,
                metadata_={"source": "plan_repuestos_catalogo_hop.md"}
            )
            session.add(doc)

        await session.commit()

        # 3. Vectorizar cada chunk con prefijo search_document:
        print("[*] Vectorizando fragmentos con nomic-embed-text en Ollama...")
        for idx, chunk_text in enumerate(raw_chunks):
            embed_text = f"search_document: {chunk_text}"
            embedding = await ollama.generate_embedding(embed_text)

            chunk_record = KnowledgeVectorChunkModel(
                id=uuid.uuid4(),
                document_id=doc_id,
                connection_id=connection_id,
                chunk_index=idx,
                chunk_text=chunk_text,
                embedding=embedding,
                metadata_={
                    "source": "plan_repuestos_catalogo_hop.md",
                    "chunk": idx,
                    "total_chunks": len(raw_chunks),
                    "context": "catalogo_hop_repuestos"
                },
                status="verified",
                scope="global",
                trigger_signal="manual_teach",
                user_id="system"
            )
            session.add(chunk_record)

        await session.commit()
        print(f"[+] ¡Listo! {len(raw_chunks)} fragmentos indexados correctamente con connection_id {connection_id}.")


if __name__ == "__main__":
    asyncio.run(reindex_hop_catalog())
