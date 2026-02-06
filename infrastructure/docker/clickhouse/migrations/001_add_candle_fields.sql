-- ============================================
-- MIGRATION 001: Add Fields to Candles Tables
-- Purpose: Add quote_volume and is_synthetic fields
-- Date: 2026-01-01
-- Phase: 2 - Data Processing & Analytics
-- ============================================

-- Add quote_volume to candles_1m
ALTER TABLE trading.candles_1m
ADD COLUMN IF NOT EXISTS quote_volume Float64 DEFAULT 0 COMMENT 'Quote asset volume (price × quantity)' CODEC(ZSTD);

-- Add is_synthetic to candles_1m
ALTER TABLE trading.candles_1m
ADD COLUMN IF NOT EXISTS is_synthetic UInt8 DEFAULT 0 COMMENT 'Flag for gap-filled candles (1=synthetic)' CODEC(ZSTD);

-- Update materialized view to include quote_volume
DROP VIEW IF EXISTS trading.candles_1m_mv;
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

-- Record migration
INSERT INTO trading.schema_migrations (version, name)
VALUES ('001', 'add_candle_fields');
