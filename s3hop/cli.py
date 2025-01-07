#!/usr/bin/env python3

import argparse
import sys

from . import core


def main():
    parser = argparse.ArgumentParser(
        description="Copy files between S3 buckets across AWS accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s source-profile s3://source-bucket/prefix/ dest-profile s3://dest-bucket/prefix/
  %(prog)s prod s3://prod-bucket/data/ staging s3://staging-bucket/backup/
        """,
    )

    parser.add_argument("source_profile", help="AWS profile for source account")
    parser.add_argument("source_url", help="Source S3 URL (s3://bucket-name/prefix/)")
    parser.add_argument("dest_profile", help="AWS profile for destination account")
    parser.add_argument(
        "dest_url", help="Destination S3 URL (s3://bucket-name/prefix/)"
    )

    args = parser.parse_args()

    try:
        core.copy_bucket(
            args.source_profile, args.source_url, args.dest_profile, args.dest_url
        )
    except ValueError as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
