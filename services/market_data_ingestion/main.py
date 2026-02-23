"""
Market Data Ingestion Service - Simplified for Phase 2

Phase 2 Architecture:
- WebSocket → Redis ONLY (real-time price signals)
- Sync Service → REST API → ClickHouse (authoritative candles)

This service NO LONGER:
- Writes to ClickHouse (no market_trades table)
- Sends to Kinesis/Kafka
- Backs up to S3

It ONLY captures real-time price signals for trading strategies.
"""

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.loader import get_enabled_exchanges
from config.settings import get_settings
from factory.client_factory import create_cache_client, create_exchange_websockets
from services.market_data_ingestion.stream_processor import StreamProcessor

# Configure logging
os.makedirs("data/logs", exist_ok=True)

_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter(_fmt))

_file = RotatingFileHandler(
    "data/logs/market_data_ingestion_errors.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
)
_file.setLevel(logging.ERROR)
_file.setFormatter(logging.Formatter(_fmt))

logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
logger = logging.getLogger(__name__)


async def main():
    """
    Multi-exchange WebSocket ingestion - Redis ONLY

    Architecture (Phase 2):
    - WebSocket trades → Redis (latest_price cache)
    - Sync Service → REST API → ClickHouse (authoritative klines)
    - Indicator Service → ClickHouse (scheduled calculations)

    Why simplified:
    - WebSocket captures only ~4% of trades (sampled)
    - Building candles from WebSocket is inaccurate
    - REST API provides authoritative OHLCV data
    - Redis provides real-time signals for strategies

    Usage:
        python services/market_data_ingestion/main.py

    Configuration:
        Edit config/providers/exchanges.yaml to:
        - Enable/disable exchanges (enabled: true/false)
        - Add/remove symbols
    """

    settings = get_settings()

    # Load exchange configurations
    enabled_configs = get_enabled_exchanges()
    total_symbols = sum(len(c.symbols) for c in enabled_configs.values())

    logger.info("=" * 70)
    logger.info("🚀 Multi-Exchange Market Data Ingestion Service (Phase 2)")
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

    # Create Redis cache client
    cache_client = create_cache_client()

    # Single processor handles all exchanges (Redis ONLY)
    processor = StreamProcessor(cache_client=cache_client)

    # Connect to Redis
    logger.info("🔗 Connecting to Redis...")
    await processor.connect()

    # Register callbacks - all exchanges → same processor
    logger.info("📡 Registering callbacks...")
    for exchange in exchanges:
        exchange.on_trade(processor.process_trade)
        exchange.on_orderbook(processor.process_orderbook)

    logger.info("✓ All callbacks registered")

    # Print startup banner
    print("\n" + "=" * 70)
    print("🚀 MULTI-EXCHANGE WEBSOCKET INGESTION - RUNNING (Redis ONLY)")
    print("=" * 70)
    print(f"📊 Exchanges:     {', '.join(c.name for c in enabled_configs.values())}")
    print(f"📈 Symbols:       {total_symbols} total pairs")
    print("📦 Data Types:    Trades + Order Books")
    print("🔄 Destination:   Redis (real-time signals)")
    print("=" * 70)
    print(f"🔗 Redis:         {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print("=" * 70)
    print("📝 Configuration: config/providers/exchanges.yaml")
    print("=" * 70)
    print("ℹ️  Industry Standard: REST API for candles (Sync Service)")
    print("ℹ️  WebSocket for real-time signals only (~4% of volume)")
    print("=" * 70)
    print("Press Ctrl+C to stop gracefully")
    print("=" * 70 + "\n")

    try:
        # Connect all exchanges first (build URLs)
        logger.info(f"🔗 Connecting to {len(exchanges)} exchanges...")
        for exchange in exchanges:
            await exchange.connect()

        # Start queue consumers (must be after callbacks registered, before start)
        for exchange in exchanges:
            exchange.start_consumer()

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
            await exchange.stop_consumer()
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
