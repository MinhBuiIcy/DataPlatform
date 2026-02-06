"""
Kafka consumer implementation

Event-driven consumer for Kafka topics
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from aiokafka import AIOKafkaConsumer

from config.settings import get_settings
from core.interfaces.streaming_consumer import BaseStreamConsumer

logger = logging.getLogger(__name__)


class KafkaStreamConsumer(BaseStreamConsumer):
    """
    Kafka stream consumer implementation

    Features:
    - Async message consumption
    - Auto-commit with configurable interval
    - Consumer groups for load balancing
    - JSON deserialization
    """

    def __init__(self):
        self.settings = get_settings()
        self.consumer = None
        self._topics = []

    async def connect(self) -> None:
        """Initialize Kafka consumer"""
        try:
            self.consumer = AIOKafkaConsumer(
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",  # Start from latest (not earliest)
                enable_auto_commit=True,
                auto_commit_interval_ms=1000,  # Commit every 1s
                group_id=None,  # Will be set when subscribing
            )

            await self.consumer.start()

            logger.info(f"✓ Connected to Kafka consumer: {self.settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"✗ Failed to connect Kafka consumer: {e}")
            raise

    async def subscribe(self, topics: list[str]) -> None:
        """
        Subscribe to topics

        Args:
            topics: List of topic names to subscribe to
        """
        if not self.consumer:
            raise RuntimeError("Kafka consumer not connected")

        self._topics = topics
        self.consumer.subscribe(topics=topics)

        logger.info(f"✓ Subscribed to topics: {', '.join(topics)}")

    async def consume(self) -> AsyncIterator[dict[str, Any]]:
        """
        Consume messages from subscribed topics

        Yields:
            Message data as dictionary
        """
        if not self.consumer:
            raise RuntimeError("Kafka consumer not connected")

        if not self._topics:
            raise RuntimeError("No topics subscribed")

        try:
            async for message in self.consumer:
                logger.debug(
                    f"Consumed message from {message.topic}: "
                    f"Partition={message.partition}, Offset={message.offset}"
                )

                yield message.value

        except Exception as e:
            logger.error(f"✗ Kafka consume error: {e}", exc_info=True)
            raise

    async def commit(self) -> None:
        """
        Commit current offset

        Note: Auto-commit is enabled by default. Only call this for manual commit.
        """
        if not self.consumer:
            raise RuntimeError("Kafka consumer not connected")

        await self.consumer.commit()
        logger.debug("Committed consumer offset")

    async def close(self) -> None:
        """Cleanup connections"""
        if self.consumer:
            await self.consumer.stop()
            logger.info("✓ Kafka consumer closed")
