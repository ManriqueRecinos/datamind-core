"""Pruebas de contrato para los endpoints de conocimiento (Fase 3)."""

import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_contract_ingest_and_search():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Ingestar
        doc = {
            "title": "Procedimiento de Etiquetado",
            "category": "process_manual",
            "department": "Empaque",
            "content": "Las etiquetas deben contener el código de barras y la fecha de expiración en la esquina inferior derecha."
        }
        res_ingest = await client.post("/api/v1/knowledge/ingest", json=doc)
        assert res_ingest.status_code == 201
        data_ingest = res_ingest.json()
        assert "document_id" in data_ingest
        assert data_ingest["status"] == "indexed"
        assert data_ingest["chunks_created"] >= 1

        # Buscar
        search = {"query": "código de barras de etiquetas", "top_k": 2}
        res_search = await client.post("/api/v1/knowledge/search", json=search)
        assert res_search.status_code == 200
        data_search = res_search.json()
        assert data_search["total_results"] >= 1
        assert "código de barras" in data_search["results"][0]["chunk_text"]
