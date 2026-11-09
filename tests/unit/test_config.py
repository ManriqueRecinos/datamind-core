"""Pruebas unitarias para la configuración y variables de entorno (Fase 1)."""

import pytest
from app.core.config import Settings, get_settings


def test_settings_load_defaults():
    settings = get_settings()
    assert settings.app_port == 8000
    assert "postgresql+asyncpg://" in settings.postgres_async_dsn
    assert "enterprise_rag" in settings.postgres_async_dsn
    assert settings.ollama_base_url.startswith("http")
    assert settings.llm_model == "qwen2.5:3b"
    assert settings.embedding_model == "nomic-embed-text"


def test_settings_postgres_dsn():
    s = Settings(
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5432,
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="secretpassword",
        POSTGRES_DB="test_db"
    )
    assert s.postgres_async_dsn == "postgresql+asyncpg://postgres:secretpassword@127.0.0.1:5432/test_db"
    assert s.postgres_sync_dsn == "postgresql://postgres:secretpassword@127.0.0.1:5432/test_db"
