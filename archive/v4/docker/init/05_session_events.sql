-- Session events table for timeline materialized view
-- Stores Kafka events for fast PostgreSQL queries instead of scanning Kafka topics

CREATE TABLE IF NOT EXISTS session_events (
    event_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    correlation_id UUID,
    source VARCHAR(100),
    kafka_topic VARCHAR(100),
    kafka_partition INTEGER,
    kafka_offset BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Primary index for session timeline queries
CREATE INDEX IF NOT EXISTS idx_session_events_session_timestamp
    ON session_events(session_id, timestamp DESC);

-- Index for querying by event type within a session
CREATE INDEX IF NOT EXISTS idx_session_events_session_type
    ON session_events(session_id, event_type);

-- GIN index for JSONB payload queries (e.g., finding bullets used)
CREATE INDEX IF NOT EXISTS idx_session_events_payload
    ON session_events USING GIN (payload);

-- Index for correlation_id lookups
CREATE INDEX IF NOT EXISTS idx_session_events_correlation
    ON session_events(correlation_id);

-- Index for event_type queries across all sessions
CREATE INDEX IF NOT EXISTS idx_session_events_type_timestamp
    ON session_events(event_type, timestamp DESC);

-- Comment explaining purpose
COMMENT ON TABLE session_events IS
    'Materialized view of Kafka events for fast session timeline queries. '
    'Populated by Curator SessionEventConsumer from Kafka topics: '
    'session.created, llm.request.prepared, llm.response.received, '
    'bullet.effectiveness, token.usage';
