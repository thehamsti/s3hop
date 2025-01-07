import sys
from unittest.mock import Mock, patch

import pytest

from s3hop import cli


def test_main_successful():
    """Test successful CLI execution"""
    test_args = [
        "script_name",
        "source-profile",
        "s3://source-bucket/prefix/",
        "dest-profile",
        "s3://dest-bucket/prefix/",
    ]

    with patch.object(sys, "argv", test_args):
        with patch("s3hop.core.copy_bucket") as mock_copy:
            cli.main()
            mock_copy.assert_called_once_with(
                "source-profile",
                "s3://source-bucket/prefix/",
                "dest-profile",
                "s3://dest-bucket/prefix/",
            )


def test_main_invalid_args():
    """Test CLI with invalid arguments"""
    test_args = ["script_name"]  # Missing required arguments

    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 2  # argparse uses exit code 2 for argument errors


def test_main_value_error():
    """Test CLI handling of ValueError"""
    test_args = [
        "script_name",
        "source-profile",
        "invalid-url",  # Invalid S3 URL
        "dest-profile",
        "s3://dest-bucket/prefix/",
    ]

    with patch.object(sys, "argv", test_args):
        with patch("s3hop.core.copy_bucket") as mock_copy:
            mock_copy.side_effect = ValueError("Invalid S3 URL")
            with pytest.raises(SystemExit) as exc_info:
                cli.main()
            assert exc_info.value.code == 1


def test_main_keyboard_interrupt():
    """Test CLI handling of KeyboardInterrupt"""
    test_args = [
        "script_name",
        "source-profile",
        "s3://source-bucket/prefix/",
        "dest-profile",
        "s3://dest-bucket/prefix/",
    ]

    with patch.object(sys, "argv", test_args):
        with patch("s3hop.core.copy_bucket") as mock_copy:
            mock_copy.side_effect = KeyboardInterrupt()
            with pytest.raises(SystemExit) as exc_info:
                cli.main()
            assert exc_info.value.code == 1
