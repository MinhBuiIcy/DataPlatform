"""
Integration tests for candle aggregation pipeline

Tests trades → candles materialized view aggregation

Requirements:
- Docker services running (make docker-up)
- ClickHouse with candles tables
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.models.market_data import Trade
from factory.client_factory import create_timeseries_db


@pytest.mark.integration
@pytest.mark.asyncio
async def test_candles_1m_aggregation():
    """
    Test 1-minute candles are auto-generated from trades

    Flow:
    1. Insert 100 trades within 1 minute
    2. Wait for materialized view to aggregate
    3. Query candles_1m table
    4. Verify 1 candle with correct OHLCV
    """
    db = create_timeseries_db()
    await db.connect()

    try:
        # Step 1: Insert 100 trades at same timestamp (within 1 minute)
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        exchange = "binance"
        symbol = "TEST_BTCUSDT"

        trades = []
        for i in range(100):
            # Use incrementing timestamps so argMax/argMin can work correctly
            from datetime import timedelta

            trade = Trade(
                timestamp=now + timedelta(milliseconds=i),  # Each trade 1ms apart
                exchange=exchange,
                symbol=symbol,
                trade_id=f"test_{i}",
                price=Decimal(50000 + i),  # Prices: 50000 to 50099
                quantity=Decimal(0.1),
                side="buy",
                is_buyer_maker=False,
            )
            trades.append(trade.to_dict())

        # Insert trades
        await db.insert_trades(trades)

        # Step 2: Wait for materialized view to aggregate (2-3 seconds)
        await asyncio.sleep(3)

        # Step 3: Query candles_1m
        candles = await db.query_candles(exchange=exchange, symbol=symbol, timeframe="1m", limit=10)

        # Step 4: Verify candle
        assert len(candles) >= 1, "Should have at least 1 candle"

        latest_candle = candles[-1]

        # Verify OHLCV values
        assert latest_candle.open == Decimal(50000), "Open should be first price"
        assert latest_candle.high == Decimal(50099), "High should be max price"
        assert latest_candle.low == Decimal(50000), "Low should be min price"
        assert latest_candle.close == Decimal(50099), "Close should be last price"
        assert latest_candle.volume == Decimal(10.0), "Volume = 100 * 0.1"
        assert latest_candle.trades_count == 100, "Should have 100 trades"

    finally:
        await db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_open_candle_in_query():
    """
    CRITICAL: Ensure queries only return CLOSED candles

    The current open candle (incomplete) should NEVER be included
    """
    db = create_timeseries_db()
    await db.connect()

    try:
        # Query candles (should exclude current minute)
        candles = await db.query_candles(
            exchange="binance", symbol="BTCUSDT", timeframe="1m", limit=10
        )

        if candles:
            latest_candle = candles[-1]
            current_minute = datetime.now(UTC).replace(second=0, microsecond=0)

            # Latest candle should be at least 1 minute old
            assert latest_candle.timestamp < current_minute, (
                f"Query returned open candle: {latest_candle.timestamp} >= {current_minute}"
            )

    finally:
        await db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quote_volume_calculation():
    """Test quote_volume = SUM(price * quantity) for all trades"""
    db = create_timeseries_db()
    await db.connect()

    try:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        exchange = "binance"
        symbol = "TEST_QUOTE_VOL"

        # Insert trades with known prices/quantities
        trades = [
            {
                "timestamp": now,
                "exchange": exchange,
                "symbol": symbol,
                "trade_id": "test_1",
                "price": 100.0,
                "quantity": 2.0,  # quote_volume = 200
                "side": "buy",
                "is_buyer_maker": False,
            },
            {
                "timestamp": now,
                "exchange": exchange,
                "symbol": symbol,
                "trade_id": "test_2",
                "price": 150.0,
                "quantity": 1.0,  # quote_volume = 150
                "side": "buy",
                "is_buyer_maker": False,
            },
        ]

        await db.insert_trades(trades)
        await asyncio.sleep(3)

        candles = await db.query_candles(exchange=exchange, symbol=symbol, timeframe="1m", limit=1)

        assert len(candles) == 1
        candle = candles[0]

        # Expected: 200 + 150 = 350
        expected_quote_volume = Decimal(350.0)
        assert abs(candle.quote_volume - expected_quote_volume) < Decimal(0.01), (
            f"Quote volume mismatch: {candle.quote_volume} vs {expected_quote_volume}"
        )

    finally:
        await db.close()
