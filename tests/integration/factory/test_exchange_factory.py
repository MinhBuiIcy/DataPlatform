"""
Integration tests for exchange factory wiring

Tests that factory returns correct exchange instances.
This validates the factory pattern abstraction layer.
"""

import pytest
from factory.client_factory import create_exchange_rest_api
from providers.binance.rest_api import BinanceRestAPI
from providers.coinbase.rest_api import CoinbaseRestAPI
from providers.kraken.rest_api import KrakenRestAPI


@pytest.mark.integration
def test_binance_rest_api_factory_wiring():
    """Verify factory returns correct Binance REST API instance"""
    api = create_exchange_rest_api("binance")
    assert isinstance(api, BinanceRestAPI)
    print("\n✓ Factory creates BinanceRestAPI instance")


@pytest.mark.integration
def test_coinbase_rest_api_factory_wiring():
    """Verify factory returns correct Coinbase REST API instance"""
    api = create_exchange_rest_api("coinbase")
    assert isinstance(api, CoinbaseRestAPI)
    print("\n✓ Factory creates CoinbaseRestAPI instance")


@pytest.mark.integration
def test_kraken_rest_api_factory_wiring():
    """Verify factory returns correct Kraken REST API instance"""
    api = create_exchange_rest_api("kraken")
    assert isinstance(api, KrakenRestAPI)
    print("\n✓ Factory creates KrakenRestAPI instance")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
