# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Algorithmic Trading Platform - A cloud-native, multi-exchange cryptocurrency market data platform with real-time streaming, analytics, and ML capabilities. Built for local development with LocalStack/Docker and production deployment to AWS/GCP/Azure.

**Current Phase**: Phase 2 Complete (OHLCV Candles + Technical Indicators via Scheduled Jobs)

## Development Commands

### Dependency Management
This project uses **uv** (not pip):
```bash
uv sync                      # Install dependencies
uv add <package-name>        # Add new dependency
# Update pyproject.toml, NOT requirements.txt
```

### Testing
```bash
# Unit tests (fast, no Docker required)
uv run pytest tests/unit/ -v -m unit

# Integration tests (requires Docker + Terraform)
uv run pytest tests/integration/ -v -m integration

# Skip slow tests
uv run pytest -m "not slow"

# Single test file
uv run pytest tests/unit/indicators/test_moving_averages.py -v

# With coverage
uv run pytest --cov=. --cov-report=html
```

### Infrastructure

**Docker Services** (ClickHouse, Redis, PostgreSQL, Grafana):
```bash
make docker-up              # Start all services
make docker-down            # Stop services
make docker-ps              # Check status
make docker-logs            # View logs
make docker-clean           # Remove all data (CAUTION!)
```

**Terraform** (LocalStack/AWS resources: S3, Kinesis):
```bash
make terraform-init         # Initialize
make terraform-plan         # Preview changes
make terraform-apply        # Deploy (creates .env.terraform)
make terraform-destroy      # Tear down
```

**Complete Setup**:
```bash
make setup-local            # Docker + Terraform in one command
```

### Running Services (Phase 2)

**Critical**: Run in this order to ensure proper data flow:

```bash
# Terminal 1: Market Data Ingestion (WebSocket → Redis signals)
uv run python services/market_data_ingestion/main.py
# Real-time price updates, NOT authoritative candles

# Terminal 2: Sync Service (REST API → ClickHouse candles)
uv run python services/sync_service/main.py
# Runs every 60s, fetches latest klines from exchange REST API
# Initial backfill: 100 candles on startup

# Terminal 3: Indicator Service (ClickHouse → Calculate → Redis/ClickHouse)
uv run python services/indicator_service/main.py
# Runs every 60s (+10s delay after sync)
# Catch-up mode: Processes all historical candles on startup
# Calculates: SMA 20/50, EMA 12/26, RSI, MACD
```

**Access Points**:
- Grafana: http://localhost:3000 (admin/admin)
- ClickHouse: http://localhost:8123
- Redis: localhost:6379
- PostgreSQL: localhost:5432

## Architecture Patterns

### 1. Cloud-Agnostic Abstraction Layer

**Dependency Flow**:
```
services/ → domain/ → factory/ → providers/ → core/interfaces/
                         ↓
                     config/
```

**Key Principle**: Business logic never imports cloud-specific code directly.

**Core Abstractions** (`core/interfaces/`):
- `BaseStreamClient` - Kinesis, Kafka, PubSub
- `BaseStorageClient` - S3, GCS, Blob Storage
- `BaseCacheClient` - Redis, Memcached
- `BaseTimeSeriesDB` - ClickHouse, TimescaleDB
- `BaseExchangeWebSocket` - Binance, Coinbase, Kraken
- `BaseExchangeRestAPI` - Exchange REST APIs (Phase 2)

**Concrete Implementations** (`providers/`):
- `providers/aws/` - AWS services
- `providers/opensource/` - ClickHouse, Redis, Kafka
- `providers/binance/` - Binance WebSocket + REST API
- `providers/coinbase/` - Coinbase WebSocket + REST API
- `providers/kraken/` - Kraken WebSocket + REST API

### 2. Factory Pattern for Dependency Injection

**Always use factories** (located in `factory/client_factory.py`):

```python
# ✅ CORRECT - Cloud-agnostic
from factory.client_factory import (
    create_exchange_rest_api,
    create_timeseries_db,
    create_cache_client
)
api = create_exchange_rest_api("binance")  # Returns BinanceRestAPI
db = create_timeseries_db()  # Returns ClickHouseClient
cache = create_cache_client()  # Returns RedisClient

# ❌ WRONG - Direct import creates vendor lock-in
from providers.binance.rest_api import BinanceRestAPI
api = BinanceRestAPI()
```

