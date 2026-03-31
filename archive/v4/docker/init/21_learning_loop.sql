-- =============================================================================
-- 21_learning_loop.sql
-- Consolidated Learning Loop Schema (v3)
--
-- This file consolidates and replaces files 21-31 from the original schema.
-- It is IDEMPOTENT - safe to run multiple times.
--
-- Created: 2025-12-06
-- Sections:
--   1. Core Tables (problem_clusters, session_turns, turn_clusters)
--   2. Knowledge Graph Tables (problem_nodes, tool_nodes, concept_nodes, knowledge_edges)
--   3. Supporting Tables (turn_attribution, retrieval_parameters)
--   4. Column Additions to playbook_bullets
--   5. Functions and Triggers
--   6. Views
--   7. Indexes
-- =============================================================================

-- =============================================================================
-- SECTION 1: CORE TABLES
-- =============================================================================

-- Problem clusters: Archetypes of problem types discovered via DBSCAN
-- v3 schema with turn-level statistics
CREATE TABLE IF NOT EXISTS problem_clusters (
    cluster_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    centroid VECTOR(384) NOT NULL,

    -- v3: Cluster metadata
    label TEXT,
    description TEXT,

    -- v3: Turn-level statistics
    turn_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,

    -- v2 legacy columns (kept for compatibility, deprecated)
    member_count INTEGER DEFAULT 0,
    avg_effectiveness FLOAT DEFAULT 0.5,
    representative_problems TEXT[] DEFAULT '{}',

    -- Lifecycle
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add v3 columns if migrating from v2 schema
ALTER TABLE problem_clusters ADD COLUMN IF NOT EXISTS label TEXT;
ALTER TABLE problem_clusters ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE problem_clusters ADD COLUMN IF NOT EXISTS turn_count INT DEFAULT 0;
ALTER TABLE problem_clusters ADD COLUMN IF NOT EXISTS success_count INT DEFAULT 0;
ALTER TABLE problem_clusters ADD COLUMN IF NOT EXISTS failure_count INT DEFAULT 0;

-- Session turns: First-class learning units (v3)
CREATE TABLE IF NOT EXISTS session_turns (
    turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    turn_number INT NOT NULL,

    -- Content
    user_message TEXT,
    assistant_response TEXT,
    tool_calls JSONB,
    tool_results JSONB,

    -- Sub-task analysis (extracted by REFLECTOR)
    sub_task TEXT,
    sub_task_embedding VECTOR(384),

    -- Micro-outcome (per-turn success/failure)
    micro_outcome TEXT CHECK (micro_outcome IN ('progress', 'solved', 'stuck', 'error')),
    error_trace TEXT,

    -- Attribution (which bullets influenced THIS turn)
    bullets_shown UUID[],
    bullets_helped UUID[],
    bullets_harmed UUID[],
    bullets_irrelevant UUID[],

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(session_id, turn_number)
);

-- Turn to cluster membership (v3)
CREATE TABLE IF NOT EXISTS turn_clusters (
    turn_id UUID PRIMARY KEY REFERENCES session_turns(turn_id) ON DELETE CASCADE,
    cluster_id UUID REFERENCES problem_clusters(cluster_id) ON DELETE SET NULL,
    distance FLOAT NOT NULL
);

-- =============================================================================
-- SECTION 2: KNOWLEDGE GRAPH TABLES
-- =============================================================================

-- Problem nodes (standalone problems for graph traversal)
CREATE TABLE IF NOT EXISTS problem_nodes (
    problem_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    domain VARCHAR(100) NOT NULL DEFAULT 'general',
    source_session_id UUID,
    source_task_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tool nodes (APIs, functions, libraries extracted from code)
CREATE TABLE IF NOT EXISTS tool_nodes (
    tool_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL UNIQUE,
    module VARCHAR(100),
    method VARCHAR(100),
    description TEXT,
    embedding VECTOR(384),
    usage_count INTEGER DEFAULT 0,
    helpful_count INTEGER DEFAULT 0,
    harmful_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Concept nodes (domain taxonomy) - for future use
CREATE TABLE IF NOT EXISTS concept_nodes (
    concept_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    parent_concept_id UUID REFERENCES concept_nodes(concept_id),
    embedding VECTOR(384),
    domain VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, domain)
);

-- Knowledge edges: Central edge table for knowledge graph
CREATE TABLE IF NOT EXISTS knowledge_edges (
    edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source node (polymorphic reference)
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN (
        'problem', 'solution', 'tool', 'concept', 'cluster'
    )),
    source_id UUID NOT NULL,

    -- Target node (polymorphic reference)
    target_type VARCHAR(20) NOT NULL CHECK (target_type IN (
        'problem', 'solution', 'tool', 'concept', 'cluster'
    )),
    target_id UUID NOT NULL,

    -- Relationship type (v3: includes caused_failure)
    -- NOTE: 'uses' and 'belongs_to' removed Dec 2025 - never implemented, not needed for solution coverage
    edge_type VARCHAR(50) NOT NULL CHECK (edge_type IN (
        'solved_by',           -- cluster --solved_by--> solution (bullet helped on this problem type)
        'similar_to',          -- bullet --similar_to--> bullet (alternative solutions)
        'caused_failure',      -- cluster --caused_failure--> solution (bullet harmed on this problem type)
        'not_applicable_for',  -- cluster --not_applicable_for--> solution (bullet irrelevant to problem type)
        'related_to',          -- bullet --related_to--> bullet (audit trail for synthesis)
        -- Legacy types kept for backward compatibility (no new edges created):
        'contains',            -- concept --contains--> problem
        'requires',            -- solution --requires--> concept
        'caused_by',           -- failure --caused_by--> anti-pattern
        'supersedes'           -- new_solution --supersedes--> old_solution
    )),

    -- Edge weight (effectiveness/confidence)
    weight FLOAT DEFAULT 1.0 CHECK (weight >= 0.0 AND weight <= 1.0),

    -- Evidence tracking
    evidence_count INTEGER DEFAULT 1,
    last_evidence_at TIMESTAMPTZ DEFAULT NOW(),

    -- Provenance
    source_session_id UUID,
    source_event_type VARCHAR(50),

    -- Additional context (e.g., reason for not_applicable_for edges)
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Lifecycle
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate edges
    UNIQUE(source_type, source_id, target_type, target_id, edge_type)
);

-- Ensure metadata column exists (migration from older schema)
ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- Update edge_type constraint (Dec 2025: removed 'uses' and 'belongs_to' - never implemented)
-- Dec 2025: Added 'refines' for STRATEGIST bullet refinements
ALTER TABLE knowledge_edges DROP CONSTRAINT IF EXISTS knowledge_edges_edge_type_check;
ALTER TABLE knowledge_edges ADD CONSTRAINT knowledge_edges_edge_type_check
CHECK (edge_type IN (
    'solved_by', 'similar_to', 'caused_failure', 'not_applicable_for', 'related_to', 'refines',
    -- Legacy types (backward compat):
    'contains', 'requires', 'caused_by', 'supersedes'
));

-- =============================================================================
-- SECTION 3: SUPPORTING TABLES
-- =============================================================================

-- Turn attribution: Causal attribution of bullets to turns
CREATE TABLE IF NOT EXISTS turn_attribution (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    turn_number INTEGER NOT NULL,
    bullet_id UUID NOT NULL,

    -- Causal signals (extracted from conversation content)
    causal_credit FLOAT DEFAULT 0.0,
    pattern_match BOOLEAN DEFAULT FALSE,
    test_passed_this_turn BOOLEAN DEFAULT FALSE,

    -- Signal details
    signal_type VARCHAR(50),
    signal_strength FLOAT DEFAULT 0.0,
    code_snippet TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(session_id, turn_number, bullet_id)
);

-- Retrieval parameters: Thompson Sampling on (alpha, beta) weights
CREATE TABLE IF NOT EXISTS retrieval_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Weight parameters for hybrid scoring
    alpha FLOAT NOT NULL CHECK (alpha >= 0 AND alpha <= 1),
    beta FLOAT NOT NULL CHECK (beta >= 0 AND beta <= 1),

    -- Thompson Sampling counters
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,

    -- Track usage for learning
    selection_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,

    -- Lifecycle
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(alpha, beta)
);

