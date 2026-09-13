-- 008_add_memory_relationships.sql
-- Adds the memory_relationships table for Phase 5.2

CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- ensure uuid_generate_v4 is available

CREATE TABLE memory_relationships (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(36) NOT NULL,
    source_memory_id VARCHAR(36) NOT NULL,
    target_memory_id VARCHAR(36) NOT NULL,
    relationship_type VARCHAR(20) NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_source_memory FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE RESTRICT,
    CONSTRAINT fk_target_memory FOREIGN KEY (target_memory_id) REFERENCES memories(id) ON DELETE RESTRICT,
    CONSTRAINT chk_no_self CHECK (source_memory_id <> target_memory_id),
    CONSTRAINT uq_user_source_target_type UNIQUE (user_id, source_memory_id, target_memory_id, relationship_type),
    CONSTRAINT chk_relationship_type CHECK (
        relationship_type IN ('UPDATES','SUPERSEDES','CONTRADICTS','RELEVANT_TO')
    )
);

-- Trigger to update the updated_at column on row modification
CREATE OR REPLACE FUNCTION update_memory_relationship_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_memory_relationship_timestamp
BEFORE UPDATE ON memory_relationships
FOR EACH ROW EXECUTE FUNCTION update_memory_relationship_timestamp();

-- Indexes for efficient queries
CREATE INDEX idx_memory_relationships_user_source ON memory_relationships (user_id, source_memory_id);
CREATE INDEX idx_memory_relationships_user_target ON memory_relationships (user_id, target_memory_id);