**Available Factories**:
- `create_exchange_rest_api(name)` - REST API clients (ccxt-based)
- `create_exchange_websockets()` - WebSocket clients (multi-exchange)
- `create_timeseries_db()` - Database (ClickHouse with queues)
- `create_cache_client()` - Cache (Redis with queues)
- `create_stream_client()` - Streaming (Kinesis/Kafka)
- `create_storage_client()` - Object storage (S3)

### 3. Configuration Management

**Multi-layered Config System**:

1. **`.env` file** - Secrets, credentials, endpoints (Pydantic Settings)
   ```python
   from config.settings import get_settings
   settings = get_settings()  # Singleton pattern
   print(settings.CLICKHOUSE_PASSWORD)  # From .env
   ```

2. **YAML configs** (`config/providers/`) - Service/provider settings
   ```python
   from config.loader import get_enabled_exchanges
   exchanges = get_enabled_exchanges()  # Returns only enabled exchanges
   ```

**YAML Configuration Files**:
- `exchanges.yaml` - WebSocket + REST API settings per exchange
- `sync.yaml` - Sync Service timing, REST API config
- `indicators.yaml` - Indicator definitions + service settings
- `databases.yaml` - ClickHouse, Redis, PostgreSQL connection params
- `streaming.yaml` - Kafka/Kinesis topics (reserved for Phase 3+)

**Container Mode**: Settings default to Docker service names:
```python
CLICKHOUSE_HOST = "clickhouse"  # Not "localhost" - Docker network hostname
REDIS_HOST = "redis"
POSTGRES_HOST = "postgres"
```

**CRITICAL GOTCHA - Settings Singleton Reset**:
```python
# When testing config changes, reset the singleton
from config.settings import Settings
if hasattr(Settings, '_yaml_loaded'):
    delattr(Settings, '_yaml_loaded')
settings = get_settings()  # Now reloads from YAML
```

### 4. Phase 2 Data Flow Architecture

**Industry Standard: Scheduled Jobs (NOT Event-Driven)**

```
Exchange REST API (ccxt library - authoritative source)
    ↓
┌───────────────────────────────────────────────────────┐
│ Sync Service (every 60 seconds)                       │
│  - Initial backfill: 100 candles on startup           │
│  - Regular sync: 5 latest candles per timeframe       │
│  - Sequential processing (avoid ClickHouse conflicts) │
└────────────────────┬──────────────────────────────────┘
                     ↓
    ClickHouse (candles_1m, candles_5m, candles_1h)
    ReplacingMergeTree - auto-deduplication
                     ↓
┌───────────────────────────────────────────────────────┐
│ Indicator Service (every 60s + 10s delay)             │
│  - Catch-up mode: Process all historical candles      │
│  - Query latest 200 candles from ClickHouse           │
│  - Calculate: SMA, EMA, RSI, MACD, Stochastic         │
│  - Save to ClickHouse + Redis (60s TTL)               │
└────────────────────┬──────────────────────────────────┘
                     ↓
        Grafana Dashboard (technical-analysis)
        4 panels: Price+Indicators, RSI, MACD, Volume


Separate Pipeline (Real-time signals only):
┌───────────────────────────────────────────────────────┐
│ Exchange WebSocket (Binance, Coinbase, Kraken)        │
│  - 60+ symbols, real-time trade events                │
│  - Samples ~4% of trades (NOT authoritative)          │
└────────────────────┬──────────────────────────────────┘
                     ↓
                Redis (latest_price:{exchange}:{symbol})
                Real-time signals for strategies (Phase 3+)
```

**Why REST API over WebSocket for Candles?**
- WebSocket captures only ~4% of trades (sampling)
- Exchange REST API is authoritative, complete OHLCV data
- Simpler: No gap handling, no deduplication complexity
- Industry standard: QuantConnect, TradingView, ccxt all use REST for candles

**Why Scheduled Jobs over Event-Driven?**
- Simpler: 60-second loops, predictable execution
- Easier debugging: No Kafka consumer complexity
- No gap handling needed: Sync Service ensures continuity
- Event-driven reserved for Phase 3+ (trading strategies)

### 5. ClickHouse Connection Patterns (CRITICAL)

