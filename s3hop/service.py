"""Service layer for s3hop operations.

This module provides the main service class that orchestrates
all transfer operations, following the service layer pattern.
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import TYPE_CHECKING, Callable

from .config import TransferConfig, parse_s3_url
from .logging import setup_logging
from .models import ProgressState, S3Location, TransferSummary
from .progress import (
    ProgressDisplay,
    print_analysis,
    print_dry_run_info,
    print_summary,
)
from .s3 import S3ClientManager, TransferManager, analyze_transfer_needs, list_objects_parallel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TransferService:
    """High-level service for managing S3 bucket transfers.

    This class provides the main entry point for transfer operations,
    coordinating between the S3 clients, analysis, and transfer manager.
    """

    def __init__(self, config: TransferConfig | None = None) -> None:
        """Initialize the transfer service.

        Args:
            config: Transfer configuration.
        """
        self._config = config or TransferConfig()
        self._source_client: S3ClientManager | None = None
        self._dest_client: S3ClientManager | None = None
        self._transfer_manager: TransferManager | None = None
        self._cancelled = False

    def copy_bucket(
        self,
        source_profile: str,
        source_url: str,
        dest_profile: str,
        dest_url: str,
    ) -> TransferSummary:
        """Copy objects from source bucket to destination bucket.

        Args:
            source_profile: AWS profile for source account.
            source_url: Source S3 URL (s3://bucket-name/prefix/).
            dest_profile: AWS profile for destination account.
            dest_url: Destination S3 URL (s3://bucket-name/prefix/).

        Returns:
            TransferSummary with operation results.
        """
        # Setup signal handlers for graceful cancellation
        self._setup_signal_handlers()

        # Parse URLs
        source_location = parse_s3_url(source_url)
        dest_location = parse_s3_url(dest_url)

        logger.info(f"Source: {source_location}")
        logger.info(f"Destination: {dest_location}")

        if not self._config.quiet:
            print(f"Source: bucket={source_location.bucket}, prefix={source_location.prefix}")
            print(f"Destination: bucket={dest_location.bucket}, prefix={dest_location.prefix}")

        # Create S3 clients
        self._source_client = S3ClientManager(
            profile_name=source_profile,
            config=self._config,
            region=self._config.get_source_region(),
        )
        self._dest_client = S3ClientManager(
            profile_name=dest_profile,
            config=self._config,
            region=self._config.get_dest_region(),
        )

        try:
            # Validate bucket access
            logger.info("Validating bucket access...")
            self._source_client.validate_bucket_access(source_location.bucket)
            self._dest_client.validate_bucket_access(
                dest_location.bucket, write_access=True
            )

            # List objects from both buckets (in parallel)
            if not self._config.quiet:
                print("Analyzing source and destination buckets...")

            source_objects, dest_objects = list_objects_parallel(
                self._source_client,
                self._dest_client,
                source_location,
                dest_location,
                self._config,
            )

            # Analyze transfer needs
            analysis = analyze_transfer_needs(
                source_objects,
                dest_objects,
                source_location,
                dest_location,
                verify_checksums=self._config.verify_checksums,
            )

            # Print analysis
            if not self._config.quiet:
                print_analysis(analysis)

            # Check if there's anything to transfer
            if not analysis.to_transfer:
                if not self._config.quiet:
                    print("\nAll files are already up to date in the destination bucket.")
                return self._create_empty_summary(analysis)

            # Handle dry run
            if self._config.dry_run:
                print_dry_run_info(analysis)
                return self._create_empty_summary(analysis)

            # Execute transfer
            return self._execute_transfer(
                analysis,
                source_location,
                dest_location,
            )

        finally:
            # Cleanup clients
            if self._source_client:
                self._source_client.close()
            if self._dest_client:
                self._dest_client.close()

    def _execute_transfer(
        self,
        analysis,
        source_location: S3Location,
        dest_location: S3Location,
    ) -> TransferSummary:
        """Execute the transfer operation.

        Args:
            analysis: Transfer analysis.
            source_location: Source S3 location.
            dest_location: Destination S3 location.

        Returns:
            TransferSummary with results.
        """
        # Create transfer manager
        self._transfer_manager = TransferManager(
            self._source_client,
            self._dest_client,
            self._config,
        )

        # Create progress display
        progress_display = ProgressDisplay(
            total_bytes=analysis.total_transfer_size,
            total_files=analysis.transfer_count,
            quiet=self._config.quiet,
        )

        def progress_callback(state: ProgressState) -> None:
            progress_display.update(state)

        try:
            progress_display.start()

            # Execute transfer
            summary = self._transfer_manager.execute_transfer(
                analysis,
                source_location,
                dest_location,
                progress_callback=progress_callback,
            )

            progress_display.close()

            # Print summary
            if not self._config.quiet or self._config.json_output:
                print_summary(summary, json_output=self._config.json_output)

            return summary

        except KeyboardInterrupt:
            progress_display.close()
            if self._transfer_manager:
                self._transfer_manager.cancel()
            print("\nTransfer interrupted by user")

            # Still get a partial summary
            if self._transfer_manager and self._transfer_manager.progress:
                state = self._transfer_manager.progress.get_state()
                print(f"Transferred {state.processed_files} files before cancellation")

            sys.exit(1)

    def _create_empty_summary(self, analysis) -> TransferSummary:
        """Create an empty summary when no transfer is needed."""
        from datetime import datetime

        now = datetime.now()
        return TransferSummary(
            start_time=now,
            end_time=now,
            total_files=analysis.source_count,
            transferred_files=0,
            skipped_files=analysis.existing_count,
            failed_files=0,
            total_bytes=analysis.total_existing_size,
            transferred_bytes=0,
            skipped_bytes=analysis.total_existing_size,
        )

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):  # type: ignore[no-untyped-def]
            self._cancelled = True
            if self._transfer_manager:
                self._transfer_manager.cancel()
            print("\nReceived interrupt signal, cancelling transfer...")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


def run_transfer(
    source_profile: str,
    source_url: str,
    dest_profile: str,
    dest_url: str,
    config: TransferConfig | None = None,
) -> TransferSummary:
    """Convenience function to run a transfer operation.

    Args:
        source_profile: AWS profile for source account.
        source_url: Source S3 URL.
        dest_profile: AWS profile for destination account.
        dest_url: Destination S3 URL.
        config: Optional transfer configuration.

    Returns:
        TransferSummary with results.
    """
    service = TransferService(config)
    return service.copy_bucket(source_profile, source_url, dest_profile, dest_url)
