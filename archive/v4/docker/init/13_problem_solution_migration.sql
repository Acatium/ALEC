-- ============================================================================
-- ALEC Phase 0.1: Problem-Solution Structure Migration
-- ============================================================================
-- Adds problem_description, solution_description, and problem_embedding
-- fields to the playbook_bullets table for enhanced retrieval capabilities.
--
-- This migration:
-- 1. Adds new columns to playbook_bullets table
-- 2. Backfills solution_description from existing content
-- 3. Creates index for problem-based retrieval (commented - run after embeddings)
--
-- Run order: 13 (after LLM management tables)
-- ============================================================================

-- Add new columns for problem-solution structure
-- NOTE: problem_embedding uses vector(384) for sentence-transformers (unified architecture)
ALTER TABLE playbook_bullets
ADD COLUMN IF NOT EXISTS problem_description TEXT,
ADD COLUMN IF NOT EXISTS solution_description TEXT,
ADD COLUMN IF NOT EXISTS problem_embedding vector(384);

-- Backfill solution_description from existing content for all existing bullets
-- This preserves current behavior while enabling future problem-solution separation
UPDATE playbook_bullets
SET solution_description = content
WHERE solution_description IS NULL;

-- Add comment to document the migration
COMMENT ON COLUMN playbook_bullets.problem_description IS 'Extracted problem/task description from the interaction context';
COMMENT ON COLUMN playbook_bullets.solution_description IS 'The approach/solution that addressed the problem';
COMMENT ON COLUMN playbook_bullets.problem_embedding IS 'Sentence-transformers embeddings (384 dims) for problem-based semantic retrieval';

-- Create index for problem-based retrieval
-- Note: Commented out - run this manually after problem_embeddings are populated
-- to avoid overhead on empty column
-- CREATE INDEX IF NOT EXISTS idx_playbook_bullets_problem_embedding
-- ON playbook_bullets USING ivfflat (problem_embedding vector_cosine_ops)
-- WITH (lists = 100);

-- Log the migration
DO $$
DECLARE
    bullets_updated INTEGER;
    bullets_total INTEGER;
BEGIN
    SELECT COUNT(*) INTO bullets_updated
    FROM playbook_bullets
    WHERE solution_description IS NOT NULL;

    SELECT COUNT(*) INTO bullets_total
    FROM playbook_bullets;

    RAISE NOTICE 'Phase 0.1 migration completed:';
    RAISE NOTICE '  - Added problem_description, solution_description, problem_embedding columns';
    RAISE NOTICE '  - Backfilled solution_description for % of % bullets', bullets_updated, bullets_total;
    RAISE NOTICE '  - problem_description and problem_embedding remain NULL (will be populated later)';
    RAISE NOTICE '  - Index creation deferred until embeddings are populated';
END $$;

-- ============================================================================
-- End of Phase 0.1 Migration
-- ============================================================================
