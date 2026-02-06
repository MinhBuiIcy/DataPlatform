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
    # ============================================
    @property
    def STREAM_MARKET_TRADES(self) -> str:
        """
        Cloud-agnostic stream/topic name for market trades
        Returns Kafka topic if opensource, Kinesis stream if aws/localstack
        """
        if self.CLOUD_PROVIDER.lower() == "opensource":
            return self.KAFKA_TOPIC_MARKET_TRADES
        return self.KINESIS_STREAM_MARKET_TRADES

    @property
    def STREAM_ORDER_BOOKS(self) -> str:
        """
        Cloud-agnostic stream/topic name for order books
        Returns Kafka topic if opensource, Kinesis stream if aws/localstack
        """
        if self.CLOUD_PROVIDER.lower() == "opensource":
            return self.KAFKA_TOPIC_ORDER_BOOKS
        return self.KINESIS_STREAM_MARKET_TRADES  # Currently using same stream for both

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
