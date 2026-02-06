"""
Kafka implementation of stream client

Works with Kafka (KRaft mode) - no ZooKeeper needed
"""

import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from config.settings import get_settings
from core.interfaces.streaming_producer import BaseStreamProducer

logger = logging.getLogger(__name__)


class KafkaStreamProducer(BaseStreamProducer):
    """
    Kafka stream implementation

    Features:
    - Real-time data streaming
    - Auto-scaling partitions
    - Better performance than Kinesis mock
    - No heap overflow issues
    - Production-ready for Phase 6
    """

    def __init__(self):
        self.settings = get_settings()
        self.producer = None

    async def connect(self) -> None:
        """Initialize Kafka producer"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                compression_type="gzip",  # Compress messages
                acks="all",  # Wait for all replicas (durability)
                max_request_size=1048576,  # 1MB max message size
            )

            await self.producer.start()

            logger.info(f"✓ Connected to Kafka: {self.settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"✗ Failed to connect to Kafka: {e}")
            raise

    async def send_record(
        self, stream_name: str, data: dict[str, Any], partition_key: str
    ) -> dict[str, Any]:
        """
        Send single record to Kafka topic

        Args:
            stream_name: Topic name (e.g., 'market-trades')
            data: Data dictionary (will be JSON serialized)
            partition_key: Partition key (e.g., symbol for same-symbol ordering)

        Returns:
            Response with topic, partition, and offset
        """
        if not self.producer:
            raise RuntimeError("Kafka producer not connected")

        try:
            # Send to Kafka (topic = stream_name, key = partition_key)
            metadata = await self.producer.send_and_wait(
                topic=stream_name, value=data, key=partition_key
            )

            logger.debug(
                f"Sent record to {stream_name}: "
                f"Partition={metadata.partition}, Offset={metadata.offset}"
            )

            return {
                "topic": metadata.topic,
                "partition": metadata.partition,
                "offset": metadata.offset,
                "timestamp": metadata.timestamp,
            }

        except Exception as e:
            logger.error(f"✗ Kafka send_record error: {e}")
            raise

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
        """Close producer"""
        if self.producer:
            try:
                await self.producer.stop()
                logger.info("✓ Kafka connection closed")
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")


# Import asyncio for batch operations
import asyncio
