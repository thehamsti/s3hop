#!/usr/bin/env python3

import os.path
import queue
import re
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime

import boto3
import humanize
from botocore.exceptions import ClientError
from tqdm import tqdm


class TransferStatus:
    NEW = "new"
    EXISTING = "existing"
    UPDATED = "updated"


class ProgressTracker:
    def __init__(self):
        self.start_time = time.time()
        self.total_files = 0
        self.total_size = 0
        self.processed_files = 0
        self.processed_size = 0
        self.current_speed = 0  # bytes per second
        self.failed_files = []
        self.extension_stats = defaultdict(lambda: {"count": 0, "size": 0})
        self.skipped_files = 0
        self.skipped_size = 0
        self.status_counts = {
            TransferStatus.NEW: 0,
            TransferStatus.EXISTING: 0,
            TransferStatus.UPDATED: 0,
        }
        self._lock = threading.Lock()

    def update(self, file_size):
        with self._lock:
            self.processed_files += 1
            self.processed_size += file_size
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                self.current_speed = self.processed_size / elapsed

    def add_total(self, count, size):
        with self._lock:
            self.total_files = count
            self.total_size = size

    def add_failed(self, key):
        with self._lock:
            self.failed_files.append(key)

    def add_skipped(self, size):
        with self._lock:
            self.skipped_files += 1
            self.skipped_size += size

    def update_status_count(self, status):
        with self._lock:
            self.status_counts[status] += 1

    def update_extension_stats(self, key, size):
        ext = key.split(".")[-1].lower() if "." in key else "no_extension"
        with self._lock:
            self.extension_stats[ext]["count"] += 1
            self.extension_stats[ext]["size"] += size

    def get_progress_stats(self):
        with self._lock:
            elapsed = time.time() - self.start_time
            remaining_size = self.total_size - self.processed_size - self.skipped_size
            eta_seconds = (
                remaining_size / self.current_speed if self.current_speed > 0 else 0
            )

            return {
                "processed": self.processed_files,
                "total": self.total_files,
                "processed_size": humanize.naturalsize(self.processed_size),
                "total_size": humanize.naturalsize(self.total_size),
                "speed": humanize.naturalsize(self.current_speed) + "/s",
                "elapsed": humanize.naturaldelta(elapsed),
                "eta": (
                    humanize.naturaldelta(eta_seconds)
                    if eta_seconds > 0
                    else "calculating..."
                ),
                "percent": (
                    ((self.processed_size + self.skipped_size) / self.total_size * 100)
                    if self.total_size > 0
                    else 0
                ),
                "skipped": self.skipped_files,
                "skipped_size": humanize.naturalsize(self.skipped_size),
            }


def parse_s3_url(s3_url):
    """
    Parse an S3 URL in the format s3://bucket-name/prefix/
    Returns tuple of (bucket_name, prefix)
    """
    match = re.match(r"s3://([^/]+)/?(.*)$", s3_url)
    if not match:
        raise ValueError(
            f"Invalid S3 URL format: {s3_url}. Expected format: s3://bucket-name/prefix/"
        )

    bucket = match.group(1)
    prefix = match.group(2)

    # Ensure prefix ends with '/' if it's not empty
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    return bucket, prefix


def create_s3_client(profile_name=None, region="us-east-1"):
    """Create an S3 client with the specified profile and region."""
    session = boto3.Session(profile_name=profile_name)
    return session.client("s3", region_name=region)


def get_relative_path(key, prefix):
    """Extract the relative path of a file, ignoring the prefix structure"""
    if prefix:
        # Remove the prefix if it exists
        if key.startswith(prefix):
            key = key[len(prefix) :]
    return key.lstrip("/")


def get_object_info(client, bucket, prefix):
    """Get information about objects in the bucket/prefix"""
    objects = {}
    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if "Contents" in page:
            for obj in page["Contents"]:
                key = obj["Key"]
                rel_path = get_relative_path(key, prefix)
                objects[rel_path] = {
                    "full_key": key,
                    "size": obj["Size"],
                    "etag": obj["ETag"].strip('"'),
                    "last_modified": obj["LastModified"],
                }

    return objects


def analyze_transfer_needs(source_objects, dest_objects):
    """
    Analyze which files need to be transferred by matching relative paths.
    Returns files to transfer and existing files.
    """
    to_transfer = {}
    existing = {}
    total_new_size = 0
    total_existing_size = 0

    # Compare files based on their relative paths
    for rel_path, source_info in source_objects.items():
        if rel_path in dest_objects:
            # File exists in destination (by relative path)
            dest_info = dest_objects[rel_path]
            if (
                source_info["etag"] != dest_info["etag"]
                or source_info["last_modified"] > dest_info["last_modified"]
            ):
                # File needs update
                to_transfer[source_info["full_key"]] = {
                    "size": source_info["size"],
                    "dest_key": dest_info["full_key"],
                    "status": TransferStatus.UPDATED,
                }
                total_new_size += source_info["size"]
            else:
                # File is identical
                existing[source_info["full_key"]] = {
                    "size": source_info["size"],
                    "dest_key": dest_info["full_key"],
                }
                total_existing_size += source_info["size"]
        else:
            # New file
            to_transfer[source_info["full_key"]] = {
                "size": source_info["size"],
                "dest_key": None,  # Will be calculated during transfer
                "status": TransferStatus.NEW,
            }
            total_new_size += source_info["size"]

    return to_transfer, existing, total_new_size, total_existing_size


