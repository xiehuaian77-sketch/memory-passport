-- 009_add_memory_evaluation.sql
-- Evaluation Foundation: datasets, cases, runs, and results (Phase 5.6A)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Evaluation Datasets
CREATE TABLE evaluation_datasets (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(36) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_eval_dataset_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_eval_datasets_user_created ON evaluation_datasets (user_id, created_at DESC);

-- 2. Evaluation Cases
CREATE TABLE evaluation_cases (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    query TEXT NOT NULL,
    expected_memory_ids_json TEXT NOT NULL DEFAULT '[]',
    expected_relevance_json TEXT NOT NULL DEFAULT '{}',
    tags VARCHAR(200) NOT NULL DEFAULT '',
    temporal_anchor TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_eval_case_dataset FOREIGN KEY (dataset_id) REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
    CONSTRAINT fk_eval_case_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_eval_cases_dataset_user ON evaluation_cases (dataset_id, user_id);

-- 3. Evaluation Runs
CREATE TABLE evaluation_runs (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    name VARCHAR(100) NOT NULL,
    app_version VARCHAR(50) NOT NULL DEFAULT '1.9.0',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retrieval_config_json TEXT NOT NULL DEFAULT '{}',
    summary_metrics_json TEXT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    CONSTRAINT fk_eval_run_dataset FOREIGN KEY (dataset_id) REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
    CONSTRAINT fk_eval_run_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_eval_run_status CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

CREATE INDEX idx_eval_runs_user_dataset ON evaluation_runs (user_id, dataset_id, created_at DESC);

-- 4. Evaluation Results
CREATE TABLE evaluation_results (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id VARCHAR(36) NOT NULL,
    case_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    retrieved_memory_ids_json TEXT NOT NULL DEFAULT '[]',
    scores_json TEXT NOT NULL DEFAULT '[]',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    latency_ms FLOAT NOT NULL DEFAULT 0.0,
    context_chars INTEGER NOT NULL DEFAULT 0,
    passed BOOLEAN NOT NULL DEFAULT TRUE,
    details_json TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_eval_result_run FOREIGN KEY (run_id) REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_eval_result_case FOREIGN KEY (case_id) REFERENCES evaluation_cases(id) ON DELETE CASCADE,
    CONSTRAINT fk_eval_result_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_eval_results_run_user ON evaluation_results (run_id, user_id);
CREATE INDEX idx_eval_results_case_user ON evaluation_results (case_id, user_id);
