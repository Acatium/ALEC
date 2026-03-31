-- Add container tracking to evaluation_experiments table
-- This allows reliable start/stop of evaluation containers

ALTER TABLE evaluation_experiments
ADD COLUMN IF NOT EXISTS container_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS container_name VARCHAR(255);

-- Add index for container lookups
CREATE INDEX IF NOT EXISTS idx_evaluation_experiments_container_id
ON evaluation_experiments(container_id)
WHERE container_id IS NOT NULL;

COMMENT ON COLUMN evaluation_experiments.container_id IS 'Docker container ID for running evaluation';
COMMENT ON COLUMN evaluation_experiments.container_name IS 'Docker container name for running evaluation';
