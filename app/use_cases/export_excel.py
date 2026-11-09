"""Caso de uso para recuperar un dataset en caché y generar el archivo Excel."""

from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities import QueryDataset
from app.infrastructure.database.models import QueryDatasetModel
from app.infrastructure.export.excel_generator import ExcelGenerator


class ExportExcelUseCase:
    """Orquesta la recuperación de datos tabulares cacheados y la emisión del archivo .xlsx."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.generator = ExcelGenerator()

    async def execute(self, dataset_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Recupera el dataset por su ID y genera el archivo binario.
        Retorna: (excel_bytes, filename) o (None, error_detail) si expiró o no existe.
        """
        record = await self.session.get(QueryDatasetModel, dataset_id)
        if not record:
            return None, "El conjunto de datos solicitado no existe o ha expirado."

        # Verificar si expiró
        if record.expires_at < datetime.now(timezone.utc):
            return None, "El conjunto de datos ha expirado de la memoria caché."

        dataset = QueryDataset(
            dataset_id=record.dataset_id,
            sql_executed=record.sql_executed,
            columns=record.columns,
            rows=record.rows,
            row_count=record.row_count,
            created_at=record.created_at,
            expires_at=record.expires_at
        )

        excel_bytes = self.generator.generate_excel_bytes(
            dataset=dataset,
            title="DataMind AI - Reporte Analítico de Datos"
        )

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"datamind_report_{timestamp_str}.xlsx"
        return excel_bytes, filename
