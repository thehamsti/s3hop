"""Progress display and reporting for s3hop.

This module provides progress bar display using tqdm and
summary printing functionality.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, TextIO

import humanize
from tqdm import tqdm

if TYPE_CHECKING:
    from .models import ProgressState, TransferAnalysis, TransferSummary


class ProgressDisplay:
    """Manages progress bar display for transfer operations."""

    def __init__(
        self,
        total_bytes: int,
        total_files: int,
        description: str = "Transferring",
        quiet: bool = False,
        stream: TextIO | None = None,
    ) -> None:
        """Initialize the progress display.

        Args:
            total_bytes: Total bytes to transfer.
            total_files: Total files to process.
            description: Description for the progress bar.
            quiet: If True, suppress progress output.
            stream: Output stream (default: stderr).
        """
        self._total_bytes = total_bytes
        self._total_files = total_files
        self._quiet = quiet
        self._stream = stream or sys.stderr

        self._progress_bar: tqdm | None = None
        self._status_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_state: ProgressState | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the progress display."""
        if self._quiet:
            return

        self._progress_bar = tqdm(
            total=self._total_bytes,
            unit="B",
            unit_scale=True,
            desc="Transferring",
            ncols=100,
            file=self._stream,
            leave=True,
        )

    def update(self, state: ProgressState) -> None:
        """Update the progress display with new state.

        Args:
            state: Current progress state.
        """
        if self._quiet or self._progress_bar is None:
            return

        with self._lock:
            self._last_state = state

            # Update progress bar
            current = state.processed_bytes
            if current > self._progress_bar.n:
                self._progress_bar.update(current - self._progress_bar.n)

            # Update postfix with stats
            self._progress_bar.set_postfix(
                files=f"{state.processed_files}/{state.total_files}",
                speed=humanize.naturalsize(state.current_speed) + "/s",
                eta=humanize.naturaldelta(state.eta_seconds) if state.eta_seconds > 0 else "...",
                failed=state.failed_files if state.failed_files > 0 else None,
            )

    def close(self) -> None:
        """Close the progress display."""
        self._stop_event.set()

        if self._status_thread and self._status_thread.is_alive():
            self._status_thread.join(timeout=2)

        if self._progress_bar:
            self._progress_bar.close()


def print_analysis(analysis: TransferAnalysis, stream: TextIO | None = None) -> None:
    """Print pre-transfer analysis results.

    Args:
        analysis: Transfer analysis to display.
        stream: Output stream (default: stdout).
    """
    stream = stream or sys.stdout

    print("\n=== Pre-transfer Analysis ===", file=stream)
    print(f"Total files in source: {analysis.source_count}", file=stream)
    print(
        f"Files already in destination: {analysis.existing_count} "
        f"({humanize.naturalsize(analysis.total_existing_size)})",
        file=stream,
    )
    print(
        f"Files to transfer: {analysis.transfer_count} "
        f"({humanize.naturalsize(analysis.total_transfer_size)})",
        file=stream,
    )

    if analysis.transfer_count > 0:
        print(f"  - New files: {analysis.new_count}", file=stream)
        print(f"  - Updated files: {analysis.update_count}", file=stream)


def print_summary(
    summary: TransferSummary,
    stream: TextIO | None = None,
    json_output: bool = False,
) -> None:
    """Print transfer summary.

    Args:
        summary: Transfer summary to display.
        stream: Output stream (default: stdout).
        json_output: If True, output as JSON.
    """
    stream = stream or sys.stdout

    if json_output:
        print(json.dumps(summary.to_dict(), indent=2), file=stream)
        return

    print("\n=== Transfer Summary ===", file=stream)
    print(f"Start time: {summary.start_time.strftime('%Y-%m-%d %H:%M:%S')}", file=stream)
    print(f"End time: {summary.end_time.strftime('%Y-%m-%d %H:%M:%S')}", file=stream)
    print(f"Duration: {humanize.naturaldelta(summary.duration_seconds)}", file=stream)

    print("\nTransfer Statistics:", file=stream)
    print(f"  Transferred: {summary.transferred_files} files", file=stream)
    print(f"  Skipped (already exist): {summary.skipped_files} files", file=stream)
    print(f"  Failed: {summary.failed_files} files", file=stream)

    print(f"\nData processed:", file=stream)
    print(f"  Transferred: {humanize.naturalsize(summary.transferred_bytes)}", file=stream)
    print(f"  Skipped: {humanize.naturalsize(summary.skipped_bytes)}", file=stream)
    if summary.duration_seconds > 0:
        print(
            f"  Average speed: {humanize.naturalsize(summary.average_speed_bytes_per_sec)}/s",
            file=stream,
        )

    if summary.failed_transfers:
        print(f"\nFailed transfers ({len(summary.failed_transfers)}):", file=stream)
        for result in summary.failed_transfers[:10]:
            print(f"  - {result.source_key}: {result.error_message}", file=stream)
        if len(summary.failed_transfers) > 10:
            print(f"  ... and {len(summary.failed_transfers) - 10} more", file=stream)

    if summary.extension_stats:
        print("\nFile type statistics:", file=stream)
        sorted_stats = sorted(
            summary.extension_stats.items(),
            key=lambda x: x[1]["size"],
            reverse=True,
        )
        for ext, stats in sorted_stats[:10]:
            print(
                f"  .{ext}: {stats['count']} files, "
                f"{humanize.naturalsize(stats['size'])}",
                file=stream,
            )


def print_dry_run_info(analysis: TransferAnalysis, stream: TextIO | None = None) -> None:
    """Print dry run information.

    Args:
        analysis: Transfer analysis.
        stream: Output stream (default: stdout).
    """
    stream = stream or sys.stdout

    print("\n=== Dry Run - No files will be transferred ===", file=stream)
    print(f"Would transfer {analysis.transfer_count} files", file=stream)
    print(f"Would skip {analysis.existing_count} existing files", file=stream)

    if analysis.to_transfer:
        print("\nFiles that would be transferred:", file=stream)
        for item in analysis.to_transfer[:20]:
            status_str = "NEW" if item.status.value == "new" else "UPDATE"
            print(
                f"  [{status_str}] {item.source.key} "
                f"({humanize.naturalsize(item.source.size)})",
                file=stream,
            )
        if len(analysis.to_transfer) > 20:
            print(f"  ... and {len(analysis.to_transfer) - 20} more", file=stream)
