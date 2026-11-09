"""Esquemas de validación Pydantic V2 para la API de conocimiento (RAG)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IngestKnowledgeRequest(BaseModel):
    """Esquema de entrada para registrar un manual de procesos."""
    title: str = Field(..., min_length=3, max_length=255, description="Título del proceso o manual")
    category: str = Field(default="process_manual", description="Categoría (process_manual, policy, db_schema)")
    department: str = Field(..., min_length=2, max_length=100, description="Departamento responsable")
    content: str = Field(..., min_length=10, description="Texto completo del manual o procedimiento")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos adicionales")


class IngestKnowledgeResponse(BaseModel):
    """Esquema de salida tras la ingesta exitosa."""
    document_id: str
    title: str
    category: str
    department: str
    chunks_created: int
    status: str


class SearchKnowledgeRequest(BaseModel):
    """Esquema para búsqueda semántica directa en pgvector."""
    query: str = Field(..., min_length=2, description="Texto de búsqueda en lenguaje natural")
    top_k: int = Field(default=4, ge=1, le=20, description="Número de resultados a recuperar")
    category: Optional[str] = Field(default=None, description="Filtro opcional por categoría")


class ChunkResultItem(BaseModel):
    """Elemento individual de resultado de búsqueda vectorial."""
    id: str
    document_id: str
    chunk_index: int
    chunk_text: str
    similarity_score: float
    metadata: Dict[str, Any]


class SearchKnowledgeResponse(BaseModel):
    """Respuesta con los fragmentos más relevantes."""
    query: str
    total_results: int
    results: List[ChunkResultItem]


class SchemaSyncRequest(BaseModel):
    """Solicitud opcional para sincronizar tablas específicas de MariaDB."""
    tables: Optional[List[str]] = Field(default=None, description="Lista opcional de tablas o None para todas")


class SchemaSyncResponse(BaseModel):
    """Respuesta tras sincronizar el diccionario de datos de MariaDB hacia pgvector."""
    status: str
    database: str
    tables_indexed: int
    tables: List[str]
