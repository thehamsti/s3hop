"""Custom exception hierarchy for s3hop.

This module provides a structured exception hierarchy for better error handling
and more informative error messages throughout the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from botocore.exceptions import ClientError


class S3HopError(Exception):
    """Base exception for all s3hop errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(self.format_message())

    def format_message(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ConfigurationError(S3HopError):
    """Raised when there's a configuration problem."""

    pass


class InvalidS3UrlError(ConfigurationError):
    """Raised when an S3 URL is malformed."""

    def __init__(self, url: str) -> None:
        super().__init__(
            "Invalid S3 URL format",
            f"'{url}' does not match expected format s3://bucket-name/prefix/",
        )
        self.url = url


class ProfileNotFoundError(ConfigurationError):
    """Raised when an AWS profile cannot be found."""

    def __init__(self, profile_name: str) -> None:
        super().__init__(
            "AWS profile not found",
            f"Profile '{profile_name}' is not configured in your AWS credentials",
        )
        self.profile_name = profile_name


class S3ConnectionError(S3HopError):
    """Raised when there's a connection problem with S3."""

    def __init__(
        self,
        message: str,
        bucket: str | None = None,
        region: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        details_parts = []
        if bucket:
            details_parts.append(f"bucket={bucket}")
        if region:
            details_parts.append(f"region={region}")
        if original_error:
            details_parts.append(f"error={original_error}")

        super().__init__(message, ", ".join(details_parts) if details_parts else None)
        self.bucket = bucket
        self.region = region
        self.original_error = original_error


class BucketAccessError(S3ConnectionError):
    """Raised when access to a bucket is denied."""

    def __init__(self, bucket: str, operation: str, original_error: Exception | None = None) -> None:
        super().__init__(
            f"Access denied for {operation} operation on bucket",
            bucket=bucket,
            original_error=original_error,
        )
        self.operation = operation


class BucketNotFoundError(S3ConnectionError):
    """Raised when a bucket does not exist."""

    def __init__(self, bucket: str) -> None:
        super().__init__(f"Bucket '{bucket}' does not exist", bucket=bucket)


class TransferError(S3HopError):
    """Base exception for transfer-related errors."""

    def __init__(
        self,
        message: str,
        source_key: str | None = None,
        dest_key: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        details_parts = []
        if source_key:
            details_parts.append(f"source={source_key}")
        if dest_key:
            details_parts.append(f"dest={dest_key}")
        if original_error:
            details_parts.append(f"error={original_error}")

        super().__init__(message, ", ".join(details_parts) if details_parts else None)
        self.source_key = source_key
        self.dest_key = dest_key
        self.original_error = original_error


class DownloadError(TransferError):
    """Raised when downloading an object fails."""

    def __init__(self, source_key: str, original_error: Exception | None = None) -> None:
        super().__init__(
            "Failed to download object",
            source_key=source_key,
            original_error=original_error,
        )


class UploadError(TransferError):
    """Raised when uploading an object fails."""

    def __init__(
        self,
        dest_key: str,
        source_key: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(
            "Failed to upload object",
            source_key=source_key,
            dest_key=dest_key,
            original_error=original_error,
        )


class RetryExhaustedError(TransferError):
    """Raised when all retry attempts have been exhausted."""

    def __init__(
        self,
        operation: str,
        max_retries: int,
        source_key: str | None = None,
        dest_key: str | None = None,
        last_error: Exception | None = None,
    ) -> None:
        super().__init__(
            f"Exhausted {max_retries} retries for {operation}",
            source_key=source_key,
            dest_key=dest_key,
            original_error=last_error,
        )
        self.operation = operation
        self.max_retries = max_retries
        self.last_error = last_error


class AnalysisError(S3HopError):
    """Raised when analyzing transfer needs fails."""

    pass


def is_retryable_error(error: ClientError) -> bool:
    """Determine if a boto3 ClientError is retryable.

    Args:
        error: The ClientError to check.

    Returns:
        True if the error is retryable, False otherwise.
    """
    retryable_error_codes = {
        "InternalError",
        "ServiceUnavailable",
        "SlowDown",
        "RequestTimeout",
        "RequestTimeoutException",
        "Throttling",
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
        "TransientError",
    }

    error_code = error.response.get("Error", {}).get("Code", "")
    http_status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)

    # Retry on specific error codes
    if error_code in retryable_error_codes:
        return True

    # Retry on 5xx HTTP status codes
    if 500 <= http_status < 600:
        return True

    return False