-- Seed initial parameter combinations (idempotent)
INSERT INTO retrieval_parameters (alpha, beta) VALUES
    (1.0, 0.0),
    (0.8, 0.2),
    (0.7, 0.3),
    (0.6, 0.4),
    (0.5, 0.5),
    (0.4, 0.6),
    (0.3, 0.7)
ON CONFLICT (alpha, beta) DO NOTHING;

-- HDBSCAN label map: Maps HDBSCAN integer labels to problem_cluster UUIDs
-- Required for incremental assignment via approximate_predict()
CREATE TABLE IF NOT EXISTS hdbscan_label_map (
    hdbscan_label INTEGER PRIMARY KEY,
    cluster_id UUID REFERENCES problem_clusters(cluster_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hdbscan_label_map_cluster ON hdbscan_label_map(cluster_id);

-- =============================================================================
-- SECTION 4: COLUMN ADDITIONS TO playbook_bullets
-- =============================================================================

-- Add proven_at column (promotion tracking)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'playbook_bullets' AND column_name = 'proven_at'
    ) THEN
        ALTER TABLE playbook_bullets ADD COLUMN proven_at TIMESTAMPTZ;
    END IF;
END $$;

-- Add total_causal_credit column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'playbook_bullets' AND column_name = 'total_causal_credit'
    ) THEN
        ALTER TABLE playbook_bullets ADD COLUMN total_causal_credit FLOAT DEFAULT 0.0;
    END IF;
