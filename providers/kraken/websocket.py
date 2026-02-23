"""
Kraken WebSocket client for real-time market data

Handles:
- Trade channel
- Book channel (order book depth)
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


class KrakenWebSocketClient(BaseExchangeWebSocket):
    """
    Kraken WebSocket implementation

    Features:
    - Trade channel for real-time trades
    - Book channel for order book depth (10 levels)
    - Auto-reconnect on disconnect
    - Data normalization to standard models

    WebSocket Documentation:
    https://docs.kraken.com/websockets/
    """

    WS_URL = "wss://ws.kraken.com/"

    def __init__(self, symbols: list[str]):
        """
        Initialize Kraken WebSocket client

        Args:
            symbols: List of pairs (e.g., ["XBT/USD", "ETH/USD"])
        """
        super().__init__(symbols)
        self.websocket = None

    async def connect(self) -> None:
        """
        Connect to Kraken WebSocket

        Subscribes to:
        - Trade channel: real-time trade executions
        - Book channel: order book snapshots and updates (depth 10)
        """
        logger.info(f"Connecting to Kraken WebSocket with {len(self.symbols)} symbols...")
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

                    # Subscribe to trade channel
                    trade_subscription = {
                        "event": "subscribe",
                        "pair": self.symbols,
                        "subscription": {"name": "trade"},
                    }
                    await websocket.send(json.dumps(trade_subscription))

                    # Subscribe to book channel (depth 10)
                    book_subscription = {
                        "event": "subscribe",
                        "pair": self.symbols,
                        "subscription": {"name": "book", "depth": 10},
                    }
                    await websocket.send(json.dumps(book_subscription))

                    logger.info(f"✓ Connected to Kraken WebSocket: {len(self.symbols)} symbols")

                    async for message in websocket:
                        if not self.running:
                            break

                        try:
                            data = json.loads(message)
                            await self._handle_message(data)

                        except Exception as e:
                            logger.error(f"Error processing Kraken message: {e}")
                            continue

            except Exception as e:
                logger.error(f"✗ Kraken WebSocket connection error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def _handle_message(self, data) -> None:
        """
        Route message to appropriate handler

        Kraken messages are arrays:
        - Trade: [channelID, [[price, volume, time, side, ...]], "trade", "XBT/USD"]
        - Book: [channelID, {"bs": [...], "as": [...]}, "book-10", "XBT/USD"]
        - Status: {"event": "heartbeat"} or {"event": "systemStatus"}

        Args:
            data: Parsed JSON message from Kraken
        """
        # Dict messages are status/subscription messages
        if isinstance(data, dict):
            event = data.get("event")
            if event in ["heartbeat", "systemStatus", "subscriptionStatus"]:
                return  # Ignore status messages
            return

        # Array messages are data updates
        if isinstance(data, list) and len(data) >= 4:
            # Book updates with checksum are 5-element arrays where data[2] is a dict:
            # [channelID, data, {"c": "checksum"}, "book-10", "XBT/USD"]
            if isinstance(data[2], dict) and len(data) >= 5:
                channel_name = data[3]
                pair = data[4]
            else:
                channel_name = data[2]
                pair = data[3]

            if channel_name == "trade":
                # Trade data
                trades_list = data[1]
                for trade_data in trades_list:
                    trade = self._parse_trade(trade_data, pair)
                    await self._notify_trade(trade)

            elif channel_name.startswith("book"):
                # Order book data
                book_data = data[1]
                orderbook = self._parse_orderbook(book_data, pair)
                await self._notify_orderbook(orderbook)

    def _parse_trade(self, data: list, pair: str) -> Trade:
        """
        Parse Kraken trade data to Trade model

        Kraken trade format (array):
        [
            "50000.00000",     # Price
            "0.10000000",      # Volume
            "1640000000.123456", # Time (unix timestamp with decimals)
            "b",               # Side: "b" = buy, "s" = sell
            "l",               # Order type: "l" = limit, "m" = market
            ""                 # Misc
        ]

        Args:
            data: Trade data array
            pair: Trading pair (e.g., "XBT/USD")

        Returns:
            Normalized Trade object
        """
        price_str, volume_str, time_str, side_char, order_type, _ = data[:6]

        return Trade(
            timestamp=datetime.fromtimestamp(float(time_str), tz=UTC),
            exchange="kraken",
            symbol=pair,
            trade_id=time_str,  # Kraken doesn't provide trade ID, use timestamp
            price=Decimal(price_str),
            quantity=Decimal(volume_str),
            side="buy" if side_char == "b" else "sell",
            is_buyer_maker=(side_char == "s"),  # Seller is maker if side=s
        )

    def _parse_orderbook(self, data: dict, pair: str) -> OrderBook:
        """
        Parse Kraken book data to OrderBook model

        Kraken book format (dict):
        {
            "as": [              # Asks
                ["50001.00000", "0.15000000", "1640000000.123456"],
                ["50002.00000", "0.25000000", "1640000000.123456"]
            ],
            "bs": [              # Bids
                ["50000.00000", "0.10000000", "1640000000.123456"],
                ["49999.00000", "0.20000000", "1640000000.123456"]
            ]
        }

        Or snapshot format:
        {
            "a": [[price, volume, timestamp], ...],  # Asks (snapshot)
            "b": [[price, volume, timestamp], ...]   # Bids (snapshot)
        }

        Args:
            data: Order book data dict
            pair: Trading pair

        Returns:
            Normalized OrderBook object
        """
        # Handle both snapshot (a/b keys) and update (as/bs keys) formats
        asks_key = "as" if "as" in data else "a"
        bids_key = "bs" if "bs" in data else "b"

        asks = data.get(asks_key, [])
        bids = data.get(bids_key, [])

        return OrderBook(
            timestamp=datetime.now(UTC),
            exchange="kraken",
            symbol=pair,
            bids=[(Decimal(p), Decimal(v)) for p, v, *_ in bids[:10]],  # Top 10
            asks=[(Decimal(p), Decimal(v)) for p, v, *_ in asks[:10]],
            checksum=0,  # Kraken doesn't provide checksum in this format
        )

    async def stop(self) -> None:
        """Stop WebSocket connection and cleanup"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("✓ Kraken WebSocket client stopped")
