"""
Integration tests for multi-exchange market data ingestion

Tests:
- Multi-exchange WebSocket connectivity
- Data flow: WebSocket → Processor → ClickHouse/Redis
- Data validation
- YAML configuration loading
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from config.loader import get_enabled_exchanges
from core.models.market_data import OrderBook, Trade
from factory.client_factory import create_exchange_websockets
from providers.opensource.clickhouse import ClickHouseClient
from providers.opensource.redis_client import RedisClient
from services.market_data_ingestion.stream_processor import StreamProcessor


@pytest.mark.integration
@pytest.mark.asyncio
async def test_yaml_config_loading():
    """Test YAML configuration loads correctly"""
    # Load enabled exchanges
    enabled = get_enabled_exchanges()

    assert len(enabled) > 0, "At least one exchange should be enabled"

    for name, config in enabled.items():
        assert config.enabled is True
        assert len(config.symbols) > 0, f"{name} should have symbols configured"
        assert config.websocket_url.startswith("wss://") or config.websocket_url.startswith("ws://")
        assert config.features.trades is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchange_factory_creation():
    """Test factory creates exchange WebSocket clients"""
    exchanges = create_exchange_websockets()

    assert len(exchanges) > 0, "Should create at least one exchange client"

    for exchange in exchanges:
        assert hasattr(exchange, "on_trade")
        assert hasattr(exchange, "on_orderbook")
        assert hasattr(exchange, "start")
        assert hasattr(exchange, "stop")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_data_validator():
    """Test data validation logic"""
    from core.validators.market_data import DataValidator

    validator = DataValidator(spike_threshold_pct=10.0)

    # Valid trade
    trade = Trade(
        timestamp=datetime.now(UTC),
        exchange="binance",
        symbol="BTCUSDT",
        trade_id="123456",
        price=Decimal("50000"),
        quantity=Decimal("0.1"),
        side="buy",
        is_buyer_maker=False,
    )

    is_valid, error = validator.validate_trade(trade)
    assert is_valid is True
    assert error is None

    # Invalid trade - negative price
    invalid_trade = Trade(
        timestamp=datetime.now(UTC),
        exchange="binance",
        symbol="BTCUSDT",
        trade_id="123457",
        price=Decimal("-100"),
        quantity=Decimal("0.1"),
        side="buy",
        is_buyer_maker=False,
    )

    is_valid, error = validator.validate_trade(invalid_trade)
    assert is_valid is False
    assert "Invalid price" in error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orderbook_validator():
    """Test order book validation"""
    from core.validators.market_data import DataValidator

    validator = DataValidator()

    # Valid order book
    orderbook = OrderBook(
        timestamp=datetime.now(UTC),
        exchange="binance",
        symbol="BTCUSDT",
        bids=[(Decimal("50000"), Decimal("0.1")), (Decimal("49999"), Decimal("0.2"))],
        asks=[(Decimal("50001"), Decimal("0.15")), (Decimal("50002"), Decimal("0.25"))],
        checksum=0,
    )

    is_valid, error = validator.validate_orderbook(orderbook)
    assert is_valid is True

    # Invalid - crossed book
    crossed_book = OrderBook(
        timestamp=datetime.now(UTC),
        exchange="binance",
        symbol="BTCUSDT",
        bids=[(Decimal("50002"), Decimal("0.1"))],  # Bid > ask
        asks=[(Decimal("50001"), Decimal("0.15"))],
        checksum=0,
    )

    is_valid, error = validator.validate_orderbook(crossed_book)
    assert is_valid is False
    assert "Crossed book" in error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_processor_trade_flow():
    """Test trade processing flow"""
    processor = StreamProcessor(buffer_size=10)

    # Create mock trade
    trade = Trade(
        timestamp=datetime.now(UTC),
        exchange="binance",
        symbol="BTCUSDT",
        trade_id="test_123",
        price=Decimal("50000"),
        quantity=Decimal("0.1"),
        side="buy",
        is_buyer_maker=False,
    )

    # Connect processor
    await processor.connect()

    try:
        # Process trade
        await processor.process_trade(trade)

        # Check buffer
        assert len(processor.trade_buffer) == 1
        assert processor.trade_buffer[0]["symbol"] == "BTCUSDT"

        # Check validation stats
        stats = processor.validator.get_stats()
        assert stats["symbols_tracked"] >= 1

    finally:
        await processor.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_clickhouse_trade_insertion():
    """Test trades are inserted into ClickHouse"""
    clickhouse = ClickHouseClient()
    await clickhouse.connect()

    try:
        # Insert test trades
        trades = [
            {
                "timestamp": datetime.now(UTC),
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "trade_id": f"test_{i}",
                "price": "50000.00",
                "quantity": "0.1",
                "side": "buy",
                "is_buyer_maker": False,
            }
            for i in range(5)
        ]

        count = await clickhouse.insert_trades(trades)
        assert count == 5

        # Query back
        result = await clickhouse.query(
            "SELECT COUNT(*) as cnt FROM trading.market_trades WHERE trade_id LIKE 'test_%'"
        )
        assert result[0]["cnt"] >= 5

    finally:
        # Cleanup
        await clickhouse.query("DELETE FROM trading.market_trades WHERE trade_id LIKE 'test_%'")
        await clickhouse.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_clickhouse_orderbook_insertion():
    """Test order books are inserted into ClickHouse"""
    clickhouse = ClickHouseClient()
    await clickhouse.connect()

    try:
        # Insert test order books
        orderbooks = [
            {
                "timestamp": datetime.now(UTC),
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "bids": [("50000", "0.1"), ("49999", "0.2")],
                "asks": [("50001", "0.15"), ("50002", "0.25")],
                "checksum": 0,
            }
            for _ in range(3)
        ]

        count = await clickhouse.insert_orderbooks(orderbooks)
        assert count == 3

        # Query back
        result = await clickhouse.query(
            "SELECT COUNT(*) as cnt FROM trading.orderbook_snapshots WHERE symbol = 'BTCUSDT'"
        )
        assert result[0]["cnt"] >= 3

    finally:
        # Cleanup
        await clickhouse.query(
            "DELETE FROM trading.orderbook_snapshots WHERE symbol = 'BTCUSDT' AND exchange = 'binance'"
        )
        await clickhouse.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_operations():
    """Test Redis cache for latest prices"""
    redis = RedisClient()
    await redis.connect()

    try:
        # Set latest price
        import json

        cache_value = json.dumps(
            {"price": "50000.00", "timestamp": datetime.now(UTC).isoformat(), "side": "buy"}
        )

        await redis.set("latest_price:test:BTCUSDT", cache_value, ex=60)

        # Get back
        result = await redis.get("latest_price:test:BTCUSDT")
        assert result is not None

        data = json.loads(result)
        assert data["price"] == "50000.00"

    finally:
        # Cleanup
        await redis.delete("latest_price:test:BTCUSDT")
        await redis.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_multi_exchange_concurrent():
    """Test multiple exchanges can run concurrently (short test)"""
    exchanges = create_exchange_websockets()
    processor = StreamProcessor(buffer_size=100)

    await processor.connect()

    # Track received data
    received_trades = []
    received_orderbooks = []

    async def track_trade(trade):
        received_trades.append(trade)
        await processor.process_trade(trade)

    async def track_orderbook(ob):
        received_orderbooks.append(ob)
        await processor.process_orderbook(ob)

    # Register callbacks
    for exchange in exchanges:
        exchange.on_trade(track_trade)
        exchange.on_orderbook(track_orderbook)

    # Run for 10 seconds
    try:
        # Connect all exchanges first (build WebSocket URLs)
        for exchange in exchanges:
            await exchange.connect()

        # Start all exchanges concurrently
        tasks = [exchange.start() for exchange in exchanges]
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)
    except TimeoutError:
        pass  # Expected - we stop after 10 seconds
    finally:
        # Cleanup
        for exchange in exchanges:
            await exchange.stop()
        await processor.close()

    # Verify we received data
    print(f"\nReceived {len(received_trades)} trades, {len(received_orderbooks)} orderbooks")
    assert len(received_trades) > 0 or len(received_orderbooks) > 0, (
        "Should receive at least some data in 10 seconds"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
