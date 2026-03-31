-- =============================================================================
-- 23_v3_aku_columns.sql
-- Add v3 AKU (Atomic Knowledge Unit) columns to playbook_bullets and problem_clusters
--
-- This migration adds:
--   playbook_bullets: situation, assertion, modality, polarity,
--                     situation_embedding, assertion_embedding, last_validated_at
--   problem_clusters: domain
--
-- Data is migrated from existing columns where sensible.
-- All operations are idempotent (safe to run multiple times).
--
-- Created: 2025-12-14
-- =============================================================================

-- Skip if already applied
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM schema_migrations WHERE migration_name = '23_v3_aku_columns.sql'
    ) THEN
        RAISE NOTICE 'Migration 23_v3_aku_columns.sql already applied, skipping';
        RETURN;
    END IF;

    -- =========================================================================
    -- SECTION 1: Add columns to playbook_bullets
    -- =========================================================================

    -- situation: The problem context (migrated from problem_description)
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS situation TEXT;

    -- assertion: The actionable advice (migrated from content)
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS assertion TEXT;

    -- modality: must/should/could (defaults to 'should')
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS modality VARCHAR(20) DEFAULT 'should';

    -- polarity: do/dont/know (defaults to 'do')
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS polarity VARCHAR(20) DEFAULT 'do';

    -- situation_embedding: For retrieval (migrated from problem_embedding)
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS situation_embedding VECTOR(384);

    -- assertion_embedding: For deduplication (migrated from embedding)
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS assertion_embedding VECTOR(384);

    -- last_validated_at: When bullet was last confirmed effective
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS last_validated_at TIMESTAMPTZ;

    -- updated_at: Track last modification time
    ALTER TABLE playbook_bullets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

    -- =========================================================================
    -- SECTION 2: Migrate data from existing columns
    -- =========================================================================

    -- Migrate situation from problem_description
    UPDATE playbook_bullets
    SET situation = problem_description
    WHERE situation IS NULL AND problem_description IS NOT NULL;

    -- Migrate assertion from content (or solution_description if content is generic)
    UPDATE playbook_bullets
    SET assertion = COALESCE(solution_description, content)
    WHERE assertion IS NULL;

    -- Migrate situation_embedding from problem_embedding
    UPDATE playbook_bullets
    SET situation_embedding = problem_embedding
    WHERE situation_embedding IS NULL AND problem_embedding IS NOT NULL;

    -- Migrate assertion_embedding from embedding
    UPDATE playbook_bullets
    SET assertion_embedding = embedding
    WHERE assertion_embedding IS NULL AND embedding IS NOT NULL;

    -- Set last_validated_at for proven bullets
    UPDATE playbook_bullets
    SET last_validated_at = proven_at
    WHERE last_validated_at IS NULL AND proven_at IS NOT NULL;

    -- =========================================================================
    -- SECTION 3: Add domain column to problem_clusters
    -- =========================================================================

    ALTER TABLE problem_clusters ADD COLUMN IF NOT EXISTS domain VARCHAR(100);

    -- =========================================================================
    -- SECTION 3b: Add cluster_id to session_turns
    -- =========================================================================

    ALTER TABLE session_turns ADD COLUMN IF NOT EXISTS cluster_id UUID
    REFERENCES problem_clusters(cluster_id) ON DELETE SET NULL;

    -- =========================================================================
    -- SECTION 4: Create indexes for new columns
    -- =========================================================================

    -- Index on situation_embedding for vector search (only if not exists)
    CREATE INDEX IF NOT EXISTS idx_bullets_situation_embedding
    ON playbook_bullets USING ivfflat (situation_embedding vector_cosine_ops)
    WITH (lists = 100);

    -- Index on assertion_embedding for dedup search
    CREATE INDEX IF NOT EXISTS idx_bullets_assertion_embedding
    ON playbook_bullets USING ivfflat (assertion_embedding vector_cosine_ops)
    WITH (lists = 100);

    -- Index on modality and polarity for filtering
    CREATE INDEX IF NOT EXISTS idx_bullets_modality_polarity
    ON playbook_bullets (modality, polarity);

    -- Index on problem_clusters.domain
    CREATE INDEX IF NOT EXISTS idx_clusters_domain
    ON problem_clusters (domain)
    WHERE domain IS NOT NULL;

    -- Index on session_turns.cluster_id
    CREATE INDEX IF NOT EXISTS idx_session_turns_cluster
    ON session_turns (cluster_id)
    WHERE cluster_id IS NOT NULL;

    -- =========================================================================
    -- SECTION 5: Add constraints
    -- =========================================================================

    -- Modality constraint
    ALTER TABLE playbook_bullets DROP CONSTRAINT IF EXISTS playbook_bullets_modality_check;
    ALTER TABLE playbook_bullets ADD CONSTRAINT playbook_bullets_modality_check
    CHECK (modality IS NULL OR modality IN ('must', 'should', 'could'));

    -- Polarity constraint
    ALTER TABLE playbook_bullets DROP CONSTRAINT IF EXISTS playbook_bullets_polarity_check;
    ALTER TABLE playbook_bullets ADD CONSTRAINT playbook_bullets_polarity_check
    CHECK (polarity IS NULL OR polarity IN ('do', 'dont', 'know'));

    -- =========================================================================
    -- SECTION 6: Record migration
    -- =========================================================================

    INSERT INTO schema_migrations (migration_name) VALUES ('23_v3_aku_columns.sql')
    ON CONFLICT (migration_name) DO NOTHING;

    RAISE NOTICE 'Migration 23_v3_aku_columns.sql applied successfully';
END $$;

-- =============================================================================
-- VERIFICATION QUERIES (for manual checking)
-- =============================================================================
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name = 'playbook_bullets' AND column_name IN
--   ('situation', 'assertion', 'modality', 'polarity', 'situation_embedding', 'assertion_embedding');
--
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name = 'problem_clusters' AND column_name = 'domain';
