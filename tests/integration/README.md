# Integration Tests - Organized by Concern

This directory contains integration tests organized by concern into clear folders.

## Folder Structure

```
tests/integration/
├── conftest.py                          # Shared fixtures and YAML patching
│
├── factory/                             # 🏭 Factory Pattern (3 tests)
│   ├── test_exchange_factory.py         # Factory wiring only (isinstance checks)
│   └── test_rest_api_network.py         # Network calls (@pytest.mark.external)
│
├── config/                              # ⚙️ Config Loading (2 tests)
│   └── test_indicator_service_config.py # Settings integration
│
├── infrastructure/                      # 🔧 Infrastructure (@pytest.mark.tier2 - 4 tests)
│   ├── clickhouse/
│   │   ├── test_connection.py           # Basic connectivity only
│   │   └── test_connection_pool.py      # Concurrent query handling
│   ├── redis/
│   │   └── test_connection.py           # Basic connectivity only
│   └── docker/
│       └── test_service_readiness.py    # All services reachable
│
├── pipelines/                           # 🚀 Data Flow (@pytest.mark.tier1 - 11 tests)
│   ├── test_rest_api_ingestion.py       # REST API → ClickHouse
│   ├── test_sync_service.py             # 🔥 TIER 1: Sync Service end-to-end
│   ├── test_indicator_pipeline.py       # 🔥 TIER 1: Indicator Service end-to-end
│   ├── test_websocket_ingestion.py      # WebSocket → Redis
│   ├── test_phase2_complete.py          # 🔥🔥🔥 TIER 1 CRITICAL: Full pipeline
│   └── test_grafana_compatibility.py    # Grafana query test
│
└── idempotency/                         # 🔁 Data Quality (@pytest.mark.tier3 - 6 tests)
    ├── test_sync_idempotency.py         # 🔥 TIER 1: No duplicate candles
    ├── test_candle_quality.py           # Gaps, OHLC ranges
    ├── test_indicator_quality.py        # Indicator value ranges
    └── test_cache_consistency.py        # Redis format
```

## Test Tiers

### 🔥🔥🔥 TIER 1 - Production Critical (Must Always Pass)

Run with: `uv run pytest tests/integration/ -v -m tier1`

**4 critical tests:**
1. `pipelines/test_phase2_complete.py::test_full_phase2_pipeline` - Complete Phase 2 validation
2. `pipelines/test_sync_service.py::test_sync_exchange_klines_single_symbol` - Core sync functionality
3. `pipelines/test_indicator_pipeline.py::test_calculate_and_store_indicators` - Indicator calculation
4. `idempotency/test_sync_idempotency.py::test_multiple_sync_cycles_no_duplicates` - ReplacingMergeTree deduplication

These tests validate the complete Phase 2 pipeline and must always pass.

### 🔧 TIER 2 - Infrastructure (Docker Connectivity)

Run with: `uv run pytest tests/integration/ -v -m tier2`

**4 tests:**
- ClickHouse, Redis, PostgreSQL connectivity
- Connection pool handling

These verify Docker services are reachable and working.

### 🔁 TIER 3 - Quality Checks (Data Validation)

Run with: `uv run pytest tests/integration/ -v -m tier3`

**6 tests:**
- Candle timestamp continuity
- Indicator value ranges (RSI 0-100, SMA/EMA positive)
- Redis cache format

These validate data quality and consistency (can be flaky, depends on data).

### 🌐 External - Network Calls (Internet Required)

Run with: `uv run pytest tests/integration/ -v -m external`

**3 tests:**
- Binance, Coinbase, Kraken REST API network calls

Skip in CI with: `pytest -m "not external"`

## Running Tests

### Run all integration tests (skip external)
```bash
uv run pytest tests/integration/ -v -m "integration and not external"
```

### Run by tier (recommended workflow)
```bash
# Step 1: Infrastructure tests (tier2) - Verify Docker setup
uv run pytest tests/integration/ -v -m tier2

# Step 2: Production critical (tier1) - Must pass
uv run pytest tests/integration/ -v -m tier1

# Step 3: Quality checks (tier3) - Advisory
uv run pytest tests/integration/ -v -m tier3
```

### Run specific folder
```bash
# Run only pipeline tests (most important)
uv run pytest tests/integration/pipelines/ -v

# Run only infrastructure tests
uv run pytest tests/integration/infrastructure/ -v
```

### Run CRITICAL test
```bash
uv run pytest tests/integration/pipelines/test_phase2_complete.py::test_full_phase2_pipeline -v -s
```

## Test Coverage

**Total: 36 integration tests**

- Factory: 6 tests (3 wiring + 3 network)
- Config: 2 tests
- Infrastructure: 4 tests
- Pipelines: 18 tests (including TIER 1 critical)
- Idempotency: 6 tests

## Prerequisites

All tests require:
- Docker services running: `make docker-up`
- ClickHouse migrations applied (auto-applied on startup)

Some tests require services running:
- Sync Service: `uv run python services/sync_service/main.py`
- Indicator Service: `uv run python services/indicator_service/main.py`
- WebSocket Service: `uv run python services/market_data_ingestion/main.py`

## CI/CD Strategy

Recommended GitHub Actions / GitLab CI workflow:

```yaml
# Stage 1: Infrastructure check (tier2)
- name: Test infrastructure
  run: uv run pytest tests/integration/ -v -m tier2

# Stage 2: Production critical (tier1) - MUST PASS
- name: Test production critical
  run: uv run pytest tests/integration/ -v -m tier1

# Stage 3: Quality checks (tier3) - Allow failures
- name: Test data quality
  run: uv run pytest tests/integration/ -v -m tier3
  continue-on-error: true

# Skip external tests in CI (rate limits)
- name: All integration tests (skip external)
  run: uv run pytest tests/integration/ -v -m "integration and not external"
```

## Refactoring Notes

This structure was created to organize tests by concern:
- **Before**: 8 files, 36 tests, mixed concerns
- **After**: 5 folders, 16 files, 36 tests, clear separation

**Benefits:**
- Clear organization by concern
- Easy to identify which tests validate critical business logic
- Tiered testing strategy (TIER 1 > TIER 2 > TIER 3)
- Fast test discovery for specific areas
- CI-friendly (can skip slow/external tests)

**Old Files** (to be deleted after verification):
- `test_multi_exchange.py` (moved to unit tests)
- `test_docker_connections.py` (refactored into infrastructure/)
- `test_candles_aggregation.py` (split into pipelines/)
- `test_indicator_service.py` (split into pipelines/ + config/)
- `test_market_data_flow.py` (split by concern)
- `test_phase2_pipeline.py` (split by concern)
- `test_sync_service.py` (split into pipelines/ + factory/)
