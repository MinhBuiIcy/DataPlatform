"""Interfaces module - Abstract base classes for cloud services"""

from .cache import BaseCacheClient
from .database import BaseTimeSeriesDB
from .storage import BaseStorageClient
from .streaming_consumer import BaseStreamConsumer
from .streaming_producer import BaseStreamProducer

__all__ = [
    "BaseStreamProducer",
    "BaseStreamConsumer",
    "BaseTimeSeriesDB",
    "BaseCacheClient",
    "BaseStorageClient",
]
