-- ============================================
-- MIGRATION 005: Migrate Candles to AggregatingMergeTree
-- Purpose: Fix duplicate candles issue with proper aggregation
-- Date: 2026-02-07
-- Phase: 2 - Data Processing & Analytics
-- ============================================

-- ============================================
-- Background: Why AggregatingMergeTree?
-- ============================================
-- Problem: MergeTree/ReplacingMergeTree creates duplicates when MV fires incrementally
-- Solution: AggregatingMergeTree automatically merges aggregates (sum, max, min)
--
-- Example with duplicates:
--   16:25:00 → volume: 0.06, 0.04, 0.02 (3 rows from incremental MV)
--   ReplacingMergeTree: Keeps 1 row → LOST 0.06 + 0.04 data!
--   AggregatingMergeTree: sum(0.06, 0.04, 0.02) = 0.12 ✅
--
-- Reference: https://www.glassflow.dev/blog/aggregatingmergetree-clickhouse
-- ============================================

-- ============================================
-- Step 1: Backup existing tables
-- ============================================

-- Rename old tables (keep for rollback)
RENAME TABLE trading.candles_1m TO trading.candles_1m_old;
RENAME TABLE trading.candles_5m TO trading.candles_5m_old;
RENAME TABLE trading.candles_1h TO trading.candles_1h_old;

-- Drop old MVs (will recreate with new tables)
DROP VIEW IF EXISTS trading.candles_1m_mv;
DROP VIEW IF EXISTS trading.candles_5m_mv;
DROP VIEW IF EXISTS trading.candles_1h_mv;
DROP VIEW IF EXISTS trading.candles_1m_to_kafka_mv;
DROP VIEW IF EXISTS trading.candles_5m_to_kafka_mv;
DROP VIEW IF EXISTS trading.candles_1h_to_kafka_mv;

-- ============================================
-- Step 2: Create new tables with AggregatingMergeTree
-- ============================================

