"""Entidades del Dominio puro, libres de dependencias de frameworks externos."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class DocumentChunk:
    """Representa un fragmento de texto con su representación vectorial."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = ""
    chunk_index: int = 0
    chunk_text: str = ""
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    similarity_score: Optional[float] = None


@dataclass
class ChatMessage:
    """Representa un mensaje en una sesión de chat."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = "user"  # user, assistant, system
    content: str = ""
    intent: Optional[str] = None  # process_qa, data_query, general_chat
    generated_sql: Optional[str] = None
    dataset_id: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ChatSession:
    """Representa una sesión de conversación multi-turno."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default_user"
    title: str = "Nueva conversación"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: List[ChatMessage] = field(default_factory=list)


@dataclass
class QueryDataset:
    """Caché temporal de resultados de una consulta SQL para exportación a Excel."""
    dataset_id: str = field(default_factory=lambda: f"ds_{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    sql_executed: str = ""
    columns: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
