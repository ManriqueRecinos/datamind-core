"""Esquemas Pydantic V2 para la interacción conversacional del chat."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Solicitud de chat enviada desde Laravel."""
    prompt: str = Field(..., min_length=1, description="Pregunta del usuario en lenguaje natural")
    session_id: Optional[str] = Field(default=None, description="UUID de sesión existente o None para nueva")
    user_id: Optional[str] = Field(default="laravel_user", description="Identificador del usuario en Laravel")
    user_role: Optional[str] = Field(default="user", description="Rol maestro del usuario (ej: super-admin, data-analyst)")
    user_permissions: Optional[List[str]] = Field(default_factory=list, description="Lista de slugs de permisos autorizados")
    connection_id: Optional[str] = Field(default=None, description="UUID de la conexión de BD seleccionada")
    retry_message_id: Optional[str] = Field(default=None, description="UUID opcional de un mensaje de usuario previo a reintentar")
    attachment_ids: Optional[List[str]] = Field(default_factory=list, description="UUIDs de archivos adjuntos cargados en la sesión")


class ChatResponse(BaseModel):
    """Respuesta síncrona del chat con referencias a datos estructurados."""
    session_id: str
    message: str
    intent: str  # process_qa, data_query, general_chat
    has_tabular_data: bool = False
    dataset_id: Optional[str] = None
    row_count: Optional[int] = None
    generated_sql: Optional[str] = None
    columns: Optional[List[str]] = None
    preview_rows: Optional[List[Dict[str, Any]]] = None
    chart_config: Optional[Dict[str, Any]] = None
    latency_ms: int = 0


class ChatSessionSummarySchema(BaseModel):
    """Resumen de una sesión de chat para el panel de historial del usuario."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatMessageHistoryItemSchema(BaseModel):
    """Mensaje individual dentro del historial de una conversación."""
    id: str
    role: str
    content: str
    intent: Optional[str] = None
    generated_sql: Optional[str] = None
    dataset_id: Optional[str] = None
    has_tabular_data: bool = False
    row_count: Optional[int] = None
    columns: Optional[List[str]] = None
    preview_rows: Optional[List[Dict[str, Any]]] = None
    chart_config: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    rules_applied: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    created_at: str


class ChatSessionDetailSchema(BaseModel):
    """Detalle completo de una sesión con su lista de mensajes."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageHistoryItemSchema] = Field(default_factory=list)


class StreamTokenEvent(BaseModel):
    """Evento SSE de token parcial."""
    text: str


class StreamDatasetEvent(BaseModel):
    """Evento SSE que informa la presencia de dataset para habilitar el botón de Excel."""
    dataset_id: str
    row_count: int
    columns: List[str]
    preview_rows: Optional[List[Dict[str, Any]]] = None
