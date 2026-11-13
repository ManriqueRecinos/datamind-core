"""Esquemas de solicitud y respuesta para la API de Query Blueprint."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.domain.query_blueprint import QueryBlueprint


class ParseBlueprintRequest(BaseModel):
    sql: str = Field(..., description="Sentencia SQL a analizar y estructurar")
    dialect: str = Field(default="postgres", description="Dialecto: postgres o mysql")


class ParseBlueprintResponse(BaseModel):
    blueprint: QueryBlueprint = Field(..., description="Blueprint generado del árbol SQL")
    dialect: str = Field(default="postgres", description="Dialecto utilizado")


class CompileBlueprintRequest(BaseModel):
    blueprint: QueryBlueprint = Field(..., description="Estructura del Query Blueprint a compilar")
    dialect: str = Field(default="postgres", description="Dialecto destino: postgres o mysql")


class CompileBlueprintResponse(BaseModel):
    sql: str = Field(..., description="Sentencia SQL compilada")
    dialect: str = Field(default="postgres", description="Dialecto utilizado")


class ValidateBlueprintRequest(BaseModel):
    blueprint: QueryBlueprint = Field(..., description="Estructura del Query Blueprint")
    connection_id: str = Field(..., description="ID de la conexión para validar contra tablas vectorizadas")


class ValidateBlueprintResponse(BaseModel):
    is_valid: bool = Field(..., description="Indica si el blueprint cumple las reglas de tablas y columnas")
    errors: List[str] = Field(default_factory=list, description="Errores semánticos o de inconsistencia encontrados")
    warnings: List[str] = Field(default_factory=list, description="Advertencias no bloqueantes")


class DryRunBlueprintRequest(BaseModel):
    sql: Optional[str] = Field(None, description="Sentencia SQL directa para prueba")
    blueprint: Optional[QueryBlueprint] = Field(None, description="Opcional: blueprint a compilar si no se pasa sql")
    connection_id: str = Field(..., description="ID de la conexión donde ejecutar la prueba con LIMIT 20")
    dialect: str = Field(default="postgres", description="Dialecto destino")


class DryRunBlueprintResponse(BaseModel):
    success: bool = Field(..., description="Indica si la ejecución fue exitosa")
    error: Optional[str] = Field(None, description="Detalle del error en caso de fallo")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="Primeras filas obtenidas (máx 20)")
    columns: List[str] = Field(default_factory=list, description="Nombres de las columnas devueltas")
    row_count: int = Field(default=0, description="Total de filas devueltas en la muestra")
    sql_executed: str = Field(..., description="Sentencia SQL final ejecutada con LIMIT forzado")
