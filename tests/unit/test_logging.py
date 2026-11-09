"""Prueba unitaria para el formateador de logs estructurados y ofuscación de credenciales (Fase 8)."""

from app.core.logging import mask_sensitive_data


def test_mask_sensitive_data_password():
    raw = "Conexión fallida con password=MiPasswordSuperSecreto en el servidor"
    masked = mask_sensitive_data(raw)
    assert "MiPasswordSuperSecreto" not in masked
    assert "password=***" in masked


def test_mask_sensitive_data_bearer_token():
    raw = "Headers: Authorization: Bearer secret_token_123456"
    masked = mask_sensitive_data(raw)
    assert "secret_token_123456" not in masked
    assert "Bearer ***" in masked


def test_mask_sensitive_data_postgres_url():
    raw = "DSN: postgresql+asyncpg://postgres:miPasswordSecreto@localhost:5432/enterprise_rag"
    masked = mask_sensitive_data(raw)
    assert "miPasswordSecreto" not in masked
    assert "postgresql+asyncpg://postgres:***@localhost:5432/enterprise_rag" in masked
