from datetime import datetime
from unittest.mock import Mock, patch

import boto3
import pytest
from botocore.exceptions import ClientError

from s3hop.core import (
    ProgressTracker,
    TransferStatus,
    analyze_transfer_needs,
    get_object_info,
    get_relative_path,
    parse_s3_url,
)


# URL Parsing Tests
def test_parse_s3_url_with_prefix():
    """Test parsing S3 URL with prefix"""
    url = "s3://my-bucket/some/prefix/"
    bucket, prefix = parse_s3_url(url)
    assert bucket == "my-bucket"
    assert prefix == "some/prefix/"


def test_parse_s3_url_without_prefix():
    """Test parsing S3 URL without prefix"""
    url = "s3://my-bucket"
    bucket, prefix = parse_s3_url(url)
    assert bucket == "my-bucket"
    assert prefix == ""


def test_parse_s3_url_invalid():
    """Test parsing invalid S3 URL"""
    with pytest.raises(ValueError):
        parse_s3_url("not-an-s3-url")


def test_parse_s3_url_with_trailing_slash():
    """Test parsing S3 URL with trailing slash"""
    url = "s3://my-bucket/"
    bucket, prefix = parse_s3_url(url)
    assert bucket == "my-bucket"
    assert prefix == ""


# Progress Tracker Tests
def test_progress_tracker_initialization():
    """Test ProgressTracker initialization"""
    tracker = ProgressTracker()
    assert tracker.total_files == 0
    assert tracker.total_size == 0
    assert tracker.processed_files == 0
    assert tracker.processed_size == 0
    assert tracker.current_speed == 0
    assert len(tracker.failed_files) == 0
    assert tracker.skipped_files == 0
    assert tracker.skipped_size == 0


def test_progress_tracker_update():
    """Test ProgressTracker update method"""
    tracker = ProgressTracker()
    tracker.update(1000)  # 1KB
    assert tracker.processed_files == 1
    assert tracker.processed_size == 1000


def test_progress_tracker_add_failed():
    """Test ProgressTracker failed files tracking"""
    tracker = ProgressTracker()
    tracker.add_failed("failed-file.txt")
    assert len(tracker.failed_files) == 1
    assert tracker.failed_files[0] == "failed-file.txt"


def test_progress_tracker_extension_stats():
    """Test ProgressTracker extension statistics"""
    tracker = ProgressTracker()
    tracker.update_extension_stats("test.txt", 1000)
    tracker.update_extension_stats("data.txt", 2000)
    tracker.update_extension_stats("image.jpg", 3000)

    assert tracker.extension_stats["txt"]["count"] == 2
    assert tracker.extension_stats["txt"]["size"] == 3000
    assert tracker.extension_stats["jpg"]["count"] == 1
    assert tracker.extension_stats["jpg"]["size"] == 3000


# Path Handling Tests
def test_get_relative_path_with_prefix():
    """Test getting relative path with prefix"""
    key = "prefix/path/to/file.txt"
    prefix = "prefix/"
    assert get_relative_path(key, prefix) == "path/to/file.txt"


def test_get_relative_path_without_prefix():
    """Test getting relative path without prefix"""
    key = "path/to/file.txt"
    prefix = ""
    assert get_relative_path(key, prefix) == "path/to/file.txt"


def test_get_relative_path_exact_prefix():
    """Test getting relative path with exact prefix match"""
    key = "prefix/file.txt"
    prefix = "prefix/"
    assert get_relative_path(key, prefix) == "file.txt"


# Transfer Analysis Tests
def test_analyze_transfer_needs_new_file():
    """Test analyzing transfer needs for new files"""
    source_objects = {
        "file.txt": {
            "full_key": "file.txt",
            "size": 1000,
            "etag": "abc123",
            "last_modified": datetime.now(),
        }
    }
    dest_objects = {}

    to_transfer, existing, new_size, existing_size = analyze_transfer_needs(
        source_objects, dest_objects
    )

    assert len(to_transfer) == 1
    assert len(existing) == 0
    assert new_size == 1000
    assert existing_size == 0
    assert to_transfer["file.txt"]["status"] == TransferStatus.NEW


def test_analyze_transfer_needs_existing_file():
    """Test analyzing transfer needs for existing unchanged files"""
    now = datetime.now()
    etag = "abc123"
    source_objects = {
        "file.txt": {
            "full_key": "file.txt",
            "size": 1000,
            "etag": etag,
            "last_modified": now,
        }
    }
    dest_objects = {
        "file.txt": {
            "full_key": "file.txt",
            "size": 1000,
            "etag": etag,
            "last_modified": now,
        }
    }

    to_transfer, existing, new_size, existing_size = analyze_transfer_needs(
        source_objects, dest_objects
    )

    assert len(to_transfer) == 0
    assert len(existing) == 1
    assert new_size == 0
    assert existing_size == 1000


def test_analyze_transfer_needs_updated_file():
    """Test analyzing transfer needs for updated files"""
    etag = "abc123"
    new_etag = "def456"
    now = datetime.now()
    source_objects = {
        "file.txt": {
            "full_key": "file.txt",
            "size": 1000,
            "etag": new_etag,
            "last_modified": now,
        }
    }
    dest_objects = {
        "file.txt": {
            "full_key": "file.txt",
            "size": 1000,
            "etag": etag,
            "last_modified": now,
        }
    }

    to_transfer, existing, new_size, existing_size = analyze_transfer_needs(
        source_objects, dest_objects
    )

    assert len(to_transfer) == 1
    assert len(existing) == 0
    assert new_size == 1000
    assert existing_size == 0
    assert to_transfer["file.txt"]["status"] == TransferStatus.UPDATED


# S3 Client Tests
@patch("boto3.Session")
def test_create_s3_client(mock_session):
    """Test S3 client creation with profile"""
    mock_client = Mock()
    mock_session.return_value.client.return_value = mock_client

    from s3hop.core import create_s3_client

    client = create_s3_client(profile_name="test-profile")

    mock_session.assert_called_once_with(profile_name="test-profile")
    mock_session.return_value.client.assert_called_once_with(
        "s3", region_name="us-east-1"
    )


@patch("boto3.Session")
def test_get_object_info_success(mock_session):
    """Test getting object info from S3"""
    mock_client = Mock()
    mock_paginator = Mock()
    mock_client.get_paginator.return_value = mock_paginator

    # Mock S3 response
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "test/file.txt",
                    "Size": 1000,
                    "ETag": '"abc123"',
                    "LastModified": datetime.now(),
                }
            ]
        }
    ]

    mock_session.return_value.client.return_value = mock_client

    from s3hop.core import get_object_info

    objects = get_object_info(mock_client, "test-bucket", "test/")

    assert len(objects) == 1
    assert "file.txt" in objects
    assert objects["file.txt"]["size"] == 1000
    assert objects["file.txt"]["etag"] == "abc123"


@patch("boto3.Session")
def test_get_object_info_empty_bucket(mock_session):
    """Test getting object info from empty bucket"""
    mock_client = Mock()
    mock_paginator = Mock()
    mock_client.get_paginator.return_value = mock_paginator

    # Mock empty S3 response
    mock_paginator.paginate.return_value = [{}]

    mock_session.return_value.client.return_value = mock_client

    from s3hop.core import get_object_info

    objects = get_object_info(mock_client, "test-bucket", "test/")

    assert len(objects) == 0
