-- Migration: Ensure problem_embedding is vector(384) dims
-- Phase 0.5.5: Unified embedding architecture using sentence-transformers for all embeddings
--
-- Why:
--   - OpenAI embeddings (1536 dims) require OPENAI_API_KEY which complicates deployment
--   - Sentence-transformers (384 dims) runs locally with no external dependencies
--   - Single embedding model simplifies architecture and debugging
--   - 384-dim embeddings are faster for similarity search (smaller vectors)
--
-- IDEMPOTENT: Safe to run on fresh install (already 384) or migration (from 1536)

-- Drop the existing index (if any) that might have been built for wrong dimensions
DROP INDEX IF EXISTS idx_playbook_bullets_problem_embedding;

-- Only migrate if column is wrong type (1536 dims)
-- Fresh installs already have vector(384) from 01_init_db.sql
DO $$
DECLARE
    current_type TEXT;
BEGIN
    SELECT format_type(atttypid, atttypmod) INTO current_type
    FROM pg_attribute
    WHERE attrelid = 'playbook_bullets'::regclass
      AND attname = 'problem_embedding';

    IF current_type = 'vector(1536)' THEN
        -- Clear values before type change (pgvector can't cast between dimensions)
        UPDATE playbook_bullets SET problem_embedding = NULL;
        -- Change to 384 dims
        ALTER TABLE playbook_bullets ALTER COLUMN problem_embedding TYPE vector(384);
        RAISE NOTICE 'Migrated problem_embedding from vector(1536) to vector(384)';
    ELSIF current_type = 'vector(384)' THEN
        RAISE NOTICE 'problem_embedding already vector(384) - no migration needed';
    ELSE
        RAISE NOTICE 'problem_embedding has unexpected type: % - skipping migration', current_type;
    END IF;
END $$;

-- Recreate index for 384-dim vectors
-- Using ivfflat for approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS idx_playbook_bullets_problem_embedding
ON playbook_bullets USING ivfflat (problem_embedding vector_cosine_ops)
WITH (lists = 100);

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 18_problem_embedding_384.sql completed';
END $$;
