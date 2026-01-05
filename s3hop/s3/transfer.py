"""S3 transfer operations with parallel execution and retry logic.

This module provides the TransferManager class that handles:
- Parallel file transfers using ThreadPoolExecutor
- Automatic retry with exponential backoff
- Progress tracking and reporting
- Streaming transfers to minimize memory usage
"""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TYPE_CHECKING, Callable

import boto3.s3.transfer
from botocore.exceptions import ClientError

from ..config import TransferConfig
from ..exceptions import (
    DownloadError,
    RetryExhaustedError,
    TransferError,
    UploadError,
    is_retryable_error,
)
from ..models import (
    OperationResult,
    ProgressState,
    S3Location,
    TransferAnalysis,
    TransferItem,
    TransferResult,
    TransferStatus,
    TransferSummary,
)

if TYPE_CHECKING:
    from .client import S3ClientManager

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Thread-safe progress tracker for transfer operations."""

    def __init__(self, total_files: int, total_bytes: int) -> None:
        """Initialize the progress tracker.

        Args:
            total_files: Total number of files to process.
            total_bytes: Total bytes to transfer.
        """
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._total_files = total_files
        self._total_bytes = total_bytes
        self._processed_files = 0
        self._processed_bytes = 0
        self._skipped_files = 0
        self._skipped_bytes = 0
        self._failed_files = 0
        self._current_file = ""
        self._bytes_since_last_speed_calc = 0
        self._last_speed_calc_time = time.time()
        self._current_speed = 0.0

    def update_progress(
        self,
        bytes_transferred: int = 0,
        file_completed: bool = False,
        current_file: str | None = None,
    ) -> None:
        """Update transfer progress.

        Args:
            bytes_transferred: Additional bytes transferred.
            file_completed: Whether a file transfer completed.
            current_file: Name of the current file being transferred.
        """
        with self._lock:
            if bytes_transferred > 0:
                self._processed_bytes += bytes_transferred
                self._bytes_since_last_speed_calc += bytes_transferred

            if file_completed:
                self._processed_files += 1

            if current_file is not None:
                self._current_file = current_file

            # Update speed calculation every second
            now = time.time()
            elapsed_since_calc = now - self._last_speed_calc_time
            if elapsed_since_calc >= 1.0:
                self._current_speed = self._bytes_since_last_speed_calc / elapsed_since_calc
                self._bytes_since_last_speed_calc = 0
                self._last_speed_calc_time = now

    def mark_skipped(self, size: int) -> None:
        """Mark a file as skipped."""
        with self._lock:
            self._skipped_files += 1
            self._skipped_bytes += size
            self._processed_files += 1

    def mark_failed(self) -> None:
        """Mark a file as failed."""
        with self._lock:
            self._failed_files += 1
            self._processed_files += 1

    def get_state(self) -> ProgressState:
        """Get the current progress state."""
        with self._lock:
            elapsed = time.time() - self._start_time
            remaining_bytes = self._total_bytes - self._processed_bytes - self._skipped_bytes

            eta = 0.0
            if self._current_speed > 0:
                eta = remaining_bytes / self._current_speed

            return ProgressState(
                processed_files=self._processed_files,
                total_files=self._total_files,
                processed_bytes=self._processed_bytes,
                total_bytes=self._total_bytes,
                current_speed=self._current_speed,
                current_file=self._current_file,
                eta_seconds=eta,
                skipped_files=self._skipped_files,
                failed_files=self._failed_files,
            )


class TransferManager:
    """Manages parallel S3 transfers with retry logic and progress tracking."""

    def __init__(
        self,
        source_client: S3ClientManager,
        dest_client: S3ClientManager,
        config: TransferConfig | None = None,
    ) -> None:
        """Initialize the transfer manager.

        Args:
            source_client: S3 client for source bucket.
            dest_client: S3 client for destination bucket.
            config: Transfer configuration.
        """
        self._source_client = source_client
        self._dest_client = dest_client
        self._config = config or TransferConfig()
        self._cancelled = threading.Event()
        self._progress_tracker: ProgressTracker | None = None

    @property
    def progress(self) -> ProgressTracker | None:
        """Get the current progress tracker."""
        return self._progress_tracker

    def cancel(self) -> None:
        """Cancel the current transfer operation."""
        self._cancelled.set()
        logger.info("Transfer cancellation requested")

    def execute_transfer(
        self,
        analysis: TransferAnalysis,
        source_location: S3Location,
        dest_location: S3Location,
        progress_callback: Callable[[ProgressState], None] | None = None,
    ) -> TransferSummary:
        """Execute the transfer based on analysis results.

        Args:
            analysis: Transfer analysis with files to transfer.
            source_location: Source S3 location.
            dest_location: Destination S3 location.
            progress_callback: Optional callback for progress updates.

        Returns:
            TransferSummary with results.
        """
        start_time = datetime.now()
        self._cancelled.clear()

        # Initialize progress tracker
        total_files = analysis.transfer_count + analysis.existing_count
        self._progress_tracker = ProgressTracker(
            total_files=total_files,
            total_bytes=analysis.total_transfer_size + analysis.total_existing_size,
        )

        # Track results
        results: list[TransferResult] = []
        failed_results: list[TransferResult] = []
        extension_stats: dict[str, dict[str, int]] = {}

        # Mark existing files as skipped
        for item in analysis.existing:
            self._progress_tracker.mark_skipped(item.source.size)
            ext = item.source.extension
            if ext not in extension_stats:
                extension_stats[ext] = {"count": 0, "size": 0}
            extension_stats[ext]["count"] += 1
            extension_stats[ext]["size"] += item.source.size

        if self._config.dry_run:
            logger.info("Dry run mode - no files will be transferred")
            return self._create_dry_run_summary(
                analysis, start_time, extension_stats
            )

        # Execute parallel transfers
        if analysis.to_transfer:
            results, failed_results = self._execute_parallel_transfers(
                analysis.to_transfer,
                source_location,
                dest_location,
                progress_callback,
            )

            # Update extension stats
            for result in results:
                if result.success:
                    ext = result.source_key.rsplit(".", 1)[-1].lower() if "." in result.source_key else "no_extension"
                    if ext not in extension_stats:
                        extension_stats[ext] = {"count": 0, "size": 0}
                    extension_stats[ext]["count"] += 1
                    extension_stats[ext]["size"] += result.size

        end_time = datetime.now()

        # Calculate totals
        transferred_bytes = sum(r.size for r in results if r.success)
        transferred_files = sum(1 for r in results if r.success)

        return TransferSummary(
            start_time=start_time,
            end_time=end_time,
            total_files=total_files,
            transferred_files=transferred_files,
            skipped_files=analysis.existing_count,
            failed_files=len(failed_results),
            total_bytes=analysis.total_transfer_size + analysis.total_existing_size,
            transferred_bytes=transferred_bytes,
            skipped_bytes=analysis.total_existing_size,
            failed_transfers=failed_results,
            extension_stats=extension_stats,
        )

    def _execute_parallel_transfers(
        self,
        items: list[TransferItem],
        source_location: S3Location,
        dest_location: S3Location,
        progress_callback: Callable[[ProgressState], None] | None,
    ) -> tuple[list[TransferResult], list[TransferResult]]:
        """Execute transfers in parallel using ThreadPoolExecutor.

        Args:
            items: List of items to transfer.
            source_location: Source S3 location.
            dest_location: Destination S3 location.
            progress_callback: Optional progress callback.

        Returns:
            Tuple of (successful_results, failed_results).
        """
        results: list[TransferResult] = []
        failed_results: list[TransferResult] = []

        with ThreadPoolExecutor(max_workers=self._config.max_workers) as executor:
            # Submit all transfer tasks
            future_to_item = {
                executor.submit(
                    self._transfer_single_file,
                    item,
                    source_location,
                    dest_location,
                ): item
                for item in items
            }

            # Process completed transfers
            for future in as_completed(future_to_item):
                if self._cancelled.is_set():
                    logger.info("Transfer cancelled, stopping remaining tasks")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                item = future_to_item[future]
                try:
                    result = future.result()
                    results.append(result)

                    if not result.success:
                        failed_results.append(result)

                except Exception as e:
                    logger.error(f"Unexpected error transferring {item.source.key}: {e}")
                    result = TransferResult(
                        source_key=item.source.key,
                        dest_key=item.destination_key,
                        size=item.source.size,
                        success=False,
                        status=TransferStatus.FAILED,
                        error_message=str(e),
                    )
                    results.append(result)
                    failed_results.append(result)
                    if self._progress_tracker:
                        self._progress_tracker.mark_failed()

                # Update progress callback
                if progress_callback and self._progress_tracker:
                    progress_callback(self._progress_tracker.get_state())

        return results, failed_results

    def _transfer_single_file(
        self,
        item: TransferItem,
        source_location: S3Location,
        dest_location: S3Location,
    ) -> TransferResult:
        """Transfer a single file with retry logic.

        Args:
            item: Transfer item to process.
            source_location: Source S3 location.
            dest_location: Destination S3 location.

        Returns:
            TransferResult indicating success or failure.
        """
        start_time = time.time()
        last_error: Exception | None = None
        retries = 0

        if self._progress_tracker:
            self._progress_tracker.update_progress(current_file=item.source.key)

        for attempt in range(self._config.retry.max_retries + 1):
            if self._cancelled.is_set():
                return TransferResult(
                    source_key=item.source.key,
                    dest_key=item.destination_key,
                    size=item.source.size,
                    success=False,
                    status=TransferStatus.FAILED,
                    error_message="Transfer cancelled",
                )

            try:
                # Download from source
                response = self._source_client.get_object_stream(
                    source_location.bucket,
                    item.source.key,
                )

                # Create progress callback for this file
                def upload_callback(bytes_transferred: int) -> None:
                    if self._progress_tracker:
                        self._progress_tracker.update_progress(
                            bytes_transferred=bytes_transferred
                        )

                # Upload to destination
                self._upload_with_config(
                    response,
                    dest_location.bucket,
                    item.destination_key,
                    item.source.size,
                    upload_callback,
                )

                # Mark file as completed
                if self._progress_tracker:
                    self._progress_tracker.update_progress(file_completed=True)

                duration = time.time() - start_time
                logger.debug(
                    f"Transferred {item.source.key} -> {item.destination_key} "
                    f"({item.source.size} bytes in {duration:.2f}s)"
                )

                return TransferResult(
                    source_key=item.source.key,
                    dest_key=item.destination_key,
                    size=item.source.size,
                    success=True,
                    status=item.status,
                    duration_seconds=duration,
                    retries=retries,
                )

            except ClientError as e:
                last_error = e
                if is_retryable_error(e) and attempt < self._config.retry.max_retries:
                    retries += 1
                    delay = self._config.retry.get_delay(attempt)
                    logger.warning(
                        f"Retryable error for {item.source.key}, "
                        f"attempt {attempt + 1}/{self._config.retry.max_retries + 1}, "
                        f"waiting {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    break

            except Exception as e:
                last_error = e
                logger.error(f"Non-retryable error for {item.source.key}: {e}")
                break

        # All retries exhausted or non-retryable error
        if self._progress_tracker:
            self._progress_tracker.mark_failed()

        duration = time.time() - start_time
        error_msg = str(last_error) if last_error else "Unknown error"

        logger.error(
            f"Failed to transfer {item.source.key} after {retries} retries: {error_msg}"
        )

        return TransferResult(
            source_key=item.source.key,
            dest_key=item.destination_key,
            size=item.source.size,
            success=False,
            status=TransferStatus.FAILED,
            duration_seconds=duration,
            error_message=error_msg,
            retries=retries,
        )

    def _upload_with_config(
        self,
        source_response: dict,
        dest_bucket: str,
        dest_key: str,
        size: int,
        progress_callback: Callable[[int], None] | None = None,
    ) -> None:
        """Upload a file to S3 with optimized multipart configuration.

        Args:
            source_response: Response from get_object with streaming Body.
            dest_bucket: Destination bucket name.
            dest_key: Destination object key.
            size: Size of the file in bytes.
            progress_callback: Optional callback for progress updates.
        """
        mp_config = self._config.multipart
        chunk_size = mp_config.calculate_chunksize(size)

        transfer_config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=mp_config.threshold,
            max_concurrency=mp_config.max_concurrency,
            multipart_chunksize=chunk_size,
            use_threads=mp_config.use_threads,
        )

        self._dest_client.client.upload_fileobj(
            source_response["Body"],
            dest_bucket,
            dest_key,
            Config=transfer_config,
            Callback=progress_callback,
        )

    def _create_dry_run_summary(
        self,
        analysis: TransferAnalysis,
        start_time: datetime,
        extension_stats: dict[str, dict[str, int]],
    ) -> TransferSummary:
        """Create a summary for dry run mode."""
        return TransferSummary(
            start_time=start_time,
            end_time=datetime.now(),
            total_files=analysis.transfer_count + analysis.existing_count,
            transferred_files=0,
            skipped_files=analysis.existing_count + analysis.transfer_count,
            failed_files=0,
            total_bytes=analysis.total_transfer_size + analysis.total_existing_size,
            transferred_bytes=0,
            skipped_bytes=analysis.total_transfer_size + analysis.total_existing_size,
            extension_stats=extension_stats,
        )
