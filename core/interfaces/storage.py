from abc import ABC, abstractmethod


class BaseStorageClient(ABC):
    """
    Abstract interface for object storage

    Implementations:
    - S3StorageClient (AWS)
    - GCSStorageClient (GCP)
    - BlobStorageClient (Azure)
    - MinIOStorageClient (Self-hosted)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize storage client"""

    @abstractmethod
    async def upload_file(
        self, bucket: str, key: str, data: bytes, metadata: dict | None = None
    ) -> str:
        """
        Upload file to storage

        Args:
            bucket: Bucket/container name
            key: Object key/path
            data: File content as bytes
            metadata: Optional metadata tags

        Returns:
            URI of uploaded object (e.g., s3://bucket/key)
        """

    @abstractmethod
    async def download_file(self, bucket: str, key: str) -> bytes:
        """
        Download file from storage

        Args:
            bucket: Bucket/container name
            key: Object key/path

        Returns:
            File content as bytes
        """

    @abstractmethod
    async def list_objects(self, bucket: str, prefix: str) -> list[dict]:
        """
        List objects in bucket

        Args:
            bucket: Bucket/container name
            prefix: Key prefix filter

        Returns:
            List of object metadata dictionaries
        """

    @abstractmethod
    async def close(self) -> None:
        """Close client"""
