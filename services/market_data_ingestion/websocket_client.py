"""
Binance WebSocket client for real-time trade streams

Handles:
- Connection with auto-reconnect
- Multiple symbols
- Data normalization to Trade model
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from websockets import connect

from core.models.market_data import Trade

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """
    Binance WebSocket client for real-time trade streams

    Features:
    - Multi-symbol streaming
    - Auto-reconnect on disconnect
    - Trade data normalization
    - Callback pattern for event handling
    """

    BASE_URL = "wss://stream.binance.com:9443/ws"

    def __init__(self, symbols: list[str]):
        """
        Initialize WebSocket client

        Args:
            symbols: List of symbols (lowercase, e.g., ["btcusdt", "ethusdt"])
        """
        self.symbols = symbols
        self.callbacks: list[Callable] = []
        self.running = False

    def on_trade(self, callback: Callable[[Trade], None]) -> None:
        """
        Register callback for trade events

        Args:
            callback: Async function to call when trade received

        Example:
            >>> ws_client = BinanceWebSocketClient(["btcusdt"])
            >>> ws_client.on_trade(processor.process_trade)
            >>> await ws_client.start()
        """
        self.callbacks.append(callback)

    async def start(self) -> None:
        """
        Start WebSocket connection with auto-reconnect

        Runs forever until stop() is called.
        Automatically reconnects on disconnect with 5s delay.
        """
        self.running = True

        # Build stream URL for multiple symbols
        # Format: wss://stream.binance.com:9443/ws/btcusdt@trade/ethusdt@trade
        streams = "/".join([f"{symbol}@trade" for symbol in self.symbols])
        url = f"{self.BASE_URL}/{streams}"

        while self.running:
            try:
                async with connect(url) as websocket:
                    logger.info(f"✓ Connected to Binance WebSocket: {self.symbols}")

                    async for message in websocket:
                        if not self.running:
                            break

                        try:
                            data = json.loads(message)
                            trade = self._parse_trade(data)

                            # Trigger all registered callbacks
                            for callback in self.callbacks:
                                await callback(trade)

                        except Exception as e:
                            logger.error(f"Error processing trade message: {e}")
                            continue

            except Exception as e:
                logger.error(f"✗ WebSocket connection error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    def _parse_trade(self, data: dict) -> Trade:
        """
        Parse Binance trade message to Trade model

        Binance message format:
        {
            "e": "trade",              // Event type
            "E": 1234567890000,        // Event time
            "s": "BTCUSDT",            // Symbol
            "t": 12345,                // Trade ID
            "p": "50000.00",           // Price
            "q": "0.1",                // Quantity
            "T": 1234567890000,        // Trade time
            "m": true,                 // Is buyer maker?
            ...
        }

        Args:
            data: Raw Binance WebSocket message

        Returns:
            Trade: Normalized Trade object
        """
        return Trade(
            timestamp=datetime.fromtimestamp(data["T"] / 1000),
            exchange="binance",
            symbol=data["s"],
            trade_id=str(data["t"]),
            price=Decimal(data["p"]),
            quantity=Decimal(data["q"]),
            side="sell" if data["m"] else "buy",  # m=true → buyer is maker → taker is seller
            is_buyer_maker=data["m"],
        )

    async def stop(self) -> None:
        """Stop WebSocket connection"""
        self.running = False
        logger.info("WebSocket client stopping...")
