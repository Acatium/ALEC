-- ALEC Database Initialization Script
-- This script is automatically executed when the postgres container is first created
-- It creates the simplified schema for the bullet learning system

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Create the main playbook_bullets table
CREATE TABLE IF NOT EXISTS playbook_bullets (
    bullet_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    domain VARCHAR(100) NOT NULL,  -- includes 'GENERAL' for fallback bullets
    category VARCHAR(50) NOT NULL CHECK (category IN ('cheat_sheets', 'constraints', 'examples', 'meta_prompts', 'solutions')),

    -- Effectiveness tracking counters
    helpful_count INTEGER DEFAULT 0,
    harmful_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0,

    -- Auto-calculated effectiveness score (includes neutral to match Thompson Sampling)
    effectiveness_score FLOAT GENERATED ALWAYS AS (
        CASE
            WHEN (helpful_count + harmful_count + neutral_count) = 0 THEN 0.5
            ELSE helpful_count::float / (helpful_count + harmful_count + neutral_count)
        END
    ) STORED,

    -- Metadata
    tags TEXT[] DEFAULT '{}',
    source VARCHAR(50) DEFAULT 'llm-generated' CHECK (source IN ('llm-generated', 'session-extracted', 'human-curated')),
    embedding vector(384),  -- For semantic search with all-MiniLM-L6-v2 embeddings

    -- Problem-Solution Structure
    problem_description TEXT,  -- Extracted problem/task from the interaction
    solution_description TEXT,  -- The approach/solution that worked
    problem_embedding vector(384),  -- sentence-transformers embeddings for problem-based retrieval

    -- Lifecycle status (v3)
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('unvalidated', 'candidate', 'active', 'proven', 'archived', 'banned')),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_domain_category ON playbook_bullets(domain, category);
CREATE INDEX IF NOT EXISTS idx_effectiveness ON playbook_bullets(effectiveness_score DESC NULLS LAST, usage_count DESC);
CREATE INDEX IF NOT EXISTS idx_domain_effectiveness ON playbook_bullets(domain, effectiveness_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_last_used ON playbook_bullets(last_used_at DESC);

-- Vector similarity indexes (created after embeddings are populated)
-- Note: embedding uses all-MiniLM-L6-v2 (384 dims), problem_embedding uses OpenAI ada-002 (1536 dims)
-- CREATE INDEX idx_embedding ON playbook_bullets USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- CREATE INDEX idx_problem_embedding ON playbook_bullets USING ivfflat (problem_embedding vector_cosine_ops) WITH (lists = 100);

-- Seed GENERAL domain bullets for cold-start
-- These provide fallback context when domain-specific bullets don't exist

-- Cheat Sheets (quick reference knowledge)
INSERT INTO playbook_bullets (content, domain, category, tags, source) VALUES
('Use print() or console.log() statements to debug variable values at key points', 'GENERAL', 'cheat_sheets', ARRAY['debugging', 'basics'], 'human-curated'),
('Check for None/null/undefined values before accessing object properties', 'GENERAL', 'cheat_sheets', ARRAY['safety', 'null-check'], 'human-curated'),
('Binary search has O(log n) complexity and requires sorted data', 'GENERAL', 'cheat_sheets', ARRAY['algorithms', 'performance'], 'human-curated'),
('Use version control (git) to track changes and enable rollback', 'GENERAL', 'cheat_sheets', ARRAY['git', 'best-practices'], 'human-curated'),
('Test edge cases: empty input, single element, maximum values, negative numbers', 'GENERAL', 'cheat_sheets', ARRAY['testing', 'edge-cases'], 'human-curated');

-- Constraints (rules and guardrails)
INSERT INTO playbook_bullets (content, domain, category, tags, source) VALUES
('Never modify production data without a backup', 'GENERAL', 'constraints', ARRAY['safety', 'production'], 'human-curated'),
('Always validate and sanitize user input before processing', 'GENERAL', 'constraints', ARRAY['security', 'validation'], 'human-curated'),
('Do not store passwords in plain text - use proper hashing', 'GENERAL', 'constraints', ARRAY['security', 'passwords'], 'human-curated'),
('Avoid premature optimization - profile first, optimize later', 'GENERAL', 'constraints', ARRAY['performance', 'best-practices'], 'human-curated'),
('Never expose sensitive data in error messages or logs', 'GENERAL', 'constraints', ARRAY['security', 'logging'], 'human-curated');

-- Examples (concrete demonstrations)
INSERT INTO playbook_bullets (content, domain, category, tags, source) VALUES
('When user says "it doesn''t work", ask for specific error messages and steps to reproduce', 'GENERAL', 'examples', ARRAY['communication', 'debugging'], 'human-curated'),
('If getting "undefined is not a function", check: 1) typos, 2) import statements, 3) async/await usage', 'GENERAL', 'examples', ARRAY['debugging', 'javascript'], 'human-curated'),
('For "connection refused" errors, verify: 1) service is running, 2) correct port, 3) firewall rules', 'GENERAL', 'examples', ARRAY['networking', 'debugging'], 'human-curated'),
('When optimizing database queries, add indexes on columns used in WHERE and JOIN clauses', 'GENERAL', 'examples', ARRAY['database', 'performance'], 'human-curated'),
('To fix "permission denied", check file ownership and use chmod/chown appropriately', 'GENERAL', 'examples', ARRAY['filesystem', 'linux'], 'human-curated');

-- Meta Prompts (reasoning guidance)
INSERT INTO playbook_bullets (content, domain, category, tags, source) VALUES
('Break complex problems into smaller, independently testable parts', 'GENERAL', 'meta_prompts', ARRAY['problem-solving', 'methodology'], 'human-curated'),
('When stuck, explain the problem to someone else (rubber duck debugging)', 'GENERAL', 'meta_prompts', ARRAY['debugging', 'methodology'], 'human-curated'),
('Read error messages carefully - they often contain the exact solution', 'GENERAL', 'meta_prompts', ARRAY['debugging', 'attention'], 'human-curated'),
('Consider both the immediate fix and the long-term maintainable solution', 'GENERAL', 'meta_prompts', ARRAY['architecture', 'planning'], 'human-curated'),
('Ask clarifying questions before making assumptions about requirements', 'GENERAL', 'meta_prompts', ARRAY['communication', 'requirements'], 'human-curated');

-- Add some Python-specific bullets since tests use Python debugging domain
INSERT INTO playbook_bullets (content, domain, category, tags, source) VALUES
('Use asyncio.gather() to run multiple async operations concurrently', 'python-debugging', 'cheat_sheets', ARRAY['async', 'concurrency'], 'human-curated'),
('Common async error: "RuntimeError: This event loop is already running" - use nest_asyncio or run in separate thread', 'python-debugging', 'examples', ARRAY['async', 'errors'], 'human-curated'),
('Debug async code with asyncio.create_task() and asyncio.current_task() to track task execution', 'python-debugging', 'cheat_sheets', ARRAY['async', 'debugging'], 'human-curated'),
('Use try/except with asyncio.TimeoutError for handling async timeouts', 'python-debugging', 'examples', ARRAY['async', 'error-handling'], 'human-curated'),
('Always await async functions - forgetting await causes coroutine objects instead of results', 'python-debugging', 'constraints', ARRAY['async', 'common-mistakes'], 'human-curated');

-- Log the initialization
DO $$
BEGIN
    RAISE NOTICE 'ALEC database initialized successfully with % bullets',
        (SELECT COUNT(*) FROM playbook_bullets);
END $$;