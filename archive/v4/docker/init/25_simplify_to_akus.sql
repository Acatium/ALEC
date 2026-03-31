-- =============================================================================
-- 25_simplify_to_akus.sql
-- AKU Simplification: Schema Migration
--
-- This migration:
--   1. Renames playbook_bullets → akus
--   2. Renames bullet_id → aku_id
--   3. Drops deprecated columns (modality, polarity, category, domain, etc.)
--   4. Renames session_turns columns (bullets_* → akus_*)
--   5. Updates knowledge_edges target_type ('bullet' → 'aku')
--
-- Target schema: 14 fields (was 30+)
--
-- Created: 2025-12-19
-- =============================================================================

-- Skip if already applied
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM schema_migrations WHERE migration_name = '25_simplify_to_akus.sql'
    ) THEN
        RAISE NOTICE 'Migration 25_simplify_to_akus.sql already applied, skipping';
        RETURN;
    END IF;

    -- =========================================================================
    -- SECTION 1: Rename playbook_bullets → akus
    -- =========================================================================

    -- Check if table needs renaming
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'playbook_bullets') THEN
        -- Drop views that depend on playbook_bullets first
        DROP VIEW IF EXISTS playbook_effectiveness_summary CASCADE;
        DROP VIEW IF EXISTS bullet_effectiveness_view CASCADE;

        -- Rename the table
        ALTER TABLE playbook_bullets RENAME TO akus;
        RAISE NOTICE 'Renamed playbook_bullets → akus';
    END IF;

    -- =========================================================================
    -- SECTION 2: Rename bullet_id → aku_id
    -- =========================================================================

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'akus' AND column_name = 'bullet_id'
    ) THEN
        ALTER TABLE akus RENAME COLUMN bullet_id TO aku_id;
        RAISE NOTICE 'Renamed bullet_id → aku_id';
    END IF;

    -- =========================================================================
    -- SECTION 3: Drop deprecated columns from akus
    -- =========================================================================

    -- Drop modality (replaced by Thompson Sampling effectiveness)
    ALTER TABLE akus DROP COLUMN IF EXISTS modality CASCADE;

    -- Drop polarity (replaced by assertion text content)
    ALTER TABLE akus DROP COLUMN IF EXISTS polarity CASCADE;

    -- Drop category (derived from polarity, no longer needed)
    ALTER TABLE akus DROP COLUMN IF EXISTS category CASCADE;

    -- Drop domain (cross-app via embeddings, not domain filtering)
    ALTER TABLE akus DROP COLUMN IF EXISTS domain CASCADE;

    -- Drop content (replaced by situation + assertion)
    ALTER TABLE akus DROP COLUMN IF EXISTS content CASCADE;

    -- Drop problem_description (replaced by situation)
    ALTER TABLE akus DROP COLUMN IF EXISTS problem_description CASCADE;

    -- Drop solution_description (replaced by assertion)
    ALTER TABLE akus DROP COLUMN IF EXISTS solution_description CASCADE;

    -- Drop embedding (replaced by situation_embedding)
    ALTER TABLE akus DROP COLUMN IF EXISTS embedding CASCADE;

    -- Drop problem_embedding (replaced by situation_embedding)
    ALTER TABLE akus DROP COLUMN IF EXISTS problem_embedding CASCADE;

    -- Drop signal_type (no longer used)
    ALTER TABLE akus DROP COLUMN IF EXISTS signal_type CASCADE;

    -- Drop usage_count (derived from counters)
    ALTER TABLE akus DROP COLUMN IF EXISTS usage_count CASCADE;

    -- Drop effectiveness_score (computed on-the-fly)
    ALTER TABLE akus DROP COLUMN IF EXISTS effectiveness_score CASCADE;

    -- Drop tags (use metadata JSONB instead)
    ALTER TABLE akus DROP COLUMN IF EXISTS tags CASCADE;

    -- Drop proven_at (use status transitions)
    ALTER TABLE akus DROP COLUMN IF EXISTS proven_at CASCADE;

    -- Drop last_validated_at (not actively used)
    ALTER TABLE akus DROP COLUMN IF EXISTS last_validated_at CASCADE;

    -- Drop last_used_at (not actively used)
    ALTER TABLE akus DROP COLUMN IF EXISTS last_used_at CASCADE;

    -- Drop updated_at (use created_at + metadata)
    ALTER TABLE akus DROP COLUMN IF EXISTS updated_at CASCADE;

    -- Drop total_causal_credit (not used in v3)
    ALTER TABLE akus DROP COLUMN IF EXISTS total_causal_credit CASCADE;

    RAISE NOTICE 'Dropped deprecated columns from akus table';

    -- =========================================================================
    -- SECTION 4: Ensure required columns exist
    -- =========================================================================

    -- Add metadata JSONB column if not exists
    ALTER TABLE akus ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

    -- Ensure cluster_id exists (may have been added in earlier migration)
    ALTER TABLE akus ADD COLUMN IF NOT EXISTS cluster_id UUID;

    -- Add foreign key constraint if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'akus_cluster_id_fkey'
        AND table_name = 'akus'
    ) THEN
        -- Only add if problem_clusters table exists
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'problem_clusters') THEN
            ALTER TABLE akus ADD CONSTRAINT akus_cluster_id_fkey
            FOREIGN KEY (cluster_id) REFERENCES problem_clusters(cluster_id) ON DELETE SET NULL;
        END IF;
    END IF;

    -- =========================================================================
    -- SECTION 5: Update source constraint for new valid values
    -- =========================================================================

    -- Drop old constraint
    ALTER TABLE akus DROP CONSTRAINT IF EXISTS playbook_bullets_source_check;
    ALTER TABLE akus DROP CONSTRAINT IF EXISTS akus_source_check;

    -- Add new constraint with all valid sources
    ALTER TABLE akus ADD CONSTRAINT akus_source_check
    CHECK (source IN ('llm-generated', 'session-extracted', 'human-curated', 'strategist', 'reflector', 'e2e-test', 'curator'));

    -- =========================================================================
    -- SECTION 6: Update status constraint
    -- =========================================================================

    -- Drop old constraint
    ALTER TABLE akus DROP CONSTRAINT IF EXISTS playbook_bullets_status_check;
    ALTER TABLE akus DROP CONSTRAINT IF EXISTS akus_status_check;

    -- Add new constraint (simplified statuses)
    ALTER TABLE akus ADD CONSTRAINT akus_status_check
    CHECK (status IN ('candidate', 'active', 'archived', 'banned'));

    -- Migrate 'unvalidated' and 'proven' to new statuses
    UPDATE akus SET status = 'candidate' WHERE status = 'unvalidated';
    UPDATE akus SET status = 'active' WHERE status = 'proven';

    -- =========================================================================
    -- SECTION 7: Rename session_turns columns
    -- =========================================================================

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'session_turns' AND column_name = 'bullets_shown'
    ) THEN
        ALTER TABLE session_turns RENAME COLUMN bullets_shown TO akus_shown;
        RAISE NOTICE 'Renamed bullets_shown → akus_shown';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'session_turns' AND column_name = 'bullets_helped'
    ) THEN
        ALTER TABLE session_turns RENAME COLUMN bullets_helped TO akus_helped;
        RAISE NOTICE 'Renamed bullets_helped → akus_helped';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'session_turns' AND column_name = 'bullets_harmed'
    ) THEN
        ALTER TABLE session_turns RENAME COLUMN bullets_harmed TO akus_harmed;
        RAISE NOTICE 'Renamed bullets_harmed → akus_harmed';
    END IF;

    -- =========================================================================
    -- SECTION 8: Update knowledge_edges target_type
    -- =========================================================================

    -- Drop old constraint and add new one that includes 'aku'
    ALTER TABLE knowledge_edges DROP CONSTRAINT IF EXISTS knowledge_edges_target_type_check;
    ALTER TABLE knowledge_edges ADD CONSTRAINT knowledge_edges_target_type_check
        CHECK (target_type IN ('cluster', 'aku', 'solution'));

    -- Update both 'bullet' and 'solution' to 'aku' for consistency
    UPDATE knowledge_edges SET target_type = 'aku' WHERE target_type IN ('bullet', 'solution');
    RAISE NOTICE 'Updated knowledge_edges target_type bullet/solution → aku';

    -- =========================================================================
    -- SECTION 9: Recreate indexes with new names
    -- =========================================================================

    -- Drop old indexes
    DROP INDEX IF EXISTS idx_domain_category;
    DROP INDEX IF EXISTS idx_effectiveness;
    DROP INDEX IF EXISTS idx_domain_effectiveness;
    DROP INDEX IF EXISTS idx_last_used;
    DROP INDEX IF EXISTS idx_bullets_situation_embedding;
    DROP INDEX IF EXISTS idx_bullets_assertion_embedding;
    DROP INDEX IF EXISTS idx_bullets_modality_polarity;

    -- Create new indexes
    CREATE INDEX IF NOT EXISTS idx_akus_situation_embedding
    ON akus USING ivfflat (situation_embedding vector_cosine_ops)
    WITH (lists = 100);

    CREATE INDEX IF NOT EXISTS idx_akus_assertion_embedding
    ON akus USING ivfflat (assertion_embedding vector_cosine_ops)
    WITH (lists = 100);

    CREATE INDEX IF NOT EXISTS idx_akus_status
    ON akus (status);

    CREATE INDEX IF NOT EXISTS idx_akus_source
    ON akus (source);

    CREATE INDEX IF NOT EXISTS idx_akus_created_at
    ON akus (created_at DESC);

    CREATE INDEX IF NOT EXISTS idx_akus_cluster_id
    ON akus (cluster_id)
    WHERE cluster_id IS NOT NULL;

    RAISE NOTICE 'Recreated indexes for akus table';

    -- =========================================================================
    -- SECTION 10: Add comments for documentation
    -- =========================================================================

    COMMENT ON TABLE akus IS 'Atomic Knowledge Units (AKUs) - simplified from playbook_bullets. 14 fields.';
    COMMENT ON COLUMN akus.aku_id IS 'Primary key (renamed from bullet_id)';
    COMMENT ON COLUMN akus.situation IS 'Retrieval trigger - when this AKU applies (max 60 chars recommended)';
    COMMENT ON COLUMN akus.assertion IS 'Actionable advice - what to do (max 100 chars recommended)';
    COMMENT ON COLUMN akus.situation_embedding IS 'Vector embedding for retrieval similarity search';
    COMMENT ON COLUMN akus.assertion_embedding IS 'Vector embedding for deduplication';
    COMMENT ON COLUMN akus.helpful_count IS 'Times this AKU helped (Thompson Sampling alpha)';
    COMMENT ON COLUMN akus.harmful_count IS 'Times this AKU harmed (Thompson Sampling beta)';
    COMMENT ON COLUMN akus.neutral_count IS 'Times this AKU had no effect';
    COMMENT ON COLUMN akus.evidence_count IS 'Deduplication evidence - incremented when similar AKU merged';
    COMMENT ON COLUMN akus.status IS 'Lifecycle: candidate → active → archived/banned';
    COMMENT ON COLUMN akus.cluster_id IS 'Problem cluster this AKU was created for';
    COMMENT ON COLUMN akus.source IS 'Origin: reflector, strategist, human-curated, etc.';
    COMMENT ON COLUMN akus.metadata IS 'Additional metadata as JSONB';

    -- =========================================================================
    -- SECTION 11: Record migration
    -- =========================================================================

    INSERT INTO schema_migrations (migration_name) VALUES ('25_simplify_to_akus.sql')
    ON CONFLICT (migration_name) DO NOTHING;

    RAISE NOTICE 'Migration 25_simplify_to_akus.sql applied successfully';
    RAISE NOTICE 'Target schema achieved: 14 fields in akus table';

END $$;

-- =============================================================================
-- VERIFICATION QUERY (run manually to confirm)
-- =============================================================================
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_name = 'akus'
-- ORDER BY ordinal_position;
--
-- Expected columns (14):
--   aku_id, situation, assertion, situation_embedding, assertion_embedding,
--   helpful_count, harmful_count, neutral_count, evidence_count,
--   status, cluster_id, source, created_at, metadata
