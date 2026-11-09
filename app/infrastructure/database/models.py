"""Modelos ORM de SQLAlchemy para PostgreSQL con soporte nativo de pgvector."""

import uuid
from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class KnowledgeDocumentModel(Base):
    """Modelo relacional para documentos de procesos de la empresa."""
    __tablename__ = "knowledge_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False, index=True)  # process_manual, policy, db_schema
    department = Column(String(100), nullable=False, index=True)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    chunks = relationship("KnowledgeVectorChunkModel", back_populates="document", cascade="all, delete-orphan")


class KnowledgeVectorChunkModel(Base):
    """Modelo para fragmentos vectorizados de conocimiento e índice HNSW."""
    __tablename__ = "knowledge_vector_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("KnowledgeDocumentModel", back_populates="chunks")

    __table_args__ = (
        Index(
            "idx_vector_chunks_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"}
        ),
    )


class ChatSessionModel(Base):
    """Modelo para sesiones conversacionales."""
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="Nueva conversación")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages = relationship("ChatMessageModel", back_populates="session", cascade="all, delete-orphan")


class ChatMessageModel(Base):
    """Modelo para mensajes de chat."""
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)  # process_qa, data_query, general_chat
    generated_sql = Column(Text, nullable=True)
    dataset_id = Column(String(64), nullable=True, index=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("ChatSessionModel", back_populates="messages")


class QueryDatasetModel(Base):
    """Modelo de almacenamiento temporal de resultados tabulares para exportación a Excel."""
    __tablename__ = "query_datasets"

    dataset_id = Column(String(64), primary_key=True)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    sql_executed = Column(Text, nullable=False)
    columns = Column(JSONB, nullable=False)
    rows = Column(JSONB, nullable=False)
    row_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class DatabaseConnectionModel(Base):
    """Modelo para gestionar conexiones dinámicas a múltiples bases de datos (PostgreSQL / MariaDB / MySQL)."""
    __tablename__ = "database_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    engine = Column(String(30), nullable=False, default="mariadb")  # mariadb, mysql, postgresql
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=3306)
    database_name = Column(String(120), nullable=False)
    username = Column(String(120), nullable=False)
    password = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    synced_tables = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
