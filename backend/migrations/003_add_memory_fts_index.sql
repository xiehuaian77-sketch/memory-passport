-- Phase 2.4 Migration: Add GIN index for PostgreSQL full-text search on memories.content
CREATE INDEX IF NOT EXISTS ix_memories_content_fts
ON memories
USING gin (to_tsvector('simple', content));
