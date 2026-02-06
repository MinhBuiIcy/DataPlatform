-- ============================================
-- MIGRATION 003: Update Indicators Table
-- Purpose: Switch to ReplacingMergeTree for deduplication, remove TTL
-- Date: 2026-01-01
-- Phase: 2 - Data Processing & Analytics
-- ============================================

-- Backup existing data (if any)
CREATE TABLE IF NOT EXISTS trading.indicators_backup AS trading.indicators;

-- Drop old table
DROP TABLE IF EXISTS trading.indicators;

-- Recreate with ReplacingMergeTree engine
CREATE TABLE trading.indicators (
    timestamp DateTime COMMENT 'Indicator calculation time',
    exchange LowCardinality(String) COMMENT 'Exchange name',
    symbol String COMMENT 'Trading pair',
    timeframe LowCardinality(String) COMMENT 'Timeframe (1m, 5m, 1h)',
    indicator_name LowCardinality(String) COMMENT 'Indicator name (sma_20, ema_50, rsi_14)',
    indicator_value Float64 COMMENT 'Calculated indicator value',

    INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 3
) ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timeframe, indicator_name, timestamp)
COMMENT 'Technical indicators - ReplacingMergeTree for deduplication, no TTL for backtesting';
-- No TTL - keep all historical data for backtesting

-- Restore data if backup exists
INSERT INTO trading.indicators
SELECT * FROM trading.indicators_backup;

-- Drop backup
DROP TABLE IF EXISTS trading.indicators_backup;

-- Record migration
INSERT INTO trading.schema_migrations (version, name)
VALUES ('003', 'update_indicators_table');
