"""Prueba de integración para la conexión asíncrona a PostgreSQL 17 y pgvector (Fase 2)."""

import pytest
from sqlalchemy import text
from app.infrastructure.database.postgres_adapter import engine, AsyncSessionLocal


@pytest.mark.asyncio
async def test_postgres_connection_and_pgvector():
    async with AsyncSessionLocal() as session:
        # Verificar extensión vector
        result = await session.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = result.fetchone()
        assert row is not None, "La extensión vector debe estar activa en enterprise_rag"
        assert row[0] == "vector"

        # Verificar tablas creadas
        tables_res = await session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        table_names = [t[0] for t in tables_res.fetchall()]
        assert "knowledge_documents" in table_names
        assert "knowledge_vector_chunks" in table_names
        assert "chat_sessions" in table_names
        assert "chat_messages" in table_names
        assert "query_datasets" in table_names
