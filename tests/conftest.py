"""Pytest configuration and fixtures for s3hop tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from s3hop.config import TransferConfig
from s3hop.models import S3Location, S3Object, TransferItem, TransferStatus


@pytest.fixture
def sample_s3_object() -> S3Object:
    """Create a sample S3Object for testing."""
    return S3Object(
        key="prefix/path/to/file.txt",
        size=1024,
        etag="abc123def456",
        last_modified=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        relative_path="path/to/file.txt",
    )


@pytest.fixture
def sample_s3_objects() -> dict[str, S3Object]:
    """Create a collection of sample S3Objects for testing."""
    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    return {
        "file1.txt": S3Object(
            key="prefix/file1.txt",
            size=1000,
            etag="etag1",
            last_modified=base_time,
            relative_path="file1.txt",
        ),
        "file2.json": S3Object(
            key="prefix/file2.json",
            size=2000,
            etag="etag2",
            last_modified=base_time,
            relative_path="file2.json",
        ),
        "subdir/file3.csv": S3Object(
            key="prefix/subdir/file3.csv",
            size=3000,
            etag="etag3",
            last_modified=base_time,
            relative_path="subdir/file3.csv",
        ),
    }


@pytest.fixture
def sample_location() -> S3Location:
    """Create a sample S3Location for testing."""
    return S3Location(bucket="test-bucket", prefix="test-prefix/")


@pytest.fixture
def sample_transfer_config() -> TransferConfig:
    """Create a sample TransferConfig for testing."""
    return TransferConfig(
        max_workers=5,
        dry_run=False,
        verbose=False,
    )


@pytest.fixture
def mock_s3_client() -> Mock:
    """Create a mock S3 client."""
    client = Mock()

    # Mock paginator
    paginator = Mock()
    client.get_paginator.return_value = paginator

    return client


@pytest.fixture
def mock_boto3_session(mock_s3_client: Mock) -> Mock:
    """Create a mock boto3 session."""
    session = Mock()
    session.client.return_value = mock_s3_client
    return session


def create_s3_response_page(
    objects: list[dict[str, Any]],
    is_truncated: bool = False,
    continuation_token: str | None = None,
) -> dict[str, Any]:
    """Helper to create an S3 ListObjectsV2 response page."""
    response: dict[str, Any] = {
        "IsTruncated": is_truncated,
        "Contents": objects,
    }
    if continuation_token:
        response["NextContinuationToken"] = continuation_token
    return response


def create_s3_object_response(
    key: str,
    size: int = 1000,
    etag: str = "abc123",
    storage_class: str = "STANDARD",
) -> dict[str, Any]:
    """Helper to create an S3 object metadata response."""
    return {
        "Key": key,
        "Size": size,
        "ETag": f'"{etag}"',
        "LastModified": datetime.now(timezone.utc),
        "StorageClass": storage_class,
    }
