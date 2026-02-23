-- ============================================
-- MIGRATION 004: Multi-Timeframe Candle Tables
-- Purpose: 5m/1h candle aggregation with MVs and Kafka event publishing
-- Date: 2026-02-06
-- Phase: 2 - Data Processing & Analytics (Backfill Pipeline)
-- ============================================

-- ============================================
-- 5-Minute Candles Table
-- ============================================
CREATE TABLE IF NOT EXISTS trading.candles_5m (
    timestamp DateTime CODEC(DoubleDelta),
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    open Float64 CODEC(Gorilla),
    high Float64 CODEC(Gorilla),
    low Float64 CODEC(Gorilla),
    close Float64 CODEC(Gorilla),
    volume Float64 CODEC(Gorilla),
    quote_volume Float64 DEFAULT 0 CODEC(ZSTD),
    trades_count UInt32 DEFAULT 0 CODEC(ZSTD),
    is_synthetic UInt8 DEFAULT 0 CODEC(ZSTD)
)
ENGINE = ReplacingMergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
COMMENT '5-minute OHLCV candles (aggregated from 1m)';

-- ============================================
-- 1-Hour Candles Table
-- ============================================
CREATE TABLE IF NOT EXISTS trading.candles_1h (
    timestamp DateTime CODEC(DoubleDelta),
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    open Float64 CODEC(Gorilla),
    high Float64 CODEC(Gorilla),
    low Float64 CODEC(Gorilla),
    close Float64 CODEC(Gorilla),
    volume Float64 CODEC(Gorilla),
    quote_volume Float64 DEFAULT 0 CODEC(ZSTD),
    trades_count UInt32 DEFAULT 0 CODEC(ZSTD),
    is_synthetic UInt8 DEFAULT 0 CODEC(ZSTD)
)
ENGINE = ReplacingMergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
COMMENT '1-hour OHLCV candles (aggregated from 1m)';

-- ============================================
-- Materialized Views: Aggregate 1m → 5m and 1m → 1h
-- ============================================

-- 5m MV: Aggregate from candles_1m inserts
DROP VIEW IF EXISTS trading.candles_5m_mv;
CREATE MATERIALIZED VIEW trading.candles_5m_mv
TO trading.candles_5m
AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    0 AS is_synthetic
FROM trading.candles_1m
GROUP BY timestamp, exchange, symbol;

-- 1h MV: Aggregate from candles_1m inserts
DROP VIEW IF EXISTS trading.candles_1h_mv;
CREATE MATERIALIZED VIEW trading.candles_1h_mv
TO trading.candles_1h
AS
SELECT
    toStartOfHour(timestamp) AS timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    0 AS is_synthetic
FROM trading.candles_1m
GROUP BY timestamp, exchange, symbol;

-- ============================================
-- Kafka Event Publishing MVs (5m and 1h)
-- Reuse existing candles_to_kafka Kafka Engine table
-- ============================================

-- Publish 5m candle events to Kafka
DROP VIEW IF EXISTS trading.candles_5m_to_kafka_mv;
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
DROP VIEW IF EXISTS trading.candles_1h_to_kafka_mv;
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
-- Backfill: Populate 5m/1h from existing 1m data
-- ============================================

INSERT INTO trading.candles_5m
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    0 AS is_synthetic
FROM trading.candles_1m
WHERE is_synthetic = 0
GROUP BY timestamp, exchange, symbol;

INSERT INTO trading.candles_1h
SELECT
    toStartOfHour(timestamp) AS timestamp,
    exchange,
    symbol,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trades_count) AS trades_count,
    0 AS is_synthetic
FROM trading.candles_1m
WHERE is_synthetic = 0
GROUP BY timestamp, exchange, symbol;

-- Record migration
INSERT INTO trading.schema_migrations (version, name)
VALUES ('004', 'multi_timeframe_candles');
