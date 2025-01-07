# s3hop - Cross-account S3 bucket streaming copy

[![PyPI version](https://badge.fury.io/py/s3hop.svg)](https://badge.fury.io/py/s3hop)
[![Python Versions](https://img.shields.io/pypi/pyversions/s3hop.svg)](https://pypi.org/project/s3hop/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://pepy.tech/badge/s3hop)](https://pepy.tech/project/s3hop)

A command-line tool to efficiently copy files between S3 buckets across different AWS accounts.

## Features

- Copy files between S3 buckets across different AWS accounts
- Smart file comparison to only copy new or updated files
- Progress tracking with ETA and transfer speed
- Detailed transfer summary with file type statistics
- Handles large files and directories efficiently using streaming
- Preserves file structure between source and destination

## Quick Start

```bash
# Install
pip install s3hop

# Use
s3hop source-profile s3://source-bucket/prefix/ dest-profile s3://dest-bucket/prefix/
```

## Installation

You can install this package directly from PyPI:

```bash
pip install s3hop
```

Or install from source:

```bash
git clone https://github.com/thehamsti/s3hop.git
cd s3hop
pip install .
```

## Prerequisites

1. Python 3.6 or later
2. AWS credentials configured for both source and destination accounts
3. Appropriate S3 permissions in both accounts

### AWS Credentials Setup

1. Configure your AWS credentials for both accounts in `~/.aws/credentials`:

```ini
[source-profile]
aws_access_key_id = YOUR_SOURCE_ACCESS_KEY
aws_secret_access_key = YOUR_SOURCE_SECRET_KEY

[dest-profile]
aws_access_key_id = YOUR_DEST_ACCESS_KEY
aws_secret_access_key = YOUR_DEST_SECRET_KEY
```

2. Ensure you have the necessary S3 permissions:
   - Source bucket: `s3:ListBucket`, `s3:GetObject`
   - Destination bucket: `s3:ListBucket`, `s3:PutObject`

## Usage

Basic usage:

```bash
s3hop source-profile s3://source-bucket/prefix/ dest-profile s3://dest-bucket/prefix/
```

Example with specific profiles and paths:

```bash
s3hop prod s3://prod-bucket/data/ staging s3://staging-bucket/backup/
```

### Arguments

- `source-profile`: AWS profile for the source account
- `source_url`: Source S3 URL (s3://bucket-name/prefix/)
- `dest-profile`: AWS profile for the destination account
- `dest_url`: Destination S3 URL (s3://bucket-name/prefix/)

## Features in Detail

1. **Smart File Comparison**

   - Compares files using ETags and last modified timestamps
   - Only copies new or updated files
   - Preserves existing files that haven't changed

2. **Progress Tracking**

   - Real-time transfer speed
   - Estimated time remaining
   - Progress bar with file counts
   - Total data transferred/remaining

3. **Transfer Summary**
   - Start and end times
   - Duration
   - Number of files transferred/skipped
   - File type statistics
   - Failed transfers (if any)

## Development

For development setup and contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes and version history.

## Security

For security issues, please email security@hamsti.co instead of using the issue tracker.

## Support

- 📫 Email: john@hamsti.co
- 🐛 Issues: [GitHub Issues](https://github.com/thehamsti/s3hop/issues)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Built with [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- Progress bars powered by [tqdm](https://github.com/tqdm/tqdm)
