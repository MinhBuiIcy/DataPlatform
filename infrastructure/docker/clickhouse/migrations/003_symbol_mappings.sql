-- ============================================
-- MIGRATION 003: Symbol Mappings Table
-- Purpose: Multi-exchange symbol normalization
-- Date: 2025-12-25
-- ============================================

-- Drop if exists (for clean migration)
DROP TABLE IF EXISTS trading.symbol_mappings;

-- Create symbol mappings table
CREATE TABLE IF NOT EXISTS trading.symbol_mappings (
    base_asset LowCardinality(String) COMMENT 'Normalized asset symbol (BTC, ETH, etc)',
    quote_asset LowCardinality(String) COMMENT 'Quote currency (USDT, USD, etc)',
    exchange LowCardinality(String) COMMENT 'Exchange name (binance, coinbase, kraken)',
    symbol String COMMENT 'Exchange-specific symbol (BTCUSDT, BTC-USD, XBT/USD)',
    created_at DateTime DEFAULT now() COMMENT 'Record creation timestamp'
) ENGINE = MergeTree()
ORDER BY (base_asset, quote_asset, exchange)
COMMENT 'Symbol normalization mapping for multi-exchange comparison';

-- Create indexes for fast lookups
-- Primary key already covers (base_asset, quote_asset, exchange)

-- Sample data will be loaded via scripts/load_symbol_mappings.py