-- 1-minute candles (base aggregation from trades)
CREATE TABLE trading.candles_1m (
    timestamp DateTime CODEC(Delta(4), ZSTD(1)),
    exchange LowCardinality(String) CODEC(ZSTD(1)),
    symbol LowCardinality(String) CODEC(ZSTD(1)),

    -- OHLC: Use SimpleAggregateFunction for automatic merging
    open SimpleAggregateFunction(any, Float64) CODEC(ZSTD(1)),           -- any = keep first value
    high SimpleAggregateFunction(max, Float64) CODEC(ZSTD(1)),           -- max across duplicates
    low SimpleAggregateFunction(min, Float64) CODEC(ZSTD(1)),            -- min across duplicates
    close SimpleAggregateFunction(anyLast, Float64) CODEC(ZSTD(1)),      -- anyLast = keep last value

    -- Volume: SUM across duplicates (critical fix!)
    volume SimpleAggregateFunction(sum, Float64) CODEC(ZSTD(1)),
    quote_volume SimpleAggregateFunction(sum, Float64) CODEC(ZSTD(1)),
    trades_count SimpleAggregateFunction(sum, UInt64) CODEC(ZSTD(1)),

    -- Metadata
    is_synthetic UInt8 DEFAULT 0 COMMENT 'Flag for gap-filled candles (1=synthetic)' CODEC(ZSTD(1))
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + toIntervalDay(180)
SETTINGS index_granularity = 8192
COMMENT '1-minute OHLCV candles with automatic aggregation (no duplicates!)';

-- 5-minute candles (aggregated from 1m)
CREATE TABLE trading.candles_5m (
    timestamp DateTime CODEC(DoubleDelta),
    exchange LowCardinality(String),
    symbol LowCardinality(String),

    open SimpleAggregateFunction(any, Float64) CODEC(Gorilla),
    high SimpleAggregateFunction(max, Float64) CODEC(Gorilla),
    low SimpleAggregateFunction(min, Float64) CODEC(Gorilla),
    close SimpleAggregateFunction(anyLast, Float64) CODEC(Gorilla),

    volume SimpleAggregateFunction(sum, Float64) CODEC(Gorilla),
    quote_volume SimpleAggregateFunction(sum, Float64) CODEC(ZSTD),
    trades_count SimpleAggregateFunction(sum, UInt32) CODEC(ZSTD),

    is_synthetic UInt8 DEFAULT 0 CODEC(ZSTD)
)
ENGINE = AggregatingMergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
COMMENT '5-minute OHLCV candles (aggregated from 1m)';

-- 1-hour candles (aggregated from 1m)
CREATE TABLE trading.candles_1h (
    timestamp DateTime CODEC(DoubleDelta),
    exchange LowCardinality(String),
    symbol LowCardinality(String),

    open SimpleAggregateFunction(any, Float64) CODEC(Gorilla),
    high SimpleAggregateFunction(max, Float64) CODEC(Gorilla),
    low SimpleAggregateFunction(min, Float64) CODEC(Gorilla),
    close SimpleAggregateFunction(anyLast, Float64) CODEC(Gorilla),

    volume SimpleAggregateFunction(sum, Float64) CODEC(Gorilla),
    quote_volume SimpleAggregateFunction(sum, Float64) CODEC(ZSTD),
    trades_count SimpleAggregateFunction(sum, UInt32) CODEC(ZSTD),

    is_synthetic UInt8 DEFAULT 0 CODEC(ZSTD)
)
ENGINE = AggregatingMergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
COMMENT '1-hour OHLCV candles (aggregated from 1m)';

-- ============================================
-- Step 3: Migrate data (deduplicate on insert)
-- ============================================

-- Migrate 1m candles (group by to deduplicate old data)
INSERT INTO trading.candles_1m
SELECT
    timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,        -- First open
    max(high) AS high,                      -- Highest high
    min(low) AS low,                        -- Lowest low
    argMax(close, timestamp) AS close,      -- Last close
    sum(volume) AS volume,                  -- Total volume (FIX!)
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    max(is_synthetic) AS is_synthetic       -- Keep synthetic flag if any row was synthetic
FROM trading.candles_1m_old
GROUP BY timestamp, exchange, symbol;

-- Migrate 5m candles
INSERT INTO trading.candles_5m
SELECT
    timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    max(is_synthetic) AS is_synthetic
FROM trading.candles_5m_old
GROUP BY timestamp, exchange, symbol;

-- Migrate 1h candles
INSERT INTO trading.candles_1h
SELECT
    timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    max(is_synthetic) AS is_synthetic
FROM trading.candles_1h_old
GROUP BY timestamp, exchange, symbol;

-- ============================================
-- Step 4: Recreate Materialized Views
-- ============================================

-- MV: Trades → candles_1m (real-time aggregation)
CREATE MATERIALIZED VIEW trading.candles_1m_mv
TO trading.candles_1m
AS
SELECT
    toStartOfMinute(timestamp) AS timestamp,
    exchange,
    symbol,
    argMin(price, timestamp) AS open,
    max(price) AS high,
    min(price) AS low,
    argMax(price, timestamp) AS close,
    sum(quantity) AS volume,
    sum(price * quantity) AS quote_volume,
    count() AS trades_count,
    0 AS is_synthetic
FROM trading.market_trades
GROUP BY timestamp, exchange, symbol;

-- MV: candles_1m → candles_5m
CREATE MATERIALIZED VIEW trading.candles_5m_mv
TO trading.candles_5m
AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp,
    exchange,
    symbol,
    any(open) AS open,                      -- any = keep first (for SimpleAggregateFunction)
    max(high) AS high,
    min(low) AS low,
    anyLast(close) AS close,                -- anyLast = keep last
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    0 AS is_synthetic
FROM trading.candles_1m
WHERE is_synthetic = 0
GROUP BY timestamp, exchange, symbol;

-- MV: candles_1m → candles_1h
CREATE MATERIALIZED VIEW trading.candles_1h_mv
TO trading.candles_1h
AS
SELECT
    toStartOfHour(timestamp) AS timestamp,
    exchange,
    symbol,
    any(open) AS open,
    max(high) AS high,
    min(low) AS low,
    anyLast(close) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    0 AS is_synthetic
FROM trading.candles_1m
WHERE is_synthetic = 0
GROUP BY timestamp, exchange, symbol;

-- ============================================
-- Step 5: Recreate Kafka Event Publishing MVs
-- ============================================

-- Publish 1m candle events to Kafka
CREATE MATERIALIZED VIEW trading.candles_1m_to_kafka_mv
TO trading.candles_to_kafka
AS
SELECT
    exchange,
    symbol,
    '1m' as timeframe,
    timestamp as candle_time,
    open,
    high,
    low,
    close,
    volume,
    quote_volume,
    trades_count
FROM trading.candles_1m
WHERE is_synthetic = 0;

-- Publish 5m candle events to Kafka
CREATE MATERIALIZED VIEW trading.candles_5m_to_kafka_mv
TO trading.candles_to_kafka
AS
SELECT
    exchange,
    symbol,
    '5m' as timeframe,
    timestamp as candle_time,
    open,
    high,
    low,
    close,
    volume,
    quote_volume,
    trades_count
FROM trading.candles_5m
WHERE is_synthetic = 0;

-- Publish 1h candle events to Kafka
CREATE MATERIALIZED VIEW trading.candles_1h_to_kafka_mv
TO trading.candles_to_kafka
AS
SELECT
    exchange,
    symbol,
    '1h' as timeframe,
    timestamp as candle_time,
    open,
    high,
    low,
    close,
    volume,
    quote_volume,
    trades_count
FROM trading.candles_1h
WHERE is_synthetic = 0;

-- ============================================
-- Step 6: Cleanup old tables (optional - keep for rollback)
-- ============================================

-- Uncomment after verifying migration:
-- DROP TABLE IF EXISTS trading.candles_1m_old;
-- DROP TABLE IF EXISTS trading.candles_5m_old;
-- DROP TABLE IF EXISTS trading.candles_1h_old;

-- Record migration
INSERT INTO trading.schema_migrations (version, name)
VALUES ('005', 'aggregating_merge_tree_candles');

-- ============================================
-- Verification Queries
-- ============================================

-- Check for duplicates (should be 0 after merge)
-- SELECT timestamp, count() as dup_count
-- FROM trading.candles_1m
-- WHERE exchange='binance' AND symbol='BTCUSDT'
-- GROUP BY timestamp
-- HAVING count() > 1;

-- Compare volume before/after
-- SELECT sum(volume) FROM trading.candles_1m_old WHERE exchange='binance' AND symbol='BTCUSDT';
-- SELECT sum(volume) FROM trading.candles_1m WHERE exchange='binance' AND symbol='BTCUSDT';
