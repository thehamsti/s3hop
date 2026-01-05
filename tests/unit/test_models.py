"""Tests for s3hop models."""

from datetime import datetime, timezone

import pytest

from s3hop.models import (
    OperationResult,
    ProgressState,
    S3Location,
    S3Object,
    TransferAnalysis,
    TransferItem,
    TransferResult,
    TransferStatus,
    TransferSummary,
)


class TestTransferStatus:
    """Tests for TransferStatus enum."""

    def test_status_values(self) -> None:
        """Test enum values."""
        assert TransferStatus.NEW.value == "new"
        assert TransferStatus.EXISTING.value == "existing"
        assert TransferStatus.UPDATED.value == "updated"
        assert TransferStatus.FAILED.value == "failed"
        assert TransferStatus.SKIPPED.value == "skipped"

    def test_status_str(self) -> None:
        """Test string representation."""
        assert str(TransferStatus.NEW) == "new"
        assert str(TransferStatus.UPDATED) == "updated"


class TestS3Location:
    """Tests for S3Location dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        loc = S3Location(bucket="my-bucket", prefix="my-prefix/")
        assert loc.bucket == "my-bucket"
        assert loc.prefix == "my-prefix/"

    def test_url_with_prefix(self) -> None:
        """Test URL generation with prefix."""
        loc = S3Location(bucket="my-bucket", prefix="path/to/")
        assert loc.url == "s3://my-bucket/path/to/"

    def test_url_without_prefix(self) -> None:
        """Test URL generation without prefix."""
        loc = S3Location(bucket="my-bucket", prefix="")
        assert loc.url == "s3://my-bucket/"

    def test_str(self) -> None:
        """Test string representation."""
        loc = S3Location(bucket="my-bucket", prefix="prefix/")
        assert str(loc) == "s3://my-bucket/prefix/"

    def test_immutability(self) -> None:
        """Test that S3Location is immutable."""
        loc = S3Location(bucket="bucket", prefix="prefix/")
        with pytest.raises(AttributeError):
            loc.bucket = "other"  # type: ignore


class TestS3Object:
    """Tests for S3Object dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        now = datetime.now(timezone.utc)
        obj = S3Object(
            key="path/to/file.txt",
            size=1024,
            etag="abc123",
            last_modified=now,
        )
        assert obj.key == "path/to/file.txt"
        assert obj.size == 1024
        assert obj.etag == "abc123"
        assert obj.last_modified == now

    def test_etag_normalization(self) -> None:
        """Test that quoted ETags are normalized."""
        obj = S3Object(
            key="file.txt",
            size=100,
            etag='"abc123"',
            last_modified=datetime.now(timezone.utc),
        )
        assert obj.etag == "abc123"

    def test_extension(self) -> None:
        """Test file extension extraction."""
        obj = S3Object(
            key="path/to/file.TXT",
            size=100,
            etag="abc",
            last_modified=datetime.now(timezone.utc),
        )
        assert obj.extension == "txt"

    def test_extension_no_extension(self) -> None:
        """Test extension for files without extension."""
        obj = S3Object(
            key="path/to/file",
            size=100,
            etag="abc",
            last_modified=datetime.now(timezone.utc),
        )
        assert obj.extension == "no_extension"

    def test_is_multipart(self) -> None:
        """Test multipart detection."""
        multipart = S3Object(
            key="file.txt",
            size=100,
            etag="abc123-5",
            last_modified=datetime.now(timezone.utc),
        )
        regular = S3Object(
            key="file.txt",
            size=100,
            etag="abc123",
            last_modified=datetime.now(timezone.utc),
        )
        assert multipart.is_multipart is True
        assert regular.is_multipart is False


class TestTransferItem:
    """Tests for TransferItem dataclass."""

    def test_needs_transfer_new(self) -> None:
        """Test needs_transfer for new files."""
        obj = S3Object(
            key="file.txt",
            size=100,
            etag="abc",
            last_modified=datetime.now(timezone.utc),
        )
        item = TransferItem(
            source=obj,
            destination_key="dest/file.txt",
            status=TransferStatus.NEW,
        )
        assert item.needs_transfer is True

    def test_needs_transfer_updated(self) -> None:
        """Test needs_transfer for updated files."""
        obj = S3Object(
            key="file.txt",
            size=100,
            etag="abc",
            last_modified=datetime.now(timezone.utc),
        )
        item = TransferItem(
            source=obj,
            destination_key="dest/file.txt",
            status=TransferStatus.UPDATED,
        )
        assert item.needs_transfer is True

    def test_needs_transfer_existing(self) -> None:
        """Test needs_transfer for existing files."""
        obj = S3Object(
            key="file.txt",
            size=100,
            etag="abc",
            last_modified=datetime.now(timezone.utc),
        )
        item = TransferItem(
            source=obj,
            destination_key="dest/file.txt",
            status=TransferStatus.EXISTING,
        )
        assert item.needs_transfer is False


