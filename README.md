# 🚀 Algorithmic Trading Platform

A production-ready, cloud-native algorithmic trading platform built with modern data engineering and ML technologies. Real-time crypto market data processing, strategy backtesting, and automated trading execution.

## 🎯 Project Overview

This platform demonstrates advanced technical skills in:

- **Stream Processing**: Real-time market data ingestion and processing
- **Time-Series Analytics**: High-performance OLAP queries on billions of ticks
- **Machine Learning**: Price prediction and trading signal generation
- **Distributed Systems**: Event-driven microservices architecture
- **Cloud-Native Development**: LocalStack for AWS services, managed databases
- **DevOps**: Infrastructure as Code, local → cloud portability

**Tech Stack:**

- **AWS Services (LocalStack)**: S3, Kinesis, Lambda, DynamoDB, EventBridge, SQS
- **Stateful Services**: ClickHouse, Redis, PostgreSQL (Docker or Cloud Managed)
- **Application Layer**: FastAPI, Python, MLflow, Jupyter
- **Monitoring**: Grafana, Prometheus

---

## 📊 Architecture

### Local Development (LocalStack + Docker)

```
Binance/Coinbase WebSocket
    ↓
AWS Kinesis (LocalStack) / Kafka (Docker)
    ↓
Lambda Functions (LocalStack) / Python Services
    ↓
├── S3 (LocalStack) - Raw data storage
├── ClickHouse (Docker/Cloud) - Time-series OLAP
├── Redis (Docker/Cloud) - Caching & state
├── PostgreSQL (Docker/Cloud) - Metadata
└── DynamoDB (LocalStack) - Alternative NoSQL
    ↓
├── Strategy Engine (Lambda or Python service)
├── ML Pipeline (SageMaker Local / Jupyter)
└── FastAPI (API Gateway LocalStack + Lambda)
    ↓
├── EventBridge (LocalStack) - Event orchestration
├── Grafana (Docker) - Real-time monitoring
└── CloudWatch (LocalStack) - Logs & metrics
```

### Cloud Production (Same code, different endpoints)

```
Replace LocalStack endpoints with real AWS services
- LocalStack S3 → AWS S3
- LocalStack Kinesis → AWS Kinesis
- LocalStack Lambda → AWS Lambda
- Docker ClickHouse → ClickHouse Cloud
- Docker Redis → AWS ElastiCache
```

---

## 📁 Project Structure