END $$;

-- Add cluster_id FK
ALTER TABLE playbook_bullets
ADD COLUMN IF NOT EXISTS cluster_id UUID REFERENCES problem_clusters(cluster_id) ON DELETE SET NULL;

-- Add signal_type column
ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS signal_type VARCHAR(20);

-- Backfill signal_type
UPDATE playbook_bullets SET signal_type = 'success' WHERE signal_type IS NULL;

-- Add evidence_count column
ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS evidence_count INT DEFAULT 1;

-- Add metadata column for storing rejection_reason, session context, etc.
ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- Update status constraint to include 'unvalidated'
ALTER TABLE playbook_bullets DROP CONSTRAINT IF EXISTS playbook_bullets_status_check;
ALTER TABLE playbook_bullets ADD CONSTRAINT playbook_bullets_status_check
CHECK (status IN ('unvalidated', 'candidate', 'active', 'proven', 'archived', 'banned'));

-- Migrate existing high-effectiveness bullets to proven status
UPDATE playbook_bullets
SET proven_at = created_at
WHERE proven_at IS NULL
  AND helpful_count >= 3
  AND (helpful_count + harmful_count + neutral_count) >= 3
  AND helpful_count::float / NULLIF(helpful_count + harmful_count + neutral_count, 0) >= 0.7;

-- =============================================================================
-- SECTION 5: FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Trigger: Update updated_at on problem_clusters
CREATE OR REPLACE FUNCTION update_problem_clusters_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS problem_clusters_updated_at_trigger ON problem_clusters;
CREATE TRIGGER problem_clusters_updated_at_trigger
    BEFORE UPDATE ON problem_clusters
    FOR EACH ROW
    EXECUTE FUNCTION update_problem_clusters_updated_at();

