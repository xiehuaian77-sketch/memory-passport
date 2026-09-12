-- Phase 5.0 Migration: Add temporal memory & supersession columns
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by_memory_id VARCHAR(36) REFERENCES memories(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_memories_valid_time ON memories(user_id, valid_from, valid_until);
CREATE INDEX IF NOT EXISTS ix_memories_superseded_by ON memories(superseded_by_memory_id);
