-- ALEC v5 Schema
-- PostgreSQL 17 + pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- ENGAGEMENT
-- ============================================================

CREATE TABLE engagements (
    engagement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT DEFAULT 'setup',
        -- 'setup', 'active', 'paused', 'converged', 'archived'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    config JSONB DEFAULT '{}',
        -- convergence_thresholds, budget_limits, cycle_interval
    last_heartbeat TIMESTAMPTZ
);

-- Migration for existing deployments:
-- ALTER TABLE engagements ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;
-- ALTER TABLE engagements ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
-- UPDATE engagements SET summary = problem_statement WHERE summary = '';

-- ============================================================
-- MODELS & ALIGNMENT
-- ============================================================

CREATE TABLE models (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    model_type TEXT NOT NULL,
        -- 'discovered', 'proposed', 'synthesized'
    purpose TEXT,
    perspective TEXT,
    expected_divergences TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TIER 1: RAW OBSERVATIONS (append-only)
-- ============================================================

CREATE TABLE observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    session_id UUID,
    worker_id TEXT,
    source_ref TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    observation_type TEXT NOT NULL,
        -- 'entity', 'relationship', 'insight', 'contradiction',
        -- 'gap', 'decision', 'alignment'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- ============================================================
-- TIER 2: STRUCTURED INDEX
-- ============================================================

CREATE TABLE entities (
    entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    model_id UUID REFERENCES models(model_id),
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
        -- 'service', 'database', 'team', 'api', 'policy',
        -- 'person', 'document', 'capability', 'domain',
        -- 'repository', 'schema', 'process'
    aliases TEXT[] DEFAULT '{}',
    embedding vector(384),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_referenced TIMESTAMPTZ DEFAULT NOW(),
    observation_count INT DEFAULT 0,
    status TEXT DEFAULT 'active',
        -- 'active', 'merged', 'deprecated'
    properties JSONB DEFAULT '{}'
);

CREATE TABLE relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    from_entity UUID NOT NULL REFERENCES entities(entity_id),
    to_entity UUID NOT NULL REFERENCES entities(entity_id),
    relationship_type TEXT NOT NULL,
        -- 'depends_on', 'owned_by', 'reads_from', 'writes_to',
        -- 'calls', 'governs', 'implements', 'contains',
        -- 'supersedes', 'related_to'
    evidence UUID[] DEFAULT '{}',
    confidence FLOAT DEFAULT 0.5,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_confirmed TIMESTAMPTZ DEFAULT NOW(),
    properties JSONB DEFAULT '{}',
    CONSTRAINT uq_relationship_triple
        UNIQUE (engagement_id, from_entity, to_entity, relationship_type)
);

CREATE TABLE alignments (
    alignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    from_entity UUID NOT NULL REFERENCES entities(entity_id),
    to_entity UUID NOT NULL REFERENCES entities(entity_id),
    alignment_type TEXT NOT NULL,
        -- 'equivalent', 'overlaps_with', 'contains',
        -- 'contained_by', 'implements', 'contradicts',
        -- 'unaligned', 'supersedes'
    confidence FLOAT DEFAULT 0.5,
    evidence UUID[] DEFAULT '{}',
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    content TEXT NOT NULL,
    embedding vector(384),
    entities_referenced UUID[] DEFAULT '{}',
    source_observations UUID[] DEFAULT '{}',
    reinforcement_count INT DEFAULT 1,
    last_retrieved TIMESTAMPTZ,
    superseded_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'active'
        -- 'active', 'consolidated', 'superseded', 'decayed'
);

-- ============================================================
-- TIER 3: CONSOLIDATED KNOWLEDGE
-- ============================================================

CREATE TABLE consolidated_units (
    unit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    subject_entity UUID REFERENCES entities(entity_id),
    related_entities UUID[] DEFAULT '{}',
    summary TEXT NOT NULL,
    embedding vector(384),
    source_items UUID[] DEFAULT '{}',
    source_observations UUID[] DEFAULT '{}',
    token_count INT NOT NULL,
    freshness TIMESTAMPTZ DEFAULT NOW(),
    retrieval_count INT DEFAULT 0,
    version INT DEFAULT 1,
    status TEXT DEFAULT 'current'
        -- 'current', 'stale', 'archived'
);

