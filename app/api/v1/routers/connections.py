"""Endpoints REST para gestión dinámica de bases de datos y vectorización selectiva de tablas."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.schemas.connections import (
    ConnectionCreateRequest,
    ConnectionInfoResponse,
    ConnectionTestRequest,
    VectorizeTablesRequest,
)
from app.infrastructure.database.postgres_adapter import get_db_session
from app.use_cases.manage_connections import ManageConnectionsUseCase

router = APIRouter(prefix="/connections", tags=["Database Connections & Schema Discovery"])


@router.get(
    "",
    response_model=List[ConnectionInfoResponse],
    summary="Listar todas las conexiones de bases de datos registradas"
)
async def list_connections(session: AsyncSession = Depends(get_db_session)):
    use_case = ManageConnectionsUseCase(session)
    items = await use_case.list_connections()
    return [ConnectionInfoResponse(**item) for item in items]


@router.post(
    "/test",
    summary="Probar credenciales de conexión a PostgreSQL o MariaDB/MySQL sin guardar"
)
async def test_connection(
    payload: ConnectionTestRequest,
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    try:
        use_case = ManageConnectionsUseCase(session)
        return await use_case.test_credentials(
            engine=payload.engine,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            password=payload.password or ""
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo conectar a la base de datos ({payload.engine}://{payload.host}:{payload.port}/{payload.database_name}): {str(e)}"
        )


@router.post(
    "",
    response_model=ConnectionInfoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar una nueva conexión tras verificar conectividad"
)
async def create_connection(
    payload: ConnectionCreateRequest,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        use_case = ManageConnectionsUseCase(session)
        created = await use_case.create_connection(
            name=payload.name,
            engine=payload.engine,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            password=payload.password or "",
            set_active=payload.set_active
        )
        return ConnectionInfoResponse(**created)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear y verificar la conexión: {str(e)}"
        )


@router.post(
    "/{connection_id}/activate",
    response_model=ConnectionInfoResponse,
    summary="Activar una conexión para que el Chat consulte sobre ella"
)
async def activate_connection(
    connection_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        use_case = ManageConnectionsUseCase(session)
        updated = await use_case.activate_connection(connection_id)
        return ConnectionInfoResponse(**updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{connection_id}/tables",
    summary="Detectar y listar todas las tablas y columnas de la conexión"
)
async def get_connection_tables(
    connection_id: str,
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    try:
        use_case = ManageConnectionsUseCase(session)
        return await use_case.get_connection_tables(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al inspeccionar las tablas de la base de datos: {str(e)}"
        )


@router.post(
    "/{connection_id}/vectorize",
    summary="Vectorizar en pgvector las tablas seleccionadas por el usuario"
)
async def vectorize_connection_tables(
    connection_id: str,
    payload: VectorizeTablesRequest,
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    try:
        use_case = ManageConnectionsUseCase(session)
        return await use_case.vectorize_selected_tables(
            connection_id=connection_id,
            selected_tables=payload.tables
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la vectorización de tablas: {str(e)}"
        )


@router.delete(
    "/{connection_id}",
    summary="Eliminar una conexión y sus vectores de esquema asociados"
)
async def delete_connection(
    connection_id: str,
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    try:
        use_case = ManageConnectionsUseCase(session)
        return await use_case.delete_connection(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
