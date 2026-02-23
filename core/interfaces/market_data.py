"""
Abstract base classes for exchange clients

Cloud-agnostic interfaces for:
- WebSocket real-time data (BaseExchangeWebSocket)
- REST API historical/authoritative data (BaseExchangeRestAPI)
"""

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime

from core.models.market_data import Candle, OrderBook, Trade

logger = logging.getLogger(__name__)


class BaseExchangeWebSocket(ABC):
    """
    Abstract base class for exchange WebSocket clients

    Cloud-agnostic interface - supports any exchange (Binance, Coinbase, Kraken, etc.)

    Uses an internal asyncio.Queue to decouple WebSocket message reading from
    callback processing. This prevents slow callbacks from blocking the WebSocket
    reader and causing ping/pong timeouts.

    Implementations:
    - BinanceWebSocketClient (providers/binance/websocket.py)
    - CoinbaseWebSocketClient (providers/coinbase/websocket.py)
    - KrakenWebSocketClient (providers/kraken/websocket.py)

    Example:
        >>> from providers.binance.websocket import BinanceWebSocketClient
        >>>
        >>> # Create client
        >>> client = BinanceWebSocketClient(["BTCUSDT", "ETHUSDT"])
        >>>
        >>> # Register callbacks
        >>> async def handle_trade(trade: Trade):
        ...     print(f"Trade: {trade.symbol} @ {trade.price}")
        >>>
        >>> client.on_trade(handle_trade)
        >>>
        >>> # Connect and start
        >>> await client.connect()
        >>> client.start_consumer()
        >>> await client.start()
    """

    def __init__(self, symbols: list[str]):
        """
        Initialize WebSocket client

        Args:
            symbols: List of trading symbols (e.g., ["BTCUSDT", "ETHUSDT"])
        """
        self.symbols = symbols
        self.callbacks_trade: list[Callable[[Trade], Awaitable[None]]] = []
        self.callbacks_orderbook: list[Callable[[OrderBook], Awaitable[None]]] = []
        self.running = False

        # Load config from settings (lazy to avoid import at module level)
        self._queue: asyncio.Queue | None = None
        self._consumer_tasks: list[asyncio.Task] = []
        self._last_orderbook_time: dict[str, float] = {}  # symbol_key → monotonic time
        self._ws_config_cache: dict | None = None

    def _get_ws_config(self) -> dict:
        """Load WebSocket config from settings (cached after first call)."""
        if self._ws_config_cache is not None:
            return self._ws_config_cache
        from config.settings import get_settings
        settings = get_settings()
        self._ws_config_cache = {
            "queue_max_size": settings.WS_QUEUE_MAX_SIZE,
            "consumer_workers": settings.WS_CONSUMER_WORKERS,
            "ping_interval": settings.WS_PING_INTERVAL,
            "ping_timeout": settings.WS_PING_TIMEOUT,
            "max_message_size": settings.WS_MAX_MESSAGE_SIZE,
            "orderbook_sample_interval_s": settings.WS_ORDERBOOK_SAMPLE_INTERVAL_MS / 1000.0,
        }
        return self._ws_config_cache

    def _ensure_queue(self) -> asyncio.Queue:
        """Lazily create the queue (needs event loop context)."""
        if self._queue is None:
            config = self._get_ws_config()
            self._queue = asyncio.Queue(maxsize=config["queue_max_size"])
        return self._queue

    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to exchange WebSocket

        This should:
        1. Establish WebSocket connection
        2. Send subscription messages
        3. Verify connection success

        Raises:
            ConnectionError: If connection fails
        """

    @abstractmethod
    async def start(self) -> None:
        """
        Start WebSocket message loop

        This should:
        1. Set self.running = True
        2. Start listening for messages
        3. Parse and dispatch to callbacks
        4. Handle reconnections on disconnect

        This is a long-running coroutine that doesn't return until stop() is called.
        """

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop WebSocket and cleanup

        This should:
        1. Set self.running = False
        2. Close WebSocket connection
        3. Cancel any pending tasks
        """

    @abstractmethod
    def _parse_trade(self, data: dict) -> Trade:
        """
        Parse exchange-specific trade format to standard Trade model

        Args:
            data: Raw trade data from exchange WebSocket

        Returns:
            Normalized Trade object
        """

    @abstractmethod
    def _parse_orderbook(self, data: dict) -> OrderBook:
        """
        Parse exchange-specific order book format to standard OrderBook model

        Args:
            data: Raw order book data from exchange WebSocket

        Returns:
            Normalized OrderBook object
        """

    def on_trade(self, callback: Callable[[Trade], Awaitable[None]]) -> None:
        """Register trade callback."""
        self.callbacks_trade.append(callback)

    def on_orderbook(self, callback: Callable[[OrderBook], Awaitable[None]]) -> None:
        """Register order book callback."""
        self.callbacks_orderbook.append(callback)

    def start_consumer(self) -> None:
        """Start background queue consumer workers.

        Must be called after callbacks are registered and before start().
        Number of workers is configured via exchanges.yaml websocket.consumer_workers.
        """
        config = self._get_ws_config()
        num_workers = config["consumer_workers"]
        self._ensure_queue()
        for i in range(num_workers):
            task = asyncio.create_task(self._consume_queue(), name=f"ws-consumer-{i}")
            self._consumer_tasks.append(task)
        logger.info(f"Started {num_workers} queue consumer workers")

    async def stop_consumer(self) -> None:
        """Stop all background queue consumer workers."""
        for task in self._consumer_tasks:
            if not task.done():
                task.cancel()
        for task in self._consumer_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._consumer_tasks.clear()

    async def _notify_trade(self, trade: Trade) -> None:
        """
        Enqueue a trade for async processing.

        Non-blocking: drops the message if queue is full to keep
        the WebSocket reader fast.
        """
        queue = self._ensure_queue()
        try:
            queue.put_nowait(("trade", trade))
        except asyncio.QueueFull:
            logger.warning(
                f"Queue full, dropping trade: {trade.exchange}:{trade.symbol}"
            )

    async def _notify_orderbook(self, orderbook: OrderBook) -> None:
        """
        Enqueue an orderbook for async processing.

        Pre-filters by sampling: keeps at most 1 orderbook per symbol per
        configured interval. This reduces queue pressure from ~200 msg/s
        to ~20 msg/s (1/s × 20 symbols).
        """
        # Pre-filter: sample 1 per symbol per interval
        symbol_key = f"{orderbook.exchange}:{orderbook.symbol}"
        now = time.monotonic()
        last = self._last_orderbook_time.get(symbol_key, 0.0)
        interval = self._get_ws_config()["orderbook_sample_interval_s"]

        if now - last < interval:
            return  # Skip, too soon since last sample

        self._last_orderbook_time[symbol_key] = now

        queue = self._ensure_queue()
        try:
            queue.put_nowait(("orderbook", orderbook))
        except asyncio.QueueFull:
            logger.warning(
                f"Queue full, dropping orderbook: {orderbook.exchange}:{orderbook.symbol}"
            )

    async def _consume_queue(self) -> None:
        """Background consumer that processes queued messages via callbacks."""
        queue = self._ensure_queue()
        while True:
            try:
                msg_type, data = await queue.get()

                if msg_type == "trade":
                    for callback in self.callbacks_trade:
                        try:
                            await callback(data)
                        except Exception as e:
                            logger.error(f"Error in trade callback: {e}")
                elif msg_type == "orderbook":
                    for callback in self.callbacks_orderbook:
                        try:
                            await callback(data)
                        except Exception as e:
                            logger.error(f"Error in orderbook callback: {e}")

                queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue consumer: {e}")


