"""
Abstract base class for exchange WebSocket clients

Cloud-agnostic interface for connecting to cryptocurrency exchanges
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from core.models.market_data import OrderBook, Trade


class BaseExchangeWebSocket(ABC):
    """
    Abstract base class for exchange WebSocket clients

    Cloud-agnostic interface - supports any exchange (Binance, Coinbase, Kraken, etc.)

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

        Example:
            >>> # Binance format
            >>> data = {
            ...     "e": "trade",
            ...     "s": "BTCUSDT",
            ...     "p": "50000.00",
            ...     "q": "0.1",
            ...     "T": 1640000000000
            ... }
            >>> trade = self._parse_trade(data)
        """

    @abstractmethod
    def _parse_orderbook(self, data: dict) -> OrderBook:
        """
        Parse exchange-specific order book format to standard OrderBook model

        Args:
            data: Raw order book data from exchange WebSocket

        Returns:
            Normalized OrderBook object

        Example:
            >>> # Binance depth format
            >>> data = {
            ...     "bids": [["50000", "0.1"], ["49999", "0.2"]],
            ...     "asks": [["50001", "0.15"], ["50002", "0.25"]]
            ... }
            >>> orderbook = self._parse_orderbook(data)
        """

    def on_trade(self, callback: Callable[[Trade], Awaitable[None]]) -> None:
        """
        Register trade callback

        The callback will be called for every trade received.

        Args:
            callback: Async function that takes a Trade object

        Example:
            >>> async def handle_trade(trade: Trade):
            ...     print(f"New trade: {trade.symbol} @ {trade.price}")
            >>>
            >>> client.on_trade(handle_trade)
        """
        self.callbacks_trade.append(callback)

    def on_orderbook(self, callback: Callable[[OrderBook], Awaitable[None]]) -> None:
        """
        Register order book callback

        The callback will be called for every order book update received.

        Args:
            callback: Async function that takes an OrderBook object

        Example:
            >>> async def handle_orderbook(ob: OrderBook):
            ...     print(f"Order book: {ob.symbol} spread={ob.spread}")
            >>>
            >>> client.on_orderbook(handle_orderbook)
        """
        self.callbacks_orderbook.append(callback)

    async def _notify_trade(self, trade: Trade) -> None:
        """
        Notify all trade callbacks

        Called internally when a trade is received and parsed.

        Args:
            trade: Parsed Trade object
        """
        for callback in self.callbacks_trade:
            try:
                await callback(trade)
            except Exception as e:
                # Don't let callback errors crash the WebSocket
                print(f"Error in trade callback: {e}")

    async def _notify_orderbook(self, orderbook: OrderBook) -> None:
        """
        Notify all order book callbacks

        Called internally when an order book update is received and parsed.

        Args:
            orderbook: Parsed OrderBook object
        """
        for callback in self.callbacks_orderbook:
            try:
                await callback(orderbook)
            except Exception as e:
                # Don't let callback errors crash the WebSocket
                print(f"Error in orderbook callback: {e}")
