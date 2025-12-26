#!/usr/bin/env python3
"""
Load symbol mappings from exchanges.yaml to ClickHouse

Usage:
    uv run python scripts/load_symbol_mappings.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.loader import load_exchanges_config
from providers.opensource.clickhouse import ClickHouseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_mappings_from_config() -> list[tuple[str, str, str, str]]:
    """
    Load symbol mappings from exchanges.yaml

    Returns:
        List of tuples: (base_asset, quote_asset, exchange, native_symbol)
    """
    configs = load_exchanges_config()

    mappings = []
    for exchange_name, config in configs.items():
        for symbol in config.symbols:
            mappings.append(
                (
                    symbol.base,  # BTC
                    symbol.quote,  # USDT
                    exchange_name,  # binance
                    symbol.native,  # BTCUSDT
                )
            )

    return mappings


async def main():
    """Main entry point"""
    logger.info("Loading mappings from config/providers/exchanges.yaml...")
    mappings = load_mappings_from_config()
    logger.info(f"✓ Loaded {len(mappings)} mappings")

    # Show breakdown
    from collections import Counter

    exchange_counts = Counter(m[2] for m in mappings)
    logger.info("Mappings per exchange:")
    for exchange, count in exchange_counts.items():
        logger.info(f"  {exchange:10s}: {count} symbols")

    # Connect to ClickHouse
    clickhouse = ClickHouseClient()
    await clickhouse.connect()

    try:
        # Clear existing data
        logger.info("\nClearing existing symbol mappings...")
        clickhouse.client.execute("TRUNCATE TABLE trading.symbol_mappings")

        # Insert new mappings
        logger.info(f"Inserting {len(mappings)} symbol mappings...")
        query = """
            INSERT INTO trading.symbol_mappings
            (base_asset, quote_asset, exchange, symbol)
            VALUES
        """
        clickhouse.client.execute(query, mappings)

        # Verify
        result = clickhouse.client.execute("SELECT COUNT(*) as count FROM trading.symbol_mappings")
        count = result[0][0]
        logger.info(f"✓ Successfully inserted {count} symbol mappings")

        # Show sample
        logger.info("\nSample mappings:")
        samples = clickhouse.client.execute("""
            SELECT base_asset, quote_asset, exchange, symbol
            FROM trading.symbol_mappings
            ORDER BY base_asset, exchange
            LIMIT 10
        """)
        for row in samples:
            logger.info(f"  {row[0]}/{row[1]}: {row[2]:10s} → {row[3]}")

    finally:
        await clickhouse.close()

    logger.info(f"\n✅ Done! {count} symbol mappings loaded")


if __name__ == "__main__":
    asyncio.run(main())