```
DataPlatform/
│
├── 📁 config/                           # Configuration Management
│   ├── __init__.py
│   ├── settings.py                      # Pydantic Settings (from .env)
│   ├── base.py                          # Base config classes
│   │
│   ├── environments/                    # Environment-specific configs
│   │   ├── local.yaml                   # LocalStack + Docker
│   │   ├── dev.yaml
│   │   ├── staging.yaml
│   │   └── production.yaml
│   │
│   └── providers/                       # Cloud provider configs
│       ├── aws.yaml
│       ├── gcp.yaml
│       ├── azure.yaml
│       └── localstack.yaml
│
├── 📁 core/                             # Core Abstractions (Cloud-agnostic)
│   ├── __init__.py
│   │
│   ├── interfaces/                      # Abstract Base Classes
│   │   ├── storage.py                   # BaseStorageClient (S3, GCS, Blob)
│   │   ├── streaming.py                 # BaseStreamClient (Kinesis, Kafka, Pub/Sub)
│   │   ├── cache.py                     # BaseCacheClient (Redis, Memcached)
│   │   ├── database.py                  # BaseTimeSeriesDB (ClickHouse, TimescaleDB)
│   │   ├── queue.py                     # BaseQueueClient (SQS, Cloud Tasks)
│   │   ├── pubsub.py                    # BasePubSubClient (SNS, Pub/Sub)
│   │   ├── secrets.py                   # BaseSecretsManager
│   │   └── serverless.py                # BaseFunctionClient (Lambda, Cloud Functions)
│   │
│   ├── models/                          # Data Models (Pydantic)
│   │   ├── market_data.py               # Tick, Candle, OrderBook models
│   │   ├── trading.py                   # Order, Position, Trade models
│   │   ├── strategy.py                  # Strategy, Signal models
│   │   └── events.py                    # Event schemas
│   │
│   ├── exceptions/                      # Custom Exceptions
│   │   ├── base.py                      # BasePlatformException
│   │   ├── storage.py                   # StorageException
│   │   ├── streaming.py                 # StreamException
│   │   ├── trading.py                   # InsufficientBalance, InvalidOrder
│   │   └── market_data.py               # MarketDataException
│   │
│   └── utils/                           # Shared Utilities
│       ├── logger.py                    # Structured logging (JSON)
│       ├── retry.py                     # Retry with exponential backoff
│       ├── circuit_breaker.py           # Circuit breaker pattern
│       ├── time_utils.py                # Timezone, timestamp utils
│       ├── validation.py                # Data validation
│       └── metrics.py                   # Prometheus metrics
│
├── 📁 providers/                        # Cloud Provider Implementations
│   ├── __init__.py
│   │
│   ├── aws/                             # AWS Services
│   │   ├── s3.py                        # S3StorageClient
│   │   ├── kinesis.py                   # KinesisStreamClient
│   │   ├── dynamodb.py                  # DynamoDBClient
│   │   ├── sqs.py                       # SQSQueueClient
│   │   ├── sns.py                       # SNSPubSubClient
│   │   ├── lambda_client.py             # LambdaClient
│   │   ├── secrets_manager.py           # AWSSecretsManager
│   │   └── eventbridge.py               # EventBridgeClient
│   │
│   ├── gcp/                             # Google Cloud Platform
│   │   ├── gcs.py                       # GCSStorageClient
│   │   ├── pubsub.py                    # PubSubClient
│   │   ├── bigquery.py                  # BigQueryClient
│   │   ├── cloud_functions.py           # CloudFunctionClient
│   │   └── secret_manager.py            # GCPSecretsManager
│   │
│   ├── azure/                           # Microsoft Azure
│   │   ├── blob_storage.py              # BlobStorageClient
│   │   ├── event_hub.py                 # EventHubClient
│   │   ├── service_bus.py               # ServiceBusClient
│   │   └── key_vault.py                 # KeyVaultSecretsManager
│   │
│   ├── localstack/                      # LocalStack (AWS Emulation)
│   │   ├── s3.py                        # LocalStackS3Client
│   │   ├── kinesis.py                   # LocalStackKinesisClient
│   │   ├── lambda_client.py
│   │   └── sqs.py
│   │
│   ├── s3_compatible/                   # S3-compatible Storage
│   │   ├── minio.py                     # MinIOStorageClient
│   │   └── r2.py                        # CloudflareR2Client
│   │
│   └── opensource/                      # Open-source Alternatives
│       ├── kafka.py                     # KafkaStreamClient
│       ├── redis_client.py              # RedisClient
│       ├── clickhouse.py                # ClickHouseClient
│       └── postgres.py                  # PostgresClient
│
├── 📁 factory/                          # Factory Pattern
│   ├── __init__.py
│   ├── client_factory.py                # Main factory
│   ├── storage_factory.py               # create_storage_client()
│   ├── streaming_factory.py             # create_stream_client()
│   ├── cache_factory.py                 # create_cache_client()
│   └── database_factory.py              # create_timeseries_db()
│
├── 📁 domain/                           # Business Logic (Trading Domain)
│   ├── __init__.py
│   │
│   ├── strategies/                      # Trading Strategies
│   │   ├── base.py                      # BaseStrategy (abstract)
│   │   ├── ma_crossover.py              # Moving Average Crossover
│   │   ├── rsi_strategy.py              # RSI-based
│   │   ├── mean_reversion.py            # Mean reversion
│   │   ├── ml_strategy.py               # ML-based
│   │   └── registry.py                  # Strategy registry
│   │
│   ├── indicators/                      # Technical Indicators
│   │   ├── base.py                      # BaseIndicator
│   │   ├── moving_averages.py           # SMA, EMA, WMA
│   │   ├── momentum.py                  # RSI, MACD, Stochastic
│   │   ├── volatility.py                # Bollinger Bands, ATR
│   │   └── volume.py                    # OBV, VWAP
│   │
│   ├── risk/                            # Risk Management
│   │   ├── position_sizer.py            # Kelly Criterion, Fixed %
│   │   ├── stop_loss.py                 # Stop-loss strategies
│   │   ├── portfolio_manager.py         # Multi-strategy portfolio
│   │   └── risk_limits.py               # Position limits, drawdown
│   │
│   ├── backtesting/                     # Backtesting Engine
│   │   ├── engine.py                    # BacktestEngine
│   │   ├── metrics.py                   # Sharpe, Sortino, etc.
│   │   ├── optimizer.py                 # Parameter optimization
│   │   └── report.py                    # Report generator
│   │
│   └── execution/                       # Order Execution
│       ├── paper_trading.py             # Paper trading simulator
│       ├── order_manager.py             # Order management
│       └── position_tracker.py          # Position tracking
│
├── 📁 services/                         # Microservices
│   ├── __init__.py
│   │
│   ├── market_data_ingestion/           # Real-time Data Ingestion
│   │   ├── main.py                      # Entry point
│   │   ├── websocket_client.py          # Binance/Coinbase WS
│   │   ├── stream_processor.py          # Send to Kinesis
│   │   ├── data_validator.py            # Validate data
│   │   └── Dockerfile
│   │
│   ├── stream_processor/                # Lambda/Function Processing
│   │   ├── handler.py                   # Lambda handler
│   │   ├── aggregator.py                # Ticks → Candles
│   │   └── requirements.txt
│   │
│   ├── strategy_engine/                 # Strategy Execution
│   │   ├── main.py
│   │   ├── executor.py                  # Execute strategies
│   │   ├── signal_processor.py          # Process signals
│   │   └── Dockerfile
│   │
│   ├── trading_api/                     # REST/WebSocket API
│   │   ├── main.py                      # FastAPI app
│   │   ├── routes/
│   │   │   ├── prices.py                # GET /prices/{symbol}
│   │   │   ├── candles.py               # GET /candles/{symbol}
│   │   │   ├── indicators.py            # GET /indicators/{symbol}
│   │   │   ├── strategies.py            # Strategy CRUD
│   │   │   ├── orders.py                # Order management
│   │   │   └── websocket.py             # WebSocket endpoint
│   │   ├── dependencies.py
│   │   ├── middleware.py
│   │   └── Dockerfile
│   │
│   └── ml_pipeline/                     # ML Training & Inference
│       ├── feature_engineering.py
│       ├── train.py
│       ├── inference.py
│       └── requirements.txt
│
├── 📁 infrastructure/                   # Infrastructure as Code
│   │
│   ├── cdk/                             # AWS CDK (Python)
│   │   ├── app.py
│   │   └── stacks/
│   │       ├── storage_stack.py         # S3 buckets
│   │       ├── streaming_stack.py       # Kinesis streams
│   │       ├── lambda_stack.py          # Lambda functions
│   │       ├── api_stack.py             # API Gateway
│   │       └── monitoring_stack.py      # CloudWatch
│   │
│   ├── terraform/                       # Terraform (Alternative)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── modules/
│   │
│   ├── docker/                          # Docker Configs
│   │   ├── docker-compose.local.yml     # LocalStack + services
│   │   ├── docker-compose.cloud.yml
│   │   └── Dockerfile.base
│   │
│   └── kubernetes/                      # Kubernetes Manifests
│       ├── deployments/
│       ├── services/
│       └── configmaps/
│
├── 📁 scripts/                          # Utility Scripts
│   ├── init_project_structure.py        # Initialize project
│   ├── download_historical_data.py      # Download market data
│   ├── load_data_to_clickhouse.py       # Load to ClickHouse
│   ├── generate_synthetic_data.py       # Generate test data
│   └── run_backtest.py                  # CLI backtest
│
├── 📁 notebooks/                        # Jupyter Notebooks
│   ├── 01_data_exploration.ipynb
│   ├── 02_indicator_analysis.ipynb
│   ├── 03_strategy_backtest.ipynb
│   ├── 04_ml_feature_engineering.ipynb
│   └── 05_model_training.ipynb
│
├── 📁 tests/                            # Tests
│   ├── unit/                            # Unit tests
│   │   ├── test_indicators.py
│   │   ├── test_strategies.py
│   │   └── test_providers/
│   ├── integration/                     # Integration tests
│   │   ├── test_stream_pipeline.py
│   │   └── test_api.py
│   └── fixtures/                        # Test fixtures
│
├── 📁 data/                             # Data Storage (gitignored)
│   ├── raw/                             # Raw market data
│   ├── processed/                       # Processed candles
│   ├── models/                          # Trained ML models
│   ├── backtest_results/                # Backtest outputs
│   └── logs/                            # Application logs
│
├── 📁 docs/                             # Documentation
│   ├── architecture.md
│   ├── api.md
│   ├── deployment.md
│   └── diagrams/
│
├── 📁 monitoring/                       # Monitoring & Observability
│   ├── grafana/
│   │   ├── dashboards/
│   │   └── provisioning/
│   └── prometheus/
│       └── prometheus.yml
│
├── .env.example                         # Environment template
├── .gitignore                           # Git ignore rules
├── pyproject.toml                       # Poetry dependencies
├── requirements.txt                     # Pip dependencies
├── Makefile                             # Common commands
├── README.md                            # This file
└── LICENSE
```

