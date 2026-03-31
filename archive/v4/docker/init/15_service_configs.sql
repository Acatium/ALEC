-- ============================================================================
-- ALEC Service Configuration Table
-- ============================================================================
-- Stores all configurable parameters for the four main services:
-- SESSION, ADVISOR, GENERATOR, CLUSTERER
--
-- This enables runtime configuration changes via the admin UI without
-- requiring service restarts or code deployments.
--
-- Run order: 15 (after evaluation_tracking, before ab_testing)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Service Configurations Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS service_configs (
    config_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,  -- session, advisor, generator, clusterer
    parameter_name VARCHAR(100) NOT NULL,
    parameter_value JSONB NOT NULL,
    default_value JSONB NOT NULL,
    description TEXT,
    category VARCHAR(50),  -- timing, selection, extraction, clustering, llm, etc.
    data_type VARCHAR(20) NOT NULL DEFAULT 'number',  -- number, string, boolean, array, object
    min_value FLOAT,  -- For numeric parameters
    max_value FLOAT,  -- For numeric parameters
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(service_name, parameter_name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_service_configs_service ON service_configs(service_name);
CREATE INDEX IF NOT EXISTS idx_service_configs_category ON service_configs(category);

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_service_configs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS service_configs_updated_trigger ON service_configs;
CREATE TRIGGER service_configs_updated_trigger
    BEFORE UPDATE ON service_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_service_configs_timestamp();

-- ============================================================================
-- Service Config Changelog Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS service_config_changelog (
    changelog_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,
    parameter_name VARCHAR(100) NOT NULL,
    previous_value JSONB,
    new_value JSONB NOT NULL,
    change_description TEXT,
    changed_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_config_changelog_service ON service_config_changelog(service_name);
CREATE INDEX IF NOT EXISTS idx_service_config_changelog_created ON service_config_changelog(created_at DESC);

-- ============================================================================
-- SESSION Service Parameters (21 parameters)
-- ============================================================================

INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, description, category, data_type, min_value, max_value) VALUES
-- Timing parameters
('session', 'initial_bullets_timeout_ms', '30000', '30000', 'Time to wait for initial bullets_ready signal from ADVISOR', 'timing', 'number', 1000, 120000),
('session', 'initial_bullets_poll_interval_ms', '100', '100', 'Poll interval for initial bullets wait', 'timing', 'number', 50, 1000),
('session', 'per_turn_bullets_timeout_ms', '10000', '10000', 'Time to wait for per-turn bullets_ready signal (shorter for graceful fallback)', 'timing', 'number', 1000, 30000),
('session', 'per_turn_bullets_poll_interval_ms', '100', '100', 'Poll interval for per-turn bullets wait', 'timing', 'number', 50, 500),
('session', 'llm_http_timeout_seconds', '120.0', '120.0', 'HTTP timeout for LLM Gateway calls', 'timing', 'number', 30, 600),

-- Bullet injection
('session', 'do_bullets_max', '5', '5', 'Maximum [+] (success/progress) bullets to include in prompt', 'injection', 'number', 1, 15),
('session', 'avoid_bullets_max', '3', '3', 'Maximum [-] (failure/constraints) bullets to include (conditional on error context)', 'injection', 'number', 0, 10),

-- Context accumulation
('session', 'max_problem_context_length', '2000', '2000', 'Maximum accumulated problem context length (bounded accumulation)', 'context', 'number', 500, 10000),
('session', 'problem_context_addition_cap', '500', '500', 'Characters to add per turn to problem context', 'context', 'number', 100, 2000),
('session', 'problem_context_min_length', '50', '50', 'Minimum message length to consider for problem context accumulation', 'context', 'number', 10, 200),
('session', 'problem_context_initial_cap', '1000', '1000', 'Initial problem context cap before accumulation', 'context', 'number', 200, 5000),

-- Truncation limits
('session', 'previous_response_truncate_length', '500', '500', 'Truncate previous AI response for error detection', 'truncation', 'number', 100, 2000),
('session', 'user_input_truncate_for_event', '300', '300', 'Truncate user input for event payload', 'truncation', 'number', 100, 1000),
('session', 'user_input_truncate_for_embedding', '1000', '1000', 'Truncate user input for embedding generation', 'truncation', 'number', 200, 3000),

-- LLM settings
('session', 'llm_model', '"claude-haiku-4-5-20251001"', '"claude-haiku-4-5-20251001"', 'LLM model for session responses', 'llm', 'string', NULL, NULL),
('session', 'llm_temperature', '0.3', '0.3', 'Temperature for LLM generation (low=focused, high=creative)', 'llm', 'number', 0, 2),
('session', 'llm_max_tokens', '4096', '4096', 'Maximum output tokens per LLM call', 'llm', 'number', 256, 16384),

-- Error detection keywords (stored as JSON array)
('session', 'error_detection_keywords', '["error", "failed", "exception", "traceback", "assertionerror", "typeerror", "keyerror"]', '["error", "failed", "exception", "traceback", "assertionerror", "typeerror", "keyerror"]', 'Keywords that trigger error context detection for conditional [-] injection', 'detection', 'array', NULL, NULL)

ON CONFLICT (service_name, parameter_name) DO UPDATE SET
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    data_type = EXCLUDED.data_type,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value;

-- ============================================================================
-- ADVISOR Service Parameters (14 parameters)
-- ============================================================================

INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, description, category, data_type, min_value, max_value) VALUES
-- Thompson Sampling
('advisor', 'age_decay_rate', '0.01', '0.01', 'Age decay for Thompson Sampling (exp(-rate * days)), 1% per day', 'thompson_sampling', 'number', 0, 0.1),
('advisor', 'effectiveness_floor', '0.5', '0.5', 'Minimum effectiveness score (new bullets = 0.5, proven = up to 1.0)', 'thompson_sampling', 'number', 0, 1),

-- Hybrid retrieval
('advisor', 'hybrid_alpha', '0.7', '0.7', 'Weight for direct vector similarity in hybrid scoring', 'retrieval', 'number', 0, 1),
('advisor', 'hybrid_beta', '0.3', '0.3', 'Weight for cluster-mediated similarity in hybrid scoring', 'retrieval', 'number', 0, 1),
('advisor', 'use_hybrid_retrieval', 'true', 'true', 'Enable hybrid (vector + cluster) vs pure vector search', 'retrieval', 'boolean', NULL, NULL),
('advisor', 'similarity_threshold', '0.5', '0.5', 'Minimum cosine similarity for bullet retrieval', 'retrieval', 'number', 0, 1),

-- Selection pools
('advisor', 'exploration_slots', '1', '1', 'Reserved slots for exploration pool (unvalidated bullets)', 'selection', 'number', 0, 5),
('advisor', 'exploration_pool_size', '20', '20', 'Max candidates from exploration pool before Thompson Sampling', 'selection', 'number', 5, 100),
('advisor', 'exploitation_pool_size', '40', '40', 'Max candidates from exploitation pool before Thompson Sampling', 'selection', 'number', 10, 200),
('advisor', 'max_bullets_default', '5', '5', 'Default max bullets returned (can be overridden)', 'selection', 'number', 1, 15),
('advisor', 'max_bullets_smart_cap', '7', '7', 'Smart cap after effectiveness-weighted scoring', 'selection', 'number', 1, 15),
('advisor', 'exploration_quota', '1', '1', 'Exploration pool quota in final selection', 'selection', 'number', 0, 5),

-- Task extraction
('advisor', 'task_extraction_min_length', '10', '10', 'Minimum characters for extracted task (sanity check)', 'task_extraction', 'number', 5, 50),
('advisor', 'retrieval_context_truncate', '1000', '1000', 'Truncate retrieval context for embedding', 'task_extraction', 'number', 200, 5000)

ON CONFLICT (service_name, parameter_name) DO UPDATE SET
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    data_type = EXCLUDED.data_type,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value;

-- ============================================================================
-- GENERATOR Service Parameters (17 parameters)
-- ============================================================================

INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, description, category, data_type, min_value, max_value) VALUES
-- Attribution
('generator', 'attribution_similarity_threshold', '0.5', '0.5', 'Cosine similarity threshold for fair attribution (similarity gating)', 'attribution', 'number', 0, 1),

