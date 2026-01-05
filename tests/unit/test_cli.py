"""Tests for s3hop CLI."""

from unittest.mock import Mock, patch

import pytest

from s3hop.cli import build_config, create_parser, main
from s3hop.config import DEFAULT_MAX_RETRIES, DEFAULT_MAX_WORKERS, DEFAULT_REGION


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_creation(self) -> None:
        """Test parser is created successfully."""
        parser = create_parser()
        assert parser is not None

    def test_required_arguments(self) -> None:
        """Test required arguments are parsed correctly."""
        parser = create_parser()
        args = parser.parse_args([
            "source-profile",
            "s3://source-bucket/",
            "dest-profile",
            "s3://dest-bucket/",
        ])

        assert args.source_profile == "source-profile"
        assert args.source_url == "s3://source-bucket/"
        assert args.dest_profile == "dest-profile"
        assert args.dest_url == "s3://dest-bucket/"

    def test_missing_arguments(self) -> None:
        """Test missing arguments raise error."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_workers_option(self) -> None:
        """Test --workers option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--workers", "20",
        ])
        assert args.workers == 20

    def test_workers_short_option(self) -> None:
        """Test -w option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "-w", "15",
        ])
        assert args.workers == 15

    def test_dry_run_option(self) -> None:
        """Test --dry-run option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--dry-run",
        ])
        assert args.dry_run is True

    def test_dry_run_short_option(self) -> None:
        """Test -n option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "-n",
        ])
        assert args.dry_run is True

    def test_verbose_option(self) -> None:
        """Test --verbose option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--verbose",
        ])
        assert args.verbose is True

    def test_quiet_option(self) -> None:
        """Test --quiet option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--quiet",
        ])
        assert args.quiet is True

    def test_max_retries_option(self) -> None:
        """Test --max-retries option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--max-retries", "10",
        ])
        assert args.max_retries == 10

    def test_no_retry_option(self) -> None:
        """Test --no-retry option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--no-retry",
        ])
        assert args.no_retry is True

    def test_region_options(self) -> None:
        """Test region options."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--region", "eu-west-1",
            "--source-region", "us-east-1",
            "--dest-region", "ap-south-1",
        ])
        assert args.region == "eu-west-1"
        assert args.source_region == "us-east-1"
        assert args.dest_region == "ap-south-1"

    def test_transfer_acceleration_option(self) -> None:
        """Test --transfer-acceleration option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--transfer-acceleration",
        ])
        assert args.transfer_acceleration is True

    def test_include_exclude_options(self) -> None:
        """Test --include and --exclude options."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--include", "*.txt",
            "--include", "*.json",
            "--exclude", "temp/*",
        ])
        assert args.include == ["*.txt", "*.json"]
        assert args.exclude == ["temp/*"]

    def test_timeout_options(self) -> None:
        """Test timeout options."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--connect-timeout", "30",
            "--read-timeout", "120",
        ])
        assert args.connect_timeout == 30
        assert args.read_timeout == 120

    def test_json_output_option(self) -> None:
        """Test --json option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--json",
        ])
        assert args.json is True

    def test_log_file_option(self) -> None:
        """Test --log-file option."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--log-file", "/var/log/s3hop.log",
        ])
        assert args.log_file == "/var/log/s3hop.log"


class TestBuildConfig:
    """Tests for building TransferConfig from arguments."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
        ])
        config = build_config(args)

        assert config.max_workers == DEFAULT_MAX_WORKERS
        assert config.retry.max_retries == DEFAULT_MAX_RETRIES
        assert config.connection.region == DEFAULT_REGION
        assert config.dry_run is False
        assert config.verbose is False

    def test_config_with_options(self) -> None:
        """Test configuration with options."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--workers", "20",
            "--dry-run",
            "--verbose",
            "--max-retries", "10",
        ])
        config = build_config(args)

        assert config.max_workers == 20
        assert config.dry_run is True
        assert config.verbose is True
        assert config.retry.max_retries == 10

    def test_config_no_retry(self) -> None:
        """Test configuration with no-retry."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--no-retry",
        ])
        config = build_config(args)

        assert config.retry.max_retries == 0

    def test_config_filters(self) -> None:
        """Test configuration with filters."""
        parser = create_parser()
        args = parser.parse_args([
            "src", "s3://src/", "dst", "s3://dst/",
            "--include", "*.txt",
            "--exclude", "temp/*",
        ])
        config = build_config(args)

        assert config.filters.include_patterns == ["*.txt"]
        assert config.filters.exclude_patterns == ["temp/*"]


class TestMain:
    """Tests for main entry point."""

    @patch("s3hop.cli.TransferService")
    @patch("s3hop.cli.setup_logging")
    def test_main_successful(
        self,
        mock_setup_logging: Mock,
        mock_service_class: Mock,
    ) -> None:
        """Test successful main execution."""
        mock_service = Mock()
        mock_service.copy_bucket.return_value = Mock(failed_files=0)
        mock_service_class.return_value = mock_service

        result = main([
            "source-profile",
            "s3://source-bucket/",
            "dest-profile",
            "s3://dest-bucket/",
        ])

        assert result == 0
        mock_service.copy_bucket.assert_called_once()

    @patch("s3hop.cli.TransferService")
    @patch("s3hop.cli.setup_logging")
    def test_main_with_failures(
        self,
        mock_setup_logging: Mock,
        mock_service_class: Mock,
    ) -> None:
        """Test main execution with failed transfers."""
        mock_service = Mock()
        mock_service.copy_bucket.return_value = Mock(failed_files=5)
        mock_service_class.return_value = mock_service

        result = main([
            "src", "s3://src/", "dst", "s3://dst/",
        ])

        assert result == 1

    def test_main_missing_args(self) -> None:
        """Test main with missing arguments."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2  # argparse exit code for error

    @patch("s3hop.cli.TransferService")
    @patch("s3hop.cli.setup_logging")
    def test_main_invalid_url(
        self,
        mock_setup_logging: Mock,
        mock_service_class: Mock,
    ) -> None:
        """Test main with invalid S3 URL."""
        from s3hop.exceptions import InvalidS3UrlError

        mock_service = Mock()
        mock_service.copy_bucket.side_effect = InvalidS3UrlError("invalid-url")
        mock_service_class.return_value = mock_service

        result = main([
            "src", "invalid-url", "dst", "s3://dst/",
        ])

        assert result == 1

    @patch("s3hop.cli.TransferService")
    @patch("s3hop.cli.setup_logging")
    def test_main_profile_not_found(
        self,
        mock_setup_logging: Mock,
        mock_service_class: Mock,
    ) -> None:
        """Test main with missing AWS profile."""
        from s3hop.exceptions import ProfileNotFoundError

        mock_service = Mock()
        mock_service.copy_bucket.side_effect = ProfileNotFoundError("bad-profile")
        mock_service_class.return_value = mock_service

        result = main([
            "bad-profile", "s3://src/", "dst", "s3://dst/",
        ])

        assert result == 1

    @patch("s3hop.cli.TransferService")
    @patch("s3hop.cli.setup_logging")
    def test_main_keyboard_interrupt(
        self,
        mock_setup_logging: Mock,
        mock_service_class: Mock,
    ) -> None:
        """Test main with keyboard interrupt."""
        mock_service = Mock()
        mock_service.copy_bucket.side_effect = KeyboardInterrupt()
        mock_service_class.return_value = mock_service

        result = main([
            "src", "s3://src/", "dst", "s3://dst/",
        ])

        assert result == 1