### 🔑 Key Design Principles

**1. Separation of Concerns:**

- `core/interfaces/` - Abstract contracts (cloud-agnostic)
- `providers/` - Concrete implementations (AWS, GCP, Azure, LocalStack)
- `factory/` - Auto-create clients based on config
- `domain/` - Business logic (trading strategies, NOT cloud code)
- `services/` - Microservices (API, ingestion, strategy engine)

**2. Dependency Flow:**

```
services/ → domain/ → factory/ → providers/ → core/interfaces/
                         ↓
                     config/
```

**3. Cloud Portability:**

- Code in `services/` and `domain/` is 100% cloud-agnostic
- Switch clouds by changing `.env` file only
- No vendor lock-in

**4. Testability:**

- Mock implementations of `core/interfaces/` for testing
- Fixtures in `tests/fixtures/`
- Separate unit and integration tests

---

## 🗺️ Development Phases

### 📍 **PHASE 1: Foundation & Real-time Data** (Day 1-2)

**Goal:** Stream live crypto market data into the system

#### Minimal Features (Required):

- [X] LocalStack setup (S3, Kinesis, Lambda)
- [X] Docker Compose for stateful services (ClickHouse, Redis, Grafana)
- [X] WebSocket connection to Binance (BTC, ETH)
- [X] Stream to Kinesis (LocalStack) → S3 (raw data backup)
- [X] ClickHouse table: `trades` (symbol, price, quantity, timestamp)
- [X] Grafana dashboard: Real-time price line chart
- [X] Environment config: `.env.local` pointing to LocalStack endpoints

