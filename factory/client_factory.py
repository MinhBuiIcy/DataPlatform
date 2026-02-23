"""
Client factory - Auto-create clients based on configuration

Dependency injection pattern for cloud-agnostic code
"""

import logging

from config.settings import get_settings
from core.interfaces.cache import BaseCacheClient
from core.interfaces.database import BaseTimeSeriesDB
from core.interfaces.market_data import BaseExchangeRestAPI, BaseExchangeWebSocket
from core.interfaces.storage import BaseStorageClient
from core.interfaces.streaming_consumer import BaseStreamConsumer
from core.interfaces.streaming_producer import BaseStreamProducer

logger = logging.getLogger(__name__)


def create_stream_producer() -> BaseStreamProducer:
    """
    Create stream client based on CLOUD_PROVIDER config

    Returns:
        BaseStreamProducer: Kafka (opensource), Kinesis (aws/localstack), PubSub (gcp), etc.

    Examples:
        >>> # .env: CLOUD_PROVIDER=opensource
        >>> client = create_stream_producer()  # Returns KafkaStreamProducer
        >>>
        >>> # .env: CLOUD_PROVIDER=aws or localstack
        >>> client = create_stream_producer()  # Returns KinesisStreamProducer
    """
    settings = get_settings()
    provider = settings.CLOUD_PROVIDER.lower()

    if provider == "opensource":
        from providers.opensource.kafka_stream_producer import KafkaStreamProducer

        logger.info("✓ Creating KafkaStreamProducer (opensource)")
        return KafkaStreamProducer()

    elif provider in ["aws", "localstack"]:
        from providers.aws.kinesis import KinesisStreamProducer

        logger.info("✓ Creating KinesisStreamProducer (aws/localstack)")
        return KinesisStreamProducer()

    elif provider == "gcp":
        # TODO: Implement PubSubClient
        raise NotImplementedError("GCP PubSubClient not implemented yet")

    elif provider == "azure":
        # TODO: Implement EventHubClient
        raise NotImplementedError("Azure EventHubClient not implemented yet")

    else:
        raise ValueError(
            f"Unsupported cloud provider: {provider}. "
            f"Supported: opensource (Kafka), aws, localstack, gcp, azure"
        )


def create_stream_consumer() -> BaseStreamConsumer:
    """
    Create stream consumer based on CLOUD_PROVIDER config

    Returns:
        BaseStreamConsumer: Kafka (opensource), Kinesis (aws/localstack), etc.

    Examples:
        >>> # .env: CLOUD_PROVIDER=opensource
        >>> consumer = create_stream_consumer()  # Returns KafkaStreamConsumer
        >>>
        >>> # .env: CLOUD_PROVIDER=aws or localstack
        >>> consumer = create_stream_consumer()  # Returns KinesisStreamConsumer
    """
    settings = get_settings()
    provider = settings.CLOUD_PROVIDER.lower()

    if provider == "opensource":
        from providers.opensource.kafka_stream_consumer import KafkaStreamConsumer

        logger.info("✓ Creating KafkaStreamConsumer (opensource)")
        return KafkaStreamConsumer()

    elif provider in ["aws", "localstack"]:
        # TODO: Implement KinesisStreamConsumer
        raise NotImplementedError("Kinesis consumer not implemented yet")

    elif provider == "gcp":
        # TODO: Implement PubSubConsumer
        raise NotImplementedError("GCP PubSub consumer not implemented yet")

    elif provider == "azure":
        # TODO: Implement EventHubConsumer
        raise NotImplementedError("Azure EventHub consumer not implemented yet")

    else:
        raise ValueError(
            f"Unsupported cloud provider: {provider}. "
            f"Supported: opensource (Kafka), aws, localstack, gcp, azure"
        )


def create_cache_client() -> BaseCacheClient:
    """
    Create cache client

    Currently always returns RedisClient
    Future: Could support Memcached, etc.

    Returns:
        BaseCacheClient: Redis client
    """
    from providers.opensource.redis_client import RedisClient

    logger.info("Creating RedisClient")
    return RedisClient()


def create_timeseries_db() -> BaseTimeSeriesDB:
    """
    Create time-series database client

    Currently always returns ClickHouseClient
    Future: Could support TimescaleDB, InfluxDB

    Returns:
        BaseTimeSeriesDB: ClickHouse client
    """
    from providers.opensource.clickhouse import ClickHouseClient

    logger.info("Creating ClickHouseClient")
    return ClickHouseClient()


