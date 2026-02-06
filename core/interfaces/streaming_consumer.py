"""
Abstract interface for stream consumers (consuming messages)
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class BaseStreamConsumer(ABC):
    """
    Abstract interface for stream consumers

    Implementations:
    - KafkaStreamConsumer (Open-source)
    - KinesisStreamConsumer (AWS)
    - PubSubConsumer (GCP)
    - EventHubConsumer (Azure)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to stream service"""

    @abstractmethod
    async def subscribe(self, topics: list[str]) -> None:
        """
        Subscribe to topics

        Args:
            topics: List of topic names to subscribe to
        """

    @abstractmethod
    async def consume(self) -> AsyncIterator[dict[str, Any]]:
        """
        Consume messages from subscribed topics

        Yields:
            Message data as dictionary

        Example:
            async for message in consumer.consume():
                print(message)
        """

    @abstractmethod
    async def commit(self) -> None:
        """Commit current offset (acknowledge message processing)"""

    @abstractmethod
    async def close(self) -> None:
        """Cleanup connections"""
