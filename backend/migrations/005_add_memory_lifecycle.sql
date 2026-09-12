-- Phase 3.1 Migration: Add memory lifecycle columns (status, version, provenance)
ALTER TABLE memories ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_conversation_id VARCHAR(36) REFERENCES conversations(id) ON DELETE SET NULL;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_message_id VARCHAR(36) REFERENCES conversation_messages(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_memories_user_status ON memories(user_id, status);
CREATE INDEX IF NOT EXISTS ix_memories_source_conversation ON memories(source_conversation_id);
