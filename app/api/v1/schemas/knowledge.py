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


class TrainKnowledgeRequest(BaseModel):
    """Solicitud estructurada para enseñar una regla, relación, fórmula o SQL de ejemplo a la IA."""
    category: str = Field(
        default="business_rule",
        description="Categoría: custom_relation, business_rule, kpi_formula, sql_example"
    )
    title: str = Field(..., min_length=3, max_length=255, description="Título descriptivo de la enseñanza")
    content: str = Field(..., min_length=5, description="Regla, relación, fórmula o consulta SQL de ejemplo")
    connection_id: Optional[str] = Field(default=None, description="ID de conexión asociada (opcional)")
    source_table: Optional[str] = Field(default=None, description="Tabla origen si es custom_relation")
    source_column: Optional[str] = Field(default=None, description="Columna llave foránea si es custom_relation")
    target_table: Optional[str] = Field(default=None, description="Tabla maestra destino si es custom_relation")
    target_column: Optional[str] = Field(default="id", description="Columna llave primaria destino")
    label_column: Optional[str] = Field(default=None, description="Columna con el nombre legible en la tabla maestra")
    sql_query: Optional[str] = Field(default=None, description="Consulta SELECT verificada cuando category=sql_example")


class KnowledgeCandidateItem(BaseModel):
    """Representación serializada de un candidato de conocimiento."""
    id: str
    title: str
    content: str
    knowledge_type: str
    status: str
    scope: str
    user_id: Optional[str] = None
    target_entity: Optional[str] = None
    target_column: Optional[str] = None
    prescriptive_condition: Optional[str] = None
    trigger_signal: str
    version: int
    confirmed_at: Optional[str] = None
    proposed_global_at: Optional[str] = None
    conflict_with_id: Optional[str] = None
    created_at: str


class KnowledgeCandidatesResponse(BaseModel):
    """Lista de candidatos de conocimiento y propuestas pendientes."""
    total: int
    candidates: List[KnowledgeCandidateItem]


class PromoteCandidateRequest(BaseModel):
    """Solicitud de un administrador para promover una regla a alcance global."""
    edited_content: Optional[str] = Field(default=None, description="Contenido corregido o refinado opcional")
    reason: Optional[str] = Field(default=None, description="Motivo o justificación de la promoción")


class RejectCandidateRequest(BaseModel):
    """Solicitud para descartar un candidato."""
    reason: Optional[str] = Field(default=None, description="Motivo por el cual se descarta")


class RollbackCandidateRequest(BaseModel):
    """Solicitud para revertir o desactivar una regla."""
    reason: Optional[str] = Field(default=None, description="Justificación de la reversión")


class UnresolvedQueryTermItem(BaseModel):
    """Elemento individual de la cola de términos no entendidos."""
    id: str
    connection_id: Optional[str] = None
    session_id: str
    user_id: str
    prompt: str
    extracted_term: str
    failure_reason: str
    candidate_tables: List[Dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None
    status: str
    resolved_target: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str


class UnresolvedTermsResponse(BaseModel):
    """Respuesta paginada de términos no entendidos."""
    total: int
    items: List[UnresolvedQueryTermItem]


class ResolveUnresolvedTermRequest(BaseModel):
    """Solicitud para marcar un término como resuelto o descartado."""
    resolved_target: str = Field(..., description="Tabla o sinónimo de destino resuelto (ej. inventario_partes)")
    status: str = Field(default="resolved", description="Estado final: resolved o ignored")

