-- Migración 006: Creación de la tabla unresolved_query_terms para cola de términos no entendidos y ambigüedades

CREATE TABLE IF NOT EXISTS unresolved_query_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id UUID NULL REFERENCES database_connections(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    prompt TEXT NOT NULL,
    extracted_term VARCHAR(150) NOT NULL,
    failure_reason VARCHAR(50) NOT NULL DEFAULT 'ambiguous_candidates',
    candidate_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolved_target VARCHAR(150) NULL,
    resolved_by VARCHAR(100) NULL,
    resolved_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT chk_unresolved_failure_reason CHECK (
        failure_reason IN ('sql_repair_exhausted', 'low_retrieval_confidence', 'ambiguous_candidates')
    ),
    CONSTRAINT chk_unresolved_status CHECK (
        status IN ('pending', 'resolved', 'ignored')
    )
);

CREATE INDEX IF NOT EXISTS idx_uqt_conn_status ON unresolved_query_terms(connection_id, status);
CREATE INDEX IF NOT EXISTS idx_uqt_session_id ON unresolved_query_terms(session_id);
CREATE INDEX IF NOT EXISTS idx_uqt_user_id ON unresolved_query_terms(user_id);
CREATE INDEX IF NOT EXISTS idx_uqt_created_at ON unresolved_query_terms(created_at DESC);
