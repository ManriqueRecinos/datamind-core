"""Pruebas de contrato para el gestor dinámico de bases de datos y vectorización selectiva."""

import pytest
import httpx
from app.core.config import get_settings
from app.main import app


@pytest.mark.asyncio
async def test_contract_connections_lifecycle_and_selective_vectorization():
    """Verifica el flujo completo: probar conexión PostgreSQL, guardar, listar tablas y vectorizar selectivamente."""
    settings = get_settings()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Probar conexión contra PostgreSQL local (enterprise_rag)
        test_payload = {
            "engine": "postgresql",
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database_name": settings.postgres_db,
            "username": settings.postgres_user,
            "password": settings.postgres_password
        }
        test_res = await client.post("/api/v1/connections/test", json=test_payload)
        assert test_res.status_code == 200, f"Error en /connections/test: {test_res.text}"
        test_data = test_res.json()
        assert test_data["connected"] is True
        assert test_data["engine"] == "postgresql"
        assert test_data["tables_detected"] >= 1

        # 2. Guardar la nueva conexión
        create_payload = {
            **test_payload,
            "name": "PostgreSQL Local Test",
            "set_active": False
        }
        create_res = await client.post("/api/v1/connections", json=create_payload)
        assert create_res.status_code == 201, f"Error en /connections create: {create_res.text}"
        created_conn = create_res.json()
        conn_id = created_conn["id"]
        assert created_conn["name"] == "PostgreSQL Local Test"
        assert created_conn["password_masked"] == "********"

        # 3. Listar todas las tablas detectadas en esa conexión
        tables_res = await client.get(f"/api/v1/connections/{conn_id}/tables")
        assert tables_res.status_code == 200
        tables_data = tables_res.json()
        assert tables_data["total_tables"] >= 1
        table_names = [t["table_name"] for t in tables_data["tables"]]
        assert "chat_sessions" in table_names

        # 4. Vectorizar selectivamente una tabla ('chat_sessions')
        vec_res = await client.post(
            f"/api/v1/connections/{conn_id}/vectorize",
            json={"tables": ["chat_sessions"]}
        )
        assert vec_res.status_code == 200, f"Error en vectorización: {vec_res.text}"
        vec_data = vec_res.json()
        assert vec_data["status"] == "vectorized"
        assert vec_data["tables_vectorized_now"] == 1
        assert "chat_sessions" in vec_data["tables"]

        # 5. Eliminar la conexión temporal de prueba
        del_res = await client.delete(f"/api/v1/connections/{conn_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"
