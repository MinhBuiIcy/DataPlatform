"""
Unit tests for core models (Pydantic)

Tests Trade, Candle, OrderBook models
"""

from datetime import datetime
from decimal import Decimal

import pytest

from core.models.market_data import Candle, OrderBook, Trade


class TestTradeModel:
    """Test Trade model validation and serialization"""

    def test_valid_trade_creation(self):
        """Test creating valid trade"""
        trade = Trade(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            side="buy",
            is_buyer_maker=True,
        )

        assert trade.exchange == "binance"
        assert trade.symbol == "BTCUSDT"
        assert trade.price == Decimal("50000.00")
        assert trade.quantity == Decimal("0.1")
        assert trade.side == "buy"
        assert trade.is_buyer_maker is True

    def test_trade_to_dict(self):
        """Test trade serialization to dict"""
        trade = Trade(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            side="buy",
            is_buyer_maker=False,
        )

        trade_dict = trade.to_dict()

        assert trade_dict["exchange"] == "binance"
        assert trade_dict["symbol"] == "BTCUSDT"
        assert trade_dict["price"] == "50000.00"
        assert trade_dict["quantity"] == "0.1"
        assert trade_dict["side"] == "buy"
        assert trade_dict["is_buyer_maker"] is False

    def test_invalid_side(self):
        """Test that invalid side raises validation error"""
        with pytest.raises(ValueError):
            Trade(
                timestamp=datetime(2023, 12, 18, 10, 0, 0),
                exchange="binance",
                symbol="BTCUSDT",
                trade_id="12345",
                price=Decimal("50000.00"),
                quantity=Decimal("0.1"),
                side="invalid",  # Must be "buy" or "sell"
                is_buyer_maker=True,
            )

    def test_json_serialization(self):
        """Test JSON serialization with Decimal and datetime"""
        trade = Trade(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            side="sell",
            is_buyer_maker=True,
        )

        # Should serialize without error
        json_str = trade.model_dump_json()
        assert "50000" in json_str
        assert "binance" in json_str


class TestCandleModel:
    """Test Candle model validation"""

    def test_valid_candle_creation(self):
        """Test creating valid candle"""
        candle = Candle(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1m",
            open=Decimal("50000.00"),
            high=Decimal("50100.00"),
            low=Decimal("49900.00"),
            close=Decimal("50050.00"),
            volume=Decimal("10.5"),
            trades_count=150,
        )

        assert candle.timeframe == "1m"
        assert candle.open == Decimal("50000.00")
        assert candle.high == Decimal("50100.00")
        assert candle.low == Decimal("49900.00")
        assert candle.close == Decimal("50050.00")
        assert candle.volume == Decimal("10.5")
        assert candle.trades_count == 150

    def test_candle_default_trades_count(self):
        """Test trades_count defaults to 0"""
        candle = Candle(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="5m",
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
        )

        assert candle.trades_count == 0


class TestOrderBookModel:
    """Test OrderBook model and computed properties"""

    def test_valid_orderbook_creation(self):
        """Test creating valid order book"""
        orderbook = OrderBook(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            bids=[
                (Decimal("50000"), Decimal("1.0")),
                (Decimal("49999"), Decimal("2.0")),
            ],
            asks=[
                (Decimal("50001"), Decimal("1.5")),
                (Decimal("50002"), Decimal("2.5")),
            ],
        )

        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0] == (Decimal("50000"), Decimal("1.0"))
        assert orderbook.asks[0] == (Decimal("50001"), Decimal("1.5"))

    def test_best_bid_ask(self):
        """Test best bid and ask properties"""
        orderbook = OrderBook(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            bids=[
                (Decimal("50000"), Decimal("1.0")),
                (Decimal("49999"), Decimal("2.0")),
            ],
            asks=[
                (Decimal("50001"), Decimal("1.5")),
                (Decimal("50002"), Decimal("2.5")),
            ],
        )

        assert orderbook.best_bid == (Decimal("50000"), Decimal("1.0"))
        assert orderbook.best_ask == (Decimal("50001"), Decimal("1.5"))

    def test_spread_calculation(self):
        """Test bid-ask spread calculation"""
        orderbook = OrderBook(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50001"), Decimal("1.5"))],
        )

        assert orderbook.spread == Decimal("1")

    def test_mid_price_calculation(self):
        """Test mid price calculation"""
        orderbook = OrderBook(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            bids=[(Decimal("50000"), Decimal("1.0"))],
            asks=[(Decimal("50002"), Decimal("1.5"))],
        )

        assert orderbook.mid_price == Decimal("50001")

    def test_empty_orderbook(self):
        """Test orderbook with no bids/asks"""
        orderbook = OrderBook(
            timestamp=datetime(2023, 12, 18, 10, 0, 0),
            exchange="binance",
            symbol="BTCUSDT",
            bids=[],
            asks=[],
        )

        assert orderbook.best_bid == (Decimal(0), Decimal(0))
        assert orderbook.best_ask == (Decimal(0), Decimal(0))
        assert orderbook.spread == Decimal(0)
        assert orderbook.mid_price == Decimal(0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