**Single Connection Limitation**:
```python
# ClickHouse driver is SYNCHRONOUS, used via asyncio.to_thread()
# ONLY ONE query at a time per connection!

# ❌ WRONG - Causes "Simultaneous queries on single connection" error
async def process_parallel(symbols):
    tasks = [db.query_candles(symbol) for symbol in symbols]
    await asyncio.gather(*tasks)  # Multiple queries on same connection!

# ✅ CORRECT - Sequential processing
async def process_sequential(symbols):
    for symbol in symbols:
        candles = await db.query_candles(symbol)  # One at a time
        await process_candles(candles)
```

**Why Sequential?**
- `clickhouse_driver.Client` doesn't support connection pooling
- All async operations use `asyncio.to_thread(self.client.execute, ...)`
- Same connection = must be sequential

**Implemented in**:
- `services/sync_service/main.py` - Sequential fetch per exchange/symbol
- `services/indicator_service/main.py` - Sequential queries + saves
- `providers/opensource/clickhouse.py` - Wraps sync driver in async

### 6. Indicator Calculation Patterns

**Avoid Re-Querying Database**:
```python
# ❌ WRONG - Re-queries database for each candle
async def process_candle(candle):
    candles = await db.query_candles(...)  # Wasteful!
    indicators = calculate(candles)

# ✅ CORRECT - Pass pre-fetched historical data
async def process_candle_with_history(candle, historical_candles):
    """
    Args:
        candle: Current candle to calculate indicators for
        historical_candles: Pre-fetched list (e.g., last 200 candles)
    """
    if len(historical_candles) < 20:
        return  # Need minimum history

    results = {}
    for indicator in indicators:
        value = indicator.get_results(historical_candles)
        results.update(value)

    await persistence.save_indicators(candle, results)
```

**Warm-Up Periods** (from `config/providers/indicators.yaml`):
- SMA: Requires `period` candles (e.g., SMA_50 needs 50)
- EMA: Needs ~4× period for convergence (EMA_50 → 200 candles)
- RSI: ~30+ candles for accuracy
- MACD: ~50+ candles (slow_period + signal_period)
- Config: `candle_lookback: 200` (safe default for all)

### 7. Database Schema Optimization

**ClickHouse Tables** (Phase 2):

`trading.candles_1m`, `trading.candles_5m`, `trading.candles_1h`:
```sql
ENGINE = ReplacingMergeTree()  -- Auto-deduplication on merge
ORDER BY (exchange, symbol, timestamp)  -- Exchange-first for multi-exchange queries
PARTITION BY toYYYYMM(timestamp)  -- Monthly partitions
TTL toDateTime(timestamp) + INTERVAL 90 DAY  -- Auto-cleanup
```

`trading.indicators`:
```sql
ENGINE = ReplacingMergeTree()
ORDER BY (exchange, symbol, timeframe, timestamp, indicator_name)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY
```

**What was REMOVED in Phase 2**:
- `market_trades` table (WebSocket trades no longer stored)
- All Materialized Views (candles_1m_mv, candles_5m_mv, etc.)
- Kafka Engine tables (candles_to_kafka)
- Migration 006 cleaned up WebSocket pipeline

**Key Pattern - ReplacingMergeTree**:
```python
# Same (exchange, symbol, timestamp) = replacement, not duplicate
await db.insert_candles([candle1, candle2, ...])
# If candle1.timestamp already exists → replaced (not duplicated)
```

## Code Organization Rules

### Where to Put New Code

**Cloud-agnostic abstractions** → `core/`
- Interfaces/ABCs: `core/interfaces/`
- Data models (Pydantic): `core/models/`
- Validators: `core/validators/` (NOT `services/validators/`)

**Cloud provider implementations** → `providers/`
- AWS: `providers/aws/`
- Open-source: `providers/opensource/`
- Exchanges: `providers/{exchange_name}/`

**Business logic** → `domain/`
- Indicators: `domain/indicators/`
- Strategies: `domain/strategies/` (Phase 3+)
- Risk management: `domain/risk/` (Phase 3+)

**Microservices** → `services/`
- Sync Service: `services/sync_service/`
- Indicator Service: `services/indicator_service/`
- Market Data Ingestion: `services/market_data_ingestion/`

**Config files** → `config/`
- Settings class: `config/settings.py`
- YAML configs: `config/providers/*.yaml`
- Loaders: `config/loader.py`

### When Adding New Exchange

1. Create `providers/{exchange}/rest_api.py` inheriting from `BaseExchangeRestAPI`
2. Create `providers/{exchange}/websocket.py` inheriting from `BaseExchangeWebSocket`
3. Add exchange config to `config/providers/exchanges.yaml`
4. Update `factory/client_factory.py` to instantiate it
5. No changes to services layer needed (factory handles it)

