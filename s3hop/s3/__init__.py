"""S3 operations subpackage.

This package provides S3 client management, object analysis, and transfer operations.
"""

from .analysis import analyze_transfer_needs, list_objects, list_objects_parallel
from .client import S3ClientManager
from .transfer import TransferManager

__all__ = [
    "S3ClientManager",
    "TransferManager",
    "analyze_transfer_needs",
    "list_objects",
    "list_objects_parallel",
]
