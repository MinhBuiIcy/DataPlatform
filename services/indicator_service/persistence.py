"""
Indicator Persistence - Save to cache + database

Strategy:
1. Cache-first (blocking, critical path, ~1-5ms) - Hot data, 60s TTL
2. Database (background, non-blocking) - Cold storage, historical data

Cloud-agnostic:
- Cache: Redis, Memcached, etc. (via BaseCacheClient)
- Database: ClickHouse, TimescaleDB, etc. (via BaseTimeSeriesDB)

Architecture:
    save_indicators() →
        ├─ _write_cache() (await - blocking)
        └─ _write_db() (asyncio.create_task - background)
"""

import json
import logging
from datetime import datetime, timedelta

from core.interfaces.cache import BaseCacheClient
from core.interfaces.database import BaseTimeSeriesDB

logger = logging.getLogger(__name__)


class IndicatorPersistence:
    """Save indicator results to cache (hot) + database (cold)"""

    def __init__(self, db: BaseTimeSeriesDB, cache: BaseCacheClient):
        self.db = db
        self.cache = cache

    async def save_indicators(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        indicators: dict[str, float],
    ) -> None:
        """
        Save indicators to cache + database

        Critical path: Cache write (blocking)
        Background: Database write (non-blocking)
        """
        if not indicators:
            logger.warning(f"No indicators to save for {exchange}/{symbol}/{timeframe}")
            return

        # Step 1: Cache-first (blocking - critical path)
        await self._write_cache(exchange, symbol, timeframe, timestamp, indicators)

        # Step 2: Database (sequential - avoids connection conflicts)
        await self._write_db(exchange, symbol, timeframe, timestamp, indicators)

    async def _write_cache(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        indicators: dict[str, float],
    ) -> None:
        """
        Write to cache with TTL

        Key: indicators:{exchange}:{symbol}:{timeframe}
        Value: JSON {timestamp, indicators}
        TTL: 60s
        """
        try:
            key = f"indicators:{exchange}:{symbol}:{timeframe}"
            value = {
                "timestamp": timestamp.isoformat(),
                "indicators": indicators,
            }

            await self.cache.set(key, json.dumps(value), ttl=timedelta(seconds=60))
            logger.debug(f"✓ Cached {len(indicators)} indicators for {symbol}")

        except Exception as e:
            # Cache miss is acceptable - log but don't crash
            logger.error(f"✗ Cache write failed for {symbol}: {e}")

    async def _write_db(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        indicators: dict[str, float],
    ) -> None:
        """
        Write to database (background)

        Uses ReplacingMergeTree (ClickHouse) or similar for deduplication
        """
        try:
            count = await self.db.insert_indicators(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                indicators=indicators,
            )

            logger.debug(f"✓ Database saved {count} indicators for {symbol}")

        except Exception as e:
            logger.error(f"✗ Database write failed for {symbol}: {e}", exc_info=True)

    async def get_from_cache(
        self, exchange: str, symbol: str, timeframe: str
    ) -> dict[str, float] | None:
        """
        Get latest indicators from cache

        Returns:
            Dict of indicators or None if cache miss
        """
        try:
            key = f"indicators:{exchange}:{symbol}:{timeframe}"
            cached = await self.cache.get(key)

            if not cached:
                return None

            data = json.loads(cached)
            return data.get("indicators")

        except Exception as e:
            logger.error(f"Cache read error for {symbol}: {e}")
            return None
