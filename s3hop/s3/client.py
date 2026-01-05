"""S3 client management with connection pooling and session reuse.

This module provides a managed S3 client that implements:
- Connection pooling for better performance
- Session reuse across operations
- Configurable timeouts and retry behavior
- Support for transfer acceleration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

import boto3
from botocore.config import Config as BotocoreConfig

from ..config import ConnectionConfig, TransferConfig
from ..exceptions import BucketAccessError, BucketNotFoundError, ProfileNotFoundError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import ListObjectsV2OutputTypeDef

logger = logging.getLogger(__name__)


class S3ClientManager:
    """Manages S3 client instances with connection pooling and configuration.

    This class creates and manages boto3 S3 clients with optimized settings
    for high-performance transfers, including connection pooling, configurable
    timeouts, and transfer acceleration support.
    """

    def __init__(
        self,
        profile_name: str | None = None,
        config: TransferConfig | None = None,
        region: str | None = None,
    ) -> None:
        """Initialize the S3 client manager.

        Args:
            profile_name: AWS profile name to use for credentials.
            config: Transfer configuration with connection settings.
            region: AWS region for the client (overrides config).
        """
        self._profile_name = profile_name
        self._config = config or TransferConfig()
        self._region = region or self._config.connection.region
        self._session: boto3.Session | None = None
        self._client: S3Client | None = None

    @property
    def session(self) -> boto3.Session:
        """Get or create the boto3 session."""
        if self._session is None:
            try:
                self._session = boto3.Session(profile_name=self._profile_name)
            except Exception as e:
                if self._profile_name:
                    raise ProfileNotFoundError(self._profile_name) from e
                raise
        return self._session

    @property
    def client(self) -> S3Client:
        """Get or create the S3 client with optimized configuration."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> S3Client:
        """Create an S3 client with optimized settings."""
        conn_config = self._config.connection

        # Build botocore config
        botocore_config = BotocoreConfig(
            connect_timeout=conn_config.connect_timeout,
            read_timeout=conn_config.read_timeout,
            max_pool_connections=conn_config.max_pool_connections,
            retries={"max_attempts": 0},  # We handle retries ourselves
        )

        # Create client with optional transfer acceleration
        endpoint_url = None
        if conn_config.use_transfer_acceleration:
            endpoint_url = "https://s3-accelerate.amazonaws.com"
            logger.info("Using S3 Transfer Acceleration")

        return self.session.client(
            "s3",
            region_name=self._region,
            config=botocore_config,
            endpoint_url=endpoint_url,
        )

    def validate_bucket_access(self, bucket: str, write_access: bool = False) -> None:
        """Validate that we have access to the specified bucket.

        Args:
            bucket: Name of the bucket to validate.
            write_access: If True, also validate write access.

        Raises:
            BucketNotFoundError: If the bucket does not exist.
            BucketAccessError: If access to the bucket is denied.
        """
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                raise BucketNotFoundError(bucket) from e
            if error_code in ("403", "AccessDenied"):
                raise BucketAccessError(bucket, "head_bucket", e) from e
            raise

        if write_access:
            # Try a harmless put operation to test write access
            try:
                # Check if we can get bucket ACL as a proxy for write access
                self.client.get_bucket_acl(Bucket=bucket)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("403", "AccessDenied"):
                    raise BucketAccessError(bucket, "write", e) from e

    def paginate_objects(
        self,
        bucket: str,
        prefix: str = "",
        page_size: int = 1000,
    ) -> Iterator[ListObjectsV2OutputTypeDef]:
        """Paginate through objects in a bucket with a given prefix.

        Args:
            bucket: Name of the bucket.
            prefix: Prefix to filter objects.
            page_size: Number of objects per page.

        Yields:
            Pages of ListObjectsV2 responses.
        """
        paginator = self.client.get_paginator("list_objects_v2")
        page_config = {"PageSize": page_size}

        for page in paginator.paginate(
            Bucket=bucket,
            Prefix=prefix,
            PaginationConfig=page_config,
        ):
            yield page

    def get_object_stream(self, bucket: str, key: str) -> dict:
        """Get an object with streaming body.

        Args:
            bucket: Name of the bucket.
            key: Object key.

        Returns:
            GetObject response with streaming Body.
        """
        return self.client.get_object(Bucket=bucket, Key=key)

    def close(self) -> None:
        """Close the client and release resources."""
        if self._client is not None:
            # boto3 clients don't have explicit close, but we clear our reference
            self._client = None
        if self._session is not None:
            self._session = None

    def __enter__(self) -> "S3ClientManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()


def create_client_pair(
    source_profile: str,
    dest_profile: str,
    config: TransferConfig | None = None,
    source_region: str | None = None,
    dest_region: str | None = None,
) -> tuple[S3ClientManager, S3ClientManager]:
    """Create a pair of S3 clients for source and destination.

    Args:
        source_profile: AWS profile for source bucket.
        dest_profile: AWS profile for destination bucket.
        config: Transfer configuration.
        source_region: Region for source bucket (optional).
        dest_region: Region for destination bucket (optional).

    Returns:
        Tuple of (source_client, dest_client) managers.
    """
    config = config or TransferConfig()

    source_client = S3ClientManager(
        profile_name=source_profile,
        config=config,
        region=source_region or config.get_source_region(),
    )

    dest_client = S3ClientManager(
        profile_name=dest_profile,
        config=config,
        region=dest_region or config.get_dest_region(),
    )

    return source_client, dest_client
