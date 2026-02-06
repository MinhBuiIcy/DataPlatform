"""
Gap detection and filling utilities for time-series data

Handles missing candles in market data due to:
- Exchange downtime
- Network issues
- Maintenance windows
"""

from datetime import timedelta

from core.models.market_data import Candle, GapInfo


def detect_gaps(candles: list[Candle], expected_interval_minutes: int) -> list[GapInfo]:
    """
    Detect missing candles in a time series

    Args:
        candles: List of candles (must be sorted by timestamp ASC)
        expected_interval_minutes: Expected interval (1, 5, 15, 60, etc.)

    Returns:
        List of gaps detected (empty list if no gaps)

    Example:
        >>> candles = [candle_at_09_00, candle_at_09_05]  # Missing 09:01-09:04
        >>> gaps = detect_gaps(candles, expected_interval_minutes=1)
        >>> gaps[0].missing_count  # 4 candles missing
        4
    """
    if len(candles) < 2:
        return []

    gaps = []
    expected_delta = timedelta(minutes=expected_interval_minutes)

    for i in range(len(candles) - 1):
        current_time = candles[i].timestamp
        next_time = candles[i + 1].timestamp
        actual_delta = next_time - current_time

        if actual_delta > expected_delta:
            # Gap detected
            missing_count = int(actual_delta.total_seconds() / 60 / expected_interval_minutes) - 1
            gaps.append(
                GapInfo(
                    start_time=current_time + expected_delta,
                    end_time=next_time - expected_delta,
                    missing_count=missing_count,
                    expected_interval_minutes=expected_interval_minutes,
                )
            )

    return gaps


def fill_gaps(candles: list[Candle], gaps: list[GapInfo]) -> list[Candle]:
    """
    Forward-fill missing candles

    Strategy:
    - OHLC = previous candle's close
    - Volume = 0
    - Quote volume = 0
    - Trade count = 0
    - Flag: is_synthetic = True

    Args:
        candles: Original candles (sorted by timestamp ASC)
        gaps: List of gaps from detect_gaps()

    Returns:
        Complete list of candles with synthetic candles inserted

    Example:
        >>> candles = [candle_at_09_00, candle_at_09_05]
        >>> gaps = detect_gaps(candles, 1)
        >>> filled = fill_gaps(candles, gaps)
        >>> len(filled)  # Original 2 + 4 synthetic = 6
        6
        >>> filled[1].is_synthetic
        True
    """
    if not gaps:
        return candles

    # Create lookup dict
    candle_dict = {c.timestamp: c for c in candles}

    # Fill each gap
    for gap in gaps:
        current_time = gap.start_time
        interval = timedelta(minutes=gap.expected_interval_minutes)

        # Get the last known price before gap
        last_candle = candle_dict[gap.start_time - interval]
        last_close = last_candle.close

        # Fill gap with synthetic candles
        while current_time <= gap.end_time:
            synthetic = Candle(
                timestamp=current_time,
                exchange=last_candle.exchange,
                symbol=last_candle.symbol,
                timeframe=last_candle.timeframe,
                open=last_close,
                high=last_close,
                low=last_close,
                close=last_close,
                volume=0,
                quote_volume=0,
                trades_count=0,
                is_synthetic=True,
            )
            candle_dict[current_time] = synthetic
            current_time += interval

    # Return sorted complete list
    return sorted(candle_dict.values(), key=lambda c: c.timestamp)


def parse_timeframe(timeframe: str) -> int:
    """
    Convert timeframe string to minutes

    Args:
        timeframe: Timeframe string (1m, 5m, 15m, 1h, 4h, 1d)

    Returns:
        Interval in minutes

    Raises:
        ValueError: If timeframe is not supported

    Example:
        >>> parse_timeframe("1h")
        60
        >>> parse_timeframe("1d")
        1440
    """
    mapping = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }
    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return mapping[timeframe]
