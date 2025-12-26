"""
Market Data Ingestion Service - Entry Point

Multi-Exchange Real-Time Data Ingestion:
- Auto-configured from config/providers/exchanges.yaml
- Trades + Order book depth data
- Data quality validation
- Distributes to: Kinesis, S3, ClickHouse, Redis
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.loader import get_enabled_exchanges, load_exchanges_config
from config.settings import get_settings
from factory.client_factory import create_exchange_websockets
from services.market_data_ingestion.stream_processor import StreamProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/logs/market_data_ingestion.log"),
    ],
)
logger = logging.getLogger(__name__)


async def sync_symbol_mappings(clickhouse_client):
    """
    Auto-sync symbol mappings from exchanges.yaml to ClickHouse

    This ensures Grafana dashboards always have up-to-date symbol mappings
    for multi-exchange comparison. Runs on service startup.

    Args:
        clickhouse_client: Connected ClickHouse client
    """
    try:
        logger.info("🔄 Syncing symbol mappings to ClickHouse...")

        # Load all exchanges (including disabled, to keep mappings complete)
        configs = load_exchanges_config()

        # Build mappings list
        mappings = []
        for exchange_name, config in configs.items():
            for symbol in config.symbols:
                mappings.append(
                    (
                        symbol.base,  # BTC
                        symbol.quote,  # USDT
                        exchange_name,  # binance
                        symbol.native,  # BTCUSDT
                    )
                )

        # Clear existing mappings
        clickhouse_client.client.execute("TRUNCATE TABLE trading.symbol_mappings")

        # Insert new mappings
        query = """
            INSERT INTO trading.symbol_mappings
            (base_asset, quote_asset, exchange, symbol)
            VALUES
        """
        clickhouse_client.client.execute(query, mappings)

        # Verify count
        result = clickhouse_client.client.execute("SELECT COUNT(*) FROM trading.symbol_mappings")
        count = result[0][0]

        logger.info(f"✓ Synced {count} symbol mappings from exchanges.yaml to ClickHouse")

    except Exception as e:
        logger.error(f"✗ Failed to sync symbol mappings: {e}")
        # Don't raise - symbol mappings are not critical for data ingestion
        # Grafana will just show raw symbols without normalization


async def main():
    """
    Multi-exchange market data ingestion orchestrator

    Architecture:
    - Configured via YAML (config/providers/exchanges.yaml)
    - Multiple exchanges running concurrently
    - Single StreamProcessor handles all exchanges
    - Callbacks registered for trades + order books
    - Distributes to: Kinesis, S3, ClickHouse, Redis

    Usage:
        python services/market_data_ingestion/main.py

    Configuration:
        Edit config/providers/exchanges.yaml to:
        - Enable/disable exchanges (enabled: true/false)
        - Add/remove symbols
        - Configure features and rate limits
    """

    settings = get_settings()

    # Load exchange configurations
    enabled_configs = get_enabled_exchanges()
    total_symbols = sum(len(c.symbols) for c in enabled_configs.values())

    logger.info("=" * 70)
    logger.info("🚀 Multi-Exchange Market Data Ingestion Service")
    logger.info("=" * 70)

    for name, config in enabled_configs.items():
        symbol_names = [s.native for s in config.symbols[:5]]
        logger.info(
            f"📊 {config.name}: {len(config.symbols)} symbols - "
            f"{', '.join(symbol_names)}{'...' if len(config.symbols) > 5 else ''}"
        )

    logger.info(f"📊 Total: {total_symbols} trading pairs across {len(enabled_configs)} exchanges")
    logger.info("=" * 70)

    # Create WebSocket clients via factory (auto-configured from YAML)
    exchanges = create_exchange_websockets()

    # Single processor handles all exchanges (4 destinations)
    processor = StreamProcessor(buffer_size=100)

    # Connect to all downstream systems
    logger.info("🔗 Connecting to downstream systems...")
    await processor.connect()

    # Auto-sync symbol mappings to ClickHouse (for Grafana dashboards)
    await sync_symbol_mappings(processor.timeseries_db)

    # Register callbacks - all exchanges → same processor
    logger.info("📡 Registering callbacks...")
    for exchange in exchanges:
        exchange.on_trade(processor.process_trade)
        exchange.on_orderbook(processor.process_orderbook)

    logger.info("✓ All callbacks registered")

    # Print startup banner
    print("\n" + "=" * 70)
    print("🚀 MULTI-EXCHANGE REAL-TIME DATA INGESTION - RUNNING")
    print("=" * 70)
    print(f"📊 Exchanges:     {', '.join(c.name for c in enabled_configs.values())}")
    print(f"📈 Symbols:       {total_symbols} total pairs")
    print("📦 Data Types:    Trades + Order Books")
    print("🔄 Destinations:  Kinesis, S3, ClickHouse, Redis")
    print(
        f"⚡ Buffer Size:   {processor.buffer_size} trades, {processor.orderbook_buffer_size} orderbooks"
    )
    print(
        f"✅ Validation:    Enabled (spike detection: {processor.validator.spike_threshold_pct}%)"
    )
    print("=" * 70)
    print(f"🔗 Kinesis:       {settings.KINESIS_STREAM_MARKET_TRADES}")
    print(f"🔗 S3:            {settings.S3_BUCKET_RAW_DATA}")
    print(f"🔗 ClickHouse:    {settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}")
    print(f"🔗 Redis:         {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print("=" * 70)
    print("📝 Configuration: config/providers/exchanges.yaml")
    print("=" * 70)
    print("Press Ctrl+C to stop gracefully")
    print("=" * 70 + "\n")

    try:
        # Connect all exchanges first (build URLs)
        logger.info(f"🔗 Connecting to {len(exchanges)} exchanges...")
        for exchange in exchanges:
            await exchange.connect()

        # Start all exchanges concurrently
        logger.info(f"🚀 Starting {len(exchanges)} exchanges...")
        await asyncio.gather(*[exchange.start() for exchange in exchanges])

    except KeyboardInterrupt:
        logger.info("\n⏹ Shutting down gracefully...")

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)

    finally:
        # Cleanup
        logger.info("🧹 Cleaning up...")
        for exchange in exchanges:
            await exchange.stop()
        await processor.close()
        logger.info("✓ Service stopped cleanly")
        print("=" * 70)


if __name__ == "__main__":
    # Ensure log directory exists
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Run service
    asyncio.run(main())
