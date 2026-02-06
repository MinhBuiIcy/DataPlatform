-- ============================================
-- MIGRATION TRACKER
-- Purpose: Track applied migrations for ClickHouse
-- Date: 2026-01-01
-- ============================================

-- Create migration tracking table
CREATE TABLE IF NOT EXISTS trading.schema_migrations (
    version String COMMENT 'Migration version (001, 002, 003, ...)',
    name String COMMENT 'Migration name/description',
    applied_at DateTime DEFAULT now() COMMENT 'When migration was applied',
    applied_by String DEFAULT 'manual' COMMENT 'Who/what applied the migration'
) ENGINE = MergeTree()
ORDER BY version
COMMENT 'Track applied database migrations';

-- Insert this tracker migration
INSERT INTO trading.schema_migrations (version, name, applied_by)
VALUES ('000', 'migration_tracker', 'init');
