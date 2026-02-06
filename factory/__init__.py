"""Factory package - Dependency injection for cloud-agnostic code"""

from .client_factory import (
    create_cache_client,
    create_storage_client,
    create_stream_consumer,
    create_stream_producer,
    create_timeseries_db,
)

__all__ = [
    "create_stream_producer",
    "create_stream_consumer",
    "create_cache_client",
    "create_timeseries_db",
    "create_storage_client",
]
