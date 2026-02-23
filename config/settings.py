"""
Application Settings - Load from YAML configs + .env secrets

Design Philosophy:
- Service configs (host, port, topics, buckets) → YAML files (public, versioned in git)
- Secrets (passwords, tokens, keys) → .env file (gitignored)

This separation allows:
- Team collaboration on infrastructure configs (YAML)
- Secure handling of credentials (.env)
- Environment-specific configs (databases.prod.yaml vs databases.yaml)

Uses Pydantic for validation and type safety
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.utils.config import load_yaml_safe


class Settings(BaseSettings):
    """
    Application settings

    Architecture:
    - Infrastructure configs → config/providers/*.yaml (public)
    - Secrets → .env (gitignored)

    Usage:
        from config.settings import get_settings

        settings = get_settings()
        print(settings.KAFKA_BOOTSTRAP_SERVERS)  # From streaming.yaml
        print(settings.CLICKHOUSE_PASSWORD)  # From .env
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra fields in .env
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Load YAML configs from files (cached at class level)
        if not hasattr(Settings, "_yaml_loaded"):
            Settings._streaming_config = load_yaml_safe("config/providers/streaming.yaml")
            Settings._database_config = load_yaml_safe("config/providers/databases.yaml")
            Settings._storage_config = load_yaml_safe("config/providers/storage.yaml")
            Settings._indicators_config = load_yaml_safe("config/providers/indicators.yaml")
            Settings._sync_config = load_yaml_safe("config/providers/sync.yaml")
            Settings._exchanges_config = load_yaml_safe("config/providers/exchanges.yaml")
            Settings._yaml_loaded = True

    # ============================================
    # ENVIRONMENT (.env only)
    # ============================================
    ENVIRONMENT: str = Field(default="local", description="Environment: local, dev, staging, prod")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # ============================================
    # CLOUD PROVIDER (.env only)
    # ============================================
    CLOUD_PROVIDER: str = Field(
        default="opensource",
        description="Cloud provider: opensource (Kafka), aws, localstack, gcp, azure",
    )

    # ============================================
    # AWS CREDENTIALS (.env only - secrets)
    # ============================================
    AWS_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: str | None = Field(default="test")  # LocalStack default
    AWS_SECRET_ACCESS_KEY: str | None = Field(default="test")  # LocalStack default
    AWS_ENDPOINT_URL: str | None = Field(default=None)  # For LocalStack

    # LocalStack
    LOCALSTACK_AUTH_TOKEN: str | None = Field(default=None)

    # ============================================
    # CLIENT QUEUE SETTINGS (from YAML)
    # ============================================
    @property
    def STREAM_QUEUE_SIZE(self) -> int:
        """Stream client queue size from streaming.yaml"""
        return self._streaming_config.get("queue", {}).get("size", 5000)

    @property
    def STREAM_WORKERS(self) -> int:
        """Stream client worker pool size from streaming.yaml"""
        return self._streaming_config.get("queue", {}).get("workers", 10)

    @property
    def DB_QUEUE_SIZE(self) -> int:
        """Database client queue size from databases.yaml"""
        return self._database_config.get("queue", {}).get("size", 2000)

    @property
    def DB_WORKERS(self) -> int:
        """Database client worker pool size from databases.yaml"""
        return self._database_config.get("queue", {}).get("workers", 3)

    @property
    def DB_BATCH_SIZE(self) -> int:
        """Database client batch size from databases.yaml"""
        return self._database_config.get("queue", {}).get("batch_size", 100)

    @property
    def CACHE_QUEUE_SIZE(self) -> int:
        """Cache client queue size from databases.yaml"""
        return self._database_config.get("redis", {}).get("queue", {}).get("size", 1000)

    @property
    def CACHE_WORKERS(self) -> int:
        """Cache client worker pool size from databases.yaml"""
        return self._database_config.get("redis", {}).get("queue", {}).get("workers", 2)

    # ============================================
    # STREAMING - Kafka/Kinesis (from YAML)
    # ============================================
    @property
    def KAFKA_BOOTSTRAP_SERVERS(self) -> str:
        """Kafka bootstrap servers from streaming.yaml"""
        return self._streaming_config.get("kafka", {}).get("bootstrap_servers", "kafka:9092")

    @property
    def KAFKA_TOPIC_MARKET_TRADES(self) -> str:
        """Kafka topic for market trades from streaming.yaml"""
        return (
            self._streaming_config.get("kafka", {})
            .get("topics", {})
            .get("market_trades", "market-trades")
        )

    @property
    def KAFKA_TOPIC_ORDER_BOOKS(self) -> str:
        """Kafka topic for order books from streaming.yaml"""
        return (
            self._streaming_config.get("kafka", {})
            .get("topics", {})
            .get("order_books", "order-books")
        )

    @property
    def KAFKA_TOPIC_CANDLE_EVENTS(self) -> str:
        """Kafka topic for candle events from streaming.yaml (Phase 2)"""
        return (
            self._streaming_config.get("kafka", {})
            .get("topics", {})
            .get("candle_events", "candle-events")
        )

    @property
    def KINESIS_STREAM_MARKET_TRADES(self) -> str:
        """Kinesis stream for market trades from streaming.yaml"""
        return (
            self._streaming_config.get("kinesis", {})
            .get("streams", {})
            .get("market_trades", "market-trades-local")
        )

    # ============================================
    # UNIFIED STREAM/TOPIC NAMES (Cloud-agnostic)
    # Phase 2: WebSocket → Redis only (no streaming to Kafka/Kinesis)
    # Kafka infrastructure kept for Phase 3+ (strategies)
    # ============================================

    # ============================================
    # CLICKHOUSE (from YAML + .env)
    # ============================================
    @property
    def CLICKHOUSE_HOST(self) -> str:
        """ClickHouse host from databases.yaml"""
        return self._database_config.get("clickhouse", {}).get("host", "clickhouse")

    @property
    def CLICKHOUSE_PORT(self) -> int:
        """ClickHouse native port from databases.yaml"""
        return self._database_config.get("clickhouse", {}).get("port", 9000)

    @property
    def CLICKHOUSE_HTTP_PORT(self) -> int:
        """ClickHouse HTTP port from databases.yaml"""
        return self._database_config.get("clickhouse", {}).get("http_port", 8123)

    @property
    def CLICKHOUSE_DB(self) -> str:
        """ClickHouse database from databases.yaml"""
        return self._database_config.get("clickhouse", {}).get("database", "trading")

    @property
    def CLICKHOUSE_USER(self) -> str:
        """ClickHouse user from databases.yaml"""
        return self._database_config.get("clickhouse", {}).get("user", "trading_user")

    @property
    def CLICKHOUSE_POOL_SIZE(self) -> int:
        """
        ClickHouse connection pool size from databases.yaml.

        Should be >= DB_WORKERS for optimal performance.
        Each worker needs a connection when executing queries.
        Defaults to DB_WORKERS if not specified.
        """
        return self._database_config.get("clickhouse", {}).get(
            "pool_size", self.DB_WORKERS
        )

    # ClickHouse password from .env (secret)
    CLICKHOUSE_PASSWORD: str = Field(default="trading_pass")

    @property
    def clickhouse_dsn(self) -> str:
        """ClickHouse connection string"""
        return (
            f"clickhouse://{self.CLICKHOUSE_USER}:{self.CLICKHOUSE_PASSWORD}"
            f"@{self.CLICKHOUSE_HOST}:{self.CLICKHOUSE_PORT}/{self.CLICKHOUSE_DB}"
        )

    # ============================================
    # REDIS (from YAML + .env)
    # ============================================
    @property
    def REDIS_HOST(self) -> str:
        """Redis host from databases.yaml"""
        return self._database_config.get("redis", {}).get("host", "redis")

    @property
    def REDIS_PORT(self) -> int:
        """Redis port from databases.yaml"""
        return self._database_config.get("redis", {}).get("port", 6379)

    @property
    def REDIS_DB(self) -> int:
        """Redis database from databases.yaml"""
        return self._database_config.get("redis", {}).get("db", 0)

    # Redis password from .env (optional secret)
    REDIS_PASSWORD: str | None = Field(default=None)

    @property
    def redis_url(self) -> str:
        """Redis connection URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ============================================
    # POSTGRESQL (from YAML + .env)
    # ============================================
    @property
    def POSTGRES_HOST(self) -> str:
        """PostgreSQL host from databases.yaml"""
        return self._database_config.get("postgres", {}).get("host", "postgres")

    @property
    def POSTGRES_PORT(self) -> int:
        """PostgreSQL port from databases.yaml"""
        return self._database_config.get("postgres", {}).get("port", 5432)

    @property
    def POSTGRES_DB(self) -> str:
        """PostgreSQL database from databases.yaml"""
        return self._database_config.get("postgres", {}).get("database", "trading")

    @property
    def POSTGRES_USER(self) -> str:
        """PostgreSQL user from databases.yaml"""
        return self._database_config.get("postgres", {}).get("user", "trading_user")

    # PostgreSQL password from .env (secret)
    POSTGRES_PASSWORD: str = Field(default="trading_pass")

    # Optional override
    POSTGRES_URL: str | None = Field(default=None)

    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL connection string (for SQLAlchemy)"""
        if self.POSTGRES_URL:
            return self.POSTGRES_URL
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ============================================
    # S3 / OBJECT STORAGE (from YAML)
    # ============================================
    @property
    def S3_BUCKET_RAW_DATA(self) -> str:
        """S3 bucket for raw data from storage.yaml"""
        return (
            self._storage_config.get("s3", {})
            .get("buckets", {})
            .get("raw_data", "trading-raw-data-local")
        )

    @property
    def S3_BUCKET_PROCESSED_DATA(self) -> str:
        """S3 bucket for processed data from storage.yaml"""
        return (
            self._storage_config.get("s3", {})
            .get("buckets", {})
            .get("processed_data", "trading-processed-data-local")
        )

    @property
    def S3_BUCKET_MODELS(self) -> str:
        """S3 bucket for ML models from storage.yaml"""
        return (
            self._storage_config.get("s3", {})
            .get("buckets", {})
            .get("models", "trading-models-local")
        )

    # ============================================
    # INDICATORS (from YAML)
    # ============================================
    @property
    def INDICATORS(self) -> list:
        """List of enabled indicators from indicators.yaml"""
        return self._indicators_config.get("indicators", [])

    @property
    def INDICATOR_CANDLE_LOOKBACK(self) -> int:
        """Number of candles to query for indicators"""
        return self._indicators_config.get("settings", {}).get("candle_lookback", 200)

    @property
    def INDICATOR_MAX_GAP_RATIO(self) -> float:
        """Max allowed ratio of synthetic candles"""
        return self._indicators_config.get("settings", {}).get("max_gap_ratio", 0.1)

    @property
    def INDICATOR_ENABLE_GAP_FILLING(self) -> bool:
        """Whether to enable gap filling"""
        return self._indicators_config.get("settings", {}).get("enable_gap_filling", True)

    # ============================================
    # WEBSOCKET (from exchanges.yaml)
    # ============================================
    @property
    def WS_QUEUE_MAX_SIZE(self) -> int:
        """Max buffered messages per exchange before dropping"""
        return self._exchanges_config.get("websocket", {}).get("queue_max_size", 10000)

    @property
    def WS_CONSUMER_WORKERS(self) -> int:
        """Number of parallel consumer workers per exchange"""
        return self._exchanges_config.get("websocket", {}).get("consumer_workers", 3)

    @property
    def WS_PING_INTERVAL(self) -> int | None:
        """Client ping interval in seconds, None to disable"""
        val = self._exchanges_config.get("websocket", {}).get("ping_interval", 60)
        return None if val is None else int(val)

    @property
    def WS_PING_TIMEOUT(self) -> int | None:
        """Max wait for pong before reconnect in seconds"""
        val = self._exchanges_config.get("websocket", {}).get("ping_timeout", 120)
        return None if val is None else int(val)

    @property
    def WS_MAX_MESSAGE_SIZE(self) -> int:
        """Max WebSocket frame size in bytes"""
        mb = self._exchanges_config.get("websocket", {}).get("max_message_size_mb", 10)
        return int(mb) * 1024 * 1024

    @property
    def WS_ORDERBOOK_SAMPLE_INTERVAL_MS(self) -> int:
        """Pre-filter interval for orderbook messages (ms). Keep 1 per symbol per interval."""
        return self._exchanges_config.get("websocket", {}).get("orderbook_sample_interval_ms", 1000)

    # ============================================
    # SYNC SERVICE (from sync.yaml)
    # ============================================
    @property
    def SYNC_ENABLED(self) -> bool:
        """Whether sync service is enabled"""
        return self._sync_config.get("sync", {}).get("enabled", True)

    @property
    def SYNC_INTERVAL_SECONDS(self) -> int:
        """Sync interval in seconds"""
        return self._sync_config.get("sync", {}).get("interval_seconds", 60)

    @property
    def SYNC_TIMEFRAMES(self) -> list[str]:
        """Timeframes to sync from sync.yaml"""
        return self._sync_config.get("sync", {}).get("timeframes", ["1m", "5m", "1h"])

    @property
    def SYNC_FETCH_LIMIT(self) -> int:
        """Number of candles to fetch per sync"""
        return self._sync_config.get("sync", {}).get("fetch_limit", 5)

    @property
    def SYNC_MAX_CONCURRENT(self) -> int:
        """Max concurrent sync tasks per cycle"""
        return self._sync_config.get("sync", {}).get("max_concurrent_syncs", 10)

    @property
    def SYNC_RATE_LIMIT_DELAY_MS(self) -> int:
        """Delay between exchange API calls"""
        return self._sync_config.get("sync", {}).get("rate_limit_delay_ms", 500)

    @property
    def SYNC_INITIAL_BACKFILL_LIMIT(self) -> int:
        """Number of candles to fetch on initial backfill"""
        return self._sync_config.get("sync", {}).get("initial_backfill_limit", 100)

    # ============================================
    # REST API (from sync.yaml)
    # ============================================
    @property
    def REST_API_ENABLE_RATE_LIMIT(self) -> bool:
        """Enable ccxt built-in rate limiting"""
        return self._sync_config.get("rest_api", {}).get("enable_rate_limit", True)

    @property
    def REST_API_TIMEOUT_MS(self) -> int:
        """Request timeout in milliseconds"""
        return self._sync_config.get("rest_api", {}).get("timeout_ms", 30000)

    @property
    def REST_API_RETRY_COUNT(self) -> int:
        """Number of retries on failure"""
        return self._sync_config.get("rest_api", {}).get("retry_count", 3)

    @property
    def REST_API_RETRY_DELAY_MS(self) -> int:
        """Delay between retries"""
        return self._sync_config.get("rest_api", {}).get("retry_delay_ms", 1000)

    # ============================================
    # INDICATOR SERVICE (from indicators.yaml)
    # ============================================
    @property
    def INDICATOR_SERVICE_INTERVAL_SECONDS(self) -> int:
        """Indicator service run interval"""
        return self._indicators_config.get("service", {}).get("interval_seconds", 60)

    @property
    def INDICATOR_SERVICE_INITIAL_DELAY_SECONDS(self) -> int:
        """Initial delay before starting indicator service"""
        return self._indicators_config.get("service", {}).get("initial_delay_seconds", 10)

    @property
    def INDICATOR_SERVICE_CATCH_UP_ENABLED(self) -> bool:
        """Whether catch-up mode is enabled"""
        return self._indicators_config.get("service", {}).get("catch_up_enabled", True)

    @property
    def INDICATOR_SERVICE_CATCH_UP_LIMIT(self) -> int:
        """Max candles to process in catch-up mode"""
        return self._indicators_config.get("service", {}).get("catch_up_limit", 1000)

    @property
    def INDICATOR_SERVICE_MIN_CANDLES(self) -> int:
        """Minimum candles required for calculation"""
        return self._indicators_config.get("service", {}).get("min_candles", 20)


# Singleton pattern
_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """
    Get application settings (singleton)

    Returns:
        Settings instance

    Example:
        >>> settings = get_settings()
        >>> print(settings.KAFKA_BOOTSTRAP_SERVERS)
        kafka:9092
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
