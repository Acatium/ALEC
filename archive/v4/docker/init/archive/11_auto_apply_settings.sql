-- Auto-apply settings and recommendation confidence
-- This adds confidence scoring and auto-apply functionality

-- Add confidence column to recommendations
ALTER TABLE agent_recommendations
ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 0.5 CHECK (confidence BETWEEN 0.0 AND 1.0);

-- Create curator settings table
CREATE TABLE IF NOT EXISTS curator_settings (
    setting_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    setting_name VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Insert default auto-apply threshold
INSERT INTO curator_settings (setting_name, setting_value, description)
VALUES ('auto_apply_threshold', '0.5', 'Confidence threshold for auto-applying recommendations to bullet-reflector')
ON CONFLICT (setting_name) DO NOTHING;

-- Add index for faster settings lookups
CREATE INDEX IF NOT EXISTS idx_curator_settings_name ON curator_settings(setting_name);

-- Update recommendation status enum to include auto_applied
-- Note: PostgreSQL doesn't easily allow adding enum values, so we use varchar
-- The status column should already be varchar based on the existing schema
