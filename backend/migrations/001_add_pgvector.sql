-- Phase 2.3A Migration: Enable pgvector extension and add 1024-dim embedding
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(1024);
