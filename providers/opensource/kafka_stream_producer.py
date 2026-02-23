"""
Kafka implementation of stream client

Works with Kafka (KRaft mode) - no ZooKeeper needed

NEW (Phase 2 WebSocket Stability): Uses queued interface pattern from BaseStreamProducer
"""

import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from config.settings import get_settings
from core.interfaces.streaming_producer import BaseStreamProducer

logger = logging.getLogger(__name__)


class KafkaStreamProducer(BaseStreamProducer):
    """
    Kafka stream implementation with internal queue + worker pool

    Architecture:
        StreamProcessor → enqueue_record() → Queue → Workers → Kafka
                              ↓ (fast)
                          Non-blocking

    Features:
    - Internal queue (5000 records) + worker pool (10 workers)
    - enqueue_record() is FAST (sync put_nowait, no await)
    - Workers handle actual Kafka sends in background
    - No WebSocket backpressure
    - Production-ready for Phase 6
    """

    def __init__(self):
        super().__init__()  # Initialize queue + workers from BaseStreamProducer
        self.settings = get_settings()
        self.producer = None

    async def connect(self) -> None:
        """Connect to Kafka + start worker pool"""
        # Start workers FIRST (BaseStreamProducer.connect())
        await super().connect()

        # Then connect to Kafka
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                compression_type="gzip",  # Compress messages
                acks=0,  # Fire-and-forget (no broker ack wait)
                max_request_size=1048576,  # 1MB max message size
                linger_ms=10,  # Batch quickly (10ms)
                max_batch_size=65536,  # Batch up to 64KB before sending
            )

            await self.producer.start()

            logger.info(f"✓ Connected to Kafka: {self.settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"✗ Failed to connect to Kafka: {e}")
            raise

    async def _send_impl(self, stream_name: str, data: dict[str, Any], partition_key: str) -> None:
        """
        Actual Kafka send (called by worker from BaseStreamProducer)

        This does the real I/O. Called in background by worker pool.
        """
        if not self.producer:
            raise RuntimeError("Kafka producer not connected")

        try:
            # Kafka batches internally via linger_ms/max_batch_size
            await self.producer.send(topic=stream_name, value=data, key=partition_key)
        except Exception as e:
            logger.error(f"✗ Kafka send error: {e}")
            # Don't raise - worker continues processing other messages

    async def send_batch(self, stream_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Send batch of records (more efficient)

        Args:
            stream_name: Topic name
            records: List of records with 'data' and 'partition_key' fields

        Returns:
            Response with success count
        """
        if not self.producer:
            raise RuntimeError("Kafka producer not connected")

        try:
            # Send all records (Kafka will batch internally)
            tasks = [
                self.producer.send(
                    topic=stream_name, value=record["data"], key=record["partition_key"]
                )
                for record in records
            ]

            # Wait for all sends
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes/failures
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            failure_count = len(results) - success_count

            if failure_count > 0:
                logger.warning(
                    f"⚠ Kafka batch: {failure_count} records failed out of {len(records)}"
                )
            else:
                logger.debug(f"Sent {len(records)} records to {stream_name}")

            return {"total": len(records), "success": success_count, "failed": failure_count}

        except Exception as e:
            logger.error(f"✗ Kafka send_batch error: {e}")
            raise

    async def close(self) -> None:
        """Stop workers + close Kafka"""
        # Close Kafka producer first
        if self.producer:
            try:
                await self.producer.stop()
                logger.info("✓ Kafka producer closed")
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")

        # Stop workers + flush queue (BaseStreamProducer.close())
        await super().close()
