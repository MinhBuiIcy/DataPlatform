"""
Unit tests for factory pattern

Tests that correct client implementations are created based on config
"""

from unittest.mock import patch

import pytest

from factory.client_factory import (
    create_cache_client,
    create_storage_client,
    create_stream_client,
    create_timeseries_db,
)
from providers.aws.kinesis import KinesisStreamClient
from providers.aws.s3 import S3StorageClient
from providers.opensource.clickhouse import ClickHouseClient
from providers.opensource.redis_client import RedisClient


class TestStreamClientFactory:
    """Test stream client factory"""

    @patch("factory.client_factory.get_settings")
    def test_create_kinesis_client_for_aws(self, mock_settings):
        """Test that AWS config creates KinesisStreamClient"""
        mock_settings.return_value.CLOUD_PROVIDER = "aws"

        client = create_stream_client()

        assert isinstance(client, KinesisStreamClient)

    @patch("factory.client_factory.get_settings")
    def test_create_kinesis_client_for_localstack(self, mock_settings):
        """Test that LocalStack config creates KinesisStreamClient"""
        mock_settings.return_value.CLOUD_PROVIDER = "localstack"

        client = create_stream_client()

        assert isinstance(client, KinesisStreamClient)

    @patch("factory.client_factory.get_settings")
    def test_unsupported_provider_raises_error(self, mock_settings):
        """Test that unsupported provider raises ValueError"""
        mock_settings.return_value.CLOUD_PROVIDER = "invalid"

        with pytest.raises(ValueError, match="Unsupported cloud provider"):
            create_stream_client()

    @patch("factory.client_factory.get_settings")
    def test_opensource_provider_creates_kafka(self, mock_settings):
        """Test that opensource provider creates KafkaStreamClient"""
        mock_settings.return_value.CLOUD_PROVIDER = "opensource"

        from providers.opensource.kafka_stream import KafkaStreamClient

        client = create_stream_client()

        assert isinstance(client, KafkaStreamClient)


class TestCacheClientFactory:
    """Test cache client factory"""

    def test_create_redis_client(self):
        """Test that factory creates RedisClient"""
        client = create_cache_client()

        assert isinstance(client, RedisClient)


class TestTimeSeriesDBFactory:
    """Test time-series database factory"""

    def test_create_clickhouse_client(self):
        """Test that factory creates ClickHouseClient"""
        client = create_timeseries_db()

        assert isinstance(client, ClickHouseClient)


class TestStorageClientFactory:
    """Test storage client factory"""

    @patch("factory.client_factory.get_settings")
    def test_create_s3_client_for_aws(self, mock_settings):
        """Test that AWS config creates S3StorageClient"""
        mock_settings.return_value.CLOUD_PROVIDER = "aws"

        client = create_storage_client()

        assert isinstance(client, S3StorageClient)

    @patch("factory.client_factory.get_settings")
    def test_create_s3_client_for_localstack(self, mock_settings):
        """Test that LocalStack config creates S3StorageClient"""
        mock_settings.return_value.CLOUD_PROVIDER = "localstack"

        client = create_storage_client()

        assert isinstance(client, S3StorageClient)

    @patch("factory.client_factory.get_settings")
    def test_gcp_provider_not_implemented(self, mock_settings):
        """Test that GCP storage is not yet implemented"""
        mock_settings.return_value.CLOUD_PROVIDER = "gcp"

        with pytest.raises(NotImplementedError, match="GCSStorageClient"):
            create_storage_client()


class TestFactoryIntegration:
    """Test that factory pattern enables cloud portability"""

    @patch("factory.client_factory.get_settings")
    def test_switching_cloud_providers(self, mock_settings):
        """Test that changing CLOUD_PROVIDER creates different clients"""

        # Test AWS
        mock_settings.return_value.CLOUD_PROVIDER = "aws"
        aws_stream = create_stream_client()
        assert isinstance(aws_stream, KinesisStreamClient)

        # Test LocalStack (same class as AWS)
        mock_settings.return_value.CLOUD_PROVIDER = "localstack"
        localstack_stream = create_stream_client()
        assert isinstance(localstack_stream, KinesisStreamClient)

        # Different instances
        assert aws_stream is not localstack_stream


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
