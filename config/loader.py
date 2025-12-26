"""
Configuration loader with YAML support and Pydantic validation
"""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class ExchangeFeatures(BaseModel):
    """Exchange feature flags"""

    trades: bool = True
    orderbook: bool = True
    orderbook_depth: int = 10
    orderbook_update_ms: int | None = None


class ExchangeRateLimits(BaseModel):
    """Exchange rate limit configuration"""

    connections_per_ip: int
    messages_per_second: int
    requests_per_minute: int | None = None


class SymbolConfig(BaseModel):
    """Symbol configuration with normalization mapping"""

    native: str  # Exchange-specific format (e.g., BTCUSDT, BTC-USD, XBT/USD)
    base: str  # Normalized base asset (e.g., BTC)
    quote: str  # Quote currency (e.g., USDT, USD)


class ExchangeConfig(BaseModel):
    """Single exchange configuration"""

    enabled: bool
    name: str
    websocket_url: str
    symbols: list[SymbolConfig]
    features: ExchangeFeatures
    rate_limits: ExchangeRateLimits

    @field_validator("symbols")
    @classmethod
    def symbols_not_empty(cls, v):
        if not v:
            raise ValueError("Symbols list cannot be empty")
        return v

    @property
    def symbol_list(self) -> list[str]:
        """Get list of native symbol strings (for backwards compatibility)"""
        return [s.native for s in self.symbols]

    @field_validator("websocket_url")
    @classmethod
    def websocket_url_valid(cls, v):
        if not v.startswith("wss://") and not v.startswith("ws://"):
            raise ValueError("WebSocket URL must start with ws:// or wss://")
        return v


class ExchangesConfig(BaseModel):
    """All exchanges configuration"""

    exchanges: dict[str, ExchangeConfig]


def load_exchanges_config(
    config_path: str = "config/providers/exchanges.yaml",
) -> dict[str, ExchangeConfig]:
    """
    Load and validate exchanges configuration from YAML

    Args:
        config_path: Path to exchanges.yaml file

    Returns:
        Dict[str, ExchangeConfig]: Validated exchange configurations

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If config is invalid

    Example:
        >>> configs = load_exchanges_config()
        >>> binance = configs["binance"]
        >>> print(binance.symbols)
        ['BTCUSDT', 'ETHUSDT', ...]
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Exchange config not found: {config_path}")

    # Load YAML
    with open(config_file) as f:
        data = yaml.safe_load(f)

    # Validate with Pydantic
    try:
        exchanges_config = ExchangesConfig(**data)
        logger.info(f"✓ Loaded {len(exchanges_config.exchanges)} exchange configurations")
        return exchanges_config.exchanges

    except Exception as e:
        logger.error(f"Failed to load exchange config: {e}")
        raise


def get_enabled_exchanges(
    config_path: str = "config/providers/exchanges.yaml",
) -> dict[str, ExchangeConfig]:
    """
    Get only enabled exchanges from configuration

    Args:
        config_path: Path to exchanges.yaml file

    Returns:
        Dict[str, ExchangeConfig]: Only enabled exchanges

    Example:
        >>> enabled = get_enabled_exchanges()
        >>> for name, config in enabled.items():
        ...     print(f"{name}: {len(config.symbols)} symbols")
        binance: 20 symbols
        coinbase: 20 symbols
    """
    all_exchanges = load_exchanges_config(config_path)
    enabled = {name: config for name, config in all_exchanges.items() if config.enabled}

    if not enabled:
        raise ValueError("No exchanges are enabled in configuration")

    logger.info(f"✓ Enabled exchanges: {', '.join(enabled.keys())}")
    return enabled


def get_all_symbols() -> dict[str, list[str]]:
    """
    Get all symbols from all enabled exchanges

    Returns:
        Dict[str, List[str]]: Exchange name → symbols list

    Example:
        >>> symbols = get_all_symbols()
        >>> print(symbols["binance"])
        ['BTCUSDT', 'ETHUSDT', ...]
    """
    enabled = get_enabled_exchanges()
    return {name: config.symbols for name, config in enabled.items()}


def get_exchange_config(exchange_name: str) -> ExchangeConfig:
    """
    Get configuration for a specific exchange

    Args:
        exchange_name: Exchange name (binance, coinbase, kraken)

    Returns:
        ExchangeConfig: Exchange configuration

    Raises:
        KeyError: If exchange not found
        ValueError: If exchange is disabled

    Example:
        >>> binance = get_exchange_config("binance")
        >>> print(binance.websocket_url)
        wss://stream.binance.com:9443/ws
    """
    all_exchanges = load_exchanges_config()

    if exchange_name not in all_exchanges:
        raise KeyError(
            f"Exchange '{exchange_name}' not found. Available: {list(all_exchanges.keys())}"
        )

    config = all_exchanges[exchange_name]

    if not config.enabled:
        raise ValueError(f"Exchange '{exchange_name}' is disabled")

    return config


# Convenience exports
__all__ = [
    "ExchangeConfig",
    "ExchangeFeatures",
    "ExchangeRateLimits",
    "load_exchanges_config",
    "get_enabled_exchanges",
    "get_all_symbols",
    "get_exchange_config",
]
