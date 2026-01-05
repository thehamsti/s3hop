"""Tests for s3hop configuration."""

import pytest

from s3hop.config import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_REGION,
    FilterConfig,
    MultipartConfig,
    RetryConfig,
    TransferConfig,
    get_relative_path,
    parse_s3_url,
    KB,
    MB,
    GB,
)
from s3hop.exceptions import InvalidS3UrlError
from s3hop.models import S3Location


class TestParseS3Url:
    """Tests for parse_s3_url function."""

    def test_with_prefix(self) -> None:
        """Test parsing URL with prefix."""
        result = parse_s3_url("s3://my-bucket/some/prefix/")
        assert result.bucket == "my-bucket"
        assert result.prefix == "some/prefix/"

    def test_without_prefix(self) -> None:
        """Test parsing URL without prefix."""
        result = parse_s3_url("s3://my-bucket")
        assert result.bucket == "my-bucket"
        assert result.prefix == ""

    def test_with_trailing_slash_only(self) -> None:
        """Test parsing URL with only trailing slash."""
        result = parse_s3_url("s3://my-bucket/")
        assert result.bucket == "my-bucket"
        assert result.prefix == ""

    def test_prefix_without_trailing_slash(self) -> None:
        """Test that prefix gets trailing slash added."""
        result = parse_s3_url("s3://my-bucket/prefix")
        assert result.prefix == "prefix/"

    def test_invalid_url(self) -> None:
        """Test invalid URL raises error."""
        with pytest.raises(InvalidS3UrlError):
            parse_s3_url("not-an-s3-url")

    def test_invalid_protocol(self) -> None:
        """Test wrong protocol raises error."""
        with pytest.raises(InvalidS3UrlError):
            parse_s3_url("http://my-bucket/prefix")

    def test_returns_s3_location(self) -> None:
        """Test return type is S3Location."""
        result = parse_s3_url("s3://bucket/prefix/")
        assert isinstance(result, S3Location)


class TestGetRelativePath:
    """Tests for get_relative_path function."""

    def test_with_prefix(self) -> None:
        """Test stripping prefix from path."""
        result = get_relative_path("prefix/path/to/file.txt", "prefix/")
        assert result == "path/to/file.txt"

    def test_without_prefix(self) -> None:
        """Test path without prefix."""
        result = get_relative_path("path/to/file.txt", "")
        assert result == "path/to/file.txt"

    def test_exact_prefix_match(self) -> None:
        """Test exact prefix match."""
        result = get_relative_path("prefix/file.txt", "prefix/")
        assert result == "file.txt"

    def test_strips_leading_slash(self) -> None:
        """Test leading slash is stripped."""
        result = get_relative_path("/file.txt", "")
        assert result == "file.txt"


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration."""
        config = RetryConfig()
        assert config.max_retries == 5
        assert config.backoff_base == 1.0
        assert config.jitter is True

    def test_get_delay_exponential(self) -> None:
        """Test exponential backoff calculation."""
        config = RetryConfig(jitter=False, backoff_base=1.0)

        assert config.get_delay(0) == 1.0
        assert config.get_delay(1) == 2.0
        assert config.get_delay(2) == 4.0
        assert config.get_delay(3) == 8.0

    def test_get_delay_max_cap(self) -> None:
        """Test delay is capped at maximum."""
        config = RetryConfig(jitter=False, backoff_base=1.0, backoff_max=10.0)

        assert config.get_delay(10) == 10.0

    def test_get_delay_with_jitter(self) -> None:
        """Test jitter adds randomness."""
        config = RetryConfig(jitter=True, backoff_base=1.0)

        # With jitter, delay should vary
        delays = [config.get_delay(0) for _ in range(10)]
        # All delays should be between 0.5 and 1.5 (base * (0.5 + random(0,1)))
        assert all(0.5 <= d <= 1.5 for d in delays)


class TestMultipartConfig:
    """Tests for MultipartConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration."""
        config = MultipartConfig()
        assert config.threshold == 8 * MB
        assert config.chunksize == 8 * MB
        assert config.max_concurrency == 10
        assert config.use_threads is True

    def test_calculate_chunksize_small_file(self) -> None:
        """Test chunk size for small files."""
        config = MultipartConfig(chunksize=8 * MB)
        # Small file should use default chunk size
        assert config.calculate_chunksize(1 * MB) == 8 * MB

    def test_calculate_chunksize_large_file(self) -> None:
        """Test chunk size for very large files."""
        config = MultipartConfig(chunksize=8 * MB)
        # 100 GB file needs larger chunks to stay under 10,000 parts
        file_size = 100 * GB
        chunk_size = config.calculate_chunksize(file_size)

        # Verify we won't exceed 10,000 parts
        num_parts = file_size // chunk_size + 1
        assert num_parts <= 10000

    def test_calculate_chunksize_minimum(self) -> None:
        """Test chunk size respects minimum."""
        config = MultipartConfig(chunksize=1 * MB)  # Below minimum
        chunk_size = config.calculate_chunksize(100 * MB)
        assert chunk_size >= 5 * MB  # AWS minimum


class TestFilterConfig:
    """Tests for FilterConfig dataclass."""

    def test_no_filters(self) -> None:
        """Test with no filters - includes everything."""
        config = FilterConfig()
        assert config.should_include("any/file.txt") is True
        assert config.should_include("another/file.json") is True

    def test_include_pattern(self) -> None:
        """Test include pattern."""
        config = FilterConfig(include_patterns=["*.txt"])
        assert config.should_include("file.txt") is True
        assert config.should_include("file.json") is False

    def test_exclude_pattern(self) -> None:
        """Test exclude pattern."""
        config = FilterConfig(exclude_patterns=["*.log"])
        assert config.should_include("file.txt") is True
        assert config.should_include("file.log") is False

    def test_include_and_exclude(self) -> None:
        """Test combined include and exclude."""
        config = FilterConfig(
            include_patterns=["*.txt"],
            exclude_patterns=["temp*"],
        )
        assert config.should_include("file.txt") is True
        assert config.should_include("temp.txt") is False  # Excluded
        assert config.should_include("file.json") is False  # Not included

    def test_glob_double_star(self) -> None:
        """Test ** glob pattern."""
        config = FilterConfig(include_patterns=["data/**/*.csv"])
        assert config.should_include("data/2024/01/report.csv") is True
        assert config.should_include("data/report.csv") is True
        assert config.should_include("other/report.csv") is False


class TestTransferConfig:
    """Tests for TransferConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration."""
        config = TransferConfig()
        assert config.max_workers == DEFAULT_MAX_WORKERS
        assert config.dry_run is False
        assert config.verbose is False
        assert config.quiet is False

    def test_get_source_region(self) -> None:
        """Test source region resolution."""
        # Without override
        config = TransferConfig()
        assert config.get_source_region() == DEFAULT_REGION

        # With override
        config = TransferConfig(source_region="eu-west-1")
        assert config.get_source_region() == "eu-west-1"

    def test_get_dest_region(self) -> None:
        """Test destination region resolution."""
        # Without override
        config = TransferConfig()
        assert config.get_dest_region() == DEFAULT_REGION

        # With override
        config = TransferConfig(dest_region="ap-south-1")
        assert config.get_dest_region() == "ap-south-1"