#### Advanced Features (Optional):

- [ ] Multi-exchange support (Binance, Coinbase, Kraken)
- [ ] 20+ crypto symbols streaming
- [ ] Order book depth data
- [ ] Data quality validation (spike detection)
- [ ] Kafka Connect for alternative ingestion

**Services:**

- LocalStack: Kinesis, S3, Lambda (optional)
- Docker: ClickHouse, Redis, Grafana
- Python: Market data ingestion service

**Tech Showcase:**

- WebSocket handling with reconnection logic
- AWS Kinesis streams (via LocalStack, production-ready code)
- S3 data lake pattern (raw data persistence)
- ClickHouse partitioning strategy
- boto3 SDK with LocalStack endpoints

---

### 📍 **PHASE 2: Data Processing & Analytics** (Day 3-4)

**Goal:** Transform raw ticks into analytical datasets

#### Minimal Features (Required):

- [ ] OHLCV candlesticks (1m, 5m, 15m, 1h)
- [ ] ClickHouse materialized views for auto-aggregation
- [ ] Basic technical indicators: SMA(20, 50), EMA(12, 26)
- [ ] Redis caching for latest prices
- [ ] Grafana candlestick charts

#### Advanced Features (Optional):

- [ ] Advanced indicators: RSI, MACD, Bollinger Bands, ATR
- [ ] Multiple timeframes (1s, 30s, 4h, 1d)
- [ ] Volume-weighted indicators (VWAP)
- [ ] Market microstructure metrics (spread, depth)
- [ ] Flink streaming jobs for complex aggregations
- [ ] Real-time correlation analysis

**Services:**

- Redis (already running)
- Lambda (LocalStack) for real-time processing (optional alternative to materialized views)

**Tech Showcase:**

- ClickHouse materialized views performance
- Incremental aggregation algorithms
- Sub-second query latency on billions of rows
- Lambda event-driven processing (Kinesis trigger)

---

### 📍 **PHASE 3: Trading API & Strategy Framework** (Day 5-6)

**Goal:** Build API and strategy execution engine

#### Minimal Features (Required):

- [ ] FastAPI REST endpoints:
  - `GET /prices/{symbol}` - Latest price
  - `GET /candles/{symbol}` - OHLCV data
  - `GET /indicators/{symbol}` - Technical indicators
- [ ] WebSocket endpoint: Real-time price streaming
- [ ] Strategy base class/interface
- [ ] Simple strategy: Moving Average Crossover (SMA 20/50)
- [ ] Paper trading simulator (virtual orders)
- [ ] PostgreSQL: strategies, orders, positions tables

#### Advanced Features (Optional):

- [ ] GraphQL API alternative
- [ ] Strategy hot-reload (no restart needed)
- [ ] Multi-strategy portfolio
- [ ] Advanced strategies: Mean reversion, Momentum, Arbitrage
- [ ] Order types: Market, Limit, Stop-Loss, Trailing Stop
- [ ] Position sizing algorithms (Kelly Criterion)
- [ ] Strategy parameters optimization (grid search)

**Services:**

- PostgreSQL (Docker)
- API Gateway + Lambda (LocalStack) OR FastAPI (Python service)
- EventBridge (LocalStack) for event routing
- SQS (LocalStack) for async processing

**Tech Showcase:**

- Event-driven architecture (EventBridge, SQS)
- Serverless API (API Gateway + Lambda) or containerized (FastAPI)
- Stateful strategy execution
- WebSocket fan-out for real-time updates
- Infrastructure as Code (AWS CDK or Terraform for LocalStack)

---

### 📍 **PHASE 4: Backtesting Engine** (Day 7-9)

**Goal:** Test strategies against historical data

#### Minimal Features (Required):

- [ ] Download historical data (yfinance, Binance API)
- [ ] Backtest framework:
  - Load historical candles from ClickHouse
  - Simulate strategy execution
  - Track virtual P&L
- [ ] Performance metrics:
  - Total return, Win rate, Max drawdown
  - Number of trades
- [ ] Simple backtest report (JSON/CSV)
- [ ] Test MA Crossover strategy (2020-2024)

#### Advanced Features (Optional):