class TestTransferResult:
    """Tests for TransferResult dataclass."""

    def test_speed_calculation(self) -> None:
        """Test speed calculation."""
        result = TransferResult(
            source_key="file.txt",
            dest_key="dest/file.txt",
            size=1000,
            success=True,
            status=TransferStatus.NEW,
            duration_seconds=2.0,
        )
        assert result.speed_bytes_per_sec == 500.0

    def test_speed_zero_duration(self) -> None:
        """Test speed calculation with zero duration."""
        result = TransferResult(
            source_key="file.txt",
            dest_key="dest/file.txt",
            size=1000,
            success=True,
            status=TransferStatus.NEW,
            duration_seconds=0.0,
        )
        assert result.speed_bytes_per_sec == 0.0


class TestTransferAnalysis:
    """Tests for TransferAnalysis dataclass."""

    def test_empty_analysis(self) -> None:
        """Test empty analysis."""
        analysis = TransferAnalysis()
        assert analysis.transfer_count == 0
        assert analysis.existing_count == 0
        assert analysis.new_count == 0
        assert analysis.update_count == 0

    def test_analysis_counts(self) -> None:
        """Test analysis count calculations."""
        obj1 = S3Object(
            key="file1.txt", size=100, etag="a",
            last_modified=datetime.now(timezone.utc),
        )
        obj2 = S3Object(
            key="file2.txt", size=200, etag="b",
            last_modified=datetime.now(timezone.utc),
        )
        obj3 = S3Object(
            key="file3.txt", size=300, etag="c",
            last_modified=datetime.now(timezone.utc),
        )

        analysis = TransferAnalysis(
            to_transfer=[
                TransferItem(source=obj1, destination_key="d1", status=TransferStatus.NEW),
                TransferItem(source=obj2, destination_key="d2", status=TransferStatus.UPDATED),
            ],
            existing=[
                TransferItem(source=obj3, destination_key="d3", status=TransferStatus.EXISTING),
            ],
            total_transfer_size=300,
            total_existing_size=300,
        )

        assert analysis.transfer_count == 2
        assert analysis.existing_count == 1
        assert analysis.new_count == 1
        assert analysis.update_count == 1


class TestTransferSummary:
    """Tests for TransferSummary dataclass."""

    def test_duration_calculation(self) -> None:
        """Test duration calculation."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 5, 0)

        summary = TransferSummary(
            start_time=start,
            end_time=end,
        )

        assert summary.duration_seconds == 300.0

    def test_average_speed(self) -> None:
        """Test average speed calculation."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 1, 0)  # 60 seconds

        summary = TransferSummary(
            start_time=start,
            end_time=end,
            transferred_bytes=6000,
        )

        assert summary.average_speed_bytes_per_sec == 100.0

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        summary = TransferSummary(
            start_time=datetime.now(),
            end_time=datetime.now(),
            transferred_files=9,
            failed_files=1,
        )

        assert summary.success_rate == 90.0

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        now = datetime.now()
        summary = TransferSummary(
            start_time=now,
            end_time=now,
            total_files=10,
            transferred_files=8,
            failed_files=2,
        )

        result = summary.to_dict()

        assert "start_time" in result
        assert "end_time" in result
        assert result["total_files"] == 10
        assert result["transferred_files"] == 8
        assert result["failed_files"] == 2


class TestProgressState:
    """Tests for ProgressState dataclass."""

    def test_percent_complete(self) -> None:
        """Test percentage calculation."""
        state = ProgressState(
            processed_bytes=500,
            total_bytes=1000,
        )
        assert state.percent_complete == 50.0

    def test_percent_complete_zero_total(self) -> None:
        """Test percentage with zero total."""
        state = ProgressState(
            processed_bytes=0,
            total_bytes=0,
        )
        assert state.percent_complete == 0.0

    def test_remaining_bytes(self) -> None:
        """Test remaining bytes calculation."""
        state = ProgressState(
            processed_bytes=300,
            total_bytes=1000,
        )
        assert state.remaining_bytes == 700