-- Function: Upsert edge with evidence counting
CREATE OR REPLACE FUNCTION upsert_edge(
    p_source_type VARCHAR(20),
    p_source_id UUID,
    p_target_type VARCHAR(20),
    p_target_id UUID,
    p_edge_type VARCHAR(50),
    p_weight FLOAT DEFAULT 1.0,
    p_session_id UUID DEFAULT NULL,
    p_event_type VARCHAR(50) DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_edge_id UUID;
BEGIN
    INSERT INTO knowledge_edges (
        source_type, source_id, target_type, target_id, edge_type,
        weight, source_session_id, source_event_type
    ) VALUES (
        p_source_type, p_source_id, p_target_type, p_target_id, p_edge_type,
        p_weight, p_session_id, p_event_type
    )
    ON CONFLICT (source_type, source_id, target_type, target_id, edge_type)
    DO UPDATE SET
        weight = (knowledge_edges.weight * knowledge_edges.evidence_count + p_weight)
                 / (knowledge_edges.evidence_count + 1),
        evidence_count = knowledge_edges.evidence_count + 1,
        last_evidence_at = NOW(),
        updated_at = NOW()
    RETURNING edge_id INTO v_edge_id;

    RETURN v_edge_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Get or create tool node
CREATE OR REPLACE FUNCTION get_or_create_tool(
    p_name VARCHAR(200),
    p_module VARCHAR(100) DEFAULT NULL,
    p_method VARCHAR(100) DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_tool_id UUID;
BEGIN
    SELECT tool_id INTO v_tool_id
    FROM tool_nodes
    WHERE name = p_name;

    IF v_tool_id IS NULL THEN
        INSERT INTO tool_nodes (name, module, method)
        VALUES (p_name, p_module, p_method)
        RETURNING tool_id INTO v_tool_id;
    ELSE
        UPDATE tool_nodes
        SET usage_count = usage_count + 1, updated_at = NOW()
        WHERE tool_id = v_tool_id;
    END IF;

    RETURN v_tool_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Find solutions for a problem via graph traversal
CREATE OR REPLACE FUNCTION find_solutions_for_problem(
    query_embedding VECTOR(384),
    max_hops INTEGER DEFAULT 3,
    min_similarity FLOAT DEFAULT 0.5,
    result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    bullet_id UUID,
    content TEXT,
    domain VARCHAR,
    similarity FLOAT,
    path_length INTEGER,
    via_edge_types TEXT[]
) AS $$
WITH RECURSIVE
starting_points AS (
    SELECT
        pb.bullet_id,
        pb.content,
        pb.domain,
        1.0 - (query_embedding <=> pb.problem_embedding) as similarity,
        0 as depth,
        ARRAY[]::TEXT[] as edge_types
    FROM playbook_bullets pb
    WHERE pb.problem_embedding IS NOT NULL
      AND pb.status NOT IN ('archived', 'banned')
      AND 1.0 - (query_embedding <=> pb.problem_embedding) >= min_similarity
      AND (
          pb.status IN ('unvalidated', 'candidate')
          OR pb.proven_at IS NOT NULL
      )
    ORDER BY pb.problem_embedding <=> query_embedding
    LIMIT 20
),
paths AS (
    SELECT
        sp.bullet_id,
        sp.content,
        sp.domain,
        sp.similarity as path_score,
        sp.depth,
        sp.edge_types
    FROM starting_points sp

    UNION ALL

    SELECT
        ke.target_id as bullet_id,
        pb.content,
        pb.domain,
        p.path_score * ke.weight as path_score,
        p.depth + 1 as depth,
        p.edge_types || ke.edge_type as edge_types
    FROM paths p
    JOIN knowledge_edges ke ON ke.source_id = p.bullet_id
                            AND ke.source_type = 'solution'
    JOIN playbook_bullets pb ON pb.bullet_id = ke.target_id
    WHERE p.depth < max_hops
      AND ke.status = 'active'
      AND ke.target_type = 'solution'
      AND pb.status NOT IN ('archived', 'banned')
      AND (
          pb.status IN ('unvalidated', 'candidate')
          OR pb.proven_at IS NOT NULL
      )
)
SELECT DISTINCT ON (p.bullet_id)
    p.bullet_id,
    p.content,
    p.domain,
    p.path_score as similarity,
    p.depth as path_length,
    p.edge_types as via_edge_types
FROM paths p
ORDER BY p.bullet_id, p.path_score DESC
LIMIT result_limit;
$$ LANGUAGE SQL STABLE;

-- Function: Get bullets from similar clusters
-- NOTE: Dec 2025 - Updated to use 'solved_by' edges (cluster→bullet direction)
-- instead of 'belongs_to' (bullet→cluster direction, removed)
CREATE OR REPLACE FUNCTION get_bullets_from_similar_clusters(
    query_embedding VECTOR(384),
    similarity_threshold FLOAT DEFAULT 0.5,
    max_clusters INTEGER DEFAULT 3,
    max_bullets_per_cluster INTEGER DEFAULT 5
)
RETURNS TABLE (
    bullet_id UUID,
    content TEXT,
    category VARCHAR,
    domain VARCHAR,
    cluster_id UUID,
    cluster_similarity FLOAT,
    edge_weight FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH similar_clusters AS (
        SELECT
            pc.cluster_id,
            1 - (pc.centroid <=> query_embedding) as similarity
        FROM problem_clusters pc
        WHERE pc.status = 'active'
          AND 1 - (pc.centroid <=> query_embedding) >= similarity_threshold
        ORDER BY pc.centroid <=> query_embedding
        LIMIT max_clusters
    ),
    cluster_bullets AS (
        -- Dec 2025: Changed from 'belongs_to' (removed) to 'solved_by'
        -- Direction is now cluster→bullet (source=cluster, target=solution)
        -- NOTE: target_type='solution' matches code (not 'bullet' which isn't in CHECK constraint)
        SELECT DISTINCT ON (ke.target_id)
            ke.target_id as bullet_id,
            ke.weight as edge_weight,
            sc.cluster_id,
            sc.similarity as cluster_similarity
        FROM similar_clusters sc
        JOIN knowledge_edges ke ON ke.source_id = sc.cluster_id
            AND ke.source_type = 'cluster'
            AND ke.target_type = 'solution'
            AND ke.edge_type = 'solved_by'
            AND ke.status = 'active'
        ORDER BY ke.target_id, sc.similarity DESC
    ),
    ranked_bullets AS (
        SELECT
            cb.*,
            ROW_NUMBER() OVER (PARTITION BY cb.cluster_id ORDER BY cb.edge_weight DESC) as cluster_rank
        FROM cluster_bullets cb
    )
    SELECT
        pb.bullet_id,
        pb.content,
        pb.category,
        pb.domain,
        rb.cluster_id,
        rb.cluster_similarity,
        rb.edge_weight
    FROM ranked_bullets rb
    JOIN playbook_bullets pb ON pb.bullet_id = rb.bullet_id
    WHERE rb.cluster_rank <= max_bullets_per_cluster
      AND pb.status NOT IN ('archived', 'banned')
      AND (
          pb.status IN ('unvalidated', 'candidate')
          OR (pb.proven_at IS NOT NULL AND pb.helpful_count > pb.harmful_count)
      )
    ORDER BY rb.cluster_similarity DESC, rb.edge_weight DESC;
END;
$$ LANGUAGE plpgsql STABLE;

-- REMOVED Dec 2025: backfill_belongs_to_edges()
-- Rationale: 'belongs_to' edge type was never used. Cluster membership is now
-- handled via solved_by/caused_failure edges (cluster -> bullet direction).
-- See ARCHITECTURE.md "Knowledge Graph Edge Ontology" for active edge types.

-- =============================================================================
-- SECTION 6: VIEWS
-- =============================================================================

-- Bullet effectiveness summary
CREATE OR REPLACE VIEW bullet_effectiveness_summary AS
SELECT
    bullet_id,
    domain,
    category,
    status,
    proven_at,
    total_causal_credit,
    helpful_count,
    harmful_count,
    neutral_count,
    (helpful_count + harmful_count + neutral_count) as total_observations,
    CASE
        WHEN (helpful_count + harmful_count + neutral_count) > 0
        THEN helpful_count::float / (helpful_count + harmful_count + neutral_count)
        ELSE 0.0
    END as effectiveness_rate,
    CASE
        WHEN proven_at IS NOT NULL THEN 'proven'
        WHEN status = 'archived' THEN 'archived'
        WHEN status = 'banned' THEN 'banned'
        ELSE 'candidate'
    END as promotion_status,
    created_at,
    last_used_at as updated_at
FROM playbook_bullets
ORDER BY
    CASE WHEN proven_at IS NOT NULL THEN 0 ELSE 1 END,
    total_causal_credit DESC,
    helpful_count DESC;

-- Learning signal summary
CREATE OR REPLACE VIEW learning_signal_summary AS
SELECT
    session_id,
    COUNT(*) as total_attributions,
    SUM(causal_credit) as total_credit,
    COUNT(DISTINCT bullet_id) as unique_bullets,
    MAX(turn_number) as max_turn,
    COUNT(*) FILTER (WHERE test_passed_this_turn) as test_pass_turns,
    COUNT(*) FILTER (WHERE pattern_match) as pattern_match_turns,
    MIN(created_at) as first_signal,
    MAX(created_at) as last_signal
FROM turn_attribution
GROUP BY session_id
ORDER BY last_signal DESC;

-- Cluster summary
CREATE OR REPLACE VIEW cluster_summary AS
SELECT
    pc.cluster_id,
    pc.label,
    pc.description,
    pc.turn_count,
    pc.success_count,
    pc.failure_count,
    pc.member_count,
    pc.avg_effectiveness,
    pc.representative_problems,
    pc.status,
    pc.created_at,
    pc.updated_at
FROM problem_clusters pc
WHERE pc.status = 'active'
ORDER BY pc.turn_count DESC, pc.success_count DESC;

-- Solution graph stats
CREATE OR REPLACE VIEW solution_graph_stats AS
SELECT
    pb.bullet_id,
    pb.content,
    pb.domain,
    pb.helpful_count,
    pb.harmful_count,
    COALESCE(incoming.edge_count, 0) as incoming_edges,
    COALESCE(outgoing.edge_count, 0) as outgoing_edges,
    COALESCE(clusters.cluster_count, 0) as cluster_memberships,
    COALESCE(tools.tool_count, 0) as tools_used
FROM playbook_bullets pb
LEFT JOIN (
    SELECT target_id, COUNT(*) as edge_count
    FROM knowledge_edges WHERE target_type = 'solution' AND status = 'active'
    GROUP BY target_id
) incoming ON incoming.target_id = pb.bullet_id
LEFT JOIN (
    SELECT source_id, COUNT(*) as edge_count
    FROM knowledge_edges WHERE source_type = 'solution' AND status = 'active'
    GROUP BY source_id
) outgoing ON outgoing.source_id = pb.bullet_id
LEFT JOIN (
    -- NOTE: Dec 2025 - changed from 'belongs_to' (removed) to 'solved_by' count via target_id
    -- target_type='solution' matches what code inserts (not 'bullet' which isn't in CHECK constraint)
    SELECT target_id as bullet_id, COUNT(*) as cluster_count
    FROM knowledge_edges WHERE target_type = 'solution' AND edge_type = 'solved_by' AND status = 'active'
    GROUP BY target_id
) clusters ON clusters.bullet_id = pb.bullet_id
LEFT JOIN (
    -- NOTE: Dec 2025 - 'uses' edge type removed. Returning 0 for backward compat.
    SELECT NULL::uuid as source_id, 0 as tool_count WHERE false
) tools ON tools.source_id = pb.bullet_id
WHERE pb.status = 'active';

-- Tool effectiveness
-- NOTE: Dec 2025 - 'uses' edge type removed. This view is kept for backward compat
-- but will return 0 for solution_count since no 'uses' edges exist.
CREATE OR REPLACE VIEW tool_effectiveness AS
SELECT
    tn.tool_id,
    tn.name,
    tn.module,
    tn.usage_count,
    0 as solution_count,  -- 'uses' edges removed Dec 2025
    0.0 as avg_edge_weight,
    0 as total_helpful
FROM tool_nodes tn
ORDER BY tn.usage_count DESC;

-- Graph retrieval stats
-- NOTE: Dec 2025 - 'uses' and 'belongs_to' edge types removed
CREATE OR REPLACE VIEW graph_retrieval_stats AS
SELECT
    (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'solved_by' AND status = 'active') as solved_by_edges,
    (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'caused_failure' AND status = 'active') as caused_failure_edges,
    (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'similar_to' AND status = 'active') as similar_to_edges,
    (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'not_applicable_for' AND status = 'active') as not_applicable_for_edges,
    (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'related_to' AND status = 'active') as related_to_edges,
    (SELECT COUNT(*) FROM problem_clusters WHERE status = 'active') as active_clusters,
    (SELECT COUNT(*) FROM playbook_bullets WHERE problem_embedding IS NOT NULL AND status NOT IN ('archived', 'banned')) as bullets_with_embeddings,
    (SELECT COUNT(DISTINCT target_id) FROM knowledge_edges WHERE edge_type = 'solved_by' AND target_type = 'solution' AND status = 'active') as bullets_with_solutions;

-- Bullet library summary
DROP VIEW IF EXISTS bullet_library_summary CASCADE;
CREATE VIEW bullet_library_summary AS
SELECT
    bullet_id,
    content,
    domain,
    category,
    status,
    helpful_count,
    harmful_count,
    neutral_count,
    usage_count,
    effectiveness_score,
    evidence_count,
    tags,
    created_at,
    CASE
        WHEN status = 'proven' THEN 0
        WHEN status = 'active' THEN 1
        WHEN status = 'candidate' THEN 2
        WHEN status = 'unvalidated' THEN 3
        WHEN status = 'archived' THEN 4
        WHEN status = 'banned' THEN 5
    END as status_order
FROM playbook_bullets
ORDER BY status_order, effectiveness_score DESC;

-- =============================================================================
-- SECTION 7: INDEXES
-- =============================================================================

-- Problem clusters indexes
CREATE INDEX IF NOT EXISTS idx_clusters_centroid ON problem_clusters
    USING ivfflat (centroid vector_cosine_ops) WITH (lists = 10);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON problem_clusters(status);
CREATE INDEX IF NOT EXISTS idx_problem_clusters_centroid ON problem_clusters
    USING ivfflat (centroid vector_cosine_ops) WITH (lists = 100);

-- Session turns indexes
CREATE INDEX IF NOT EXISTS idx_session_turns_session ON session_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_session_turns_embedding ON session_turns
    USING ivfflat (sub_task_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_session_turns_micro_outcome ON session_turns(micro_outcome);

-- Turn clusters indexes
CREATE INDEX IF NOT EXISTS idx_turn_clusters_cluster ON turn_clusters(cluster_id);

-- Knowledge edges indexes
CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_edges(source_type, source_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_edges(target_type, target_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_edges_type ON knowledge_edges(edge_type)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_edges_weight_desc ON knowledge_edges(weight DESC)
    WHERE status = 'active';

-- Problem nodes indexes
CREATE INDEX IF NOT EXISTS idx_problem_nodes_embedding ON problem_nodes
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
CREATE INDEX IF NOT EXISTS idx_problem_nodes_domain ON problem_nodes(domain);

-- Tool nodes indexes
CREATE INDEX IF NOT EXISTS idx_tool_nodes_name ON tool_nodes(name);
CREATE INDEX IF NOT EXISTS idx_tool_nodes_module ON tool_nodes(module);

-- Turn attribution indexes
CREATE INDEX IF NOT EXISTS idx_turn_attribution_session ON turn_attribution(session_id, turn_number);
CREATE INDEX IF NOT EXISTS idx_turn_attribution_bullet ON turn_attribution(bullet_id);

-- Retrieval parameters indexes
CREATE INDEX IF NOT EXISTS idx_retrieval_params_active ON retrieval_parameters(status)
    WHERE status = 'active';

-- Playbook bullets additional indexes
CREATE INDEX IF NOT EXISTS idx_bullets_cluster ON playbook_bullets(cluster_id)
    WHERE cluster_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_playbook_bullets_signal_type ON playbook_bullets(signal_type);
CREATE INDEX IF NOT EXISTS idx_playbook_bullets_problem_embedding ON playbook_bullets
    USING ivfflat (problem_embedding vector_cosine_ops) WITH (lists = 100);
-- Dec 2025: Content embedding index for dual-embedding search in ADVISOR
CREATE INDEX IF NOT EXISTS idx_playbook_bullets_embedding ON playbook_bullets
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_playbook_bullets_evidence ON playbook_bullets(status, evidence_count)
    WHERE status IN ('unvalidated', 'candidate');
CREATE INDEX IF NOT EXISTS idx_proven_bullets ON playbook_bullets(proven_at, domain)
    WHERE proven_at IS NOT NULL AND status = 'active';

-- =============================================================================
-- SECTION 8: COMMENTS
-- =============================================================================

COMMENT ON TABLE problem_clusters IS 'Problem archetypes discovered via HDBSCAN clustering. v3 adds turn-level statistics.';
COMMENT ON TABLE session_turns IS 'Turn-level learning units with sub-task analysis, micro-outcomes, and bullet attribution.';
COMMENT ON TABLE turn_clusters IS 'Turn to cluster membership mapping.';
COMMENT ON TABLE knowledge_edges IS 'Central edge table for knowledge graph. Enables multi-cluster membership and reasoning paths.';
COMMENT ON TABLE turn_attribution IS 'Causal attribution of bullets to conversation turns.';
COMMENT ON TABLE retrieval_parameters IS 'Thompson Sampling exploration of (alpha, beta) weights for hybrid retrieval.';

COMMENT ON COLUMN problem_clusters.label IS 'Human-readable cluster label (generated by CLUSTERER).';
COMMENT ON COLUMN problem_clusters.turn_count IS 'v3: Number of turns assigned to this cluster.';
COMMENT ON COLUMN problem_clusters.success_count IS 'v3: Turns with positive micro-outcome.';
COMMENT ON COLUMN problem_clusters.failure_count IS 'v3: Turns with negative micro-outcome.';
COMMENT ON COLUMN session_turns.sub_task IS 'REFLECTOR-extracted core task for this turn.';
COMMENT ON COLUMN session_turns.micro_outcome IS 'Per-turn success signal: progress, solved, stuck, error.';
COMMENT ON COLUMN knowledge_edges.edge_type IS 'Relationship type including v3 caused_failure for harm tracking.';

COMMENT ON FUNCTION upsert_edge IS 'Create or update edge with evidence-based weight averaging.';
COMMENT ON FUNCTION find_solutions_for_problem IS 'Graph traversal via recursive CTE to find solutions for a problem.';
COMMENT ON FUNCTION get_bullets_from_similar_clusters IS 'Retrieve bullets via cluster-mediated graph traversal.';
-- REMOVED Dec 2025: COMMENT ON FUNCTION backfill_belongs_to_edges

-- =============================================================================
-- Migration complete
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE '=== 21_learning_loop.sql migration completed ===';
    RAISE NOTICE 'This file consolidates the following deprecated files:';
    RAISE NOTICE '  - 21_learning_loop_schema.sql (turn_attribution, playbook_bullets columns)';
    RAISE NOTICE '  - 22_clustering_schema.sql (problem_clusters v2)';
    RAISE NOTICE '  - 23_knowledge_graph_schema.sql (knowledge graph tables)';
    RAISE NOTICE '  - 24_problem_retrieval.sql (signal_type column)';
    RAISE NOTICE '  - 25_evidence_tracking.sql (evidence_count column)';
    RAISE NOTICE '  - 26_session_views.sql (NOT included - session views)';
    RAISE NOTICE '  - 27_graph_retrieval_backfill.sql (retrieval_parameters, backfill functions)';
    RAISE NOTICE '  - 28_knowledge_edges_fix.sql (metadata column, edge_type constraint)';
    RAISE NOTICE '  - 29_turn_level_learning.sql (v3 tables)';
    RAISE NOTICE '  - 30_turn_indexes.sql (v3 indexes)';
    RAISE NOTICE '  - 31_caused_failure_edge.sql (caused_failure edge type)';
END $$;
