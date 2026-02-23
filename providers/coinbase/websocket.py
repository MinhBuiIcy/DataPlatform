"""
Coinbase WebSocket client for real-time market data

Handles:
- Ticker channel (trade data)
- Level2 channel (order book updates)
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


class CoinbaseWebSocketClient(BaseExchangeWebSocket):
    """
    Coinbase WebSocket implementation

    Features:
    - Ticker channel for trades
    - Level2 channel for order book depth
    - Auto-reconnect on disconnect
    - Data normalization to standard models

    WebSocket Documentation:
    https://docs.cloud.coinbase.com/exchange/docs/websocket-overview
    """

    WS_URL = "wss://ws-feed.exchange.coinbase.com"

    def __init__(self, symbols: list[str]):
        """
        Initialize Coinbase WebSocket client

        Args:
            symbols: List of product IDs (e.g., ["BTC-USD", "ETH-USD"])
        """
        super().__init__(symbols)
        self.websocket = None

    async def connect(self) -> None:
        """
        Connect to Coinbase WebSocket

        Subscribes to:
        - Ticker channel: real-time trade data
        - Level2 channel: order book snapshots and updates
        """
        logger.info(f"Connecting to Coinbase WebSocket with {len(self.symbols)} symbols...")
        self.url = self.WS_URL

    async def start(self) -> None:
        """
        Start WebSocket connection with auto-reconnect

        Runs forever until stop() is called.
        Automatically reconnects on disconnect with 5s delay.
        """
        self.running = True

        while self.running:
            try:
                ws_config = self._get_ws_config()
                async with connect(
                    self.url,
                    ping_interval=ws_config["ping_interval"],
                    ping_timeout=ws_config["ping_timeout"],
                    max_size=ws_config["max_message_size"],
                ) as websocket:
                    self.websocket = websocket

                    # Send subscription message
                    subscribe_message = {
                        "type": "subscribe",
                        "product_ids": self.symbols,
                        "channels": [
                            "ticker",  # Trade data
                            "level2_batch",  # Order book updates
                        ],
                    }
                    await websocket.send(json.dumps(subscribe_message))
                    logger.info(f"✓ Connected to Coinbase WebSocket: {len(self.symbols)} symbols")

                    async for message in websocket:
                        if not self.running:
                            break

                        try:
                            data = json.loads(message)
                            await self._handle_message(data)

                        except Exception as e:
                            logger.error(f"Error processing Coinbase message: {e}")
                            continue

            except Exception as e:
                logger.error(f"✗ Coinbase WebSocket connection error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def _handle_message(self, data: dict) -> None:
        """
        Route message to appropriate handler based on message type

        Args:
            data: Parsed JSON message from Coinbase
        """
        msg_type = data.get("type")

        if msg_type == "ticker":
            # Trade update
            trade = self._parse_trade(data)
            await self._notify_trade(trade)

        elif msg_type == "snapshot":
            # Initial order book snapshot
            orderbook = self._parse_orderbook(data)
            await self._notify_orderbook(orderbook)

        elif msg_type == "l2update":
            # Order book update (incremental)
            orderbook = self._parse_orderbook(data)
            await self._notify_orderbook(orderbook)

        elif msg_type in ["subscriptions", "heartbeat"]:
            # Ignore status messages
            pass

        else:
            logger.debug(f"Unknown Coinbase message type: {msg_type}")

    def _parse_trade(self, data: dict) -> Trade:
        """
        Parse Coinbase ticker message to Trade model

        Coinbase ticker format:
        {
            "type": "ticker",
            "sequence": 1234567890,
            "product_id": "BTC-USD",
            "price": "50000.00",
            "open_24h": "49000.00",
            "volume_24h": "1234.56",
            "last_size": "0.01",
            "best_bid": "49999.99",
            "best_ask": "50000.01",
            "side": "buy",
            "time": "2025-12-23T12:00:00.000000Z",
            "trade_id": 123456789
        }

        Args:
            data: Raw Coinbase ticker message

        Returns:
            Normalized Trade object
        """
        return Trade(
            timestamp=datetime.fromisoformat(data["time"].replace("Z", "+00:00")),
            exchange="coinbase",
            symbol=data["product_id"],
            trade_id=str(data.get("trade_id", 0)),
            price=Decimal(data["price"]),
            quantity=Decimal(data.get("last_size", "0")),
            side=data.get("side", "buy"),
            is_buyer_maker=(data.get("side") == "sell"),  # Seller is maker if side=sell
        )

    def _parse_orderbook(self, data: dict) -> OrderBook:
        """
        Parse Coinbase level2 message to OrderBook model

        Coinbase snapshot format:
        {
            "type": "snapshot",
            "product_id": "BTC-USD",
            "bids": [["50000.00", "0.1"], ["49999.00", "0.2"]],
            "asks": [["50001.00", "0.15"], ["50002.00", "0.25"]]
        }

        Coinbase l2update format:
        {
            "type": "l2update",
            "product_id": "BTC-USD",
            "time": "2025-12-23T12:00:00.000000Z",
            "changes": [
                ["buy", "50000.00", "0.1"],   // [side, price, size]
                ["sell", "50001.00", "0.15"]
            ]
        }

        Args:
            data: Raw Coinbase level2 message

        Returns:
            Normalized OrderBook object
        """
        if data["type"] == "snapshot":
            # Full snapshot
            timestamp = datetime.now(UTC)
            bids = [(Decimal(p), Decimal(s)) for p, s in data["bids"][:10]]
            asks = [(Decimal(p), Decimal(s)) for p, s in data["asks"][:10]]

        else:  # l2update
            # Incremental update - we'll just send the changes as a snapshot
            timestamp = datetime.fromisoformat(data["time"].replace("Z", "+00:00"))
            bids = []
            asks = []

            for change in data.get("changes", []):
                side, price, size = change
                if side == "buy":
                    bids.append((Decimal(price), Decimal(size)))
                else:
                    asks.append((Decimal(price), Decimal(size)))

            # Sort: bids descending, asks ascending
            bids.sort(reverse=True)
            asks.sort()

        return OrderBook(
            timestamp=timestamp,
            exchange="coinbase",
            symbol=data["product_id"],
            bids=bids[:10],  # Top 10
            asks=asks[:10],
            checksum=0,  # Coinbase doesn't provide checksum
        )

    async def stop(self) -> None:
        """Stop WebSocket connection and cleanup"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("✓ Coinbase WebSocket client stopped")
