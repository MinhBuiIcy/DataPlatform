# ClickHouse Migrations

## Migration Strategy

**Phase 1-2**: Manual SQL migrations
**Phase 6**: Consider golang-migrate tool

## File Naming Convention

```
{version}_{description}.sql

Examples:
000_migration_tracker.sql
001_add_candle_fields.sql
002_kafka_engine.sql
```

## Applying Migrations (Manual)

```bash
# 1. Apply migration
docker exec -i trading-clickhouse clickhouse-client < migrations/001_add_candle_fields.sql

# 2. Verify
docker exec trading-clickhouse clickhouse-client --query "SELECT * FROM trading.schema_migrations ORDER BY version"
```

## Current Schema State

**Baseline** (`init.sql` - fresh installs):
- ✅ database: trading
- ✅ market_trades
- ✅ orderbook_snapshots
- ✅ candles_1m (basic - no quote_volume, is_synthetic)
- ✅ candles_1m_mv
- ✅ indicators (basic)
- ✅ strategy_signals
- ✅ symbol_mappings

**Applied Migrations**:
- [x] 000: Migration tracker
- [x] 001: ALTER candles_1m (add quote_volume, is_synthetic)
- [x] 002: CREATE Kafka Engine for candle events (auto-creates via kafka-init service)
- [x] 003: UPDATE indicators table (MergeTree → ReplacingMergeTree, remove TTL)

**Note**: Kafka topics are auto-created by `kafka-init` service in docker-compose.yml.
See `infrastructure/docker/kafka/create-topics.sh` for topic configuration.