def print_summary(tracker):
    """Print final summary of the transfer"""
    print("\n=== Transfer Summary ===")
    print(
        f"Start time: {datetime.fromtimestamp(tracker.start_time).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {humanize.naturaldelta(time.time() - tracker.start_time)}")

    print("\nTransfer Statistics:")
    print(f"  New files: {tracker.status_counts[TransferStatus.NEW]}")
    print(f"  Updated files: {tracker.status_counts[TransferStatus.UPDATED]}")
    print(
        f"  Skipped (already exist): {tracker.status_counts[TransferStatus.EXISTING]}"
    )
    print(f"  Failed transfers: {len(tracker.failed_files)}")

    print(f"\nTotal data processed:")
    print(f"  Transferred: {humanize.naturalsize(tracker.processed_size)}")
    print(f"  Skipped: {humanize.naturalsize(tracker.skipped_size)}")
    print(
        f"  Average speed: {humanize.naturalsize(tracker.processed_size/(time.time() - tracker.start_time))}/s"
    )

    if tracker.failed_files:
        print(f"\nFailed transfers ({len(tracker.failed_files)}):")
        for file in tracker.failed_files[:10]:
            print(f"  - {file}")
        if len(tracker.failed_files) > 10:
            print(f"  ... and {len(tracker.failed_files) - 10} more")

    print("\nFile type statistics:")
    sorted_stats = sorted(
        tracker.extension_stats.items(), key=lambda x: x[1]["size"], reverse=True
    )
    for ext, stats in sorted_stats[:10]:
        print(
            f"  .{ext}: {stats['count']} files, {humanize.naturalsize(stats['size'])}"
        )


def copy_bucket(source_profile, source_url, dest_profile, dest_url):
    """
    Copy all objects from source bucket to destination bucket using streaming.

    Args:
        source_profile (str): AWS profile for source account
        source_url (str): Source S3 URL (s3://bucket-name/prefix/)
        dest_profile (str): AWS profile for destination account
        dest_url (str): Destination S3 URL (s3://bucket-name/prefix/)
    """
    # Parse source and destination URLs
    source_bucket, source_prefix = parse_s3_url(source_url)
    dest_bucket, dest_prefix = parse_s3_url(dest_url)

    print(f"Source: bucket={source_bucket}, prefix={source_prefix}")
    print(f"Destination: bucket={dest_bucket}, prefix={dest_prefix}")

    source_client = create_s3_client(profile_name=source_profile)
    dest_client = create_s3_client(profile_name=dest_profile)

    # Initialize progress tracker
    tracker = ProgressTracker()

    # Get list of objects from both buckets with relative paths
    print("Analyzing source and destination buckets...")
    source_objects = get_object_info(source_client, source_bucket, source_prefix)
    dest_objects = get_object_info(dest_client, dest_bucket, dest_prefix)

    # Analyze what needs to be transferred
    to_transfer, existing, total_new_size, total_existing_size = analyze_transfer_needs(
        source_objects, dest_objects
    )

    print("\n=== Pre-transfer Analysis ===")
    print(f"Total files in source: {len(source_objects)}")
    print(
        f"Files already in destination: {len(existing)} ({humanize.naturalsize(total_existing_size)})"
    )
    print(
        f"Files to transfer: {len(to_transfer)} ({humanize.naturalsize(total_new_size)})"
    )

    if not to_transfer:
        print("\nAll files are already up to date in the destination bucket.")
        return

    # Update tracker with totals
    tracker.add_total(
        len(source_objects), sum(obj["size"] for obj in source_objects.values())
    )

    # Mark existing files as skipped
    for source_key, info in existing.items():
        tracker.add_skipped(info["size"])
        tracker.update_status_count(TransferStatus.EXISTING)
        tracker.update_extension_stats(source_key, info["size"])

    # Create progress bar for remaining transfers
    progress_bar = tqdm(
        total=total_new_size, unit="B", unit_scale=True, desc="Transferring", ncols=100
    )

    # Create status update thread
    def update_status():
        while True:
            time.sleep(1)
            stats = tracker.get_progress_stats()
            progress_bar.set_postfix(
                files=f"{stats['processed'] + stats['skipped']}/{stats['total']}",
                speed=stats["speed"],
                eta=stats["eta"],
            )

    status_thread = threading.Thread(target=update_status, daemon=True)
    status_thread.start()

    try:
        # Process files that need to be transferred
        for source_key, info in to_transfer.items():
            size = info["size"]

            # Calculate destination key
            if info["dest_key"]:
                # Use existing destination key for updates
                dest_key = info["dest_key"]
            else:
                # Calculate new destination key for new files
                rel_path = get_relative_path(source_key, source_prefix)
                dest_key = (
                    os.path.join(dest_prefix, rel_path) if dest_prefix else rel_path
                )

            try:
                source_response = source_client.get_object(
                    Bucket=source_bucket, Key=source_key
                )

                def upload_progress_callback(bytes_transferred):
                    progress_bar.update(bytes_transferred)

                dest_client.upload_fileobj(
                    source_response["Body"],
                    dest_bucket,
                    dest_key,
                    Callback=upload_progress_callback,
                )
                # Update progress
                tracker.update(size)
                tracker.update_extension_stats(source_key, size)
                tracker.update_status_count(info["status"])
                progress_bar.update(size)

            except ClientError as e:
                print(f"\nError copying {source_key}: {str(e)}", file=sys.stderr)
                tracker.add_failed(source_key)

        progress_bar.close()
        print_summary(tracker)

    except ClientError as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nTransfer interrupted by user")
        print_summary(tracker)
        sys.exit(1)
