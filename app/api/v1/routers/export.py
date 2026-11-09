"""Endpoints para exportación y descarga de archivos Excel."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.postgres_adapter import get_db_session
from app.use_cases.export_excel import ExportExcelUseCase

router = APIRouter(prefix="/export", tags=["Excel Export"])


@router.get(
    "/excel/{dataset_id}",
    summary="Descargar reporte Excel (.xlsx) generado bajo demanda",
    response_description="Archivo binario de Microsoft Excel (.xlsx)"
)
async def download_excel_report(
    dataset_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """Genera al vuelo el archivo .xlsx para el dataset_id solicitado y lo entrega como descarga directa."""
    use_case = ExportExcelUseCase(session)
    excel_bytes, result = await use_case.execute(dataset_id)

    if excel_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result
        )

    filename = result
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