### When Adding New Technical Indicator

1. Create indicator class in `domain/indicators/` (e.g., `volatility.py`)
2. Inherit from `BaseIndicator` in `domain/indicators/base.py`
3. Implement `calculate(candles)` and `get_results(candles)` methods
4. Register in `domain/indicators/registry.py`
5. Add to `config/providers/indicators.yaml`
6. No changes to indicator service needed (loads from config)

## Common Gotchas

### 1. Settings Singleton Caching
```python
# Problem: YAML configs cached at class level
# Solution: Delete cache when testing config changes
if hasattr(Settings, '_yaml_loaded'):
    delattr(Settings, '_yaml_loaded')
```

### 2. ClickHouse Sequential Queries
```python
# Problem: "Simultaneous queries on single connection"
# Solution: Use sequential loops, NOT asyncio.gather()
for item in items:
    await db.query(...)  # Sequential
```

### 3. Indicator Warm-Up Periods
```python
# Problem: Not enough historical candles for calculation
# Solution: Check minimum candles before calculating
min_candles = settings.INDICATOR_SERVICE_MIN_CANDLES  # Default: 20
if len(candles) < min_candles:
    return  # Skip calculation
```

### 4. Docker Network Hostnames
```python
# Problem: Using localhost instead of Docker service names
CLICKHOUSE_HOST = "localhost"  # ❌ Wrong in Docker

# Solution: Use Docker service names from databases.yaml
CLICKHOUSE_HOST = "clickhouse"  # ✅ Correct
```

### 5. Hardcoded Configs
```python
# ❌ WRONG - Hardcoded values
timeout = 30000
limit = 100

# ✅ CORRECT - Use settings from YAML
timeout = settings.REST_API_TIMEOUT_MS  # From sync.yaml
limit = settings.SYNC_INITIAL_BACKFILL_LIMIT  # From sync.yaml
```

## Grafana Dashboard Management

**Auto-provisioning**:
- Dashboard JSONs: `monitoring/grafana/dashboards/*.json`
- Config: `monitoring/grafana/dashboards/dashboards.yml`
- Auto-loaded on Grafana startup via Docker volume mount

**After editing dashboard JSON**:
```bash
# Validate JSON syntax
python3 -m json.tool monitoring/grafana/dashboards/technical-analysis.json

# Restart Grafana to reload
docker restart trading-grafana
```

**Current Dashboard**: `technical-analysis.json`
- Panel 1: Price + Indicators (candlestick with SMA/EMA overlays)
- Panel 2: RSI (0-100 range with overbought/oversold zones)
- Panel 3: MACD (histogram + signal line)
- Panel 4: Volume (bar chart)

## Testing Strategy

**Test Markers**:
- `@pytest.mark.unit` - Fast, mocked dependencies
- `@pytest.mark.integration` - Requires Docker services
- `@pytest.mark.slow` - Long-running (>10s)

**Integration Test Requirements**:
1. Start Docker: `make docker-up`
2. Apply Terraform: `make terraform-apply`
3. Run tests: `uv run pytest -m integration`

**Test Coverage** (Phase 2):
- 63+ unit tests passing
- Integration tests for multi-exchange ingestion
- Indicator calculation tests (SMA, EMA, RSI, MACD)

## Environment Files

**DO NOT commit**:
- `.env` - Local secrets (gitignored)
- `.env.terraform` - Auto-generated from Terraform

**DO commit**:
- `.env.example` - Template for team

**Terraform Workflow**:
```bash
make terraform-apply  # Creates .env.terraform
# Copy values to .env manually or use env vars
```

## Phase Status

**Phase 1** (✅ Completed):
- Multi-exchange WebSocket ingestion
- 60+ symbols across Binance, Coinbase, Kraken
- Data quality validation (spike detection)
- YAML-based configuration

**Phase 2** (✅ Completed):
- REST API klines fetching (authoritative candles)
- Scheduled sync service (every 60s)
- Technical indicators (SMA, EMA, RSI, MACD)
- Grafana technical analysis dashboard
- Initial backfill + catch-up mode

**Phase 3** (Next):
- Trading API (FastAPI)
- Strategy framework
- Paper trading simulator
- RabbitMQ for order execution

**Phase 4-6** (Future):
- Backtesting engine
- ML/AI integration
- Production monitoring
