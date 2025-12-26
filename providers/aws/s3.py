"""
AWS S3 implementation of storage client

Works with both AWS and LocalStack
"""

import logging

import aioboto3

from config.settings import get_settings
from core.interfaces.storage import BaseStorageClient

logger = logging.getLogger(__name__)


class S3StorageClient(BaseStorageClient):
    """
    AWS S3 implementation

    Features:
    - Object storage (unlimited scalability)
    - Versioning and lifecycle policies
    - Server-side encryption
    - Works with LocalStack for local development
    """

    def __init__(self):
        self.settings = get_settings()
        self.session = aioboto3.Session()
        self.client = None

    async def connect(self) -> None:
        """Initialize S3 client"""
        try:
            # Create client context manager
            self.client = self.session.client(
                "s3",
                region_name=self.settings.AWS_REGION,
                endpoint_url=self.settings.AWS_ENDPOINT_URL or None,
                aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
            )

            # Enter async context
            self.client = await self.client.__aenter__()

            logger.info(f"✓ Connected to S3: {self.settings.AWS_ENDPOINT_URL or 'AWS'}")
        except Exception as e:
            logger.error(f"✗ Failed to connect to S3: {e}")
            raise

    async def upload_file(
        self, bucket: str, key: str, data: bytes, metadata: dict | None = None
    ) -> str:
        """
        Upload file to S3

        Args:
            bucket: S3 bucket name
            key: Object key (path)
            data: File content as bytes
            metadata: Optional metadata tags

        Returns:
            S3 URI (s3://bucket/key)
        """
        if not self.client:
            raise RuntimeError("S3 client not connected")

        try:
            await self.client.put_object(Bucket=bucket, Key=key, Body=data, Metadata=metadata or {})
            uri = f"s3://{bucket}/{key}"
            logger.debug(f"Uploaded to S3: {uri}")
            return uri

        except Exception as e:
            logger.error(f"✗ S3 upload error: {e}")
            raise

    async def download_file(self, bucket: str, key: str) -> bytes:
        """
        Download file from S3

        Args:
            bucket: S3 bucket name
            key: Object key (path)

        Returns:
            File content as bytes
        """
        if not self.client:
            raise RuntimeError("S3 client not connected")

        try:
            response = await self.client.get_object(Bucket=bucket, Key=key)
            data = await response["Body"].read()
            logger.debug(f"Downloaded from S3: s3://{bucket}/{key}")
            return data

        except Exception as e:
            logger.error(f"✗ S3 download error: {e}")
            raise

    async def list_objects(self, bucket: str, prefix: str) -> list[dict]:
        """
        List objects in bucket

        Args:
            bucket: S3 bucket name
            prefix: Key prefix filter

        Returns:
            List of object metadata dictionaries
        """
        if not self.client:
            raise RuntimeError("S3 client not connected")

        try:
            response = await self.client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            objects = response.get("Contents", [])
            logger.debug(f"Listed {len(objects)} objects in s3://{bucket}/{prefix}")
            return objects

        except Exception as e:
            logger.error(f"✗ S3 list error: {e}")
            raise

    async def close(self) -> None:
        """Close client"""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
                logger.info("✓ S3 connection closed")
            except Exception as e:
                logger.error(f"Error closing S3 client: {e}")
