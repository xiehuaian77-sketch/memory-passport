-- Phase 2.3E Migration: Add HNSW index for pgvector cosine distance on memories.embedding
CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw
ON memories
USING hnsw (embedding vector_cosine_ops);
