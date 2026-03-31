-- ============================================================================
-- Phase 0.1 Migration Verification Script
-- ============================================================================
-- Verifies that the problem-solution structure migration completed successfully
--
-- Expected results:
-- 1. All three new columns exist (problem_description, solution_description, problem_embedding)
-- 2. solution_description is backfilled for all existing bullets
-- 3. problem_description and problem_embedding are NULL (to be populated later)
-- 4. Column types are correct (TEXT for descriptions, vector(1536) for embedding)
-- ============================================================================

-- Check 1: Verify columns exist with correct types
SELECT
    column_name,
    data_type,
    CASE
        WHEN data_type = 'USER-DEFINED' THEN udt_name
        ELSE NULL
    END as udt_type
FROM information_schema.columns
WHERE table_name = 'playbook_bullets'
    AND column_name IN ('problem_description', 'solution_description', 'problem_embedding')
ORDER BY column_name;

-- Check 2: Verify backfill status
SELECT
    COUNT(*) as total_bullets,
    COUNT(solution_description) as solution_backfilled,
    COUNT(problem_description) as problem_filled,
    COUNT(problem_embedding) as embedding_filled,
    CASE
        WHEN COUNT(*) = COUNT(solution_description)
        THEN 'PASS: All bullets have solution_description'
        ELSE 'FAIL: Some bullets missing solution_description'
    END as backfill_status
FROM playbook_bullets;

-- Check 3: Sample data verification
SELECT
    bullet_id,
    domain,
    category,
    LEFT(content, 50) as content_preview,
    LEFT(solution_description, 50) as solution_preview,
    CASE
        WHEN content = solution_description THEN 'MATCH'
        ELSE 'DIFFERENT'
    END as content_match,
    problem_description IS NULL as problem_null,
    problem_embedding IS NULL as embedding_null
FROM playbook_bullets
LIMIT 5;

-- Check 4: Verify comments were added
SELECT
    col.column_name,
    pgd.description
FROM pg_catalog.pg_statio_all_tables as st
INNER JOIN pg_catalog.pg_description pgd ON (pgd.objoid = st.relid)
INNER JOIN information_schema.columns col ON (
    pgd.objsubid = col.ordinal_position
    AND col.table_schema = st.schemaname
    AND col.table_name = st.relname
)
WHERE st.relname = 'playbook_bullets'
    AND col.column_name IN ('problem_description', 'solution_description', 'problem_embedding')
ORDER BY col.column_name;

-- Summary message
DO $$
DECLARE
    total_count INTEGER;
    backfilled_count INTEGER;
BEGIN
    SELECT COUNT(*), COUNT(solution_description)
    INTO total_count, backfilled_count
    FROM playbook_bullets;

    RAISE NOTICE '';
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Phase 0.1 Migration Verification Summary';
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Total bullets: %', total_count;
    RAISE NOTICE 'Backfilled with solution_description: %', backfilled_count;
    RAISE NOTICE '';
    IF total_count = backfilled_count THEN
        RAISE NOTICE 'Status: PASS - Migration successful';
    ELSE
        RAISE NOTICE 'Status: FAIL - Migration incomplete';
    END IF;
    RAISE NOTICE '================================================';
    RAISE NOTICE '';
END $$;
