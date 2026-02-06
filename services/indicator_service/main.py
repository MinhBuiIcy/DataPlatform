"""
Indicator Service - Entry Point

Event-driven Kafka consumer that calculates technical indicators
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import get_settings
from factory.client_factory import (
    create_cache_client,
    create_stream_consumer,
    create_timeseries_db,
)
from services.indicator_service.calculator import IndicatorCalculator
from services.indicator_service.persistence import IndicatorPersistence

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/logs/indicator_service.log"),
    ],
)
logger = logging.getLogger(__name__)


class IndicatorService:
    """Main service orchestrator"""

    def __init__(self):
        self.settings = get_settings()
        self.running = False

        # Initialize clients
        logger.info("🔧 Initializing clients...")
        self.stream = create_stream_consumer()
        self.db = create_timeseries_db()
        self.cache = create_cache_client()

        # Initialize components
        self.persistence = IndicatorPersistence(self.db, self.cache)
        self.calculator = IndicatorCalculator(
            db=self.db,
            persistence=self.persistence,
        )

    async def start(self):
        """Start consuming candle events"""
        logger.info("🚀 Starting Indicator Service...")
        logger.info(f"📊 Kafka topic: {self.settings.KAFKA_TOPIC_CANDLE_EVENTS}")
        logger.info(f"💾 ClickHouse: {self.settings.CLICKHOUSE_HOST}")
        logger.info(f"🔴 Redis: {self.settings.redis_url}")

        self.running = True

        try:
            # Connect to all clients
            await self.stream.connect()
            logger.info("✅ Connected to Kafka")

            await self.db.connect()
            logger.info("✅ Connected to ClickHouse")

            await self.cache.connect()
            logger.info("✅ Connected to Redis")

            # Subscribe to candle events
            await self.stream.subscribe(topics=[self.settings.KAFKA_TOPIC_CANDLE_EVENTS])
            logger.info(f"✅ Subscribed to {self.settings.KAFKA_TOPIC_CANDLE_EVENTS} topic")

            # Consume events
            async for event in self.stream.consume():
                if not self.running:
                    break

                await self._process_event(event)

        except KeyboardInterrupt:
            logger.info("⚠️ Received interrupt signal")
        except Exception as e:
            logger.error(f"❌ Error in event loop: {e}", exc_info=True)
        finally:
            await self.stop()

    async def _process_event(self, event: dict):
        """Process a single candle event"""
        try:
            exchange = event.get("exchange")
            symbol = event.get("symbol")
            timeframe = event.get("timeframe")

            logger.info(
                f"📊 Processing candle event: {exchange}/{symbol}/{timeframe}"
            )

            # Calculate indicators
            await self.calculator.process_candle_event(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
            )

        except Exception as e:
            logger.error(f"❌ Error processing event: {e}", exc_info=True)

    async def stop(self):
        """Graceful shutdown"""
        logger.info("🛑 Stopping Indicator Service...")
        self.running = False

        # Close clients
        if self.stream:
            await self.stream.close()
        if self.db:
            await self.db.close()
        if self.cache:
            await self.cache.close()

        logger.info("✅ Indicator Service stopped")


def signal_handler(service):
    """Handle SIGINT/SIGTERM"""

    def handler(signum, frame):
        logger.info(f"⚠️ Received signal {signum}")
        service.running = False

    return handler


async def main():
    """Main entry point"""
    # Create service
    service = IndicatorService()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler(service))
    signal.signal(signal.SIGTERM, signal_handler(service))

    # Start service
    await service.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
