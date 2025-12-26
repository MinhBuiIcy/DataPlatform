"""
Data quality validator for real-time market data

Validates:
- Price sanity checks
- Timestamp validation
- Spike detection
- Order book integrity
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from core.models.market_data import OrderBook, Trade

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Real-time data quality validation

    Features:
    - Price spike detection (>10% change in 1 second)
    - Timestamp validation (not in future)
    - Order book integrity checks
    - Anomaly tracking and logging
    """

    def __init__(self, spike_threshold_pct: float = 10.0):
        """
        Initialize data validator

        Args:
            spike_threshold_pct: Price spike threshold percentage (default 10%)
        """
        self.spike_threshold_pct = spike_threshold_pct
        self.last_prices: dict[str, tuple[Decimal, datetime]] = {}  # {symbol: (price, timestamp)}
        self.spike_count = 0
        self.invalid_count = 0

    def validate_trade(self, trade: Trade) -> tuple[bool, str | None]:
        """
        Validate trade data quality

        Checks:
        1. Price > 0
        2. Quantity > 0
        3. Timestamp not in future
        4. Price spike detection

        Args:
            trade: Trade object to validate

        Returns:
            (is_valid, error_message)
            - (True, None) if valid
            - (False, "error reason") if invalid

        Example:
            >>> validator = DataValidator()
            >>> trade = Trade(price=Decimal("50000"), quantity=Decimal("0.1"), ...)
            >>> is_valid, error = validator.validate_trade(trade)
            >>> if not is_valid:
            ...     logger.error(f"Invalid trade: {error}")
        """

        # 1. Price validation
        if trade.price <= 0:
            self.invalid_count += 1
            return False, f"Invalid price: {trade.price} (must be > 0)"

        # 2. Quantity validation
        if trade.quantity <= 0:
            self.invalid_count += 1
            return False, f"Invalid quantity: {trade.quantity} (must be > 0)"

        # 3. Timestamp validation (not in future, allow 5s clock skew)
        now = datetime.now(UTC)
        if trade.timestamp > now + timedelta(seconds=5):
            self.invalid_count += 1
            return False, f"Future timestamp: {trade.timestamp} (now: {now})"

        # 4. Spike detection (> threshold% price change in 1 second)
        symbol_key = f"{trade.exchange}:{trade.symbol}"
        if symbol_key in self.last_prices:
            last_price, last_time = self.last_prices[symbol_key]
            time_diff = (trade.timestamp - last_time).total_seconds()

            if 0 < time_diff < 1.0:  # Within 1 second
                price_change_pct = abs((trade.price - last_price) / last_price * 100)

                if price_change_pct > self.spike_threshold_pct:
                    self.spike_count += 1
                    logger.warning(
                        f"⚠️ Price spike detected: {trade.symbol} "
                        f"{float(price_change_pct):.2f}%% change in {time_diff:.2f}s "
                        f"({float(last_price)} → {float(trade.price)})"
                    )
                    # Don't reject - log only (could be flash crash, real market event)

        # Update tracking
        self.last_prices[symbol_key] = (trade.price, trade.timestamp)

        return True, None

    def validate_orderbook(self, orderbook: OrderBook) -> tuple[bool, str | None]:
        """
        Validate order book data quality

        Checks:
        1. Bids and asks not empty
        2. Best bid < best ask (no crossed book)
        3. Bids sorted descending (highest first)
        4. Asks sorted ascending (lowest first)
        5. No negative prices or quantities

        Args:
            orderbook: OrderBook object to validate

        Returns:
            (is_valid, error_message)

        Example:
            >>> validator = DataValidator()
            >>> ob = OrderBook(bids=[(50000, 0.1)], asks=[(50001, 0.2)], ...)
            >>> is_valid, error = validator.validate_orderbook(ob)
        """

        # 1. Bids/asks not empty
        if not orderbook.bids or not orderbook.asks:
            self.invalid_count += 1
            return False, "Empty order book (no bids or asks)"

        # 2. Best bid < best ask (no crossed book)
        best_bid_price = orderbook.best_bid[0]
        best_ask_price = orderbook.best_ask[0]

        if best_bid_price >= best_ask_price:
            self.invalid_count += 1
            return False, (f"Crossed book: bid={best_bid_price} >= ask={best_ask_price}")

        # 3. Check for negative prices/quantities
        for price, qty in orderbook.bids + orderbook.asks:
            if price <= 0 or qty <= 0:
                self.invalid_count += 1
                return False, f"Invalid price/quantity: {price}/{qty}"

        # 4. Bids sorted descending (highest price first)
        for i in range(len(orderbook.bids) - 1):
            if orderbook.bids[i][0] < orderbook.bids[i + 1][0]:
                self.invalid_count += 1
                return False, (
                    f"Bids not sorted descending at index {i}: "
                    f"{orderbook.bids[i][0]} < {orderbook.bids[i + 1][0]}"
                )

        # 5. Asks sorted ascending (lowest price first)
        for i in range(len(orderbook.asks) - 1):
            if orderbook.asks[i][0] > orderbook.asks[i + 1][0]:
                self.invalid_count += 1
                return False, (
                    f"Asks not sorted ascending at index {i}: "
                    f"{orderbook.asks[i][0]} > {orderbook.asks[i + 1][0]}"
                )

        return True, None

    def get_stats(self) -> dict[str, int]:
        """
        Get validation statistics

        Returns:
            Dictionary with:
            - spike_count: Number of price spikes detected
            - invalid_count: Number of invalid records rejected
            - symbols_tracked: Number of unique symbols tracked

        Example:
            >>> stats = validator.get_stats()
            >>> print(f"Spikes: {stats['spike_count']}, Invalid: {stats['invalid_count']}")
        """
        return {
            "spike_count": self.spike_count,
            "invalid_count": self.invalid_count,
            "symbols_tracked": len(self.last_prices),
        }

    def reset_stats(self) -> None:
        """Reset statistics counters"""
        self.spike_count = 0
        self.invalid_count = 0
