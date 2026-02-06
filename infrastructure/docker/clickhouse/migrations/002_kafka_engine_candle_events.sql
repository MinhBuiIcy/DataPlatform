-- ============================================
-- MIGRATION 002: Kafka Engine for Candle Events
-- Purpose: Event-driven architecture - trigger Python service on new candles
-- Date: 2026-01-01
-- Phase: 2 - Data Processing & Analytics
-- ============================================

-- ============================================
-- Kafka Engine Table (Target for publishing events)
-- ============================================

DROP TABLE IF EXISTS trading.candles_to_kafka;
CREATE TABLE IF NOT EXISTS trading.candles_to_kafka (
    exchange String,
    symbol String,
    timeframe String,
    candle_time DateTime,
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume Float64,
    quote_volume Float64,
    trades_count UInt32
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'candle-events',
    kafka_group_name = 'clickhouse_candle_publisher',
    kafka_format = 'JSONEachRow',
    kafka_handle_error_mode = 'stream',
    kafka_skip_broken_messages = 10
COMMENT 'Kafka Engine - publishes candle events to candle-events topic';

-- ============================================
-- Materialized Views (Automatic event publishing)
-- ============================================

-- Publish 1m candle events to Kafka
DROP VIEW IF EXISTS trading.candles_1m_to_kafka_mv;
CREATE MATERIALIZED VIEW IF NOT EXISTS trading.candles_1m_to_kafka_mv
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
WHERE is_synthetic = 0;  -- Only publish real candles (not gap-filled)

-- ============================================
-- Kafka Topic Creation
-- ============================================
-- AUTOMATED: Topic 'candle-events' is created automatically by
-- kafka-init service in docker-compose.yml (./kafka/create-topics.sh)
-- No manual intervention needed!

-- Record migration
INSERT INTO trading.schema_migrations (version, name)
VALUES ('002', 'kafka_engine_candle_events');
