-- ==============================================================================
-- Migración 005: Tabla para Adjuntos de Archivos en Chat (Fase 1 Tabular)
-- Base de Datos: PostgreSQL 17
-- ==============================================================================

CREATE TABLE IF NOT EXISTS chat_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    storage_path TEXT NOT NULL,
    schema_preview JSONB NOT NULL DEFAULT '{}'::jsonb,
    row_count INTEGER NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ready',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_session_user 
    ON chat_attachments(session_id, user_id);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_created 
    ON chat_attachments(created_at);
