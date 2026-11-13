"""Router de FastAPI para endpoints de Query Blueprint: Parse, Compile, Validate y Dry-Run."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.query_blueprint import (
    CompileBlueprintRequest,
    CompileBlueprintResponse,
    DryRunBlueprintRequest,
    DryRunBlueprintResponse,
    ParseBlueprintRequest,
    ParseBlueprintResponse,
    ValidateBlueprintRequest,
    ValidateBlueprintResponse,
)
from app.infrastructure.database.postgres_adapter import get_db_session
from app.use_cases.query_blueprint import QueryBlueprintUseCase

router = APIRouter(prefix="/query-blueprint", tags=["Query Blueprint"])


@router.post("/parse", response_model=ParseBlueprintResponse, summary="Convierte SQL en Query Blueprint")
async def parse_sql_to_blueprint(request: ParseBlueprintRequest):
    """Analiza una sentencia SQL (con JOINs, WHERE, GROUP BY, ORDER BY, LIMIT o UNIONs) y genera un blueprint estructurado."""
    use_case = QueryBlueprintUseCase()
    try:
        blueprint = use_case.parse(request.sql, dialect=request.dialect)
        return ParseBlueprintResponse(blueprint=blueprint, dialect=request.dialect)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al analizar la consulta SQL: {str(e)}"
        )


@router.post("/compile", response_model=CompileBlueprintResponse, summary="Compila Query Blueprint en SQL")
async def compile_blueprint_to_sql(request: CompileBlueprintRequest):
    """Compila un QueryBlueprint en código SQL limpio para el motor indicado (postgres o mysql)."""
    use_case = QueryBlueprintUseCase()
    try:
        sql = use_case.compile(request.blueprint, dialect=request.dialect)
        return CompileBlueprintResponse(sql=sql, dialect=request.dialect)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al compilar el blueprint SQL: {str(e)}"
        )


@router.post("/validate", response_model=ValidateBlueprintResponse, summary="Valida el blueprint contra tablas vectorizadas")
async def validate_blueprint(
    request: ValidateBlueprintRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Verifica que las tablas del blueprint existan en la conexión y estén vectorizadas en el sistema."""
    use_case = QueryBlueprintUseCase(session=db)
    try:
        result = await use_case.validate(request.blueprint, request.connection_id)
        return ValidateBlueprintResponse(
            is_valid=result["is_valid"],
            errors=result["errors"],
            warnings=result["warnings"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error durante la validación del blueprint: {str(e)}"
        )


@router.post("/dry-run", response_model=DryRunBlueprintResponse, summary="Ejecuta una prueba segura (LIMIT 20)")
async def dry_run_query(
    request: DryRunBlueprintRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Ejecuta una prueba de solo lectura en la base de datos destino con un límite estricto de 20 registros."""
    use_case = QueryBlueprintUseCase(session=db)
    try:
        sql_to_run = request.sql
        if not sql_to_run and request.blueprint:
            sql_to_run = use_case.compile(request.blueprint, dialect=request.dialect)

        if not sql_to_run:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Debe suministrar una sentencia SQL o un blueprint para ejecutar la prueba."
            )

        res = await use_case.dry_run(sql_to_run, request.connection_id)
        return DryRunBlueprintResponse(
            success=res["success"],
            error=res.get("error"),
            rows=res.get("rows", []),
            columns=res.get("columns", []),
            row_count=res.get("row_count", 0),
            sql_executed=res.get("sql_executed", sql_to_run)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo en la prueba de consulta: {str(e)}"
        )
