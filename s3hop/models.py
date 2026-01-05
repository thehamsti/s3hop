"""Data models for s3hop using dataclasses and enums.

This module provides type-safe data structures for representing S3 objects,
transfer items, and operation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TransferStatus(Enum):
    """Status of a file in the transfer operation."""

    NEW = "new"
    EXISTING = "existing"
    UPDATED = "updated"
    FAILED = "failed"
    SKIPPED = "skipped"

    def __str__(self) -> str:
        return self.value


class OperationResult(Enum):
    """Result of a single transfer operation."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class S3Location:
    """Represents an S3 bucket and prefix location."""

    bucket: str
    prefix: str

    @property
    def url(self) -> str:
        """Get the S3 URL representation."""
        if self.prefix:
            return f"s3://{self.bucket}/{self.prefix}"
        return f"s3://{self.bucket}/"

    def __str__(self) -> str:
        return self.url


@dataclass
class S3Object:
    """Represents an object in S3 with its metadata."""

    key: str
    size: int
    etag: str
    last_modified: datetime
    relative_path: str = ""
    storage_class: str = "STANDARD"

    def __post_init__(self) -> None:
        # Normalize etag by removing quotes
        if self.etag.startswith('"') and self.etag.endswith('"'):
            object.__setattr__(self, "etag", self.etag[1:-1])

    @property
    def extension(self) -> str:
        """Get the file extension (lowercase)."""
        if "." in self.key:
            return self.key.rsplit(".", 1)[-1].lower()
        return "no_extension"

    @property
    def is_multipart(self) -> bool:
        """Check if this was uploaded as multipart (etag contains '-')."""
        return "-" in self.etag


@dataclass
class TransferItem:
    """Represents an item to be transferred."""

    source: S3Object
    destination_key: str
    status: TransferStatus
    source_bucket: str = ""
    dest_bucket: str = ""

    @property
    def needs_transfer(self) -> bool:
        """Check if this item needs to be transferred."""
        return self.status in (TransferStatus.NEW, TransferStatus.UPDATED)


@dataclass
class TransferResult:
    """Result of a single file transfer operation."""

    source_key: str
    dest_key: str
    size: int
    success: bool
    status: TransferStatus
    duration_seconds: float = 0.0
    error_message: str | None = None
    retries: int = 0

    @property
    def speed_bytes_per_sec(self) -> float:
        """Calculate transfer speed in bytes per second."""
        if self.duration_seconds > 0:
            return self.size / self.duration_seconds
        return 0.0


@dataclass
class TransferAnalysis:
    """Analysis of what needs to be transferred between source and destination."""

    to_transfer: list[TransferItem] = field(default_factory=list)
    existing: list[TransferItem] = field(default_factory=list)
    total_transfer_size: int = 0
    total_existing_size: int = 0
    source_count: int = 0
    dest_count: int = 0

    @property
    def transfer_count(self) -> int:
        """Number of files that need to be transferred."""
        return len(self.to_transfer)

    @property
    def existing_count(self) -> int:
        """Number of files that already exist and are up to date."""
        return len(self.existing)

    @property
    def new_count(self) -> int:
        """Number of new files to transfer."""
        return sum(1 for item in self.to_transfer if item.status == TransferStatus.NEW)

    @property
    def update_count(self) -> int:
        """Number of files that need to be updated."""
        return sum(1 for item in self.to_transfer if item.status == TransferStatus.UPDATED)


@dataclass
class TransferSummary:
    """Summary statistics for a completed transfer operation."""

    start_time: datetime
    end_time: datetime
    total_files: int = 0
    transferred_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    total_bytes: int = 0
    transferred_bytes: int = 0
    skipped_bytes: int = 0
    failed_transfers: list[TransferResult] = field(default_factory=list)
    extension_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Total duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()

    @property
    def average_speed_bytes_per_sec(self) -> float:
        """Average transfer speed in bytes per second."""
        if self.duration_seconds > 0:
            return self.transferred_bytes / self.duration_seconds
        return 0.0

    @property
    def success_rate(self) -> float:
        """Percentage of successful transfers."""
        total = self.transferred_files + self.failed_files
        if total > 0:
            return (self.transferred_files / total) * 100
        return 100.0

    def update_extension_stats(self, extension: str, size: int) -> None:
        """Update statistics for a file extension."""
        if extension not in self.extension_stats:
            self.extension_stats[extension] = {"count": 0, "size": 0}
        self.extension_stats[extension]["count"] += 1
        self.extension_stats[extension]["size"] += size

    def to_dict(self) -> dict[str, Any]:
        """Convert summary to dictionary for JSON serialization."""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "total_files": self.total_files,
            "transferred_files": self.transferred_files,
            "skipped_files": self.skipped_files,
            "failed_files": self.failed_files,
            "total_bytes": self.total_bytes,
            "transferred_bytes": self.transferred_bytes,
            "skipped_bytes": self.skipped_bytes,
            "average_speed_bytes_per_sec": self.average_speed_bytes_per_sec,
            "success_rate": self.success_rate,
            "extension_stats": self.extension_stats,
            "failed_transfer_keys": [t.source_key for t in self.failed_transfers],
        }


@dataclass
class ProgressState:
    """Current state of transfer progress for display."""

    processed_files: int = 0
    total_files: int = 0
    processed_bytes: int = 0
    total_bytes: int = 0
    current_speed: float = 0.0
    current_file: str = ""
    eta_seconds: float = 0.0
    skipped_files: int = 0
    failed_files: int = 0

    @property
    def percent_complete(self) -> float:
        """Percentage of transfer complete by bytes."""
        if self.total_bytes > 0:
            return (self.processed_bytes / self.total_bytes) * 100
        return 0.0

    @property
    def remaining_bytes(self) -> int:
        """Bytes remaining to transfer."""
        return max(0, self.total_bytes - self.processed_bytes)
