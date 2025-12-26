# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Algorithmic Trading Platform - A cloud-native, multi-exchange cryptocurrency market data platform with real-time streaming, analytics, and ML capabilities. Built for local development with LocalStack/Docker and production deployment to AWS/GCP/Azure.

**Current Phase**: Phase 1 Advanced (Multi-exchange real-time data ingestion)

## Development Commands

### Dependency Management
This project uses **uv** (not pip):
```bash
# Install dependencies
uv sync

# Add new dependency
uv add <package-name>

# Update pyproject.toml, NOT requirements.txt
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test markers
pytest -m unit              # Fast unit tests only
pytest -m integration       # Integration tests (requires Docker)
pytest -m "not slow"        # Skip slow tests

# Run single test file
pytest tests/integration/test_multi_exchange.py -v

# Run single test function
pytest tests/integration/test_multi_exchange.py::test_yaml_config_loading -v

# With coverage
pytest --cov=. --cov-report=html
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

### Running Services

**Market Data Ingestion** (Multi-exchange WebSocket → Kinesis/S3/ClickHouse/Redis):
```bash
python services/market_data_ingestion/main.py
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

**Concrete Implementations** (`providers/`):
- `providers/aws/` - AWS services
- `providers/opensource/` - ClickHouse, Redis, Kafka
- `providers/binance/` - Binance WebSocket
- `providers/coinbase/` - Coinbase WebSocket
- `providers/kraken/` - Kraken WebSocket

### 2. Factory Pattern for Dependency Injection

**Always use factories** (located in `factory/client_factory.py`):

```python
# ✅ CORRECT - Cloud-agnostic
from factory.client_factory import create_stream_client, create_cache_client
stream_client = create_stream_client()  # Returns Kinesis or Kafka based on config

# ❌ WRONG - Direct import creates vendor lock-in
from providers.aws.kinesis import KinesisStreamClient
stream_client = KinesisStreamClient()
```

**Available Factories**:
- `create_stream_client()` - Streaming (Kinesis/Kafka)
- `create_cache_client()` - Cache (Redis)
- `create_timeseries_db()` - Database (ClickHouse)
- `create_storage_client()` - Object storage (S3)
- `create_exchange_websockets()` - Exchange clients (multi-exchange)

### 3. Configuration Management

**Multi-layered Config System**:

1. **`.env` file** - Secrets, credentials, endpoints (Pydantic Settings)
   ```python
   from config.settings import get_settings
   settings = get_settings()  # Singleton pattern
   ```

2. **YAML configs** (`config/providers/`) - Exchange/provider settings
   ```python
   from config.loader import get_enabled_exchanges
   exchanges = get_enabled_exchanges()  # Returns only enabled exchanges
   ```

**Container Mode**: Settings default to Docker service names:
```python
CLICKHOUSE_HOST = "clickhouse"  # Not "localhost" - Docker network hostname
REDIS_HOST = "redis"
POSTGRES_HOST = "postgres"
```

### 4. Data Flow Architecture

**Phase 1 Multi-Exchange Ingestion**:
```
┌─ Binance WebSocket (config/providers/exchanges.yaml)
├─ Coinbase WebSocket
└─ Kraken WebSocket
    ↓
  BaseExchangeWebSocket (core/interfaces/market_data.py)
    ↓
  DataValidator (core/validators/market_data.py)
    ↓
  StreamProcessor (services/market_data_ingestion/stream_processor.py)
    ├─→ Kinesis (ephemeral streaming, 24h retention)
    ├─→ S3 (raw data backup, partitioned by exchange/symbol/date)
    ├─→ ClickHouse (long-term OLAP analytics)
    └─→ Redis (hot cache for latest prices)
```

**Key Design Decisions**:
- In-memory buffers for batching (Phase 1-5), not Redis (1000x faster)
- Validation before processing (spike detection, data quality)
- Kinesis for Phase 1 (LocalStack support), Kafka for Phase 6 (production)

### 5. Database Schema Optimization

**ClickHouse Tables**:

`trading.market_trades`:
```sql
ORDER BY (exchange, symbol, timestamp)  # Exchange-first for multi-exchange filtering
PARTITION BY toYYYYMM(timestamp)         # Monthly partitions
TTL toDateTime(timestamp) + INTERVAL 90 DAY
```

`trading.orderbook_snapshots`:
```sql
bids Array(Tuple(Float64, Float64))     # [(price, qty), ...]
asks Array(Tuple(Float64, Float64))
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 30 DAY  # Shorter TTL (high-frequency data)
```

**Computed Fields**: Calculate at query time, not stored:
```sql
SELECT
    bids[1].1 AS best_bid,
    asks[1].1 AS best_ask,
    asks[1].1 - bids[1].1 AS spread,
    (asks[1].1 + bids[1].1) / 2 AS mid_price
FROM trading.orderbook_snapshots
```

