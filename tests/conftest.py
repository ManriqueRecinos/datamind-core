"""Configuración global de pytest y fixtures asíncronos para Windows."""

import sys
import asyncio
import pytest
from app.infrastructure.database.models import Base
from app.infrastructure.database.postgres_adapter import engine

# En Windows, usar SelectorEventLoop para evitar el error 'NoneType object has no attribute send' al cerrar sockets en asyncpg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
async def cleanup_db_pool():
    """Asegura que las tablas existan y limpia las conexiones del pool al terminar cada test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
