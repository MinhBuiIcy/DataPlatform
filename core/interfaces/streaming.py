from abc import ABC, abstractmethod
from typing import Any


class BaseStreamClient(ABC):
    """
    Abstract interface for stream processing

    Implementations:
    - KinesisStreamClient (AWS)
    - KafkaStreamClient (Open-source)
    - PubSubClient (GCP)
    - EventHubClient (Azure)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to stream service"""

    @abstractmethod
    async def send_record(
        self, stream_name: str, data: dict[str, Any], partition_key: str
    ) -> dict[str, Any]:
        """
        Send a single record to stream

        Args:
            stream_name: Name of the stream/topic
            data: Data to send (will be JSON serialized)
            partition_key: Key for partitioning (e.g., symbol)

        Returns:
            Response metadata (shard_id, sequence_number, etc.)
        """

    @abstractmethod
    async def send_batch(self, stream_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Send multiple records in batch (more efficient)

        Args:
            stream_name: Name of the stream/topic
            records: List of records, each with 'data' and 'partition_key'

        Returns:
            Response with success/failure counts
        """

    @abstractmethod
    async def close(self) -> None:
        """Cleanup connections"""
