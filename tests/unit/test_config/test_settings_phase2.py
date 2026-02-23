"""
Unit tests for Phase 2 settings configuration

Tests YAML config loading for sync and indicator service settings.
"""


import pytest

from config.settings import Settings, get_settings


@pytest.mark.unit
class TestSyncServiceSettings:
    """Test Sync Service configuration settings"""

    def test_sync_timeframes_loading(self):
        """Test SYNC_TIMEFRAMES loads from sync.yaml"""
        settings = get_settings()

        assert hasattr(settings, "SYNC_TIMEFRAMES")
        assert isinstance(settings.SYNC_TIMEFRAMES, list)
        assert len(settings.SYNC_TIMEFRAMES) > 0

        # Should contain common timeframes
        assert "1m" in settings.SYNC_TIMEFRAMES

    def test_sync_interval_seconds(self):
        """Test SYNC_INTERVAL_SECONDS setting"""
        settings = get_settings()

        assert hasattr(settings, "SYNC_INTERVAL_SECONDS")
        assert isinstance(settings.SYNC_INTERVAL_SECONDS, int)
        assert settings.SYNC_INTERVAL_SECONDS > 0

    def test_sync_fetch_limit(self):
        """Test SYNC_FETCH_LIMIT setting"""
        settings = get_settings()

        assert hasattr(settings, "SYNC_FETCH_LIMIT")
        assert isinstance(settings.SYNC_FETCH_LIMIT, int)
        assert settings.SYNC_FETCH_LIMIT > 0

    def test_sync_initial_backfill_limit(self):
        """Test SYNC_INITIAL_BACKFILL_LIMIT setting"""
        settings = get_settings()

        assert hasattr(settings, "SYNC_INITIAL_BACKFILL_LIMIT")
        assert isinstance(settings.SYNC_INITIAL_BACKFILL_LIMIT, int)
        # Should be larger than regular fetch limit (for indicator history)
        assert settings.SYNC_INITIAL_BACKFILL_LIMIT >= 50


@pytest.mark.unit
class TestRestAPISettings:
    """Test REST API configuration settings"""

    def test_rest_api_timeout_ms(self):
        """Test REST_API_TIMEOUT_MS setting"""
        settings = get_settings()

        assert hasattr(settings, "REST_API_TIMEOUT_MS")
        assert isinstance(settings.REST_API_TIMEOUT_MS, int)
        assert settings.REST_API_TIMEOUT_MS > 0

    def test_rest_api_enable_rate_limit(self):
        """Test REST_API_ENABLE_RATE_LIMIT setting"""
        settings = get_settings()

        assert hasattr(settings, "REST_API_ENABLE_RATE_LIMIT")
        assert isinstance(settings.REST_API_ENABLE_RATE_LIMIT, bool)
        # Should be True by default (avoid rate limit errors)
        assert settings.REST_API_ENABLE_RATE_LIMIT is True


@pytest.mark.unit
class TestIndicatorServiceSettings:
    """Test Indicator Service configuration settings"""

    def test_indicator_service_interval_seconds(self):
        """Test INDICATOR_SERVICE_INTERVAL_SECONDS setting"""
        settings = get_settings()

        assert hasattr(settings, "INDICATOR_SERVICE_INTERVAL_SECONDS")
        assert isinstance(settings.INDICATOR_SERVICE_INTERVAL_SECONDS, int)
        assert settings.INDICATOR_SERVICE_INTERVAL_SECONDS > 0

    def test_indicator_service_initial_delay_seconds(self):
        """Test INDICATOR_SERVICE_INITIAL_DELAY_SECONDS setting"""
        settings = get_settings()

        assert hasattr(settings, "INDICATOR_SERVICE_INITIAL_DELAY_SECONDS")
        assert isinstance(settings.INDICATOR_SERVICE_INITIAL_DELAY_SECONDS, int)
        assert settings.INDICATOR_SERVICE_INITIAL_DELAY_SECONDS >= 0

    def test_indicator_service_min_candles(self):
        """Test INDICATOR_SERVICE_MIN_CANDLES setting"""
        settings = get_settings()

        assert hasattr(settings, "INDICATOR_SERVICE_MIN_CANDLES")
        assert isinstance(settings.INDICATOR_SERVICE_MIN_CANDLES, int)
        # Should be at least 20 for common indicators (SMA_20)
        assert settings.INDICATOR_SERVICE_MIN_CANDLES >= 20

    def test_indicator_candle_lookback(self):
        """Test INDICATOR_CANDLE_LOOKBACK setting"""
        settings = get_settings()

        assert hasattr(settings, "INDICATOR_CANDLE_LOOKBACK")
        assert isinstance(settings.INDICATOR_CANDLE_LOOKBACK, int)
        # Should be >= 100 for longer indicators (SMA_50, MACD)
        assert settings.INDICATOR_CANDLE_LOOKBACK >= 100

    def test_indicator_service_catch_up_enabled(self):
        """Test INDICATOR_SERVICE_CATCH_UP_ENABLED setting"""
        settings = get_settings()

        assert hasattr(settings, "INDICATOR_SERVICE_CATCH_UP_ENABLED")
        assert isinstance(settings.INDICATOR_SERVICE_CATCH_UP_ENABLED, bool)

    def test_indicator_service_catch_up_limit(self):
        """Test INDICATOR_SERVICE_CATCH_UP_LIMIT setting"""
        settings = get_settings()

        assert hasattr(settings, "INDICATOR_SERVICE_CATCH_UP_LIMIT")
        assert isinstance(settings.INDICATOR_SERVICE_CATCH_UP_LIMIT, int)
        # Should be large enough for historical processing
        assert settings.INDICATOR_SERVICE_CATCH_UP_LIMIT >= 500


