# Service Structure Convention

## Standard Structure

Every microservice in `services/` MUST follow this structure:

```
services/{service_name}/
├── __init__.py              # Package marker (can export main classes)
├── main.py                  # Entry point (CLI/startup) - REQUIRED
├── {core_logic}.py          # Main business logic files
├── config.py                # Service-specific config (optional)
├── models.py                # Service-specific Pydantic models (optional)
├── utils.py                 # Service-specific utilities (optional)
├── tests/                   # Service-specific tests (optional)
│   ├── __init__.py
│   └── test_*.py
└── Dockerfile               # If service is containerized (optional)
```

## Design Principles

1. **main.py = Entry Point Only**
   - CLI argument parsing
   - Service initialization
   - Startup/shutdown logic
   - NO business logic

2. **Flat Structure**
   - Maximum 1 level of subfolders (e.g., `routes/`)
   - Avoid deep nesting

3. **Import from Project Root**
   - Use absolute imports: `from domain.indicators import SMA`
   - Add project root to path in main.py if needed

4. **Separation of Concerns**
   - Business logic → `domain/`
   - Cloud clients → `factory/` + `providers/`
   - Service-specific code → `services/{service_name}/`

5. **Naming Convention**
   - Files: lowercase with underscores (`stream_processor.py`)
   - Classes: PascalCase (`StreamProcessor`)
   - Functions: snake_case (`process_event`)

## Service Type Templates

### Type 1: Event Consumer (Kafka/Stream Consumer)

**Example**: `indicator_service`, `stream_processor`

```
services/indicator_service/
├── __init__.py
├── main.py              # Kafka consumer setup + CLI
├── calculator.py        # Indicator calculation logic
├── persistence.py       # Save to ClickHouse/Redis (optional)
└── Dockerfile
```

**main.py pattern**:
```python
"""
Indicator Service - Kafka Consumer

Consumes candle events, calculates indicators, saves to ClickHouse/Redis
"""
import asyncio
import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import get_settings
from factory.client_factory import create_stream_client, create_timeseries_db
from services.indicator_service.calculator import IndicatorCalculator

logger = logging.getLogger(__name__)

async def main():
    settings = get_settings()

    # Initialize clients
    stream = create_stream_client()
    db = create_timeseries_db()

    # Initialize service
    calculator = IndicatorCalculator(stream, db)

    # Start consuming
    await calculator.start()

if __name__ == "__main__":
    asyncio.run(main())
```

### Type 2: WebSocket Service

**Example**: `market_data_ingestion`

```
services/market_data_ingestion/
├── __init__.py
├── main.py              # Entry point + orchestration
├── websocket_client.py  # WebSocket connections
├── stream_processor.py  # Process & distribute data
└── Dockerfile
```

### Type 3: REST/WebSocket API

**Example**: `trading_api`

```
services/trading_api/
├── __init__.py
├── main.py              # FastAPI app + uvicorn
├── routes/              # API routes (only subfolder allowed)
│   ├── __init__.py
│   ├── prices.py
│   ├── candles.py
│   └── indicators.py
├── dependencies.py      # FastAPI dependency injection
├── middleware.py        # Request/response middleware
└── Dockerfile
```

**main.py pattern**:
```python
"""
Trading API - FastAPI Application
"""
from fastapi import FastAPI
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from services.trading_api.routes import prices, candles, indicators

app = FastAPI(title="Trading API")

# Register routes
app.include_router(prices.router, prefix="/api/v1")
app.include_router(candles.router, prefix="/api/v1")
app.include_router(indicators.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Type 4: Batch Job / Cron

**Example**: `backfill_service`, `daily_report`

```
services/backfill_service/
├── __init__.py
├── main.py              # CLI with argparse
├── backfiller.py        # Backfill logic
└── Dockerfile
```

## Anti-Patterns (DON'T DO THIS)

❌ **Deep nesting**:
```
services/indicator_service/
├── src/
│   ├── core/
│   │   ├── calculators/
│   │   │   └── sma.py   # TOO DEEP!
```

✅ **Flat structure**:
```
services/indicator_service/
├── calculator.py        # All calculation logic here
```

---

❌ **Business logic in main.py**:
```python
# main.py
async def main():
    # ❌ DON'T calculate indicators in main.py
    sma = talib.SMA(closes, 20)
```

✅ **Business logic in separate file**:
```python
# calculator.py
class IndicatorCalculator:
    def calculate_sma(self, candles):
        return talib.SMA(...)

# main.py
async def main():
    calculator = IndicatorCalculator()
    result = calculator.calculate_sma(candles)
```

---

❌ **Cloud-specific imports in service**:
```python
# ❌ DON'T import providers directly
from providers.aws.kinesis import KinesisStreamClient
```

✅ **Use factory pattern**:
```python
# ✅ DO use factory
from factory.client_factory import create_stream_client
stream = create_stream_client()  # Returns Kinesis or Kafka based on config
```

## Logging Convention

All services use standard Python logging:

```python
import logging

# Configure in main.py
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"data/logs/{service_name}.log")
    ]
)
logger = logging.getLogger(__name__)
```

## Dockerfile Convention

If service is containerized:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install -e .

# Copy source
COPY . .

# Run service
CMD ["python", "services/{service_name}/main.py"]
```

## Testing Convention

Service-specific tests go in `services/{service_name}/tests/`:

```python
# services/indicator_service/tests/test_calculator.py
import pytest
from services.indicator_service.calculator import IndicatorCalculator

@pytest.mark.unit
def test_calculate_sma():
    calculator = IndicatorCalculator()
    # Test logic
```

Integration tests go in `tests/integration/`:

```python
# tests/integration/test_indicator_service.py
@pytest.mark.integration
async def test_indicator_service_end_to_end():
    # Test full service flow
```

## Checklist for New Service

- [ ] Create `services/{service_name}/` directory
- [ ] Add `__init__.py`
- [ ] Create `main.py` with entry point
- [ ] Create business logic files (`{core_logic}.py`)
- [ ] Add `Dockerfile` if containerized
- [ ] Configure logging in main.py
- [ ] Add project root to sys.path
- [ ] Use factory pattern for cloud clients
- [ ] Write unit tests in `services/{service_name}/tests/`
- [ ] Write integration tests in `tests/integration/`
- [ ] Update `README.md` with service description

## Examples in This Project

1. ✅ `market_data_ingestion` - WebSocket service
2. ✅ `indicator_service` - Kafka consumer (Phase 2)
3. ✅ `trading_api` - FastAPI REST API (Phase 3)
4. ✅ `stream_processor` - Lambda/function (Phase 1)
