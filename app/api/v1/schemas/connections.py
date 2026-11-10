"""Esquemas Pydantic V2 para gestión de conexiones dinámicas de bases de datos."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConnectionTestRequest(BaseModel):
    """Credenciales para probar conectividad sin guardar."""
    engine: str = Field(..., description="Motor de BD: 'mariadb', 'mysql' o 'postgresql'")
    host: str = Field(..., min_length=1, description="Host o IP del servidor de BD")
    port: int = Field(default=3306, ge=1, le=65535, description="Puerto TCP")
    database_name: str = Field(..., min_length=1, description="Nombre de la base de datos")
    username: str = Field(..., min_length=1, description="Usuario de lectura")
    password: Optional[str] = Field(default="", description="Contraseña del usuario")


class ConnectionCreateRequest(ConnectionTestRequest):
    """Solicitud para guardar una nueva conexión de base de datos."""
    name: str = Field(..., min_length=2, max_length=120, description="Nombre descriptivo o alias de la conexión")
    set_active: bool = Field(default=True, description="Establecer como conexión activa por defecto")
    selected_schemas: Optional[List[str]] = Field(default=None, description="Esquemas seleccionados por el usuario")


class ConnectionInfoResponse(BaseModel):
    """Información pública de una conexión registrada (con contraseña enmascarada)."""
    id: str
    name: str
    engine: str
    host: str
    port: int
    database_name: str
    username: str
    password_masked: str
    is_active: bool
    synced_tables: List[str] = []
    synced_tables_count: int = 0
    selected_schemas: Optional[List[str]] = None
    created_at: Optional[str] = None
    tables_detected: Optional[int] = None
    latency_ms: Optional[int] = None


class VectorizeTablesRequest(BaseModel):
    """Listado de tablas seleccionadas por el usuario para vectorizar en pgvector."""
    tables: List[str] = Field(..., min_length=1, description="Lista de nombres de tablas a vectorizar")
