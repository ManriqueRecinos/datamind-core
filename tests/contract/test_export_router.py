"""Pruebas de contrato para el endpoint de exportación a Excel (Fase 6)."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
import httpx
from app.infrastructure.database.models import QueryDatasetModel
from app.infrastructure.database.postgres_adapter import AsyncSessionLocal
from app.main import app


@pytest.mark.asyncio
async def test_contract_export_excel_success():
    dataset_id = f"ds_contract_{uuid.uuid4().hex[:8]}"
    # Insertar dataset de prueba en PostgreSQL
    async with AsyncSessionLocal() as session:
        ds = QueryDatasetModel(
            dataset_id=dataset_id,
            sql_executed="SELECT * FROM test",
            columns=["id", "nombre"],
            rows=[{"id": 1, "nombre": "Item 1"}],
            row_count=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        session.add(ds)
        await session.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/export/excel/{dataset_id}")
        assert res.status_code == 200
        assert "application/vnd.openxmlformats" in res.headers["content-type"]
        assert 'attachment; filename="' in res.headers["content-disposition"]
        assert len(res.content) > 0


@pytest.mark.asyncio
async def test_contract_export_excel_not_found():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/export/excel/ds_non_existent_id")
        assert res.status_code == 404
