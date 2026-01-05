"""Tests for s3hop S3 operations."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from s3hop.config import FilterConfig, TransferConfig
from s3hop.models import S3Location, S3Object, TransferStatus
from s3hop.s3.analysis import analyze_transfer_needs, list_objects, _needs_update


class TestListObjects:
    """Tests for list_objects function."""

    def test_list_objects_empty_bucket(self) -> None:
        """Test listing empty bucket."""
        mock_client = Mock()
        mock_client.paginate_objects.return_value = [{}]

        location = S3Location(bucket="test-bucket", prefix="test/")
        result = list_objects(mock_client, location)

        assert len(result) == 0

    def test_list_objects_with_objects(self) -> None:
        """Test listing bucket with objects."""
        mock_client = Mock()
        mock_client.paginate_objects.return_value = [
            {
                "Contents": [
                    {
                        "Key": "test/file1.txt",
                        "Size": 1000,
                        "ETag": '"abc123"',
                        "LastModified": datetime.now(timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                    {
                        "Key": "test/file2.json",
                        "Size": 2000,
                        "ETag": '"def456"',
                        "LastModified": datetime.now(timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                ]
            }
        ]

        location = S3Location(bucket="test-bucket", prefix="test/")
        result = list_objects(mock_client, location)

        assert len(result) == 2
        assert "file1.txt" in result
        assert "file2.json" in result
        assert result["file1.txt"].size == 1000
        assert result["file2.json"].size == 2000

    def test_list_objects_skips_directories(self) -> None:
        """Test that directory markers are skipped."""
        mock_client = Mock()
        mock_client.paginate_objects.return_value = [
            {
                "Contents": [
                    {
                        "Key": "test/subdir/",
                        "Size": 0,
                        "ETag": '""',
                        "LastModified": datetime.now(timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                    {
                        "Key": "test/file.txt",
                        "Size": 1000,
                        "ETag": '"abc"',
                        "LastModified": datetime.now(timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                ]
            }
        ]

        location = S3Location(bucket="test-bucket", prefix="test/")
        result = list_objects(mock_client, location)

        assert len(result) == 1
        assert "file.txt" in result

    def test_list_objects_with_filters(self) -> None:
        """Test listing with include/exclude filters."""
        mock_client = Mock()
        mock_client.paginate_objects.return_value = [
            {
                "Contents": [
                    {
                        "Key": "test/file.txt",
                        "Size": 1000,
                        "ETag": '"abc"',
                        "LastModified": datetime.now(timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                    {
                        "Key": "test/file.log",
                        "Size": 2000,
                        "ETag": '"def"',
                        "LastModified": datetime.now(timezone.utc),
                        "StorageClass": "STANDARD",
                    },
                ]
            }
        ]

        location = S3Location(bucket="test-bucket", prefix="test/")
        # Use ** to match any path prefix, then *.log for the extension
        filters = FilterConfig(exclude_patterns=["**/*.log"])
        result = list_objects(mock_client, location, filters)

        assert len(result) == 1
        assert "file.txt" in result


class TestAnalyzeTransferNeeds:
    """Tests for analyze_transfer_needs function."""

    def _create_object(
        self,
        key: str,
        size: int = 1000,
        etag: str = "abc123",
        rel_path: str | None = None,
    ) -> S3Object:
        """Helper to create S3Object."""
        return S3Object(
            key=key,
            size=size,
            etag=etag,
            last_modified=datetime.now(timezone.utc),
            relative_path=rel_path or key,
        )

    def test_all_new_files(self) -> None:
        """Test when all files are new."""
        source_objects = {
            "file1.txt": self._create_object("prefix/file1.txt", rel_path="file1.txt"),
            "file2.txt": self._create_object("prefix/file2.txt", rel_path="file2.txt"),
        }
        dest_objects: dict = {}

        source_loc = S3Location(bucket="src", prefix="prefix/")
        dest_loc = S3Location(bucket="dst", prefix="dest/")

        analysis = analyze_transfer_needs(
            source_objects, dest_objects, source_loc, dest_loc
        )

        assert analysis.transfer_count == 2
        assert analysis.existing_count == 0
        assert analysis.new_count == 2
        assert analysis.update_count == 0

    def test_all_existing_files(self) -> None:
        """Test when all files already exist and are identical."""
        now = datetime.now(timezone.utc)
        source_objects = {
            "file.txt": S3Object(
                key="src/file.txt",
                size=1000,
                etag="abc123",
                last_modified=now,
                relative_path="file.txt",
            ),
        }
        dest_objects = {
            "file.txt": S3Object(
                key="dst/file.txt",
                size=1000,
                etag="abc123",
                last_modified=now,
                relative_path="file.txt",
            ),
        }

        source_loc = S3Location(bucket="src", prefix="src/")
        dest_loc = S3Location(bucket="dst", prefix="dst/")

        analysis = analyze_transfer_needs(
            source_objects, dest_objects, source_loc, dest_loc
        )

        assert analysis.transfer_count == 0
        assert analysis.existing_count == 1

    def test_updated_file_different_etag(self) -> None:
        """Test file that needs update due to different ETag."""
        now = datetime.now(timezone.utc)
        source_objects = {
            "file.txt": S3Object(
                key="src/file.txt",
                size=1000,
                etag="newetag123",  # No dash to avoid multipart detection
                last_modified=now,
                relative_path="file.txt",
            ),
        }
        dest_objects = {
            "file.txt": S3Object(
                key="dst/file.txt",
                size=1000,
                etag="oldetag456",  # No dash to avoid multipart detection
                last_modified=now,
                relative_path="file.txt",
            ),
        }

        source_loc = S3Location(bucket="src", prefix="src/")
        dest_loc = S3Location(bucket="dst", prefix="dst/")

        analysis = analyze_transfer_needs(
            source_objects, dest_objects, source_loc, dest_loc
        )

        assert analysis.transfer_count == 1
        assert analysis.update_count == 1
        assert analysis.to_transfer[0].status == TransferStatus.UPDATED

    def test_mixed_scenario(self) -> None:
        """Test with mix of new, existing, and updated files."""
        now = datetime.now(timezone.utc)
        source_objects = {
            "new.txt": S3Object(
                key="new.txt", size=100, etag="aaa111",
                last_modified=now, relative_path="new.txt",
            ),
            "existing.txt": S3Object(
                key="existing.txt", size=200, etag="bbb222",
                last_modified=now, relative_path="existing.txt",
            ),
            "updated.txt": S3Object(
                key="updated.txt", size=300, etag="cccnew333",  # No dash
                last_modified=now, relative_path="updated.txt",
            ),
        }
        dest_objects = {
            "existing.txt": S3Object(
                key="existing.txt", size=200, etag="bbb222",
                last_modified=now, relative_path="existing.txt",
            ),
            "updated.txt": S3Object(
                key="updated.txt", size=300, etag="cccold333",  # No dash, different
                last_modified=now, relative_path="updated.txt",
            ),
        }

        source_loc = S3Location(bucket="src", prefix="")
        dest_loc = S3Location(bucket="dst", prefix="")

        analysis = analyze_transfer_needs(
            source_objects, dest_objects, source_loc, dest_loc
        )

        assert analysis.transfer_count == 2
        assert analysis.existing_count == 1
        assert analysis.new_count == 1
        assert analysis.update_count == 1


class TestNeedsUpdate:
    """Tests for _needs_update function."""

    def _create_object(
        self,
        etag: str = "abc",
        size: int = 1000,
        last_modified: datetime | None = None,
    ) -> S3Object:
        """Helper to create S3Object."""
        return S3Object(
            key="file.txt",
            size=size,
            etag=etag,
            last_modified=last_modified or datetime.now(timezone.utc),
        )

    def test_identical_objects(self) -> None:
        """Test identical objects don't need update."""
        now = datetime.now(timezone.utc)
        source = self._create_object(etag="abc", last_modified=now)
        dest = self._create_object(etag="abc", last_modified=now)

        assert _needs_update(source, dest) is False

    def test_different_etag(self) -> None:
        """Test different ETag needs update."""
        now = datetime.now(timezone.utc)
        source = self._create_object(etag="new", last_modified=now)
        dest = self._create_object(etag="old", last_modified=now)

        assert _needs_update(source, dest) is True

    def test_newer_source(self) -> None:
        """Test newer source needs update."""
        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new = datetime(2024, 1, 2, tzinfo=timezone.utc)
        source = self._create_object(etag="abc", last_modified=new)
        dest = self._create_object(etag="abc", last_modified=old)

        assert _needs_update(source, dest) is True

    def test_multipart_same_size_older(self) -> None:
        """Test multipart objects with same size and older destination."""
        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new = datetime(2024, 1, 2, tzinfo=timezone.utc)
        # Multipart ETags contain '-'
        source = self._create_object(etag="abc-5", size=1000, last_modified=new)
        dest = self._create_object(etag="xyz-5", size=1000, last_modified=old)

        # Without strict checksums, uses size and timestamp
        assert _needs_update(source, dest, verify_checksums=False) is True

    def test_multipart_different_size(self) -> None:
        """Test multipart objects with different sizes."""
        now = datetime.now(timezone.utc)
        source = self._create_object(etag="abc-5", size=2000, last_modified=now)
        dest = self._create_object(etag="xyz-5", size=1000, last_modified=now)

        assert _needs_update(source, dest, verify_checksums=False) is True