class BaseExchangeRestAPI(ABC):
    """
    Abstract base class for exchange REST API clients.

    Industry standard pattern: Use REST API for authoritative OHLCV/klines data,
    not WebSocket trades (which only capture ~4% of volume).

    Each exchange implements this interface to provide:
    - OHLCV/klines data fetching
    - Supported timeframes
    - Rate limit handling

    Pattern mirrors BaseExchangeWebSocket for consistency.

    Implementations:
    - BinanceRestAPI (providers/binance/rest_api.py)
    - CoinbaseRestAPI (providers/coinbase/rest_api.py)
    - KrakenRestAPI (providers/kraken/rest_api.py)

    Example:
        >>> from factory.client_factory import create_exchange_rest_api
        >>>
        >>> # Create client via factory
        >>> api = create_exchange_rest_api("binance")
        >>>
        >>> # Fetch latest candles
        >>> candles = await api.fetch_latest_klines("BTCUSDT", "1m", limit=100)
        >>>
        >>> # Fetch historical range
        >>> from datetime import datetime, timezone, timedelta
        >>> end = datetime.now(timezone.utc)
        >>> start = end - timedelta(hours=1)
        >>> candles = await api.fetch_klines("BTCUSDT", "1m", start, end)
        >>>
        >>> await api.close()
    """

    def __init__(self, exchange_name: str):
        """
        Initialize REST API client

        Args:
            exchange_name: Exchange identifier (e.g., "binance", "coinbase")
        """
        self.exchange_name = exchange_name

    @abstractmethod
    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[Candle]:
        """
        Fetch OHLCV klines from exchange REST API.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT", "BTC-USD")
            timeframe: Interval (e.g., "1m", "5m", "1h")
            start: Start time (inclusive, timezone-aware)
            end: End time (inclusive, timezone-aware)
            limit: Max candles to fetch per request (default 500)

        Returns:
            List of Candle objects, sorted by timestamp ascending

        Raises:
            ExchangeAPIError: If API request fails
            RateLimitError: If rate limit exceeded
        """

    @abstractmethod
    async def fetch_latest_klines(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[Candle]:
        """
        Fetch latest N klines (most recent data).

        Used by Sync Service to fetch latest candles without
        needing to specify time range.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            timeframe: Interval (e.g., "1m", "5m", "1h")
            limit: Number of latest candles to fetch (default 100)

        Returns:
            List of Candle objects, sorted by timestamp ascending

        Raises:
            ExchangeAPIError: If API request fails
        """

    @abstractmethod
    def get_supported_timeframes(self) -> list[str]:
        """
        Get supported timeframes for this exchange.

        Returns:
            List of timeframe strings (e.g., ["1m", "5m", "1h", "1d"])
        """

    @abstractmethod
    async def close(self) -> None:
        """Close API client connections and cleanup resources"""
