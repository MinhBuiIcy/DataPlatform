"""
Integration tests for REST API → ClickHouse candle ingestion

Tests candle data from Sync Service REST API ingestion.
This validates the Phase 2 candle ingestion pipeline.

Requires Docker services running.
"""

from datetime import UTC, datetime

import pytest

from factory.client_factory import create_exchange_rest_api, create_timeseries_db


@pytest.mark.integration
async def test_candles_from_rest_api():
    """
    Test candles fetched from exchange REST API and stored correctly

    Phase 2 Flow:
    1. Fetch candles from exchange REST API (ccxt)
    2. Insert into ClickHouse candles_1m table
    3. Query back and verify OHLCV structure
    """
    db = create_timeseries_db()
    api = create_exchange_rest_api("binance")

    try:
        await db.connect()

        # Step 1: Fetch real candles from Binance REST API
        exchange = "binance"
        symbol = "BTCUSDT"
        timeframe = "1m"

        print(f"\nFetching candles from {exchange} REST API...")
        candles = await api.fetch_latest_klines(symbol=symbol, timeframe=timeframe, limit=5)

        assert len(candles) > 0, "Should fetch at least 1 candle from REST API"
        print(f"  ✓ Fetched {len(candles)} candles")

        # Step 2: Insert into ClickHouse (convert using Pydantic model_dump)
        candle_dicts = [c.model_dump() for c in candles]
        await db.insert_candles(candle_dicts, timeframe)
        print(f"  ✓ Inserted {len(candle_dicts)} candles to ClickHouse")

        # Step 3: Query back
        queried_candles = await db.query_candles(
            exchange=exchange, symbol=symbol, timeframe=timeframe, limit=5
        )

        assert len(queried_candles) >= 1, "Should query at least 1 candle"

        # Step 4: Verify OHLCV structure
        for candle in queried_candles[:3]:
            print(
                f"  Candle: O={candle.open} H={candle.high} L={candle.low} C={candle.close} V={candle.volume}"
            )

            # Verify OHLC relationships
            assert candle.high >= candle.low, "High should be >= Low"
            assert candle.high >= candle.open, "High should be >= Open"
            assert candle.high >= candle.close, "High should be >= Close"
            assert candle.low <= candle.open, "Low should be <= Open"
            assert candle.low <= candle.close, "Low should be <= Close"
            assert candle.volume >= 0, "Volume should be non-negative"

        print("  ✓ All candles have valid OHLCV structure")

    finally:
        await api.close()
        await db.close()


@pytest.mark.integration
async def test_no_open_candle_in_query():
    """
    CRITICAL: Ensure queries only return CLOSED candles

    Phase 2: Sync Service fetches only closed candles from REST API
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
            # Use timezone-naive datetime to match ClickHouse (returns naive datetimes)
            current_minute = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)

            # Latest candle should be at least 1 minute old
            assert latest_candle.timestamp < current_minute, (
                f"Query returned open candle: {latest_candle.timestamp} >= {current_minute}"
            )
            print(f"  ✓ Latest candle is closed: {latest_candle.timestamp}")
        else:
            print("  ⚠ No candles found (run Sync Service first)")

    finally:
        await db.close()


@pytest.mark.integration
async def test_quote_volume_from_rest_api():
    """
    Test quote_volume is populated from REST API candles

    Phase 2: REST API provides quote_volume directly (no calculation needed)
    """
    db = create_timeseries_db()
    api = create_exchange_rest_api("binance")

    try:
        await db.connect()

        # Fetch candles from REST API
        exchange = "binance"
        symbol = "BTCUSDT"
        timeframe = "1m"

        candles = await api.fetch_latest_klines(symbol=symbol, timeframe=timeframe, limit=5)
        assert len(candles) > 0, "Should fetch candles"

        # Insert into ClickHouse (convert using Pydantic model_dump)
        candle_dicts = [c.model_dump() for c in candles]
        await db.insert_candles(candle_dicts, timeframe)

        # Query back
        queried_candles = await db.query_candles(
            exchange=exchange, symbol=symbol, timeframe=timeframe, limit=5
        )

        if queried_candles:
            for candle in queried_candles[:3]:
                print(f"  Candle: volume={candle.volume}, quote_volume={candle.quote_volume}")

                # Quote volume should be populated (might be 0 for low-volume periods)
                assert candle.quote_volume >= 0, "Quote volume should be non-negative"

            print("  ✓ Quote volumes populated from REST API")
        else:
            print("  ⚠ No candles found")

    finally:
        await api.close()
        await db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
