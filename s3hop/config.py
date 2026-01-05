"""Configuration management for s3hop.

This module provides dataclasses for managing all configuration options
in a centralized, type-safe manner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Pattern

from .exceptions import InvalidS3UrlError
from .models import S3Location


# Size constants
KB = 1024
MB = 1024 * KB
GB = 1024 * MB

# Default configuration values
DEFAULT_MAX_WORKERS = 10
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_BACKOFF_BASE = 1.0
DEFAULT_RETRY_BACKOFF_MAX = 60.0
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 60
DEFAULT_MULTIPART_THRESHOLD = 8 * MB
DEFAULT_MULTIPART_CHUNKSIZE = 8 * MB
DEFAULT_MAX_CONCURRENCY = 10
DEFAULT_MAX_POOL_CONNECTIONS = 50
DEFAULT_REGION = "us-east-1"

# AWS S3 limits
MAX_PARTS = 10000
MIN_PART_SIZE = 5 * MB
MAX_PART_SIZE = 5 * GB
MAX_OBJECT_SIZE = 5 * 1024 * GB  # 5 TB


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base: float = DEFAULT_RETRY_BACKOFF_BASE
    backoff_max: float = DEFAULT_RETRY_BACKOFF_MAX
    jitter: bool = True

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt with exponential backoff.

        Args:
            attempt: The current retry attempt number (0-indexed).

        Returns:
            Delay in seconds before the next retry.
        """
        import random

        delay = min(self.backoff_base * (2**attempt), self.backoff_max)
        if self.jitter:
            delay = delay * (0.5 + random.random())
        return delay


@dataclass
class ConnectionConfig:
    """Configuration for S3 connections."""

    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT
    read_timeout: int = DEFAULT_READ_TIMEOUT
    max_pool_connections: int = DEFAULT_MAX_POOL_CONNECTIONS
    region: str = DEFAULT_REGION
    use_transfer_acceleration: bool = False

    def to_botocore_config(self) -> dict:
        """Convert to botocore Config parameters."""
        return {
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "max_pool_connections": self.max_pool_connections,
            "retries": {"max_attempts": 0},  # We handle retries ourselves
        }


@dataclass
class MultipartConfig:
    """Configuration for multipart uploads."""

    threshold: int = DEFAULT_MULTIPART_THRESHOLD
    chunksize: int = DEFAULT_MULTIPART_CHUNKSIZE
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    use_threads: bool = True

    def calculate_chunksize(self, file_size: int) -> int:
        """Calculate optimal chunk size for a given file size.

        Uses the file size to determine the best chunk size while staying
        within AWS S3 limits (max 10,000 parts).

        Args:
            file_size: Size of the file in bytes.

        Returns:
            Optimal chunk size in bytes.
        """
        if file_size <= self.threshold:
            return self.chunksize

        # Calculate minimum chunk size needed to stay within 10,000 parts
        min_chunk_for_parts = (file_size // MAX_PARTS) + 1

        # Use the larger of our configured chunk size or the minimum required
        optimal_chunk = max(self.chunksize, min_chunk_for_parts)

        # Ensure we're within AWS limits
        return max(MIN_PART_SIZE, min(optimal_chunk, MAX_PART_SIZE))


@dataclass
class FilterConfig:
    """Configuration for file filtering."""

    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    _include_compiled: list[Pattern] = field(default_factory=list, repr=False)
    _exclude_compiled: list[Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Compile regex patterns."""
        self._include_compiled = [
            re.compile(self._glob_to_regex(p)) for p in self.include_patterns
        ]
        self._exclude_compiled = [
            re.compile(self._glob_to_regex(p)) for p in self.exclude_patterns
        ]

    @staticmethod
    def _glob_to_regex(pattern: str) -> str:
        """Convert a glob pattern to regex."""
        # First, handle **/ pattern specially (zero or more directories)
        pattern = pattern.replace("**/", "\x00DOUBLESTARSLASH\x00")
        # Then handle remaining ** (at end or standalone)
        pattern = pattern.replace("**", "\x00DOUBLESTAR\x00")
        # Escape special regex characters except * and ?
        pattern = re.escape(pattern)
        # Convert glob wildcards to regex (in correct order)
        # Restore **/ placeholder - matches zero or more directories
        pattern = pattern.replace("\x00DOUBLESTARSLASH\x00", "(.*/)?")
        # Restore ** placeholder - matches anything
        pattern = pattern.replace("\x00DOUBLESTAR\x00", ".*")
        # Convert single * to match anything except /
        pattern = pattern.replace(r"\*", "[^/]*")
        # Convert ? to match single character
        pattern = pattern.replace(r"\?", ".")
        return f"^{pattern}$"

    def should_include(self, key: str) -> bool:
        """Check if a key should be included based on filter patterns.

        Args:
            key: The S3 object key to check.

        Returns:
            True if the key should be included, False otherwise.
        """
        # If no include patterns, include everything
        if not self._include_compiled:
            include = True
        else:
            include = any(p.match(key) for p in self._include_compiled)

        # Check exclusions
        if include and self._exclude_compiled:
            if any(p.match(key) for p in self._exclude_compiled):
                return False

        return include


@dataclass
class TransferConfig:
    """Main configuration for transfer operations."""

    # Parallelism
    max_workers: int = DEFAULT_MAX_WORKERS

    # Retry settings
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Connection settings
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)

    # Multipart settings
    multipart: MultipartConfig = field(default_factory=MultipartConfig)

    # Filter settings
    filters: FilterConfig = field(default_factory=FilterConfig)

    # Behavior flags
    dry_run: bool = False
    delete_orphaned: bool = False
    verify_checksums: bool = False
    preserve_acl: bool = False

    # Output settings
    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    log_file: str | None = None

    # Source/destination regions (override connection.region if set)
    source_region: str | None = None
    dest_region: str | None = None

    def get_source_region(self) -> str:
        """Get the region for the source bucket."""
        return self.source_region or self.connection.region

    def get_dest_region(self) -> str:
        """Get the region for the destination bucket."""
        return self.dest_region or self.connection.region


def parse_s3_url(s3_url: str) -> S3Location:
    """Parse an S3 URL into bucket and prefix components.

    Args:
        s3_url: S3 URL in the format s3://bucket-name/prefix/

    Returns:
        S3Location with bucket and prefix.

    Raises:
        InvalidS3UrlError: If the URL format is invalid.
    """
    match = re.match(r"s3://([^/]+)/?(.*)$", s3_url)
    if not match:
        raise InvalidS3UrlError(s3_url)

    bucket = match.group(1)
    prefix = match.group(2)

    # Ensure prefix ends with '/' if it's not empty
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    return S3Location(bucket=bucket, prefix=prefix)


def get_relative_path(key: str, prefix: str) -> str:
    """Extract the relative path of a key by removing the prefix.

    Args:
        key: Full S3 object key.
        prefix: Prefix to remove.

    Returns:
        Relative path without the prefix.
    """
    if prefix and key.startswith(prefix):
        key = key[len(prefix) :]
    return key.lstrip("/")