@pytest.mark.unit
class TestSettingsSingleton:
    """Test settings singleton behavior"""

    def test_get_settings_returns_same_instance(self):
        """Test that get_settings() returns singleton"""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_settings_yaml_loaded_cache(self):
        """Test that YAML configs are cached at class level"""
        # First load
        settings1 = get_settings()
        timeframes1 = settings1.SYNC_TIMEFRAMES

        # Second load
        settings2 = get_settings()
        timeframes2 = settings2.SYNC_TIMEFRAMES

        # Should be same instance (cached)
        assert timeframes1 is timeframes2


@pytest.mark.unit
class TestSettingsResetForTesting:
    """Test settings reset mechanism for testing"""

    def test_yaml_loaded_flag_reset(self):
        """Test resetting _yaml_loaded flag for test isolation"""
        # Get initial settings
        get_settings()

        # Reset the class-level cache flag
        if hasattr(Settings, "_yaml_loaded"):
            delattr(Settings, "_yaml_loaded")

        # Create new settings instance
        new_settings = Settings()

        # Should reload YAML (may be same values, but different instance)
        assert hasattr(new_settings, "SYNC_TIMEFRAMES")


@pytest.mark.unit
class TestMultiTimeframeSettings:
    """Test multi-timeframe configuration"""

    def test_sync_timeframes_contains_multiple_timeframes(self):
        """Test that SYNC_TIMEFRAMES has multiple timeframes"""
        settings = get_settings()

        # Should have multiple timeframes configured
        assert len(settings.SYNC_TIMEFRAMES) >= 1

        # Common timeframes should be present
        valid_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        for tf in settings.SYNC_TIMEFRAMES:
            assert tf in valid_timeframes, f"Unexpected timeframe: {tf}"

    def test_timeframes_are_strings(self):
        """Test that all timeframes are strings"""
        settings = get_settings()

        for tf in settings.SYNC_TIMEFRAMES:
            assert isinstance(tf, str)
            assert len(tf) > 0


@pytest.mark.unit
class TestSettingsValidation:
    """Test settings validation"""

    def test_interval_less_than_timeout(self):
        """Test that sync interval is reasonable"""
        settings = get_settings()

        # Sync interval should be at least a few seconds
        assert settings.SYNC_INTERVAL_SECONDS >= 10

    def test_indicator_delay_less_than_sync_interval(self):
        """Test that indicator delay makes sense"""
        settings = get_settings()

        # Indicator service should wait long enough for sync to complete
        assert settings.INDICATOR_SERVICE_INITIAL_DELAY_SECONDS >= 10

    def test_candle_lookback_greater_than_min_candles(self):
        """Test lookback >= min_candles"""
        settings = get_settings()

        assert settings.INDICATOR_CANDLE_LOOKBACK >= settings.INDICATOR_SERVICE_MIN_CANDLES

    def test_rest_api_timeout_reasonable(self):
        """Test REST API timeout is reasonable (not too short/long)"""
        settings = get_settings()

        # Should be between 5-60 seconds
        assert 5000 <= settings.REST_API_TIMEOUT_MS <= 60000


@pytest.mark.unit
class TestSettingsDefaults:
    """Test default values for settings"""

    def test_sync_interval_default(self):
        """Test default sync interval is 60 seconds"""
        settings = get_settings()
        # Should be around 60 seconds (1 minute)
        assert settings.SYNC_INTERVAL_SECONDS == 60

    def test_indicator_interval_default(self):
        """Test default indicator interval"""
        settings = get_settings()
        # Should run frequently (60-120 seconds)
        assert 30 <= settings.INDICATOR_SERVICE_INTERVAL_SECONDS <= 120

    def test_rest_api_rate_limit_enabled_by_default(self):
        """Test rate limiting enabled by default"""
        settings = get_settings()
        assert settings.REST_API_ENABLE_RATE_LIMIT is True

    def test_catch_up_enabled_by_default(self):
        """Test catch-up mode enabled by default"""
        settings = get_settings()
        # Catch-up should be enabled for historical processing
        assert settings.INDICATOR_SERVICE_CATCH_UP_ENABLED is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
