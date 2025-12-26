"""
Market data models

Pydantic models for market data structures:
- Trade: Individual trade execution
- Candle: OHLCV candlestick
- OrderBook: Order book snapshot
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Trade(BaseModel):
    """
    Raw market trade event

    Represents a single trade execution on an exchange
    """

    timestamp: datetime = Field(description="Trade timestamp (UTC)")
    exchange: str = Field(description="Exchange name (binance, coinbase, kraken)")
    symbol: str = Field(description="Trading pair (BTC/USDT, ETH/USDT)")
    trade_id: str = Field(description="Exchange-specific trade ID")
    price: Decimal = Field(description="Trade price")
    quantity: Decimal = Field(description="Trade quantity (volume)")
    side: Literal["buy", "sell"] = Field(description="Taker side (buyer or seller)")
    is_buyer_maker: bool = Field(
        description="Was the buyer the maker? (true = buyer posted limit order)"
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion"""
        return {
            "timestamp": self.timestamp,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "side": self.side,
            "is_buyer_maker": self.is_buyer_maker,
        }


class Candle(BaseModel):
    """
    OHLCV candlestick

    Aggregated price data for a time interval
    """

    timestamp: datetime = Field(description="Candle open timestamp (UTC)")
    exchange: str = Field(description="Exchange name")
    symbol: str = Field(description="Trading pair")
    timeframe: str = Field(description="Timeframe (1m, 5m, 15m, 1h, 4h, 1d)")
    open: Decimal = Field(description="Opening price")
    high: Decimal = Field(description="Highest price in interval")
    low: Decimal = Field(description="Lowest price in interval")
    close: Decimal = Field(description="Closing price")
    volume: Decimal = Field(description="Total volume traded")
    trades_count: int = Field(default=0, description="Number of trades in interval")


class OrderBook(BaseModel):
    """
    Order book snapshot

    Represents the state of the order book at a point in time
    """

    timestamp: datetime = Field(description="Snapshot timestamp (UTC)")
    exchange: str = Field(description="Exchange name")
    symbol: str = Field(description="Trading pair")
    bids: list[tuple[Decimal, Decimal]] = Field(description="Bid orders [(price, quantity), ...]")
    asks: list[tuple[Decimal, Decimal]] = Field(description="Ask orders [(price, quantity), ...]")
    checksum: int = Field(default=0, description="Checksum for data integrity (exchange-specific)")

    @property
    def best_bid(self) -> tuple[Decimal, Decimal]:
        """Get best bid (highest buy price)"""
        return self.bids[0] if self.bids else (Decimal(0), Decimal(0))

    @property
    def best_ask(self) -> tuple[Decimal, Decimal]:
        """Get best ask (lowest sell price)"""
        return self.asks[0] if self.asks else (Decimal(0), Decimal(0))

    @property
    def spread(self) -> Decimal:
        """Calculate bid-ask spread"""
        if not self.bids or not self.asks:
            return Decimal(0)
        return self.best_ask[0] - self.best_bid[0]

    @property
    def mid_price(self) -> Decimal:
        """Calculate mid price (average of best bid and ask)"""
        if not self.bids or not self.asks:
            return Decimal(0)
        return (self.best_bid[0] + self.best_ask[0]) / 2

    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion"""
        return {
            "timestamp": self.timestamp,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "bids": [(str(p), str(q)) for p, q in self.bids],
            "asks": [(str(p), str(q)) for p, q in self.asks],
            "checksum": self.checksum,
        }
