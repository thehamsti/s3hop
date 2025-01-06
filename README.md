# Cross-account S3 Bucket Copying

This script efficiently copies all files from one S3 bucket to another across different AWS accounts using streaming to minimize memory usage.

## Prerequisites

1. Python 3.6 or higher
2. AWS credentials configured for both source and destination accounts
3. Required Python packages (install using `pip install -r requirements.txt`)

## AWS Credentials Setup

1. Configure AWS credentials for both accounts in `~/.aws/credentials`:

```ini
[source-profile]
aws_access_key_id = YOUR_SOURCE_ACCESS_KEY
aws_secret_access_key = YOUR_SOURCE_SECRET_KEY

[dest-profile]
aws_access_key_id = YOUR_DEST_ACCESS_KEY
aws_secret_access_key = YOUR_DEST_SECRET_KEY
```

## Usage

```bash
python copy_between_buckets.py <source_profile> <source_s3_url> <dest_profile> <dest_s3_url>
```

### Arguments:
- `source_profile`: AWS profile name for the source account
- `source_s3_url`: Source S3 URL in the format `s3://bucket-name/prefix/`
- `dest_profile`: AWS profile name for the destination account
- `dest_s3_url`: Destination S3 URL in the format `s3://bucket-name/prefix/`

### Examples:

Copy entire bucket:
```bash
python copy_between_buckets.py source-profile s3://my-source-bucket/ dest-profile s3://my-dest-bucket/
```

Copy from specific prefix:
```bash
python copy_between_buckets.py source-profile s3://my-source-bucket/data/2023/ dest-profile s3://my-dest-bucket/archive/
```

Copy to specific prefix:
```bash
python copy_between_buckets.py source-profile s3://saxion-uas2-de.k16.io/archive-zips/ dest-profile s3://my-dest-bucket/archive-zips/
```

## Features

- Supports S3 URLs with bucket names and prefixes
- Streams data directly between buckets to minimize memory usage
- Supports copying between different AWS accounts
- Shows progress and statistics during copying
- Handles errors gracefully
- Maintains directory structure when copying with prefixes
