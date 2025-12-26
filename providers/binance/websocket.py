"""
Binance WebSocket client for real-time market data

Handles:
- Trade streams
- Order book depth updates
- Auto-reconnect on disconnect
- Data normalization to standard models
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

from websockets import connect

from core.interfaces.market_data import BaseExchangeWebSocket
from core.models.market_data import OrderBook, Trade

logger = logging.getLogger(__name__)


class BinanceWebSocketClient(BaseExchangeWebSocket):
    """
    Binance WebSocket implementation

    Features:
    - Multi-symbol streaming (trades + order books)
    - Auto-reconnect on disconnect
    - Data normalization to standard Trade and OrderBook models
    - Callback pattern for event handling

    WebSocket Documentation:
    https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams
    """

    BASE_URL = "wss://stream.binance.com:9443/ws"

    def __init__(self, symbols: list[str]):
        """
        Initialize Binance WebSocket client

        Args:
            symbols: List of symbols (e.g., ["BTCUSDT", "ETHUSDT"])
        """
        super().__init__(symbols)
        self.websocket = None

    async def connect(self) -> None:
        """
        Connect to Binance WebSocket

        Subscribes to:
        - Trade streams: {symbol}@trade
        - Order book depth: {symbol}@depth@100ms (top 10 levels, 100ms updates)
        """
        # Build combined stream URL
        # Format: wss://stream.binance.com:9443/ws/btcusdt@trade/btcusdt@depth@100ms/ethusdt@trade/...
        streams = []
        for symbol in self.symbols:
            symbol_lower = symbol.lower()
            streams.append(f"{symbol_lower}@trade")
            streams.append(f"{symbol_lower}@depth@100ms")

        url = f"{self.BASE_URL}/{'/'.join(streams)}"
        logger.info(f"Connecting to Binance WebSocket with {len(self.symbols)} symbols...")
        self.url = url

    async def start(self) -> None:
        """
        Start WebSocket connection with auto-reconnect

        Runs forever until stop() is called.
        Automatically reconnects on disconnect with 5s delay.
        """
        self.running = True

        while self.running:
            try:
                async with connect(self.url) as websocket:
                    self.websocket = websocket
                    logger.info(f"✓ Connected to Binance WebSocket: {len(self.symbols)} symbols")

                    async for message in websocket:
                        if not self.running:
                            break

                        try:
                            data = json.loads(message)
                            await self._handle_message(data)

                        except Exception as e:
                            logger.error(f"Error processing Binance message: {e}")
                            continue

            except Exception as e:
                logger.error(f"✗ Binance WebSocket connection error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def _handle_message(self, data: dict) -> None:
        """
        Route message to appropriate handler based on event type

        Args:
            data: Parsed JSON message from Binance
        """
        event_type = data.get("e")

        if event_type == "trade":
            # Trade stream
            trade = self._parse_trade(data)
            await self._notify_trade(trade)

        elif event_type == "depthUpdate":
            # Order book depth update
            orderbook = self._parse_orderbook(data)
            await self._notify_orderbook(orderbook)

        else:
            logger.debug(f"Unknown Binance event type: {event_type}")

    def _parse_trade(self, data: dict) -> Trade:
        """
        Parse Binance trade message to Trade model

        Binance trade format:
        {
            "e": "trade",              // Event type
            "E": 1234567890000,        // Event time
            "s": "BTCUSDT",            // Symbol
            "t": 12345,                // Trade ID
            "p": "50000.00",           // Price
            "q": "0.1",                // Quantity
            "T": 1234567890000,        // Trade time
            "m": true,                 // Is buyer maker?
        }

        Args:
            data: Raw Binance trade message

        Returns:
            Normalized Trade object
        """
        return Trade(
            timestamp=datetime.fromtimestamp(data["T"] / 1000, tz=UTC),
            exchange="binance",
            symbol=data["s"],
            trade_id=str(data["t"]),
            price=Decimal(data["p"]),
            quantity=Decimal(data["q"]),
            side="sell" if data["m"] else "buy",  # m=true → buyer is maker → taker is seller
            is_buyer_maker=data["m"],
        )

    def _parse_orderbook(self, data: dict) -> OrderBook:
        """
        Parse Binance depth update to OrderBook model

        Binance depth format:
        {
            "e": "depthUpdate",
            "E": 1234567890000,        // Event time
            "s": "BTCUSDT",            // Symbol
            "U": 123456,               // First update ID
            "u": 123457,               // Final update ID
            "b": [                     // Bids (price, quantity)
                ["50000.00", "0.1"],
                ["49999.00", "0.2"]
            ],
            "a": [                     // Asks (price, quantity)
                ["50001.00", "0.15"],
                ["50002.00", "0.25"]
            ]
        }

        Args:
            data: Raw Binance depth message

        Returns:
            Normalized OrderBook object
        """
        return OrderBook(
            timestamp=datetime.fromtimestamp(data["E"] / 1000, tz=UTC),
            exchange="binance",
            symbol=data["s"],
            bids=[(Decimal(p), Decimal(q)) for p, q in data["b"][:10]],  # Top 10 bids
            asks=[(Decimal(p), Decimal(q)) for p, q in data["a"][:10]],  # Top 10 asks
            checksum=0,  # Binance doesn't provide checksum
        )

    async def stop(self) -> None:
        """Stop WebSocket connection and cleanup"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("✓ Binance WebSocket client stopped")
