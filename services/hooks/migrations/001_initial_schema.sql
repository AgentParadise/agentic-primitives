-- Hook Events Schema for agentic-hooks-backend
-- Version: 1.0
--
-- This schema uses time-based partitioning for efficient data management
-- and includes optimized indexes for common query patterns.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Hook events main table with time-based partitioning
-- Partitioned by created_date for efficient archival and querying
CREATE TABLE IF NOT EXISTS hook_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    workflow_id UUID,
    phase_id VARCHAR(100),
    milestone_id VARCHAR(100),
    data JSONB NOT NULL DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_date DATE NOT NULL DEFAULT CURRENT_DATE
) PARTITION BY RANGE (created_date);

-- Create partition for current month
-- In production, use a partition management tool like pg_partman
CREATE TABLE IF NOT EXISTS hook_events_default
    PARTITION OF hook_events DEFAULT;

-- Function to create monthly partitions
CREATE OR REPLACE FUNCTION create_monthly_partition(year INT, month INT)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    partition_name := 'hook_events_' || year || '_' || LPAD(month::TEXT, 2, '0');
    start_date := make_date(year, month, 1);
    end_date := start_date + INTERVAL '1 month';

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF hook_events
         FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );

    RAISE NOTICE 'Created partition: %', partition_name;
END;
$$ LANGUAGE plpgsql;

-- Create partitions for current and next 3 months
DO $$
DECLARE
    current_year INT := EXTRACT(YEAR FROM CURRENT_DATE)::INT;
    current_month INT := EXTRACT(MONTH FROM CURRENT_DATE)::INT;
    i INT;
    target_year INT;
    target_month INT;
BEGIN
    FOR i IN 0..3 LOOP
        target_month := ((current_month - 1 + i) % 12) + 1;
        target_year := current_year + ((current_month - 1 + i) / 12);
        PERFORM create_monthly_partition(target_year, target_month);
    END LOOP;
END $$;

-- Indexes for common query patterns

-- Primary index: Session-based queries (most common)
-- "Show all events for session X"
CREATE INDEX IF NOT EXISTS idx_hook_events_session
    ON hook_events (session_id);

-- Workflow-based queries
-- "Show all events for workflow Y"
CREATE INDEX IF NOT EXISTS idx_hook_events_workflow
    ON hook_events (workflow_id)
    WHERE workflow_id IS NOT NULL;

-- Event type + time queries
-- "Show all tool_execution_started events in last hour"
CREATE INDEX IF NOT EXISTS idx_hook_events_type_time
    ON hook_events (event_type, timestamp DESC);

-- Time-based queries (for dashboards)
-- "Show all events in last 24 hours"
CREATE INDEX IF NOT EXISTS idx_hook_events_timestamp
    ON hook_events (timestamp DESC);

-- Session + time compound index
-- "Show recent events for session X"
CREATE INDEX IF NOT EXISTS idx_hook_events_session_time
    ON hook_events (session_id, timestamp DESC);

-- GIN index for JSONB queries
-- "Find events where data->>'tool_name' = 'Write'"
CREATE INDEX IF NOT EXISTS idx_hook_events_data
    ON hook_events USING GIN (data);

-- Composite index for session analytics
-- "Count events by type for session X"
CREATE INDEX IF NOT EXISTS idx_hook_events_session_type
    ON hook_events (session_id, event_type);

-- ============================================================================
-- Statistics and Maintenance
-- ============================================================================

-- Function to get partition statistics
CREATE OR REPLACE FUNCTION get_partition_stats()
RETURNS TABLE (
    partition_name TEXT,
    row_count BIGINT,
    total_size TEXT,
    index_size TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.relname::TEXT as partition_name,
        pg_stat_user_tables.n_live_tup as row_count,
        pg_size_pretty(pg_total_relation_size(c.oid)) as total_size,
        pg_size_pretty(pg_indexes_size(c.oid)) as index_size
    FROM pg_class c
    JOIN pg_inherits i ON c.oid = i.inhrelid
    JOIN pg_stat_user_tables ON pg_stat_user_tables.relid = c.oid
    WHERE i.inhparent = 'hook_events'::regclass
    ORDER BY c.relname;
END;
$$ LANGUAGE plpgsql;

-- Function to archive old partitions (move to cold storage)
CREATE OR REPLACE FUNCTION archive_old_partitions(months_to_keep INT DEFAULT 3)
RETURNS VOID AS $$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
BEGIN
    cutoff_date := CURRENT_DATE - (months_to_keep || ' months')::INTERVAL;

    FOR partition_record IN
        SELECT c.relname as partition_name
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        WHERE i.inhparent = 'hook_events'::regclass
          AND c.relname ~ '^hook_events_\d{4}_\d{2}$'
          AND to_date(substring(c.relname from '\d{4}_\d{2}$'), 'YYYY_MM') < cutoff_date
    LOOP
        RAISE NOTICE 'Would archive partition: %', partition_record.partition_name;
        -- Uncomment to actually detach:
        -- EXECUTE format('ALTER TABLE hook_events DETACH PARTITION %I', partition_record.partition_name);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Example Queries for Common Use Cases
-- ============================================================================

-- Example 1: Get all events for a session
-- SELECT * FROM hook_events WHERE session_id = 'session-123' ORDER BY timestamp;

-- Example 2: Get event counts by type for last hour
-- SELECT event_type, COUNT(*)
-- FROM hook_events
-- WHERE timestamp > NOW() - INTERVAL '1 hour'
-- GROUP BY event_type;

-- Example 3: Get sessions with blocked tools
-- SELECT DISTINCT session_id
-- FROM hook_events
-- WHERE event_type = 'tool_blocked';

-- Example 4: Search by JSONB field
-- SELECT * FROM hook_events
-- WHERE data @> '{"tool_name": "Write"}';

-- Example 5: Get partition statistics
-- SELECT * FROM get_partition_stats();
