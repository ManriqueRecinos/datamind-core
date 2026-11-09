"""Esquemas Pydantic V2 para la interacción conversacional del chat."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Solicitud de chat enviada desde Laravel."""
    prompt: str = Field(..., min_length=1, description="Pregunta del usuario en lenguaje natural")
    session_id: Optional[str] = Field(default=None, description="UUID de sesión existente o None para nueva")
    user_id: Optional[str] = Field(default="laravel_user", description="Identificador del usuario en Laravel")
    connection_id: Optional[str] = Field(default=None, description="UUID de la conexión de BD seleccionada")


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
    latency_ms: int = 0


class StreamTokenEvent(BaseModel):
    """Evento SSE de token parcial."""
    text: str


class StreamDatasetEvent(BaseModel):
    """Evento SSE que informa la presencia de dataset para habilitar el botón de Excel."""
    dataset_id: str
    row_count: int
    columns: List[str]
    preview_rows: Optional[List[Dict[str, Any]]] = None
