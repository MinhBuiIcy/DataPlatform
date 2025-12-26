"""Interfaces module - Abstract base classes for cloud services"""

from .cache import BaseCacheClient
from .database import BaseTimeSeriesDB
from .storage import BaseStorageClient
from .streaming import BaseStreamClient

__all__ = [
    "BaseStreamClient",
    "BaseTimeSeriesDB",
    "BaseCacheClient",
    "BaseStorageClient",
]
