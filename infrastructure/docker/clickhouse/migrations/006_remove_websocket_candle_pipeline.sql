-- ============================================
-- MIGRATION 006: Remove WebSocket Candle Pipeline
-- Purpose: Cleanup MVs and tables not needed in new architecture
-- Date: 2026-02-07
-- Phase: 2 - Architecture Simplification
-- ============================================

-- ============================================
-- Background: Why Remove?
-- ============================================
-- Old architecture: WebSocket trades → MVs → candles_1m → MVs → 5m/1h
-- New architecture: REST API → Sync Service → candles_1m/5m/1h directly
--
-- WebSocket now only feeds Redis for real-time signals.
-- Candles are populated from authoritative exchange REST API.
-- ============================================

-- ============================================
-- Step 1: Drop Kafka Publishing MVs
-- ============================================

DROP VIEW IF EXISTS trading.candles_1m_to_kafka_mv;
DROP VIEW IF EXISTS trading.candles_5m_to_kafka_mv;
DROP VIEW IF EXISTS trading.candles_1h_to_kafka_mv;

-- ============================================
-- Step 2: Drop Candle Aggregation MVs
-- ============================================

DROP VIEW IF EXISTS trading.candles_1m_mv;
DROP VIEW IF EXISTS trading.candles_5m_mv;
DROP VIEW IF EXISTS trading.candles_1h_mv;

-- ============================================
-- Step 3: Drop Kafka Engine Table
-- ============================================

DROP TABLE IF EXISTS trading.candles_to_kafka;

-- ============================================
-- Step 4: Drop Market Trades Table
-- ============================================

-- No longer needed - WebSocket only writes to Redis
DROP TABLE IF EXISTS trading.market_trades;

-- ============================================
-- Step 5: Keep Candle Tables (Populated by Sync Service)
-- ============================================

-- These tables remain, populated by Sync Service from REST API:
-- - trading.candles_1m
-- - trading.candles_5m
-- - trading.candles_1h
-- - trading.indicators

-- Record migration
INSERT INTO trading.schema_migrations (version, name)
VALUES ('006', 'remove_websocket_candle_pipeline');

-- ============================================
-- Verification: Check remaining tables
-- ============================================

-- SHOW TABLES FROM trading;
-- Expected: candles_1m, candles_5m, candles_1h, indicators, schema_migrations, symbol_mappings
