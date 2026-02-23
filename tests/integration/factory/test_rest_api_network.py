"""
Integration tests for exchange REST API network calls

Tests actual network calls to exchange APIs.
These tests require internet connection and may be flaky.

Use @pytest.mark.external to skip in CI:
pytest -m "not external"
"""

import pytest

from factory.client_factory import create_exchange_rest_api


@pytest.mark.integration
@pytest.mark.external  # 🌐 Requires internet connection
async def test_binance_rest_api_fetch_real_data():
    """Verify Binance REST API fetches real candles (EXTERNAL DEPENDENCY)"""
    api = create_exchange_rest_api("binance")

    try:
        candles = await api.fetch_latest_klines(symbol="BTCUSDT", timeframe="1m", limit=5)

        assert len(candles) > 0
        assert all(c.exchange == "binance" for c in candles)
        assert all(c.symbol == "BTCUSDT" for c in candles)
        assert all(c.timeframe == "1m" for c in candles)

        # Verify OHLC relationships
        for candle in candles:
            assert candle.high >= candle.low
            assert candle.high >= candle.open
            assert candle.high >= candle.close
            assert candle.low <= candle.open
            assert candle.low <= candle.close

        print(f"\n✓ Binance REST API fetched {len(candles)} candles")

    finally:
        await api.close()


@pytest.mark.integration
@pytest.mark.external  # 🌐 Requires internet connection
async def test_coinbase_rest_api_fetch_real_data():
    """Verify Coinbase REST API fetches real candles (EXTERNAL DEPENDENCY)"""
    api = create_exchange_rest_api("coinbase")

    try:
        candles = await api.fetch_latest_klines(symbol="BTC-USD", timeframe="1m", limit=5)

        assert len(candles) > 0
        assert all(c.exchange == "coinbase" for c in candles)

        print(f"\n✓ Coinbase REST API fetched {len(candles)} candles")

    finally:
        await api.close()


@pytest.mark.integration
@pytest.mark.external  # 🌐 Requires internet connection
async def test_kraken_rest_api_fetch_real_data():
    """Verify Kraken REST API fetches real candles (EXTERNAL DEPENDENCY)"""
    api = create_exchange_rest_api("kraken")

    try:
        candles = await api.fetch_latest_klines(symbol="BTC/USD", timeframe="1m", limit=5)

        assert len(candles) > 0
        assert all(c.exchange == "kraken" for c in candles)

        print(f"\n✓ Kraken REST API fetched {len(candles)} candles")

    finally:
        await api.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
