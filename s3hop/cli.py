#!/usr/bin/env python3
"""Command-line interface for s3hop.

This module provides the CLI entry point with comprehensive options
for configuring transfer behavior.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from .config import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WORKERS,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_REGION,
    ConnectionConfig,
    FilterConfig,
    MultipartConfig,
    RetryConfig,
    TransferConfig,
)
from .exceptions import (
    BucketAccessError,
    BucketNotFoundError,
    ConfigurationError,
    InvalidS3UrlError,
    ProfileNotFoundError,
    S3HopError,
)
from .logging import setup_logging
from .service import TransferService


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all options."""
    parser = argparse.ArgumentParser(
        prog="s3hop",
        description="High-performance tool to copy files between S3 buckets across AWS accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  %(prog)s source-profile s3://source-bucket/prefix/ dest-profile s3://dest-bucket/prefix/

  # With parallel workers and dry-run
  %(prog)s prod s3://prod-bucket/data/ staging s3://staging-bucket/backup/ -w 20 --dry-run

  # With include/exclude filters
  %(prog)s src s3://src-bucket/ dst s3://dst-bucket/ --include "*.json" --exclude "temp/*"

  # Cross-region transfer with acceleration
  %(prog)s us-prod s3://us-bucket/ eu-prod s3://eu-bucket/ \\
      --source-region us-east-1 --dest-region eu-west-1 --transfer-acceleration

  # Verbose logging to file
  %(prog)s prod s3://prod/ staging s3://staging/ -v --log-file transfer.log
        """,
    )

    # Version
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Required positional arguments
    parser.add_argument(
        "source_profile",
        help="AWS profile name for source account",
    )
    parser.add_argument(
        "source_url",
        help="Source S3 URL (s3://bucket-name/prefix/)",
    )
    parser.add_argument(
        "dest_profile",
        help="AWS profile name for destination account",
    )
    parser.add_argument(
        "dest_url",
        help="Destination S3 URL (s3://bucket-name/prefix/)",
    )

    # Parallelism options
    parallel_group = parser.add_argument_group("Parallelism Options")
    parallel_group.add_argument(
        "-w", "--workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        metavar="N",
        help=f"Number of parallel transfer workers (default: {DEFAULT_MAX_WORKERS})",
    )

    # Retry options
    retry_group = parser.add_argument_group("Retry Options")
    retry_group.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        metavar="N",
        help=f"Maximum retry attempts for failed transfers (default: {DEFAULT_MAX_RETRIES})",
    )
    retry_group.add_argument(
        "--no-retry",
        action="store_true",
        help="Disable automatic retries",
    )

    # Region options
    region_group = parser.add_argument_group("Region Options")
    region_group.add_argument(
        "--region",
        default=DEFAULT_REGION,
        metavar="REGION",
        help=f"Default AWS region for both buckets (default: {DEFAULT_REGION})",
    )
    region_group.add_argument(
        "--source-region",
        metavar="REGION",
        help="AWS region for source bucket (overrides --region)",
    )
    region_group.add_argument(
        "--dest-region",
        metavar="REGION",
        help="AWS region for destination bucket (overrides --region)",
    )

    # Transfer options
    transfer_group = parser.add_argument_group("Transfer Options")
    transfer_group.add_argument(
        "--transfer-acceleration",
        action="store_true",
        help="Use S3 Transfer Acceleration for faster cross-region transfers",
    )
    transfer_group.add_argument(
        "--checksum",
        action="store_true",
        help="Use strict checksum verification for file comparison",
    )

    # Filter options
    filter_group = parser.add_argument_group("Filter Options")
    filter_group.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Only transfer files matching pattern (can be specified multiple times)",
    )
    filter_group.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Exclude files matching pattern (can be specified multiple times)",
    )

    # Timeout options
    timeout_group = parser.add_argument_group("Timeout Options")
    timeout_group.add_argument(
        "--connect-timeout",
        type=int,
        default=DEFAULT_CONNECT_TIMEOUT,
        metavar="SECONDS",
        help=f"Connection timeout in seconds (default: {DEFAULT_CONNECT_TIMEOUT})",
    )
    timeout_group.add_argument(
        "--read-timeout",
        type=int,
        default=DEFAULT_READ_TIMEOUT,
        metavar="SECONDS",
        help=f"Read timeout in seconds (default: {DEFAULT_READ_TIMEOUT})",
    )

    # Behavior options
    behavior_group = parser.add_argument_group("Behavior Options")
    behavior_group.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be transferred without actually transferring",
    )

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output with debug logging",
    )
    output_group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Output transfer summary as JSON",
    )
    output_group.add_argument(
        "--log-file",
        metavar="PATH",
        help="Write logs to file",
    )

    return parser


def build_config(args: argparse.Namespace) -> TransferConfig:
    """Build TransferConfig from parsed arguments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Configured TransferConfig instance.
    """
    # Retry config
    retry_config = RetryConfig(
        max_retries=0 if args.no_retry else args.max_retries,
    )

    # Connection config
    connection_config = ConnectionConfig(
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        region=args.region,
        use_transfer_acceleration=args.transfer_acceleration,
    )

    # Multipart config (using defaults)
    multipart_config = MultipartConfig()

    # Filter config
    filter_config = FilterConfig(
        include_patterns=args.include,
        exclude_patterns=args.exclude,
    )

    return TransferConfig(
        max_workers=args.workers,
        retry=retry_config,
        connection=connection_config,
        multipart=multipart_config,
        filters=filter_config,
        dry_run=args.dry_run,
        verify_checksums=args.checksum,
        verbose=args.verbose,
        quiet=args.quiet,
        json_output=args.json,
        log_file=args.log_file,
        source_region=args.source_region,
        dest_region=args.dest_region,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for s3hop CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Build configuration
    config = build_config(args)

    # Setup logging
    setup_logging(
        verbose=config.verbose,
        quiet=config.quiet,
        log_file=config.log_file,
    )

    try:
        # Create and run transfer service
        service = TransferService(config)
        summary = service.copy_bucket(
            args.source_profile,
            args.source_url,
            args.dest_profile,
            args.dest_url,
        )

        # Return exit code based on results
        if summary.failed_files > 0:
            return 1
        return 0

    except InvalidS3UrlError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except ProfileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "Hint: Check your AWS credentials file (~/.aws/credentials) "
            "or run 'aws configure --profile <name>'",
            file=sys.stderr,
        )
        return 1

    except BucketNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except BucketAccessError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "Hint: Check that the AWS profile has the necessary S3 permissions",
            file=sys.stderr,
        )
        return 1

    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    except S3HopError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if config.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
