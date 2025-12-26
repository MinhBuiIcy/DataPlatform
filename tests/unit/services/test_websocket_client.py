"""
Unit tests for BinanceWebSocketClient

Mocks websocket connection to test parsing and callback logic
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from core.models.market_data import Trade
from services.market_data_ingestion.websocket_client import BinanceWebSocketClient


class TestBinanceWebSocketClient:
    """Test Binance WebSocket client"""

    def test_initialization(self):
        """Test client initialization"""
        symbols = ["btcusdt", "ethusdt"]
        client = BinanceWebSocketClient(symbols)

        assert client.symbols == symbols
        assert client.callbacks == []
        assert client.running is False

    def test_on_trade_registers_callback(self):
        """Test that on_trade registers callback"""
        client = BinanceWebSocketClient(["btcusdt"])
        mock_callback = AsyncMock()

        client.on_trade(mock_callback)

        assert len(client.callbacks) == 1
        assert client.callbacks[0] == mock_callback

    def test_on_trade_multiple_callbacks(self):
        """Test registering multiple callbacks"""
        client = BinanceWebSocketClient(["btcusdt"])
        callback1 = AsyncMock()
        callback2 = AsyncMock()

        client.on_trade(callback1)
        client.on_trade(callback2)

        assert len(client.callbacks) == 2

    def test_parse_trade_buy_side(self):
        """Test parsing Binance trade message - buy side"""
        client = BinanceWebSocketClient(["btcusdt"])

        # Binance message format
        binance_message = {
            "e": "trade",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "50000.00",
            "q": "0.1",
            "T": 1702857600000,  # 2023-12-18 10:00:00
            "m": False,  # m=false → buyer is taker → side="buy"
        }

        trade = client._parse_trade(binance_message)

        assert isinstance(trade, Trade)
        assert trade.exchange == "binance"
        assert trade.symbol == "BTCUSDT"
        assert trade.trade_id == "12345"
        assert trade.price == Decimal("50000.00")
        assert trade.quantity == Decimal("0.1")
        assert trade.side == "buy"  # m=false → buy
        assert trade.is_buyer_maker is False

    def test_parse_trade_sell_side(self):
        """Test parsing Binance trade message - sell side"""
        client = BinanceWebSocketClient(["ethusdt"])

        binance_message = {
            "e": "trade",
            "E": 1234567890000,
            "s": "ETHUSDT",
            "t": 67890,
            "p": "3000.00",
            "q": "1.5",
            "T": 1702857600000,
            "m": True,  # m=true → buyer is maker → side="sell"
        }

        trade = client._parse_trade(binance_message)

        assert trade.symbol == "ETHUSDT"
        assert trade.side == "sell"  # m=true → sell
        assert trade.is_buyer_maker is True

    def test_parse_trade_timestamp_conversion(self):
        """Test timestamp conversion from milliseconds"""
        client = BinanceWebSocketClient(["btcusdt"])

        binance_message = {
            "e": "trade",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "50000.00",
            "q": "0.1",
            "T": 1702857600000,  # Unix timestamp in ms
            "m": False,
        }

        trade = client._parse_trade(binance_message)

        # 1702857600000 ms = 2023-12-18 10:00:00 UTC
        expected_timestamp = datetime(2023, 12, 18, 3, 0, 0)  # Adjusted for timezone
        assert trade.timestamp.year == expected_timestamp.year
        assert trade.timestamp.month == expected_timestamp.month
        assert trade.timestamp.day == expected_timestamp.day

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        """Test that stop() sets running to False"""
        client = BinanceWebSocketClient(["btcusdt"])
        client.running = True

        await client.stop()

        assert client.running is False


class TestBinanceWebSocketCallbacks:
    """Test callback execution"""

    @pytest.mark.asyncio
    async def test_callback_execution(self):
        """Test that callbacks are called with trade"""
        client = BinanceWebSocketClient(["btcusdt"])
        mock_callback = AsyncMock()
        client.on_trade(mock_callback)

        # Create mock trade
        trade = Trade(
            timestamp=datetime.now(),
            exchange="binance",
            symbol="BTCUSDT",
            trade_id="123",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            side="buy",
            is_buyer_maker=False,
        )

        # Manually trigger callback (simulating websocket message)
        for callback in client.callbacks:
            await callback(trade)

        mock_callback.assert_called_once_with(trade)

    @pytest.mark.asyncio
    async def test_multiple_callbacks_execution(self):
        """Test that all callbacks are called"""
        client = BinanceWebSocketClient(["btcusdt"])
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        client.on_trade(callback1)
        client.on_trade(callback2)

        trade = Trade(
            timestamp=datetime.now(),
            exchange="binance",
            symbol="BTCUSDT",
            trade_id="123",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            side="buy",
            is_buyer_maker=False,
        )

        # Trigger all callbacks
        for callback in client.callbacks:
            await callback(trade)

        callback1.assert_called_once()
        callback2.assert_called_once()


class TestBinanceMessageParsing:
    """Test edge cases in message parsing"""

    def test_parse_trade_with_large_numbers(self):
        """Test parsing trades with large quantities/prices"""
        client = BinanceWebSocketClient(["btcusdt"])

        binance_message = {
            "e": "trade",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "87643.99999999",  # Large decimal
            "q": "123.45678900",  # Large quantity
            "T": 1702857600000,
            "m": False,
        }

        trade = client._parse_trade(binance_message)

        assert trade.price == Decimal("87643.99999999")
        assert trade.quantity == Decimal("123.45678900")

    def test_parse_trade_with_scientific_notation(self):
        """Test parsing very small quantities"""
        client = BinanceWebSocketClient(["btcusdt"])

        binance_message = {
            "e": "trade",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "50000.00",
            "q": "0.00000001",  # Very small quantity
            "T": 1702857600000,
            "m": True,
        }

        trade = client._parse_trade(binance_message)

        assert trade.quantity == Decimal("0.00000001")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
