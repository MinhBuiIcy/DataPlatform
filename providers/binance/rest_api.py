"""
Binance REST API client for fetching klines/OHLCV data.

Uses ccxt library for unified exchange interface.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

import ccxt.async_support as ccxt

from config.settings import get_settings
from core.interfaces.market_data import BaseExchangeRestAPI
from core.models.market_data import Candle

logger = logging.getLogger(__name__)


class BinanceRestAPI(BaseExchangeRestAPI):
    """
    Binance REST API client for authoritative klines/OHLCV data.

    Industry standard: Use REST API for candles (not WebSocket trades).
    WebSocket only captures ~4% of trades, REST API is authoritative.

    Uses ccxt library for:
    - Unified interface across exchanges
    - Built-in rate limiting
    - Error handling and retries
    """

    def __init__(self):
        super().__init__(exchange_name="binance")
        settings = get_settings()

        self.client = ccxt.binance(
            {
                "enableRateLimit": settings.REST_API_ENABLE_RATE_LIMIT,
                "timeout": settings.REST_API_TIMEOUT_MS,
            }
        )
        logger.info("BinanceRestAPI initialized")

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[Candle]:
        """
        Fetch klines from Binance REST API.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Interval (e.g., "1m", "5m", "1h")
            start: Start time (inclusive)
            end: End time (inclusive)
            limit: Max candles per request (default 500)

        Returns:
            List of Candle objects
        """
        since = int(start.timestamp() * 1000)  # ccxt uses milliseconds

        try:
            ohlcv = await self.client.fetch_ohlcv(
                symbol, timeframe, since=since, limit=limit
            )

            candles = []
            for row in ohlcv:
                timestamp_ms, open_, high, low, close, volume = row

                # Filter by end time
                candle_time = datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                )
                if candle_time > end:
                    break

                candles.append(
                    Candle(
                        timestamp=candle_time,
                        exchange=self.exchange_name,
                        symbol=symbol,
                        timeframe=timeframe,
                        open=Decimal(str(open_)),
                        high=Decimal(str(high)),
                        low=Decimal(str(low)),
                        close=Decimal(str(close)),
                        volume=Decimal(str(volume)),
                        quote_volume=Decimal(str(volume * close)),  # Approximate
                        trades_count=0,  # Not provided by REST API
                        is_synthetic=False,
                    )
                )

            logger.info(
                f"Fetched {len(candles)} klines for {symbol} {timeframe} "
                f"({start.isoformat()} to {end.isoformat()})"
            )
            return candles

        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol} {timeframe}: {e}")
            raise

    async def fetch_latest_klines(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[Candle]:
        """
        Fetch latest klines (most recent data).

        Used by Sync Service to continuously sync latest candles.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Interval (e.g., "1m", "5m", "1h")
            limit: Number of latest candles (default 100)

        Returns:
            List of Candle objects
        """
        try:
            ohlcv = await self.client.fetch_ohlcv(symbol, timeframe, limit=limit)

            candles = []
            for row in ohlcv:
                timestamp_ms, open_, high, low, close, volume = row
                candle_time = datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                )

                candles.append(
                    Candle(
                        timestamp=candle_time,
                        exchange=self.exchange_name,
                        symbol=symbol,
                        timeframe=timeframe,
                        open=Decimal(str(open_)),
                        high=Decimal(str(high)),
                        low=Decimal(str(low)),
                        close=Decimal(str(close)),
                        volume=Decimal(str(volume)),
                        quote_volume=Decimal(str(volume * close)),
                        trades_count=0,
                        is_synthetic=False,
                    )
                )

            logger.debug(
                f"Fetched {len(candles)} latest klines for {symbol} {timeframe}"
            )
            return candles

        except Exception as e:
            logger.error(f"Failed to fetch latest klines for {symbol}: {e}")
            raise

    def get_supported_timeframes(self) -> list[str]:
        """Binance supported timeframes"""
        return [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "12h",
            "1d",
            "3d",
            "1w",
            "1M",
        ]

    async def close(self) -> None:
        """Close ccxt client"""
        await self.client.close()
        logger.info("BinanceRestAPI closed")
