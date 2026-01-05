"""Tests for s3hop exceptions."""

import pytest
from botocore.exceptions import ClientError

from s3hop.exceptions import (
    AnalysisError,
    BucketAccessError,
    BucketNotFoundError,
    ConfigurationError,
    DownloadError,
    InvalidS3UrlError,
    ProfileNotFoundError,
    RetryExhaustedError,
    S3ConnectionError,
    S3HopError,
    TransferError,
    UploadError,
    is_retryable_error,
)


class TestS3HopError:
    """Tests for base S3HopError."""

    def test_message_only(self) -> None:
        """Test error with message only."""
        error = S3HopError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details is None

    def test_message_with_details(self) -> None:
        """Test error with message and details."""
        error = S3HopError("Test error", "Additional info")
        assert str(error) == "Test error: Additional info"
        assert error.message == "Test error"
        assert error.details == "Additional info"


class TestInvalidS3UrlError:
    """Tests for InvalidS3UrlError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = InvalidS3UrlError("bad-url")
        assert "bad-url" in str(error)
        assert "s3://bucket-name/prefix/" in str(error)
        assert error.url == "bad-url"


class TestProfileNotFoundError:
    """Tests for ProfileNotFoundError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = ProfileNotFoundError("missing-profile")
        assert "missing-profile" in str(error)
        assert error.profile_name == "missing-profile"


class TestBucketNotFoundError:
    """Tests for BucketNotFoundError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = BucketNotFoundError("my-bucket")
        assert "my-bucket" in str(error)
        assert error.bucket == "my-bucket"


class TestBucketAccessError:
    """Tests for BucketAccessError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = BucketAccessError("my-bucket", "list_objects")
        assert "my-bucket" in str(error)
        assert "list_objects" in str(error)
        assert error.bucket == "my-bucket"
        assert error.operation == "list_objects"


class TestTransferError:
    """Tests for TransferError."""

    def test_with_source_and_dest(self) -> None:
        """Test error with source and destination keys."""
        error = TransferError(
            "Transfer failed",
            source_key="source/file.txt",
            dest_key="dest/file.txt",
        )
        assert "source/file.txt" in str(error)
        assert "dest/file.txt" in str(error)
        assert error.source_key == "source/file.txt"
        assert error.dest_key == "dest/file.txt"


class TestDownloadError:
    """Tests for DownloadError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = DownloadError("path/to/file.txt")
        assert "download" in str(error).lower()
        assert error.source_key == "path/to/file.txt"


class TestUploadError:
    """Tests for UploadError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = UploadError("dest/file.txt", source_key="src/file.txt")
        assert "upload" in str(error).lower()
        assert error.dest_key == "dest/file.txt"
        assert error.source_key == "src/file.txt"


class TestRetryExhaustedError:
    """Tests for RetryExhaustedError."""

    def test_error_message(self) -> None:
        """Test error message formatting."""
        error = RetryExhaustedError(
            operation="upload",
            max_retries=5,
            source_key="file.txt",
        )
        assert "5" in str(error)
        assert "upload" in str(error)
        assert error.max_retries == 5
        assert error.operation == "upload"


class TestIsRetryableError:
    """Tests for is_retryable_error function."""

    def _create_client_error(
        self,
        error_code: str = "Unknown",
        http_status: int = 400,
    ) -> ClientError:
        """Helper to create ClientError."""
        return ClientError(
            error_response={
                "Error": {"Code": error_code, "Message": "Test error"},
                "ResponseMetadata": {"HTTPStatusCode": http_status},
            },
            operation_name="TestOperation",
        )

    def test_retryable_error_codes(self) -> None:
        """Test retryable error codes."""
        retryable_codes = [
            "InternalError",
            "ServiceUnavailable",
            "SlowDown",
            "RequestTimeout",
            "Throttling",
        ]

        for code in retryable_codes:
            error = self._create_client_error(error_code=code)
            assert is_retryable_error(error) is True, f"{code} should be retryable"

    def test_non_retryable_error_codes(self) -> None:
        """Test non-retryable error codes."""
        non_retryable_codes = [
            "AccessDenied",
            "NoSuchBucket",
            "InvalidBucketName",
            "InvalidAccessKeyId",
        ]

        for code in non_retryable_codes:
            error = self._create_client_error(error_code=code)
            assert is_retryable_error(error) is False, f"{code} should not be retryable"

    def test_retryable_http_status(self) -> None:
        """Test retryable HTTP status codes."""
        for status in [500, 502, 503, 504]:
            error = self._create_client_error(http_status=status)
            assert is_retryable_error(error) is True, f"HTTP {status} should be retryable"

    def test_non_retryable_http_status(self) -> None:
        """Test non-retryable HTTP status codes."""
        for status in [400, 401, 403, 404]:
            error = self._create_client_error(http_status=status)
            assert is_retryable_error(error) is False, f"HTTP {status} should not be retryable"
