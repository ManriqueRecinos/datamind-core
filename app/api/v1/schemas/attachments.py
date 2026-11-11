"""Esquemas Pydantic V2 para la carga y gestión de archivos adjuntos en el chat."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AttachmentColumnSchema(BaseModel):
    """Metadatos de una columna inferida en el archivo tabular."""
    name: str = Field(..., description="Nombre limpio de la columna")
    type: str = Field(..., description="Tipo inferido (TEXT, INTEGER, DECIMAL, DATE, BOOLEAN)")
    sample_values: Optional[List[Any]] = Field(default_factory=list, description="Muestra de valores")


class AttachmentSchemaPreview(BaseModel):
    """Esquema de columnas y filas de muestra del archivo procesado."""
    columns: List[AttachmentColumnSchema] = Field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)
    total_rows: int = Field(default=0)


class AttachmentUploadResponse(BaseModel):
    """Respuesta tras procesar y validar un archivo adjunto."""
    id: str
    session_id: str
    filename: str
    original_name: str
    mime_type: str
    file_size_bytes: int
    row_count: int
    schema_preview: AttachmentSchemaPreview
    status: str = "ready"
    created_at: str


class AttachmentSummarySchema(BaseModel):
    """Resumen para listar archivos adjuntos en una sesión."""
    id: str
    session_id: str
    original_name: str
    mime_type: str
    file_size_bytes: int
    row_count: Optional[int] = None
    status: str
    created_at: str
