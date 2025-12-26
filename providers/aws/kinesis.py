"""
AWS Kinesis implementation of stream client

Works with both AWS and LocalStack
"""

import json
import logging
from typing import Any

import aioboto3

from config.settings import get_settings
from core.interfaces.streaming import BaseStreamClient

logger = logging.getLogger(__name__)


class KinesisStreamClient(BaseStreamClient):
    """
    AWS Kinesis implementation

    Features:
    - Real-time data streaming
    - Auto-scaling shards
    - Integration with Lambda, S3, etc.
    - Works with LocalStack for local development
    """

    def __init__(self):
        self.settings = get_settings()
        self.session = aioboto3.Session()
        self.client = None

    async def connect(self) -> None:
        """Initialize Kinesis client"""
        try:
            # Create client context manager
            self.client = self.session.client(
                "kinesis",
                region_name=self.settings.AWS_REGION,
                endpoint_url=self.settings.AWS_ENDPOINT_URL or None,
                aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
            )

            # Enter async context
            self.client = await self.client.__aenter__()

            logger.info(f"✓ Connected to Kinesis: {self.settings.AWS_ENDPOINT_URL or 'AWS'}")
        except Exception as e:
            logger.error(f"✗ Failed to connect to Kinesis: {e}")
            raise

    async def send_record(
        self, stream_name: str, data: dict[str, Any], partition_key: str
    ) -> dict[str, Any]:
        """
        Send single record to Kinesis

        Args:
            stream_name: Kinesis stream name
            data: Data dictionary (will be JSON serialized)
            partition_key: Partition key (e.g., symbol for same-symbol ordering)

        Returns:
            Response with ShardId and SequenceNumber
        """
        if not self.client:
            raise RuntimeError("Kinesis client not connected")

        try:
            response = await self.client.put_record(
                StreamName=stream_name,
                Data=json.dumps(data, default=str),  # default=str for Decimal/datetime
                PartitionKey=partition_key,
            )
            logger.debug(
                f"Sent record to {stream_name}: "
                f"Shard={response['ShardId']}, Seq={response['SequenceNumber']}"
            )
            return response

        except Exception as e:
            logger.error(f"✗ Kinesis send_record error: {e}")
            raise

    async def send_batch(self, stream_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Send batch of records (up to 500 records, 5MB total)

        Args:
            stream_name: Kinesis stream name
            records: List of records with 'data' and 'partition_key' fields

        Returns:
            Response with FailedRecordCount and Records
        """
        if not self.client:
            raise RuntimeError("Kinesis client not connected")

        try:
            kinesis_records = [
                {
                    "Data": json.dumps(record["data"], default=str),
                    "PartitionKey": record["partition_key"],
                }
                for record in records
            ]

            response = await self.client.put_records(
                StreamName=stream_name, Records=kinesis_records
            )

            failed_count = response.get("FailedRecordCount", 0)
            if failed_count > 0:
                logger.warning(
                    f"⚠ Kinesis batch: {failed_count} records failed out of {len(records)}"
                )
            else:
                logger.debug(f"Sent {len(records)} records to {stream_name}")

            return response

        except Exception as e:
            logger.error(f"✗ Kinesis send_batch error: {e}")
            raise

    async def close(self) -> None:
        """Close client"""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
                logger.info("✓ Kinesis connection closed")
            except Exception as e:
                logger.error(f"Error closing Kinesis client: {e}")