-- ============================================================
-- AGENT GOVERNANCE
-- ============================================================

CREATE TABLE agent_types (
    agent_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE prompt_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type_id UUID NOT NULL REFERENCES agent_types(agent_type_id),
    version_number INT NOT NULL,
    base_prompt TEXT NOT NULL,
    learned_sections JSONB DEFAULT '{}',
    parent_version_id UUID REFERENCES prompt_versions(version_id),
    change_summary TEXT NOT NULL,
    change_type TEXT NOT NULL,
        -- 'initial', 'manual', 'auto_applied', 'human_approved'
    change_source TEXT,
    evidence JSONB DEFAULT '{}',
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_type_id, version_number)
);

CREATE TABLE prompt_proposals (
    proposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    agent_type_id UUID NOT NULL REFERENCES agent_types(agent_type_id),
    current_version_id UUID REFERENCES prompt_versions(version_id),
    section_key TEXT NOT NULL,
    proposed_content TEXT NOT NULL,
    diff_summary TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    evidence_observations UUID[],
    confidence FLOAT NOT NULL,
    impact TEXT NOT NULL,
    auto_apply_eligible BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending',
        -- 'pending', 'approved', 'rejected', 'applied'
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    applied_version_id UUID REFERENCES prompt_versions(version_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- RUNTIME STATE
-- ============================================================

CREATE TABLE coordinator_instances (
    instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    focus_domain TEXT,
    source_filter TEXT[],
    prompt_version_id UUID REFERENCES prompt_versions(version_id),
    status TEXT DEFAULT 'active',
        -- 'active', 'converged', 'merged', 'terminated'
    cycles_completed INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    coordinator_id UUID REFERENCES coordinator_instances(instance_id),
    directive TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    max_scope TEXT DEFAULT 'survey',
        -- 'survey', 'focused', 'deep'
    relevant_context TEXT,
    status TEXT DEFAULT 'queued',
        -- 'queued', 'assigned', 'running', 'completed', 'failed'
    assigned_worker TEXT,
    result_summary JSONB,
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE convergence_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    cycle_number INT NOT NULL,
    reinforcement_count INT DEFAULT 0,
    expansion_count INT DEFAULT 0,
    challenge_count INT DEFAULT 0,
    ratio FLOAT,
    weighted_ratio FLOAT,
    expansion_rate INT,
    expansion_acceleration FLOAT,
    per_source_ratios JSONB DEFAULT '{}',
    secondary_convergence BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migration for existing deployments:
-- ALTER TABLE convergence_log ADD COLUMN IF NOT EXISTS weighted_ratio FLOAT;
-- ALTER TABLE convergence_log ADD COLUMN IF NOT EXISTS expansion_rate INT;
-- ALTER TABLE convergence_log ADD COLUMN IF NOT EXISTS expansion_acceleration FLOAT;
-- ALTER TABLE convergence_log ADD COLUMN IF NOT EXISTS per_source_ratios JSONB DEFAULT '{}';
-- ALTER TABLE convergence_log ADD COLUMN IF NOT EXISTS secondary_convergence BOOLEAN DEFAULT FALSE;

-- ============================================================
-- SOURCE CONFIGURATION
-- ============================================================

CREATE TABLE source_configs (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    source_type TEXT NOT NULL,
    config JSONB NOT NULL,
    auth_config JSONB DEFAULT '{}',
    worker_profile JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending',
        -- 'pending', 'verified', 'failed', 'disabled'
    priority INT NOT NULL DEFAULT 50,
    trust_tier TEXT NOT NULL DEFAULT 'reference',
        -- 'authoritative', 'analytical', 'reference'
    last_accessed TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DEVELOPER PIPELINE
-- ============================================================

CREATE TABLE code_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    description TEXT NOT NULL,
    description_embedding vector(384),
    language TEXT NOT NULL,
    code TEXT NOT NULL,
    source_type TEXT NOT NULL,
    generated_by TEXT,
    usage_count INT DEFAULT 1,
    success_count INT DEFAULT 1,
    failure_count INT DEFAULT 0,
    last_used TIMESTAMPTZ DEFAULT NOW(),
    validated BOOLEAN DEFAULT TRUE,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE code_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES code_assets(asset_id),
    requesting_agent TEXT NOT NULL,
    request_description TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    result_summary TEXT,
    error_message TEXT,
    execution_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Vector indexes (use ivfflat; requires data to build, so they'll be
-- created but won't be effective until enough rows exist)
CREATE INDEX idx_entities_embedding ON entities
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_knowledge_items_embedding ON knowledge_items
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_consolidated_embedding ON consolidated_units
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_code_assets_embedding ON code_assets
    USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100);

-- B-tree indexes
CREATE INDEX idx_entities_engagement ON entities(engagement_id);
CREATE INDEX idx_entities_model ON entities(model_id);
CREATE INDEX idx_relationships_engagement ON relationships(engagement_id);
CREATE INDEX idx_alignments_engagement ON alignments(engagement_id);
CREATE INDEX idx_observations_engagement ON observations(engagement_id);
CREATE INDEX idx_tasks_engagement_status ON tasks(engagement_id, status);
CREATE INDEX idx_convergence_engagement ON convergence_log(engagement_id, cycle_number);

-- ============================================================
-- USER ANNOTATIONS
-- ============================================================

CREATE TABLE user_annotations (
    annotation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    entity_id UUID NOT NULL REFERENCES entities(entity_id),
    annotation_type TEXT NOT NULL,
        -- 'correction', 'important', 'explore_more', 'note', 'dismiss'
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_annotations_entity ON user_annotations(entity_id);
CREATE INDEX idx_annotations_engagement ON user_annotations(engagement_id);

-- ============================================================
-- QUESTIONS
-- ============================================================

CREATE TABLE questions (
    question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    question_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
        -- 'open', 'answered', 'dismissed'
    answer TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    answered_at TIMESTAMPTZ
);
CREATE INDEX idx_questions_engagement ON questions(engagement_id);

-- ============================================================
-- SNAPSHOTS
-- ============================================================

CREATE TABLE snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    entity_count INT NOT NULL DEFAULT 0,
    relationship_count INT NOT NULL DEFAULT 0,
    observation_count INT NOT NULL DEFAULT 0,
    cycle_count INT NOT NULL DEFAULT 0,
    convergence_ratio FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_snapshots_engagement ON snapshots(engagement_id);

-- ============================================================
-- COMMUNITY ANALYSIS
-- ============================================================

CREATE TABLE community_analysis (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    cycle_number INT NOT NULL,
    algorithm TEXT NOT NULL,
    entity_count INT NOT NULL,
    community_count INT NOT NULL,
    modularity FLOAT,
    communities JSONB NOT NULL,
    hub_entities JSONB DEFAULT '[]',
    bridge_entities JSONB DEFAULT '[]',
    isolated_entities JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_community_analysis_engagement ON community_analysis(engagement_id, cycle_number);

-- ============================================================
-- ENGAGEMENT SCHEMA (dynamic ontology per engagement)
-- ============================================================

CREATE TABLE engagement_schema (
    schema_entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    kind TEXT NOT NULL,            -- 'entity_type' or 'relationship_type'
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    examples TEXT[] DEFAULT '{}',
    parent_category TEXT,         -- upper ontology category (for rel types)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(engagement_id, kind, name)
);
CREATE INDEX idx_engagement_schema ON engagement_schema(engagement_id, kind, is_active);

-- ============================================================
-- COLUMN ADDITIONS (for migrations, use ALTER TABLE IF NOT EXISTS)
-- ============================================================

-- Source management: priority + trust tier
-- ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 50;
-- ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS trust_tier TEXT NOT NULL DEFAULT 'reference';
-- ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;
