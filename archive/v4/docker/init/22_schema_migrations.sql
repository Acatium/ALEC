-- Schema migrations tracking table
-- Tracks which migrations have been applied to prevent drift

CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    checksum VARCHAR(64)  -- Optional: SHA256 of migration file for change detection
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_schema_migrations_name ON schema_migrations(migration_name);

-- Record migrations that were applied before this tracking existed
-- This bootstraps the table with known-applied migrations
INSERT INTO schema_migrations (migration_name, applied_at) VALUES
    ('01_init_db.sql', NOW()),
    ('02_sessions.sql', NOW()),
    ('03_playbooks.sql', NOW()),
    ('05_session_events.sql', NOW()),
    ('10_evaluation_tables.sql', NOW()),
    ('13_problem_solution_migration.sql', NOW()),
    ('14_evaluation_tracking.sql', NOW()),
    ('15_service_configs.sql', NOW()),
    ('17_experiment_container_tracking.sql', NOW()),
    ('18_problem_embedding_384.sql', NOW()),
    ('20_service_prompts.sql', NOW()),
    ('21_learning_loop.sql', NOW()),
    ('22_schema_migrations.sql', NOW()),
    ('26_session_views.sql', NOW())
ON CONFLICT (migration_name) DO NOTHING;

COMMENT ON TABLE schema_migrations IS 'Tracks applied database migrations to prevent schema drift';