## Code Organization Rules

### Where to Put New Code

**Cloud-agnostic abstractions** → `core/`
- Interfaces/ABCs: `core/interfaces/`
- Data models (Pydantic): `core/models/`
- Validators: `core/validators/`

**Cloud provider implementations** → `providers/`
- AWS: `providers/aws/`
- Open-source alternatives: `providers/opensource/`
- Exchange-specific: `providers/{exchange_name}/`

**Business logic** → `domain/`
- Trading strategies: `domain/strategies/`
- Technical indicators: `domain/indicators/`
- Risk management: `domain/risk/`

**Microservices** → `services/`
- Market data ingestion: `services/market_data_ingestion/`
- Trading API: `services/trading_api/`

**Config files** → `config/`
- Python settings: `config/settings.py`
- YAML configs: `config/providers/exchanges.yaml`

### When Adding New Exchange

1. Create `providers/{exchange}/websocket.py` inheriting from `BaseExchangeWebSocket`
2. Add exchange config to `config/providers/exchanges.yaml`
3. Update `factory/client_factory.py::create_exchange_websockets()` to instantiate it
4. No changes to services layer needed (factory handles it)

### Validator Location Convention

User correction from session: Validators MUST be in `core/validators/`, NOT `services/validators/`
- Reason: Validators are cloud-agnostic reusable logic
- Pattern: Same as `core/interfaces/`, `core/models/`

## Grafana Dashboard Management

**Auto-provisioning**:
- Dashboard JSONs: `monitoring/grafana/dashboards/*.json`
- Config: `monitoring/grafana/dashboards/dashboards.yml`
- Auto-loaded on Grafana startup via Docker volume mount

**After editing dashboard JSON**:
```bash
# Validate JSON syntax
python3 -m json.tool monitoring/grafana/dashboards/multi-exchange.json

# Restart Grafana to reload
docker restart trading-grafana
```

**Common JSON errors**:
- Trailing commas in arrays: `]` not `},]`
- Arrays closed with `}` instead of `]`

## Common Patterns

### Async/Await

All I/O operations are async:
```python
async def process_trade(self, trade: Trade) -> None:
    await self.kinesis.send(trade)
    await self.clickhouse.insert_trades([trade.to_dict()])
    await self.redis.set(f"price:{trade.symbol}", trade.price)
```

### Error Handling with Retry

Use built-in retry decorators (when available) or implement exponential backoff:
```python
from core.utils.retry import retry_with_backoff

@retry_with_backoff(max_retries=3)
async def send_to_kinesis(self, data):
    # Will auto-retry on failure
    pass
```

### Datetime Handling

**IMPORTANT**: Use timezone-aware datetimes:
```python
from datetime import datetime, timezone

# ✅ CORRECT
now = datetime.now(timezone.utc)

# ❌ WRONG (deprecated)
now = datetime.utcnow()
```

## Testing Strategy

**Test Markers**:
- `@pytest.mark.unit` - Fast, mocked dependencies
- `@pytest.mark.integration` - Requires Docker services
- `@pytest.mark.slow` - Long-running (>10s)

**Integration Test Requirements**:
1. Start Docker services: `make docker-up`
2. Apply Terraform: `make terraform-apply`
3. Run tests: `pytest -m integration`

**Test File Naming**:
- Unit: `tests/unit/test_*.py`
- Integration: `tests/integration/test_*.py`

## Environment Files

**DO NOT commit** `.env` files:
- `.env.example` - Template (committed)
- `.env` - Local secrets (gitignored)
- `.env.terraform` - Auto-generated from Terraform outputs

**Terraform Workflow**:
```bash
make terraform-apply              # Creates resources in LocalStack
# Outputs to .env.terraform
# Copy values to .env manually
```

## Phase 1 Status

**Completed**:
- ✅ Multi-exchange support (Binance, Coinbase, Kraken)
- ✅ 20+ symbols per exchange (60 total pairs)
- ✅ Order book depth data
- ✅ Data quality validation (spike detection)
- ✅ YAML-based configuration
- ✅ Factory pattern
- ✅ Integration tests (9 test cases)
- ✅ Grafana multi-exchange dashboard

**Deferred to Phase 6**:
- Kafka Connect (alternative to Kinesis + manual code)
- Redis-based buffering (using in-memory for Phase 1-5)

## Project Phases

See `README.md` for detailed phase breakdown. Key phases:

1. **Phase 1**: Real-time data ingestion ← **CURRENT**
2. **Phase 2**: Data processing & analytics (OHLCV candles, indicators)
3. **Phase 3**: Trading API & strategy framework
4. **Phase 4**: Backtesting engine
5. **Phase 5**: ML/AI integration
6. **Phase 6**: Production-ready features (monitoring, HA, multi-region)
