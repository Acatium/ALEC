-- Fix source constraint to allow new source values
-- This addresses the CheckViolationError when CURATOR tries to store bullets
-- with source='strategist' or source='reflector'

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'playbook_bullets_source_check'
    ) THEN
        ALTER TABLE playbook_bullets DROP CONSTRAINT playbook_bullets_source_check;
    END IF;
    
    ALTER TABLE playbook_bullets ADD CONSTRAINT playbook_bullets_source_check 
    CHECK (source IN (
        'llm-generated', 
        'session-extracted', 
        'human-curated', 
        'strategist', 
        'reflector',
        'e2e-test'
    ));
END $$;