- [ ] Advanced metrics:
  - Sharpe ratio, Sortino ratio, Calmar ratio
  - Alpha, Beta (vs BTC benchmark)
  - Value at Risk (VaR)
- [ ] Transaction costs modeling (fees, slippage)
- [ ] Walk-forward analysis
- [ ] Monte Carlo simulation
- [ ] Strategy comparison dashboard
- [ ] Optimization: Parameter grid search with parallel execution
- [ ] Backtest on tick-level data (vs candles)

**Services:** +Jupyter (for analysis)

**Tech Showcase:**

- Vectorized backtesting (pandas/numpy)
- ClickHouse query optimization for historical data
- Statistical analysis of strategy performance
- Parallel backtesting (multiple strategies/parameters)

---

### 📍 **PHASE 5: ML/AI Integration** (Day 10-12)

**Goal:** Machine learning for price prediction and signals

#### Minimal Features (Required):

- [ ] Feature engineering:
  - Price changes, returns
  - Rolling statistics (mean, std, min, max)
  - Technical indicators as features
- [ ] Train simple model (Linear Regression or XGBoost)
- [ ] Price direction prediction (up/down/neutral)
- [ ] ML-based strategy: Trade on model signals
- [ ] Backtest ML strategy
- [ ] Model evaluation: Accuracy, Precision, Recall

#### Advanced Features (Optional):

- [ ] Advanced models:
  - LSTM/GRU (time-series deep learning)
  - Transformer (attention-based)
  - LightGBM, CatBoost
  - Ensemble models
- [ ] Feature store (online + offline features)
- [ ] Automated feature selection
- [ ] MLflow experiment tracking
- [ ] Model versioning and registry
- [ ] Online learning (incremental model updates)
- [ ] Multi-step forecasting (predict next N candles)
- [ ] Confidence intervals for predictions
- [ ] SHAP/LIME for model explainability
- [ ] A/B testing framework (compare strategies)

**Services:** +Jupyter, +MLflow

**Tech Showcase:**

- End-to-end ML pipeline (data → features → training → inference)
- Real-time feature computation
- Model serving with low latency (<100ms)
- Hyperparameter tuning (Optuna, Ray Tune)
- Data drift detection

---

### 📍 **PHASE 6: Production-Ready Features** (Day 13-15)

**Goal:** Monitoring, risk management, deployment automation

#### Minimal Features (Required):

- [ ] Risk management:
  - Max position size per symbol
  - Stop-loss (fixed percentage)
  - Max daily loss limit
- [ ] Portfolio tracking:
  - Current positions
  - Realized/unrealized P&L
  - Total equity
- [ ] Prometheus metrics:
  - Trade count, P&L
  - Strategy performance
  - System health (latency, errors)
- [ ] Grafana monitoring dashboard
- [ ] Environment configs (.env.local, .env.cloud)
- [ ] Docker deployment guide

#### Advanced Features (Optional):

- [ ] Advanced risk management:
  - VaR-based position sizing
  - Portfolio diversification constraints
  - Dynamic stop-loss (ATR-based)
  - Margin requirements calculation
- [ ] Airflow orchestration:
  - Daily data refresh
  - Weekly model retraining
  - Monthly backtest reports
- [ ] Alert system:
  - Telegram/Slack notifications
  - Email alerts (critical errors)
  - PagerDuty integration
- [ ] Distributed tracing (Jaeger)
- [ ] Log aggregation (ELK stack)
- [ ] Circuit breakers and fallback strategies
- [ ] Rate limiting and throttling
- [ ] Multi-region deployment (cloud)
- [ ] Kubernetes manifests
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Infrastructure as Code (Terraform)
- [ ] **Database migrations (Alembic):**
  - Version-controlled schema changes
  - Safe rollback capability
  - Auto-generate migrations from models
  - Deployment integration

**Services:** +Airflow, +Prometheus, +Alert Manager

**Tech Showcase:**

- Observability (metrics, logs, traces)
- Graceful degradation under failures
- Auto-scaling strategies
- Zero-downtime deployment
- Disaster recovery plan

---

## 🛠️ Tech Stack Details

### LocalStack (AWS Services Emulation)

- **S3**: Object storage for raw data, backups, ML artifacts
- **Kinesis**: Real-time data streaming (alternative to Kafka)
- **Lambda**: Serverless compute for event processing
- **DynamoDB**: NoSQL database for high-throughput data
- **EventBridge**: Event bus for decoupled architecture
- **SQS/SNS**: Message queuing and pub/sub
- **API Gateway**: REST/WebSocket API endpoints
- **CloudWatch**: Logging and metrics
- **Secrets Manager**: Secure credential storage
- **Step Functions** (optional): Workflow orchestration

### Stateful Services (Docker or Cloud Managed)

#### Data Storage

- **ClickHouse**: Time-series OLAP database (billions of ticks)
  - Local: Docker container
  - Cloud: ClickHouse Cloud, Altinity Cloud
