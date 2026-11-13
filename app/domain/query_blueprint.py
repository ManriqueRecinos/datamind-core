"""Modelos de dominio y esquemas Pydantic para el Constructor de Consultas (Query Blueprint).

Permite representar, validar, serializar y deserializar consultas complejas compuestas
(SELECT con JOINs múltiples, WHERE, GROUP BY, ORDER BY, LIMIT y UNIONs), preservando
bloques sintácticos avanzados en `raw_blocks`.
"""

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator


class JoinType(str, Enum):
    INNER = "INNER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    FULL = "FULL"
    CROSS = "CROSS"


class UnionMode(str, Enum):
    UNION = "UNION"
    UNION_ALL = "UNION ALL"


class BaseTableSpec(BaseModel):
    table: str = Field(..., description="Nombre de la tabla base vectorizada")
    alias: Optional[str] = Field(None, description="Alias de la tabla base (ej. 'u')")


class OnCondition(BaseModel):
    left: str = Field(..., description="Columna o expresión izquierda (ej. 'u.id')")
    op: str = Field(default="=", description="Operador de comparación (=, !=, <, >, <=, >=, LIKE)")
    right: str = Field(..., description="Columna o expresión derecha (ej. 'ru.user_id')")


class JoinSpec(BaseModel):
    type: JoinType = Field(default=JoinType.INNER, description="Tipo de JOIN")
    table: str = Field(..., description="Nombre de la tabla a unir")
    alias: Optional[str] = Field(None, description="Alias de la tabla unida (ej. 'ru')")
    on: List[OnCondition] = Field(default_factory=list, description="Lista de condiciones de unión (ON)")


class SelectItem(BaseModel):
    expr: str = Field(..., description="Columna o expresión SQL (ej. 'u.name' o 'COUNT(*)')")
    alias: Optional[str] = Field(None, description="Alias de la columna (ej. 'nombre_usuario')")
    agg: Optional[str] = Field(None, description="Función de agregación opcional: COUNT, SUM, AVG, MIN, MAX")


class WhereCondition(BaseModel):
    left: str = Field(..., description="Columna o expresión evaluada")
    op: str = Field(default="=", description="Operador (=, !=, <, >, <=, >=, LIKE, ILIKE, IN, IS NULL, IS NOT NULL)")
    value: Optional[Any] = Field(None, description="Valor o lista de valores para la condición")
    logic: str = Field(default="AND", description="Operador lógico con respecto a la condición anterior (AND / OR)")


class OrderByItem(BaseModel):
    expr: str = Field(..., description="Columna o expresión para ordenar")
    direction: str = Field(default="ASC", description="Dirección: ASC o DESC")


class RawBlock(BaseModel):
    id: str = Field(..., description="Identificador único del bloque crudo")
    type: str = Field(default="custom", description="Tipo de bloque: cte, subquery, window, custom")
    title: Optional[str] = Field(None, description="Título descriptivo del fragmento")
    content: str = Field(..., description="Código SQL crudo no mapeable")


class SingleSelectBlueprint(BaseModel):
    """Representa una única sentencia SELECT (base para queries directas o miembros de UNION)."""
    base: BaseTableSpec = Field(..., description="Tabla principal FROM")
    joins: List[JoinSpec] = Field(default_factory=list, description="Lista de JOINs")
    select: List[SelectItem] = Field(default_factory=list, description="Columnas proyectadas")
    where: List[WhereCondition] = Field(default_factory=list, description="Condiciones WHERE")
    group_by: List[str] = Field(default_factory=list, description="Columnas GROUP BY")
    order_by: List[OrderByItem] = Field(default_factory=list, description="Ordenamiento")
    limit: Optional[int] = Field(default=None, description="Límite de filas (máx 1000)")


class UnionSpec(BaseModel):
    """Representa una rama de UNION combinada con otra consulta."""
    mode: UnionMode = Field(default=UnionMode.UNION_ALL, description="UNION o UNION ALL")
    select_query: SingleSelectBlueprint = Field(..., description="Blueprint del SELECT a unir")


class QueryBlueprint(BaseModel):
    """Blueprint maestro de una consulta compuesta, con soporte para UNIONs y raw_blocks."""
    version: str = Field(default="1.0", description="Versión del esquema")
    primary: SingleSelectBlueprint = Field(..., description="Consulta SELECT primaria")
    unions: List[UnionSpec] = Field(default_factory=list, description="Bloques UNION asociados")
    raw_blocks: List[RawBlock] = Field(
        default_factory=list,
        description="Fragmentos SQL no mapeables (CTEs, subconsultas complejas, window functions) preservados"
    )

    @model_validator(mode="after")
    def validate_complexity_limits(self):
        # 1. Validar límite de uniones
        if len(self.unions) > 10:
            raise ValueError("No se permiten más de 10 operaciones UNION en una sola consulta.")

        # 2. Validar límite de tablas en la consulta primaria
        primary_tables = 1 + len(self.primary.joins)
        if primary_tables > 30:
            raise ValueError(f"La consulta primaria excede el límite de 30 tablas unidas ({primary_tables}).")

        # 3. Validar límite de tablas en uniones
        total_tables = primary_tables
        for u in self.unions:
            u_tables = 1 + len(u.select_query.joins)
            if u_tables > 30:
                raise ValueError(f"Un bloque UNION excede el límite de 30 tablas ({u_tables}).")
            total_tables += u_tables

        if total_tables > 60:
            raise ValueError(f"La consulta compuesta excede el límite global de 60 tablas referenciadas ({total_tables}).")

        return self