-- Buffering
('generator', 'buffer_wait_timeout_seconds', '5.0', '5.0', 'Max time to wait for turn buffer to populate', 'buffering', 'number', 1, 30),
('generator', 'buffer_wait_poll_interval', '0.1', '0.1', 'Poll interval for buffer wait', 'buffering', 'number', 0.05, 1),

-- Truncation
('generator', 'turn_data_truncate', '2000', '2000', 'Truncate turn user/assistant messages for buffer storage', 'truncation', 'number', 500, 10000),
('generator', 'problem_context_truncate', '2000', '2000', 'Truncate problem context in turn buffer', 'truncation', 'number', 500, 10000),
('generator', 'conversation_smart_truncate_max', '25000', '25000', 'Max characters for smart-truncated conversation (~6K tokens)', 'truncation', 'number', 5000, 100000),
('generator', 'turn_format_max_chars', '2500', '2500', 'Max characters per turn in formatted output', 'truncation', 'number', 500, 10000),

-- Error extraction
('generator', 'error_context_max_lines', '50', '50', 'Max unique error lines for error context extraction', 'error_extraction', 'number', 10, 200),
('generator', 'error_context_max_chars', '2000', '2000', 'Max characters for error context (for embedding)', 'error_extraction', 'number', 500, 10000),