- **Redis**: In-memory caching (latest prices, positions)
  - Local: Docker container
  - Cloud: Upstash Redis, AWS ElastiCache
- **PostgreSQL**: Relational metadata (strategies, users, configs)
  - Local: Docker container
  - Cloud: Supabase, Neon, AWS RDS

#### ML & Analytics

- **Jupyter**: Interactive data exploration
- **MLflow**: Experiment tracking, model registry
- **scikit-learn, XGBoost, LightGBM**: Traditional ML
- **TensorFlow/PyTorch**: Deep learning (LSTM, Transformers)

#### Monitoring & Visualization

- **Grafana**: Real-time operational dashboards (Docker)
- **Prometheus**: Metrics collection (Docker)

### Application Layer

- **Python 3.10+**: Primary language
- **boto3**: AWS SDK (works with LocalStack)
- **FastAPI**: High-performance API framework
- **Pydantic**: Data validation
- **SQLAlchemy**: ORM for PostgreSQL
- **clickhouse-connect**: ClickHouse Python client
- **redis-py**: Redis Python client

### Infrastructure as Code

- **AWS CDK** (recommended): Define LocalStack + AWS resources in Python
- **Terraform** (alternative): HCL-based IaC
- **LocalStack Docker Compose**: Service orchestration

---

## 📦 Services Breakdown

### Minimal Stack (LocalStack + Core Services - ~3GB RAM)

```yaml
LocalStack (unified container):
- All AWS services (S3, Kinesis, Lambda, DynamoDB, etc.) - 512MB

Docker Stateful Services:
- clickhouse (1.5GB)
- redis (256MB)
- postgres (512MB)
- grafana (256MB)

Python Services (run locally, not Docker):
- market-data-ingestion (256MB)
- trading-api (512MB)
```

### Full Stack (All Services - ~8GB RAM)

```yaml
+ LocalStack Pro features (optional)
+ jupyter (1GB)
+ mlflow (512MB)
+ prometheus (512MB)
+ Additional Lambda functions
+ Step Functions workflows
```

### Cloud Alternative (Zero Local Resources)

```yaml
Replace all with managed services:
- LocalStack → Real AWS (free tier)
- Docker ClickHouse → ClickHouse Cloud ($300 credit)
- Docker Redis → Upstash Redis (free tier)
- Docker Postgres → Supabase (free tier)
- Python services → AWS Lambda or Railway
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.10+
- 8GB+ RAM (minimal), 16GB+ recommended (full stack)
- 20GB+ disk space

### 1. Clone & Setup

```bash
git clone <repo-url>
cd DataPlatform

# Copy environment template
cp .env.example .env.local
```

### 2. Start Minimal Stack (Phase 1)

```bash
# Start LocalStack + stateful services
docker-compose up -d

# Services started:
# - localstack (all AWS services)
# - clickhouse
# - redis
# - postgres
# - grafana

# Check services health
docker-compose ps

# View logs
docker-compose logs -f localstack
```

### 3. Run Market Data Ingestion

```bash
cd services/market-data-ingestion
pip install -r requirements.txt
python main.py
```

### 4. Access Dashboards

- **LocalStack Dashboard**: http://localhost:4566/_localstack/health
- **Grafana**: http://localhost:3000 (admin/admin)
- **ClickHouse**: http://localhost:8123
- **Redis**: localhost:6379
- **PostgreSQL**: localhost:5432

### 5. Verify Data Flow

```bash
# Check LocalStack health
curl http://localhost:4566/_localstack/health

# List S3 buckets (LocalStack)
aws --endpoint-url=http://localhost:4566 s3 ls

# Check Kinesis stream (LocalStack)
aws --endpoint-url=http://localhost:4566 kinesis list-streams

# Query ClickHouse
curl "http://localhost:8123/?query=SELECT count() FROM trades"
```

---

## 🌐 Local → Cloud Migration

### Configuration-Based Deployment

All services use environment variables for endpoints:

```bash
# .env.local (LocalStack + Docker)
AWS_ENDPOINT_URL=http://localhost:4566
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://admin:password@localhost:5432/trading

# .env.cloud (Production AWS)
AWS_ENDPOINT_URL=  # Empty = use real AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<real-key>
AWS_SECRET_ACCESS_KEY=<real-secret>

CLICKHOUSE_HOST=abc123.clickhouse.cloud
REDIS_URL=rediss://username:password@redis.cloud:6379
POSTGRES_URL=postgresql://user:pass@db.supabase.com/postgres
```

### Switch Environments

```bash
# Local development with LocalStack
cp .env.local .env
docker-compose up -d
python services/market-data-ingestion/main.py

# Production (real AWS + managed databases)
cp .env.cloud .env
# Deploy Lambda functions
cd infra
cdk deploy  # or terraform apply

