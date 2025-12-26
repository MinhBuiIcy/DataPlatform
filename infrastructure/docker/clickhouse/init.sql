-- ============================================
-- CLICKHOUSE INITIALIZATION SCRIPT
-- Phase 1: Foundation & Real-Time Data
-- ============================================

-- Create database
CREATE DATABASE IF NOT EXISTS trading;

-- ============================================
-- TABLE: market_trades
-- Purpose: Store raw market trades from exchanges
-- ============================================
CREATE TABLE IF NOT EXISTS trading.market_trades
(
    timestamp DateTime64(3) CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    trade_id String CODEC(ZSTD),
    price Float64 CODEC(ZSTD),
    quantity Float64 CODEC(ZSTD),
    side Enum8('buy' = 1, 'sell' = 2) CODEC(ZSTD),
    is_buyer_maker UInt8 CODEC(ZSTD)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- TABLE: orderbook_snapshots
-- Purpose: Store periodic orderbook snapshots
-- ============================================
CREATE TABLE IF NOT EXISTS trading.orderbook_snapshots
(
    timestamp DateTime64(3) CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    bids Array(Tuple(Float64, Float64)) CODEC(ZSTD),
    asks Array(Tuple(Float64, Float64)) CODEC(ZSTD),
    checksum UInt64 CODEC(ZSTD)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- TABLE: candles_1m
-- Purpose: 1-minute OHLCV candles (aggregated from trades)
-- ============================================
CREATE TABLE IF NOT EXISTS trading.candles_1m
(
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    open Float64 CODEC(ZSTD),
    high Float64 CODEC(ZSTD),
    low Float64 CODEC(ZSTD),
    close Float64 CODEC(ZSTD),
    volume Float64 CODEC(ZSTD),
    trades_count UInt32 CODEC(ZSTD)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- MATERIALIZED VIEW: Auto-generate 1m candles from trades
-- ============================================
CREATE MATERIALIZED VIEW IF NOT EXISTS trading.candles_1m_mv
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
    count() AS trades_count
FROM trading.market_trades
GROUP BY timestamp, exchange, symbol;

-- ============================================
-- TABLE: indicators
-- Purpose: Store calculated technical indicators (SMA, EMA, RSI, etc.)
-- ============================================
CREATE TABLE IF NOT EXISTS trading.indicators
(
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    timeframe LowCardinality(String) CODEC(ZSTD),
    indicator_name LowCardinality(String) CODEC(ZSTD),
    indicator_value Float64 CODEC(ZSTD)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timeframe, indicator_name, timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- TABLE: strategy_signals
-- Purpose: Store trading signals from strategies
-- ============================================
CREATE TABLE IF NOT EXISTS trading.strategy_signals
(
    timestamp DateTime64(3) CODEC(Delta, ZSTD),
    strategy_id LowCardinality(String) CODEC(ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    signal_type Enum8('buy' = 1, 'sell' = 2, 'hold' = 3) CODEC(ZSTD),
    confidence Float32 CODEC(ZSTD),
    price Float64 CODEC(ZSTD),
    metadata String CODEC(ZSTD)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (strategy_id, exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ============================================
-- TABLE: symbol_mappings
-- Purpose: Multi-exchange symbol normalization for price comparison
-- ============================================
CREATE TABLE IF NOT EXISTS trading.symbol_mappings
(
    base_asset LowCardinality(String) COMMENT 'Normalized asset symbol (BTC, ETH, etc)',
    quote_asset LowCardinality(String) COMMENT 'Quote currency (USDT, USD, etc)',
    exchange LowCardinality(String) COMMENT 'Exchange name (binance, coinbase, kraken)',
    symbol String COMMENT 'Exchange-specific symbol (BTCUSDT, BTC-USD, XBT/USD)',
    created_at DateTime DEFAULT now() COMMENT 'Record creation timestamp'
)
ENGINE = MergeTree()
ORDER BY (base_asset, quote_asset, exchange)
COMMENT 'Symbol normalization mapping for multi-exchange comparison';

-- ============================================
-- Verification queries
-- ============================================
SHOW TABLES FROM trading;

SELECT
    name,
    engine,
    partition_key,
    sorting_key,
    formatReadableSize(total_bytes) AS size
FROM system.tables
WHERE database = 'trading'
ORDER BY name;
