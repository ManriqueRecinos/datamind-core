"""Pruebas unitarias para el servicio de Humanización de Datos y Enmascaramiento."""

import pytest
from app.infrastructure.analytics.data_humanizer import DataHumanizer


def test_sensitive_columns_detection():
    """Valida que contraseñas, tokens y credenciales sean identificados como sensibles."""
    assert DataHumanizer.is_sensitive("password") is True
    assert DataHumanizer.is_sensitive("user_password") is True
    assert DataHumanizer.is_sensitive("remember_token") is True
    assert DataHumanizer.is_sensitive("gotify_pass") is True
    assert DataHumanizer.is_sensitive("gotify_app_token") is True
    assert DataHumanizer.is_sensitive("api_secret") is True
    assert DataHumanizer.is_sensitive("user_hash") is True

    # Columnas seguras
    assert DataHumanizer.is_sensitive("username") is False
    assert DataHumanizer.is_sensitive("user_name") is False
    assert DataHumanizer.is_sensitive("email") is False
    assert DataHumanizer.is_sensitive("company_name") is False


def test_sanitize_and_humanize_purges_sensitive_fields():
    """Valida que el humanizador elimine campos sensibles y renombre las columnas seguras a etiquetas humanas."""
    raw_columns = [
        "id",
        "user_name",
        "user_email",
        "user_password",
        "remember_token",
        "company_name"
    ]
    raw_rows = [
        {
            "id": 1,
            "user_name": "Manrique Recinos",
            "user_email": "manrique@supertex.com",
            "user_password": "$2y$12$e923847293847secret",
            "remember_token": "token_abc123",
            "company_name": "SUMAIE El Salvador"
        }
    ]

    human_cols, sanitized_rows, mapping = DataHumanizer.sanitize_and_humanize(raw_columns, raw_rows)

    # 1. Verificar columnas purgadas
    assert "user_password" not in human_cols
    assert "remember_token" not in human_cols
    assert "Contraseña" not in human_cols

    # 2. Verificar etiquetas humanas
    assert "Nombre de Usuario" in human_cols or "Nombre" in human_cols
    assert "Correo Electrónico" in human_cols
    assert "Empresa Asignada" in human_cols or "Empresa" in human_cols

    # 3. Verificar fila limpia
    assert len(sanitized_rows) == 1
    row = sanitized_rows[0]
    for key in row.keys():
        assert "password" not in key.lower()
        assert "token" not in key.lower()


def test_resolve_unambiguous_entity():
    """Valida la resolución de entidades lematizadas en español sin pedir aclaraciones redundantes."""
    synced_tables = ["companies", "company_user", "users"]

    # Pregunta clara con plural 'usuarios'
    is_unambiguous, target = DataHumanizer.resolve_unambiguous_entity(
        "Que usuarios hay creados actualmente?",
        synced_tables
    )
    assert is_unambiguous is True
    assert target == "users"

    # Pregunta con 'empresas'
    is_unambiguous, target = DataHumanizer.resolve_unambiguous_entity(
        "muéstrame las empresas activas",
        synced_tables
    )
    assert is_unambiguous is True
    assert target == "companies"