# Code remains IDENTICAL - boto3 SDK uses env vars!
```

### Cloud Deployment Options

#### Option A: Docker on Cloud VM (easiest)

```bash
# On AWS EC2 / GCP Compute / Azure VM
git clone <repo>
docker-compose -f docker-compose.cloud.yml up -d
```

#### Option B: Managed Services

- **Kafka**: Confluent Cloud, AWS MSK, Aiven
- **ClickHouse**: ClickHouse Cloud, Altinity.Cloud
- **Redis**: AWS ElastiCache, Redis Cloud
- **PostgreSQL**: AWS RDS, Google Cloud SQL, Supabase
- **Airflow**: Astronomer, Google Cloud Composer

#### Option C: Kubernetes

```bash
# Using Helm charts
helm install trading ./helm/trading-platform
```

---

## 📈 Project Milestones

| Phase   | Duration | Can Demo               | Technical Highlights         |
| ------- | -------- | ---------------------- | ---------------------------- |
| Phase 1 | 1-2 days | ✅ Real-time prices    | WebSocket, Kafka, ClickHouse |
| Phase 2 | 1-2 days | ✅ Charts + indicators | Materialized views, caching  |
| Phase 3 | 2 days   | ✅ Working strategy    | FastAPI, event-driven arch   |
| Phase 4 | 2-3 days | ✅ Backtest results    | Vectorized computing, stats  |
| Phase 5 | 2-3 days | ✅ ML predictions      | LSTM, feature engineering    |
| Phase 6 | 2-3 days | ✅ Production system   | Monitoring, orchestration    |

**Total:** ~2 weeks for full platform

---

## 🎓 Learning Outcomes

By completing this project, you will master:

### Data Engineering

- Stream processing architectures
- Time-series database optimization
- Data pipeline orchestration
- ETL/ELT patterns

### Backend Development

- REST + WebSocket APIs
- Event-driven microservices
- Caching strategies
- Database design

### Machine Learning

- Time-series forecasting
- Feature engineering
- Model training & evaluation
- MLOps practices

### DevOps

- Containerization (Docker)
- Infrastructure as Code
- Monitoring & alerting
- CI/CD pipelines

### System Design

- Distributed systems
- Scalability patterns
- Fault tolerance
- Performance optimization

---

## 📊 Performance Targets

### Latency

- Market data ingestion → ClickHouse: **< 100ms** (p99)
- Strategy signal generation: **< 50ms**
- API response time: **< 100ms** (p95)
- ML model inference: **< 50ms**

### Throughput

- Market data ingestion: **10,000+ trades/second**
- Strategy evaluations: **1,000+ per second**
- API requests: **5,000+ req/second**

### Data Volume

- **100M+ ticks per day** (~1GB/day compressed)
- **1B+ ticks** for backtesting (2020-2024)
- Query performance: **Sub-second** on billions of rows

---

## 🔐 Security Considerations

### Minimal (Phase 1-4)

- Environment variables for secrets
- Docker network isolation
- Read-only API keys (exchange APIs)

### Production (Phase 6)

- API authentication (JWT)
- Rate limiting
- Input validation
- HTTPS/TLS encryption
- Secrets management (Vault, AWS Secrets Manager)
- Network policies (firewall rules)
- Regular security audits

---

## 🧪 Testing Strategy

### Unit Tests

- Strategy logic
- Technical indicators calculation
- Data validation

### Integration Tests

- Kafka → ClickHouse pipeline
- API endpoints
- ML model inference

### Performance Tests

- Load testing (Locust, K6)
- Stress testing (max throughput)
- Latency benchmarks

### Backtests

- Historical strategy validation
- Out-of-sample testing
- Walk-forward analysis

---

## 📚 Resources & References

### Documentation

- [ClickHouse Docs](https://clickhouse.com/docs)
- [Kafka Docs](https://kafka.apache.org/documentation/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Flink Docs](https://flink.apache.org/)

### Data Sources

- [Binance WebSocket API](https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams)
- [yfinance](https://github.com/ranaroussi/yfinance) - Historical stock data
- [ccxt](https://github.com/ccxt/ccxt) - Multi-exchange crypto library

### Learning

- Kaggle: Crypto/Stock datasets
- QuantConnect: Algorithmic trading tutorials
- TradingView: Technical analysis

---

## 🤝 Contributing

This is a learning project showcasing technical skills. Feel free to:

- Fork and customize for your use case
- Submit issues for bugs/improvements
- Share your results and learnings

---

## ⚠️ Disclaimer

**Educational & Research Purposes Only**

This platform is built for:

- Learning data engineering and ML concepts
- Portfolio demonstration
- Academic research

**NOT intended for:**

- Real money trading without extensive modifications
- Production use without proper risk management
- Financial advice

**Trading involves significant risk of loss. Past performance does not guarantee future results.**

---

## 🔄 Database Migrations (Alembic) - Phase 4+

### Why Alembic?

**Phase 1-3 (Development):** Use `postgres/init.sql` (simple, fast iteration)

- Schema is simple and changes infrequently
- Can `docker-compose down -v` to recreate database
- No production data to preserve

**Phase 4+ (Production):** Migrate to **Alembic** (version control, safety)

- Have production data (cannot recreate database)
- Schema changes need to be tracked and reversible
- Team collaboration requires migration history

### Setup Alembic

```bash
# Install
pip install alembic psycopg2-binary

