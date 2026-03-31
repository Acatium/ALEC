-- Session views for fast analytics queries
-- Created: 2025-11-29
-- Purpose: Provide aggregated views of session_events data for dashboards and analytics

-- Session token usage summary
-- Aggregates token usage per session from session_events (llm.response.received events)
CREATE OR REPLACE VIEW session_token_summary AS
SELECT
    session_id,
    COUNT(*) as llm_calls,
    SUM((payload->'usage'->>'input_tokens')::int) as total_input_tokens,
    SUM((payload->'usage'->>'output_tokens')::int) as total_output_tokens,
    SUM((payload->'usage'->>'cache_read_input_tokens')::int) as total_cache_read_tokens,
    SUM((payload->'usage'->>'cache_creation_input_tokens')::int) as total_cache_creation_tokens,
    MIN(timestamp) as first_call_at,
    MAX(timestamp) as last_call_at
FROM session_events
WHERE event_type = 'llm.response.received'
GROUP BY session_id;

COMMENT ON VIEW session_token_summary IS
    'Aggregated token usage per session from session_events table. '
    'Used by SessionDetailPage and cost tracking dashboards.';


-- Daily session activity stats
-- For dashboard showing session and event activity over time
CREATE OR REPLACE VIEW daily_session_activity AS
SELECT
    DATE(timestamp) as date,
    COUNT(DISTINCT session_id) as sessions,
    COUNT(*) as total_events,
    COUNT(DISTINCT event_type) as event_types,
    SUM(CASE WHEN event_type = 'llm.response.received' THEN 1 ELSE 0 END) as llm_calls,
    SUM(CASE WHEN event_type = 'bullets.requested' THEN 1 ELSE 0 END) as bullet_requests
FROM session_events
GROUP BY DATE(timestamp)
ORDER BY date DESC;

COMMENT ON VIEW daily_session_activity IS
    'Daily aggregated session activity for dashboards. '
    'Shows sessions, events, and LLM calls per day.';


-- Session timeline view (enriched)
-- Returns events with additional computed fields for display
CREATE OR REPLACE VIEW session_timeline_enriched AS
SELECT
    event_id,
    session_id,
    event_type,
    timestamp,
    payload,
    correlation_id,
    source,
    created_at,
    -- Extract turn number if available
    COALESCE(
        (payload->>'turn_number')::int,
        (payload->'usage'->>'turn_number')::int
    ) as turn_number,
    -- Extract token counts for llm.response.received events
    CASE WHEN event_type = 'llm.response.received' THEN
        (payload->'usage'->>'input_tokens')::int
    END as input_tokens,
    CASE WHEN event_type = 'llm.response.received' THEN
        (payload->'usage'->>'output_tokens')::int
    END as output_tokens,
    CASE WHEN event_type = 'llm.response.received' THEN
        (payload->'usage'->>'cache_read_input_tokens')::int
    END as cache_read_tokens,
    -- Event category for UI grouping
    CASE
        WHEN event_type LIKE 'llm.%' THEN 'llm'
        WHEN event_type LIKE 'bullets.%' THEN 'bullets'
        WHEN event_type LIKE 'token.%' THEN 'token'
        WHEN event_type LIKE 'session.%' THEN 'session'
        ELSE 'other'
    END as event_category
FROM session_events
ORDER BY timestamp DESC;

COMMENT ON VIEW session_timeline_enriched IS
    'Enriched session timeline with extracted fields for UI display. '
    'Used by SessionDetailPage timeline component.';


-- Token usage by event type (for cost analysis)
CREATE OR REPLACE VIEW token_usage_by_type AS
SELECT
    DATE(timestamp) as date,
    payload->>'agent_name' as agent_name,
    COUNT(*) as calls,
    SUM((payload->>'input_tokens')::int) as total_input,
    SUM((payload->>'output_tokens')::int) as total_output,
    SUM((payload->>'cache_read_input_tokens')::int) as total_cache_read,
    SUM((payload->>'cache_creation_input_tokens')::int) as total_cache_creation
FROM session_events
WHERE event_type = 'token.usage'
GROUP BY DATE(timestamp), payload->>'agent_name'
ORDER BY date DESC, agent_name;

COMMENT ON VIEW token_usage_by_type IS
    'Token usage aggregated by date and agent name. '
    'Used for cost tracking and budget analysis.';


-- Recent sessions with token totals
-- For session list page with quick token stats
CREATE OR REPLACE VIEW recent_sessions_with_tokens AS
SELECT
    s.session_id,
    s.title,
    s.domain,
    s.status,
    s.message_count,
    s.created_at,
    s.updated_at,
    COALESCE(t.llm_calls, 0) as llm_calls,
    COALESCE(t.total_input_tokens, 0) as total_input_tokens,
    COALESCE(t.total_output_tokens, 0) as total_output_tokens,
    COALESCE(t.total_cache_read_tokens, 0) as total_cache_read_tokens
FROM sessions s
LEFT JOIN session_token_summary t ON s.session_id = t.session_id
ORDER BY s.updated_at DESC;

COMMENT ON VIEW recent_sessions_with_tokens IS
    'Sessions with aggregated token usage for list display. '
    'Joins sessions table with session_token_summary view.';
