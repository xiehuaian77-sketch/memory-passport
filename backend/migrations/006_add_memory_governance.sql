-- Phase 3.2 Migration: Add memory governance & audit tables
CREATE TABLE IF NOT EXISTS memory_audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    memory_id VARCHAR(36) REFERENCES memories(id) ON DELETE SET NULL,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actor_type VARCHAR(20) NOT NULL, -- 'user' | 'ai' | 'system'
    actor_id VARCHAR(36) NOT NULL,
    action VARCHAR(50) NOT NULL,     -- 'CREATE', 'UPDATE', 'ARCHIVE', 'RESTORE', 'DELETE', 'CONFIRM', 'EXTRACT_CANDIDATE', 'CONFLICT_DETECTED'
    from_version INTEGER,
    to_version INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_memory_audit_logs_user_id ON memory_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_memory_audit_logs_memory_id ON memory_audit_logs(memory_id);
CREATE INDEX IF NOT EXISTS ix_memory_audit_logs_created_at ON memory_audit_logs(created_at);

CREATE TABLE IF NOT EXISTS user_memory_policies (
    user_id VARCHAR(36) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    memory_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    require_confirmation BOOLEAN NOT NULL DEFAULT TRUE,
    allow_memory_retrieval BOOLEAN NOT NULL DEFAULT TRUE,
    allow_ai_extraction BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