def create_storage_client() -> BaseStorageClient:
    """
    Create storage client based on CLOUD_PROVIDER config

    Returns:
        BaseStorageClient: S3, GCS, Azure Blob, etc.

    Examples:
        >>> # .env: CLOUD_PROVIDER=aws or localstack
        >>> client = create_storage_client()  # Returns S3StorageClient
        >>>
        >>> # .env: CLOUD_PROVIDER=gcp
        >>> client = create_storage_client()  # Returns GCSStorageClient
    """
    settings = get_settings()
    provider = settings.CLOUD_PROVIDER.lower()

    if provider in ["aws", "localstack", "opensource"]:
        # For opensource: use LocalStack S3 for data lake storage
        from providers.aws.s3 import S3StorageClient

        logger.info(f"✓ Creating S3StorageClient ({provider})")
        return S3StorageClient()

    elif provider == "gcp":
        # TODO: Implement GCSStorageClient
        raise NotImplementedError("GCP GCSStorageClient not implemented yet")

    elif provider == "azure":
        # TODO: Implement BlobStorageClient
        raise NotImplementedError("Azure BlobStorageClient not implemented yet")

    else:
        raise ValueError(
            f"Unsupported cloud provider: {provider}. "
            f"Supported: aws, localstack, opensource, gcp, azure"
        )


def create_exchange_websockets() -> list[BaseExchangeWebSocket]:
    """
    Create exchange WebSocket clients based on YAML configuration

    Reads from: config/providers/exchanges.yaml
    Only creates clients for exchanges where enabled=true

    Returns:
        List[BaseExchangeWebSocket]: List of exchange clients

    Examples:
        >>> # exchanges.yaml: binance.enabled=true, coinbase.enabled=true
        >>> exchanges = create_exchange_websockets()
        >>> len(exchanges)
        2
        >>>
        >>> # To disable an exchange, set enabled=false in YAML
    """
    from config.loader import get_enabled_exchanges

    # Load enabled exchanges from YAML
    enabled_configs = get_enabled_exchanges()

    exchanges = []

    for exchange_name, config in enabled_configs.items():
        logger.info(f"Creating {config.name} WebSocket client ({len(config.symbols)} symbols)")

        if exchange_name == "binance":
            from providers.binance.websocket import BinanceWebSocketClient

            exchanges.append(BinanceWebSocketClient(config.symbol_list))

        elif exchange_name == "coinbase":
            from providers.coinbase.websocket import CoinbaseWebSocketClient

            exchanges.append(CoinbaseWebSocketClient(config.symbol_list))

        elif exchange_name == "kraken":
            from providers.kraken.websocket import KrakenWebSocketClient

            exchanges.append(KrakenWebSocketClient(config.symbol_list))

        else:
            logger.warning(
                f"Exchange '{exchange_name}' is configured but no WebSocket client "
                f"implementation found (skipping)"
            )

    if not exchanges:
        raise ValueError("No exchanges created. Check config/providers/exchanges.yaml")

    logger.info(
        f"✓ Created {len(exchanges)} exchange WebSocket clients: {list(enabled_configs.keys())}"
    )
    return exchanges


def create_exchange_rest_api(exchange_name: str) -> BaseExchangeRestAPI:
    """
    Factory method for creating exchange REST API clients.

    Industry standard: Use REST API for authoritative OHLCV/klines data.
    WebSocket trades only capture ~4% of volume, REST is authoritative.

    Args:
        exchange_name: Exchange identifier ("binance", "coinbase", "kraken")

    Returns:
        BaseExchangeRestAPI implementation for the specified exchange

    Examples:
        >>> # Create Binance REST API client
        >>> api = create_exchange_rest_api("binance")
        >>> candles = await api.fetch_latest_klines("BTC/USDT", "1m", limit=100)
        >>>
        >>> # Fetch historical range
        >>> from datetime import datetime, timezone, timedelta
        >>> end = datetime.now(timezone.utc)
        >>> start = end - timedelta(hours=1)
        >>> candles = await api.fetch_klines("BTC/USDT", "1m", start, end)
        >>>
        >>> await api.close()

    Raises:
        ValueError: If exchange_name is not supported
    """
    exchange_lower = exchange_name.lower()

    if exchange_lower == "binance":
        from providers.binance.rest_api import BinanceRestAPI

        logger.info("✓ Creating BinanceRestAPI")
        return BinanceRestAPI()

    elif exchange_lower == "coinbase":
        from providers.coinbase.rest_api import CoinbaseRestAPI

        logger.info("✓ Creating CoinbaseRestAPI")
        return CoinbaseRestAPI()

    elif exchange_lower == "kraken":
        from providers.kraken.rest_api import KrakenRestAPI

        logger.info("✓ Creating KrakenRestAPI")
        return KrakenRestAPI()

    else:
        raise ValueError(
            f"Unknown exchange: {exchange_name}. "
            f"Supported: binance, coinbase, kraken"
        )
