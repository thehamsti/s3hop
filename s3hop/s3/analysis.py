"""S3 object listing and transfer analysis.

This module provides functions for listing S3 objects and analyzing
what needs to be transferred between source and destination.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from ..config import FilterConfig, TransferConfig, get_relative_path
from ..models import S3Location, S3Object, TransferAnalysis, TransferItem, TransferStatus

if TYPE_CHECKING:
    from .client import S3ClientManager

logger = logging.getLogger(__name__)


def list_objects(
    client: S3ClientManager,
    location: S3Location,
    filters: FilterConfig | None = None,
) -> dict[str, S3Object]:
    """List all objects at an S3 location.

    Args:
        client: S3 client manager to use.
        location: S3 bucket and prefix location.
        filters: Optional filter configuration for include/exclude patterns.

    Returns:
        Dictionary mapping relative paths to S3Object instances.
    """
    objects: dict[str, S3Object] = {}
    filters = filters or FilterConfig()

    logger.debug(f"Listing objects in {location}")

    for page in client.paginate_objects(location.bucket, location.prefix):
        if "Contents" not in page:
            continue

        for obj in page["Contents"]:
            key = obj["Key"]

            # Skip directory markers
            if key.endswith("/"):
                continue

            # Apply filters
            if not filters.should_include(key):
                logger.debug(f"Filtered out: {key}")
                continue

            rel_path = get_relative_path(key, location.prefix)

            objects[rel_path] = S3Object(
                key=key,
                size=obj["Size"],
                etag=obj["ETag"],
                last_modified=obj["LastModified"],
                relative_path=rel_path,
                storage_class=obj.get("StorageClass", "STANDARD"),
            )

    logger.info(f"Found {len(objects)} objects in {location}")
    return objects


def list_objects_parallel(
    source_client: S3ClientManager,
    dest_client: S3ClientManager,
    source_location: S3Location,
    dest_location: S3Location,
    config: TransferConfig | None = None,
) -> tuple[dict[str, S3Object], dict[str, S3Object]]:
    """List objects from source and destination in parallel.

    Args:
        source_client: Client for source bucket.
        dest_client: Client for destination bucket.
        source_location: Source S3 location.
        dest_location: Destination S3 location.
        config: Transfer configuration with filter settings.

    Returns:
        Tuple of (source_objects, dest_objects) dictionaries.
    """
    config = config or TransferConfig()
    filters = config.filters

    with ThreadPoolExecutor(max_workers=2) as executor:
        source_future = executor.submit(list_objects, source_client, source_location, filters)
        dest_future = executor.submit(list_objects, dest_client, dest_location, filters)

        source_objects = source_future.result()
        dest_objects = dest_future.result()

    return source_objects, dest_objects


def analyze_transfer_needs(
    source_objects: dict[str, S3Object],
    dest_objects: dict[str, S3Object],
    source_location: S3Location,
    dest_location: S3Location,
    verify_checksums: bool = False,
) -> TransferAnalysis:
    """Analyze which files need to be transferred.

    Compares source and destination objects to determine:
    - New files that don't exist in destination
    - Updated files that have changed (different ETag or newer)
    - Existing files that are identical

    Args:
        source_objects: Objects in source bucket (by relative path).
        dest_objects: Objects in destination bucket (by relative path).
        source_location: Source S3 location.
        dest_location: Destination S3 location.
        verify_checksums: If True, use stricter checksum comparison.

    Returns:
        TransferAnalysis with categorized files.
    """
    analysis = TransferAnalysis(
        source_count=len(source_objects),
        dest_count=len(dest_objects),
    )

    for rel_path, source_obj in source_objects.items():
        # Calculate destination key
        dest_key = f"{dest_location.prefix}{rel_path}" if dest_location.prefix else rel_path

        if rel_path in dest_objects:
            dest_obj = dest_objects[rel_path]

            # Check if file needs update
            needs_update = _needs_update(source_obj, dest_obj, verify_checksums)

            if needs_update:
                item = TransferItem(
                    source=source_obj,
                    destination_key=dest_key,
                    status=TransferStatus.UPDATED,
                    source_bucket=source_location.bucket,
                    dest_bucket=dest_location.bucket,
                )
                analysis.to_transfer.append(item)
                analysis.total_transfer_size += source_obj.size
            else:
                item = TransferItem(
                    source=source_obj,
                    destination_key=dest_key,
                    status=TransferStatus.EXISTING,
                    source_bucket=source_location.bucket,
                    dest_bucket=dest_location.bucket,
                )
                analysis.existing.append(item)
                analysis.total_existing_size += source_obj.size
        else:
            # New file
            item = TransferItem(
                source=source_obj,
                destination_key=dest_key,
                status=TransferStatus.NEW,
                source_bucket=source_location.bucket,
                dest_bucket=dest_location.bucket,
            )
            analysis.to_transfer.append(item)
            analysis.total_transfer_size += source_obj.size

    logger.info(
        f"Analysis complete: {analysis.transfer_count} to transfer, "
        f"{analysis.existing_count} existing"
    )

    return analysis


def _needs_update(
    source: S3Object,
    dest: S3Object,
    verify_checksums: bool = False,
) -> bool:
    """Determine if a destination file needs to be updated.

    Args:
        source: Source S3 object.
        dest: Destination S3 object.
        verify_checksums: If True, require matching ETags.

    Returns:
        True if the destination needs to be updated.
    """
    # If either object is multipart, ETag comparison is unreliable
    # unless we do a full checksum comparison
    if source.is_multipart or dest.is_multipart:
        if verify_checksums:
            # For strict verification, different ETags mean update needed
            return source.etag != dest.etag
        else:
            # For lenient comparison, use size and modification time
            if source.size != dest.size:
                return True
            return source.last_modified > dest.last_modified

    # For non-multipart objects, ETags are MD5 and reliable
    if source.etag != dest.etag:
        return True

    # ETag matches, but check if source is newer (could be re-uploaded)
    if source.last_modified > dest.last_modified:
        return True

    return False


def find_orphaned_files(
    source_objects: dict[str, S3Object],
    dest_objects: dict[str, S3Object],
    dest_location: S3Location,
) -> list[S3Object]:
    """Find files in destination that don't exist in source.

    These are candidates for deletion when using --delete flag.

    Args:
        source_objects: Objects in source bucket.
        dest_objects: Objects in destination bucket.
        dest_location: Destination S3 location.

    Returns:
        List of S3Objects that exist in destination but not in source.
    """
    orphaned = []

    for rel_path, dest_obj in dest_objects.items():
        if rel_path not in source_objects:
            orphaned.append(dest_obj)

    if orphaned:
        logger.info(f"Found {len(orphaned)} orphaned files in destination")

    return orphaned