-- Extraction LLM
('generator', 'extraction_llm_model', '"claude-haiku-4-5-20251001"', '"claude-haiku-4-5-20251001"', 'LLM for multi-category extraction', 'llm', 'string', NULL, NULL),
('generator', 'extraction_llm_max_tokens', '4000', '4000', 'Max tokens for extraction LLM output', 'llm', 'number', 1000, 16384),
('generator', 'extraction_llm_temperature', '0.7', '0.7', 'Temperature for extraction (higher=more creative)', 'llm', 'number', 0, 2),

-- Quality gates
('generator', 'insight_min_length', '20', '20', 'Minimum characters for insight to pass quality gate', 'quality', 'number', 10, 100),

-- Semantic deduplication
('generator', 'semantic_similarity_threshold', '0.85', '0.85', 'Content embedding similarity for dedup (increment evidence on match)', 'deduplication', 'number', 0.5, 1),
('generator', 'content_embedding_truncate', '500', '500', 'Truncate bullet content for embedding', 'deduplication', 'number', 100, 2000),
('generator', 'problem_embedding_truncate', '500', '500', 'Truncate problem context for problem embedding', 'deduplication', 'number', 100, 2000),

-- Ground truth boost
('generator', 'ground_truth_helpful_boost', '9', '9', 'Initial helpful_count for ground truth bullets (90% confidence)', 'ground_truth', 'number', 1, 20)

ON CONFLICT (service_name, parameter_name) DO UPDATE SET
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    data_type = EXCLUDED.data_type,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value;

-- ============================================================================
-- CLUSTERER Service Parameters (10 parameters)
-- ============================================================================

INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, description, category, data_type, min_value, max_value) VALUES
-- DBSCAN clustering
('clusterer', 'cluster_eps', '0.3', '0.3', 'DBSCAN epsilon (max distance between points in cluster)', 'dbscan', 'number', 0.1, 0.9),
('clusterer', 'cluster_min_samples', '5', '5', 'DBSCAN min_samples (minimum points to form cluster)', 'dbscan', 'number', 2, 20),
('clusterer', 'cluster_assignment_threshold', '0.25', '0.25', 'Max distance to assign new embedding to existing cluster', 'dbscan', 'number', 0.1, 0.5),
('clusterer', 'buffer_size_for_refit', '50', '50', 'Refit DBSCAN after this many new items in buffer', 'dbscan', 'number', 10, 200),

-- Graph construction
('clusterer', 'max_clusters_for_assignment', '3', '3', 'Max clusters to assign/search when linking bullets', 'graph', 'number', 1, 10),
('clusterer', 'min_similarity_for_assignment', '0.5', '0.5', 'Minimum similarity for cluster assignment', 'graph', 'number', 0, 1),
('clusterer', 'max_tools_extracted', '20', '20', 'Maximum tools to extract from response (prevent explosion)', 'graph', 'number', 5, 100),

-- Tool extraction filters
('clusterer', 'tool_module_min_length', '2', '2', 'Minimum characters in module name for tool extraction', 'filtering', 'number', 1, 10),
('clusterer', 'tool_method_min_length', '2', '2', 'Minimum characters in method name for tool extraction', 'filtering', 'number', 1, 10),
('clusterer', 'tool_false_positives', '["self", "print", "str", "int", "list", "dict", "len", "range", "type", "None", "True", "False"]', '["self", "print", "str", "int", "list", "dict", "len", "range", "type", "None", "True", "False"]', 'Common false positives to filter from tool extraction', 'filtering', 'array', NULL, NULL)

ON CONFLICT (service_name, parameter_name) DO UPDATE SET
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    data_type = EXCLUDED.data_type,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value;

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE service_configs IS 'Runtime-configurable parameters for SESSION, ADVISOR, GENERATOR, CLUSTERER services';
COMMENT ON COLUMN service_configs.service_name IS 'Service identifier: session, advisor, generator, clusterer';
COMMENT ON COLUMN service_configs.parameter_value IS 'Current parameter value (JSONB for flexibility)';
COMMENT ON COLUMN service_configs.default_value IS 'Default/factory value for reset operations';
COMMENT ON COLUMN service_configs.category IS 'UI grouping category';
COMMENT ON COLUMN service_configs.data_type IS 'Value type: number, string, boolean, array, object';

COMMENT ON TABLE service_config_changelog IS 'Audit trail of service configuration changes';

-- ============================================================================
-- End of Service Configurations
-- ============================================================================