# Initialize (creates migrations/ folder)
alembic init migrations

# Configure
# Edit migrations/env.py to use config/settings.py
```

**migrations/env.py:**

```python
from config.settings import get_settings
settings = get_settings()

config.set_main_option("sqlalchemy.url", settings.postgres_dsn)
```

### Create Migrations

**Auto-generate from SQLAlchemy models:**

```bash
# After changing models in domain/models/
alembic revision --autogenerate -m "add phone_number to users"

# Review the generated migration
# Edit migrations/versions/xxx_add_phone_number.py if needed
```

**Manual migration:**

```bash
alembic revision -m "add index on orders.symbol"
```

**migrations/versions/001_add_phone.py:**

```python
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('users',
        sa.Column('phone_number', sa.String(20), nullable=True)
    )
    op.create_index('idx_users_phone', 'users', ['phone_number'])

def downgrade():
    op.drop_index('idx_users_phone')
    op.drop_column('users', 'phone_number')
```

### Apply Migrations

**Local development:**

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current

# View migration history
alembic history
```

**Production deployment:**

```bash
# In Dockerfile or docker-compose
CMD alembic upgrade head && python main.py
```

**docker-compose.yml:**

```yaml
services:
  trading-api:
    build: .
    command: >
      sh -c "alembic upgrade head &&
             uvicorn main:app --host 0.0.0.0"
    depends_on:
      postgres:
        condition: service_healthy
```

### Migration Best Practices

**1. Always test migrations:**

```bash
# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# Test re-upgrade
alembic upgrade head
```

**2. Never modify old migrations:**

- Create new migration to fix issues
- Old migrations are history (like Git commits)

**3. Review auto-generated migrations:**

- Alembic may miss some changes
- Check nullable, defaults, indexes

**4. Use transactions:**

```python
def upgrade():
    with op.get_context().autocommit_block():
        # DDL statements here
        pass
```

**5. Data migrations:**

```python
def upgrade():
    # Schema change
    op.add_column('users', sa.Column('status', sa.String(20)))

    # Data migration
    connection = op.get_bind()
    connection.execute(
        "UPDATE users SET status = 'active' WHERE is_active = true"
    )
```

### CI/CD Integration

**GitHub Actions:**

```yaml
- name: Run migrations
  run: |
    alembic upgrade head

- name: Run tests
  run: pytest
```

**Deployment script:**

```bash
#!/bin/bash
# deploy.sh

# Backup database
pg_dump $DB_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Run migrations
alembic upgrade head

# Deploy app
docker-compose up -d --build
```

### Converting from init.sql to Alembic

**Step 1: Initial migration from existing schema**

```bash
# Start with empty migrations
alembic init migrations

# Create initial migration matching current init.sql
alembic revision -m "initial schema"
```

**Step 2: Copy init.sql content to migration:**

```python
# migrations/versions/001_initial.py
def upgrade():
    # Copy CREATE TABLE statements from init.sql
    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        ...
    )
    """)
```

**Step 3: Mark as applied (don't re-run on existing DB):**

```bash
# On existing database
alembic stamp head

# On new database
alembic upgrade head
```

**Step 4: Future changes use Alembic**

```bash
# All new schema changes
alembic revision --autogenerate -m "add new column"
alembic upgrade head
```

### Troubleshooting

**Migration conflicts:**

```bash
# Multiple developers created migrations
# Merge and renumber
alembic merge heads -m "merge migrations"
```

**Reset migrations (development only!):**

```bash
# WARNING: Deletes all data!
docker-compose down -v
rm -rf migrations/versions/*
alembic revision -m "initial"
# Recreate schema in migration
alembic upgrade head
```

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🎯 Next Steps

### Starting Phase 1?

```bash
# Create project structure
./scripts/init-project.sh

# Start minimal stack
docker-compose -f docker-compose.phase1.yml up -d

# Run data ingestion
python services/market-data-ingestion/main.py

# Open Grafana and see real-time data!
open http://localhost:3000
```

### Questions or Issues?

- Check `/docs` folder for detailed guides
- See `/examples` for code samples
- Review `/scripts` for automation tools

---

**Built with ❤️ for learning and showcasing technical expertise**

**Keywords:** #DataEngineering #MachineLearning #AlgorithmicTrading #StreamProcessing #ClickHouse #Kafka #Python #FastAPI #Docker #CloudNative
