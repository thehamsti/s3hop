# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-01-06

### Added
- Initial release
- Core functionality to copy files between S3 buckets
- Progress tracking with ETA and transfer speed
- Smart file comparison using ETags and timestamps
- Detailed transfer summary with file type statistics
- Command-line interface with AWS profile support
- Streaming transfer to handle large files efficiently
- Support for bucket prefixes
- Error handling and graceful interruption 