-- ==============================================================================
-- Migración 004: Candidatos de Conocimiento Implícito y Auditoría Inmutable
-- Base de Datos: PostgreSQL 17 con extensión pgvector
-- ==============================================================================

-- 1. Agregar columnas a knowledge_vector_chunks con DEFAULT temporal para backfill
ALTER TABLE knowledge_vector_chunks
    ADD COLUMN IF NOT EXISTS connection_id UUID NULL,
    ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'verified',
    ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'global',
    ADD COLUMN IF NOT EXISTS user_id VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS target_entity VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS target_column VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS prescriptive_condition VARCHAR(250) NULL,
    ADD COLUMN IF NOT EXISTS trigger_signal VARCHAR(50) NOT NULL DEFAULT 'manual_teach',
    ADD COLUMN IF NOT EXISTS source_session_id UUID NULL,
    ADD COLUMN IF NOT EXISTS source_message_id UUID NULL,
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS parent_rule_id UUID NULL,
    ADD COLUMN IF NOT EXISTS conflict_with_id UUID NULL,
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP WITH TIME ZONE NULL,
    ADD COLUMN IF NOT EXISTS proposed_global_at TIMESTAMP WITH TIME ZONE NULL,
    ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(50) NOT NULL DEFAULT 'nomic-embed-text';

-- 2. Backfill explícito de filas preexistentes
-- Sincronizar connection_id desde metadata si existe
UPDATE knowledge_vector_chunks 
SET connection_id = CASE 
    WHEN metadata->>'connection_id' IS NOT NULL AND metadata->>'connection_id' ~ '^[0-9a-fA-F-]{36}$'
    THEN (metadata->>'connection_id')::uuid 
    ELSE NULL 
END
WHERE connection_id IS NULL;

UPDATE knowledge_vector_chunks 
SET status = 'verified', scope = 'global', trigger_signal = 'manual_teach'
WHERE status IS NULL OR status = '';

-- 3. Remover DEFAULTS temporales
ALTER TABLE knowledge_vector_chunks 
    ALTER COLUMN status DROP DEFAULT,
    ALTER COLUMN scope DROP DEFAULT,
    ALTER COLUMN trigger_signal DROP DEFAULT;

-- 4. Constraints CHECK obligatorios
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_kvc_status') THEN
        ALTER TABLE knowledge_vector_chunks
            ADD CONSTRAINT chk_kvc_status CHECK (status IN ('candidate', 'verified', 'conflict', 'rejected', 'rolled_back'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_kvc_scope') THEN
        ALTER TABLE knowledge_vector_chunks
            ADD CONSTRAINT chk_kvc_scope CHECK (scope IN ('user', 'global'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_kvc_user_scope') THEN
        ALTER TABLE knowledge_vector_chunks
            ADD CONSTRAINT chk_kvc_user_scope CHECK (
                (scope = 'global') OR 
                (scope = 'user' AND user_id IS NOT NULL AND user_id <> '')
            );
    END IF;
END $$;

-- 5. Índice único condicional para evitar duplicación ante reintentos
CREATE UNIQUE INDEX IF NOT EXISTS uq_kvc_source_message_signal 
    ON knowledge_vector_chunks(source_message_id, trigger_signal)
    WHERE source_message_id IS NOT NULL;

-- 6. Índices para búsqueda determinista de conflictos y recuperación aislada
CREATE INDEX IF NOT EXISTS idx_kvc_conflict_lookup 
    ON knowledge_vector_chunks(connection_id, target_entity, target_column)
    WHERE status IN ('candidate', 'verified');

CREATE INDEX IF NOT EXISTS idx_kvc_status_scope_user 
    ON knowledge_vector_chunks(connection_id, status, scope, user_id);

-- 7. Asegurar columna metadata en chat_messages para persistir rules_applied
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 8. Tabla Inmutable de Auditoría (desacoplada de FK a chat_sessions para permitir borrado limpio)
CREATE TABLE IF NOT EXISTS knowledge_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL,               -- UUID plano (desacoplado de RESTRICT)
    action VARCHAR(50) NOT NULL,         -- 'detected_candidate', 'confirmed_user', 'proposed_global', 'promoted_global', 'rejected', 'rolled_back', 'conflict_flagged'
    actor_id VARCHAR(100) NOT NULL,      -- 'user_X' o 'SYSTEM_BACKGROUND_WORKER'
    actor_role VARCHAR(50) NOT NULL,     -- 'admin', 'user', 'system'
    source_session_id UUID NULL,         -- UUID plano (sin FK a chat_sessions para no disparar trigger al borrar sesión)
    previous_state JSONB NULL,
    new_state JSONB NOT NULL,
    reason TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kvc_audit_rule ON knowledge_audit_logs(rule_id);
CREATE INDEX IF NOT EXISTS idx_kvc_audit_actor ON knowledge_audit_logs(actor_id);

-- 9. Trigger PostgreSQL anti-mutación de auditoría (prohíbe UPDATE y DELETE)
CREATE OR REPLACE FUNCTION trg_prevent_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'knowledge_audit_logs es inmutable: no se permiten operaciones de UPDATE ni DELETE.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON knowledge_audit_logs;
CREATE TRIGGER trg_audit_logs_immutable
BEFORE UPDATE OR DELETE ON knowledge_audit_logs
FOR EACH ROW
EXECUTE FUNCTION trg_prevent_audit_log_mutation();

-- 10. Vista administrativa simple de estadísticas
CREATE OR REPLACE VIEW v_knowledge_candidates_stats AS
SELECT 
    connection_id,
    status,
    scope,
    trigger_signal,
    COUNT(*) as total_rules,
    COUNT(CASE WHEN proposed_global_at IS NOT NULL AND status = 'candidate' THEN 1 END) as pending_proposals,
    MIN(created_at) as oldest_rule,
    MAX(created_at) as newest_rule
FROM knowledge_vector_chunks
GROUP BY connection_id, status, scope, trigger_signal;
