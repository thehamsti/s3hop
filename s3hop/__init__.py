"""
s3hop - High-performance tool to copy files between S3 buckets across AWS accounts

Features:
- Parallel file transfers with configurable workers
- Automatic retry with exponential backoff
- Connection pooling for optimal performance
- Smart file comparison (ETag, size, modification time)
- Streaming transfers to minimize memory usage
- Support for S3 Transfer Acceleration
- Include/exclude file patterns
- Dry-run mode
- JSON output for scripting
"""

__version__ = "0.2.0"

# Re-export main classes for convenient imports
from .config import TransferConfig, parse_s3_url
from .exceptions import S3HopError, TransferError
from .models import S3Location, S3Object, TransferStatus, TransferSummary
from .service import TransferService, run_transfer

__all__ = [
    "__version__",
    "TransferConfig",
    "TransferService",
    "TransferStatus",
    "TransferSummary",
    "S3HopError",
    "TransferError",
    "S3Location",
    "S3Object",
    "parse_s3_url",
    "run_transfer",
]
