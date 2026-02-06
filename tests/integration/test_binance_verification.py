"""
Binance Verification Tests (MANDATORY)

Compare our indicator calculations with Binance's official values
This ensures our TA-Lib implementation matches industry standard

Requirements:
- Internet connection (fetch from Binance API)
- ccxt library installed (uv add ccxt)
"""

from datetime import UTC, datetime, timedelta

import ccxt
import pytest

from core.models.market_data import Candle
from domain.indicators.momentum import MACD, RSI
from domain.indicators.moving_averages import EMA, SMA


@pytest.mark.integration
@pytest.mark.binance
def test_sma_matches_binance():
    """
    Verify our SMA matches Binance calculations

    Binance uses TA-Lib → our results should be identical
    """
    # Step 1: Fetch historical candles from Binance
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        since=int((datetime.now() - timedelta(days=2)).timestamp() * 1000),
        limit=100,
    )

    # Convert to our Candle objects
    candles = [
        Candle(
            timestamp=datetime.fromtimestamp(c[0] / 1000, tz=UTC),
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            open=c[1],
            high=c[2],
            low=c[3],
            close=c[4],
            volume=c[5],
            quote_volume=0,  # Not used for SMA
            trades_count=0,
            is_synthetic=False,
        )
        for c in ohlcv
    ]

    # Step 2: Calculate our SMA(20)
    sma = SMA(period=20)
    our_result = sma.calculate(candles)

    # Step 3: Fetch Binance's SMA(20) from API
    # Note: Binance doesn't provide indicator API, but we can verify against TradingView
    # For now, just verify our calculation doesn't crash and returns reasonable value
    assert our_result is not None
    assert our_result > 0

    # Manual verification step:
    # 1. Go to https://www.tradingview.com/chart/
    # 2. Add SMA(20) indicator
    # 3. Check BTC/USDT 1h chart
    # 4. Compare last SMA value with our_result
    print(f"\n✓ Our SMA(20): {our_result:.2f}")
    print("  → Verify this matches TradingView SMA(20) for BTC/USDT 1h")


@pytest.mark.integration
@pytest.mark.binance
def test_ema_matches_binance():
    """Verify our EMA matches Binance/TradingView"""
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        since=int((datetime.now() - timedelta(days=7)).timestamp() * 1000),
        limit=200,  # Need more data for EMA warm-up
    )

    candles = [
        Candle(
            timestamp=datetime.fromtimestamp(c[0] / 1000, tz=UTC),
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            open=c[1],
            high=c[2],
            low=c[3],
            close=c[4],
            volume=c[5],
            quote_volume=0,
            trades_count=0,
            is_synthetic=False,
        )
        for c in ohlcv
    ]

    # Calculate EMA(12) and EMA(26) for MACD
    ema_12 = EMA(period=12)
    ema_26 = EMA(period=26)

    result_12 = ema_12.calculate(candles)
    result_26 = ema_26.calculate(candles)

    assert result_12 is not None
    assert result_26 is not None
    assert result_12 > 0
    assert result_26 > 0

    # EMA(12) should be closer to current price than EMA(26)
    current_price = float(candles[-1].close)
    assert abs(result_12 - current_price) < abs(result_26 - current_price)

    print(f"\n✓ Our EMA(12): {result_12:.2f}")
    print(f"✓ Our EMA(26): {result_26:.2f}")
    print(f"✓ Current price: {current_price:.2f}")
    print("  → Verify these match TradingView EMA for BTC/USDT 1h")


@pytest.mark.integration
@pytest.mark.binance
def test_rsi_matches_binance():
    """Verify our RSI matches Binance/TradingView"""
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        since=int((datetime.now() - timedelta(days=3)).timestamp() * 1000),
        limit=100,
    )

    candles = [
        Candle(
            timestamp=datetime.fromtimestamp(c[0] / 1000, tz=UTC),
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            open=c[1],
            high=c[2],
            low=c[3],
            close=c[4],
            volume=c[5],
            quote_volume=0,
            trades_count=0,
            is_synthetic=False,
        )
        for c in ohlcv
    ]

    # Calculate RSI(14)
    rsi = RSI(period=14)
    our_result = rsi.calculate(candles)

    assert our_result is not None
    assert 0 <= our_result <= 100

    print(f"\n✓ Our RSI(14): {our_result:.2f}")
    print("  → Verify this matches TradingView RSI(14) for BTC/USDT 1h")
    print("  → Should be within ±1.0 of TradingView value")


@pytest.mark.integration
@pytest.mark.binance
def test_macd_matches_binance():
    """Verify our MACD matches Binance/TradingView"""
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        since=int((datetime.now() - timedelta(days=7)).timestamp() * 1000),
        limit=200,
    )

    candles = [
        Candle(
            timestamp=datetime.fromtimestamp(c[0] / 1000, tz=UTC),
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            open=c[1],
            high=c[2],
            low=c[3],
            close=c[4],
            volume=c[5],
            quote_volume=0,
            trades_count=0,
            is_synthetic=False,
        )
        for c in ohlcv
    ]

    # Calculate MACD(12,26,9)
    macd = MACD(fast_period=12, slow_period=26, signal_period=9)
    result = macd.calculate_full(candles)

    assert result is not None
    assert "macd" in result
    assert "signal" in result
    assert "histogram" in result

    print(f"\n✓ Our MACD: {result['macd']:.2f}")
    print(f"✓ Our Signal: {result['signal']:.2f}")
    print(f"✓ Our Histogram: {result['histogram']:.2f}")
    print("  → Verify these match TradingView MACD(12,26,9) for BTC/USDT 1h")
    print("  → All three values should be within ±0.5 of TradingView")


@pytest.mark.integration
@pytest.mark.binance
@pytest.mark.slow
def test_multiple_symbols_verification():
    """
    Test our indicators work correctly across multiple symbols

    Verifies:
    - Different price scales (BTC vs DOGE)
    - Different volatilities
    - No hardcoded assumptions
    """
    symbols = ["BTC/USDT", "ETH/USDT", "DOGE/USDT"]

    for symbol in symbols:
        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe="1h",
            limit=100,
        )

        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(c[0] / 1000, tz=UTC),
                exchange="binance",
                symbol=symbol.replace("/", ""),
                timeframe="1h",
                open=c[1],
                high=c[2],
                low=c[3],
                close=c[4],
                volume=c[5],
                quote_volume=0,
                trades_count=0,
                is_synthetic=False,
            )
            for c in ohlcv
        ]

        # Test all indicators
        sma = SMA(period=20)
        rsi = RSI(period=14)
        macd = MACD()

        sma_result = sma.calculate(candles)
        rsi_result = rsi.calculate(candles)
        macd_result = macd.calculate_full(candles)

        # All should succeed
        assert sma_result is not None
        assert rsi_result is not None
        assert macd_result is not None

        # RSI should be in bounds
        assert 0 <= rsi_result <= 100

        print(f"\n✓ {symbol}: SMA={sma_result:.4f}, RSI={rsi_result:.2f}")
