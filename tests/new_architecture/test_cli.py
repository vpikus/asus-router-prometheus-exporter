"""
Tests for the CLI module.
"""

import sys

sys.path.insert(0, 'src')

import argparse
import logging
import os
from unittest.mock import MagicMock, patch

from asus_router_exporter.cli import main, parse_args, setup_logging, validate_args


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default_level(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            setup_logging()

            mock_root.setLevel.assert_called_once_with(logging.INFO)

    def test_setup_logging_debug_level(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            setup_logging(level="DEBUG")

            mock_root.setLevel.assert_called_once_with(logging.DEBUG)

    def test_setup_logging_warning_level(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            setup_logging(level="WARNING")

            mock_root.setLevel.assert_called_once_with(logging.WARNING)

    def test_setup_logging_error_level(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            setup_logging(level="ERROR")

            mock_root.setLevel.assert_called_once_with(logging.ERROR)

    def test_setup_logging_case_insensitive(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            setup_logging(level="info")

            mock_root.setLevel.assert_called_once_with(logging.INFO)

    def test_setup_logging_with_masking(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            with patch('asus_router_exporter.utils.logging.SensitiveFormatter') as mock_formatter_cls:
                mock_formatter = MagicMock()
                mock_formatter_cls.return_value = mock_formatter

                setup_logging(mask_sensitive=True)

                mock_formatter_cls.assert_called_once()

    def test_setup_logging_without_masking(self):
        with patch('logging.getLogger') as mock_get_logger:
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            with patch('logging.Formatter') as mock_formatter_cls:
                mock_formatter = MagicMock()
                mock_formatter_cls.return_value = mock_formatter

                setup_logging(mask_sensitive=False)

                mock_formatter_cls.assert_called()


class TestParseArgs:
    """Tests for parse_args function."""

    def test_parse_args_router_host(self):
        args = parse_args(["--router-host", "10.0.0.1"])
        assert args.router_host == "10.0.0.1"

    def test_parse_args_router_auth(self):
        args = parse_args(["--router-auth", "admin:password"])
        assert args.router_auth == "admin:password"

    def test_parse_args_metrics_port(self):
        args = parse_args(["--metrics-port", "9100"])
        assert args.metrics_port == 9100

    def test_parse_args_config_path(self):
        args = parse_args(["--config", "config.yaml"])
        assert args.config_path == "config.yaml"

    def test_parse_args_log_level(self):
        args = parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_parse_args_no_mask_sensitive(self):
        args = parse_args(["--no-mask-sensitive"])
        assert args.mask_sensitive is False

    def test_parse_args_default_mask_sensitive(self):
        args = parse_args([])
        assert args.mask_sensitive is True

    def test_parse_args_default_port(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove ASUS_METRICS_PORT if set
            os.environ.pop("ASUS_METRICS_PORT", None)
            args = parse_args([])
            assert args.metrics_port == 8000

    def test_parse_args_port_from_env(self):
        with patch.dict(os.environ, {"ASUS_METRICS_PORT": "9090"}):
            args = parse_args([])
            assert args.metrics_port == 9090

    def test_parse_args_router_host_from_env(self):
        with patch.dict(os.environ, {"ASUS_ROUTER_HOST": "192.168.1.100"}):
            args = parse_args([])
            assert args.router_host == "192.168.1.100"

    def test_parse_args_router_auth_from_env(self):
        with patch.dict(os.environ, {"ASUS_ROUTER_AUTH": "secret_token"}):
            args = parse_args([])
            assert args.router_auth == "secret_token"

    def test_parse_args_log_level_from_env(self):
        with patch.dict(os.environ, {"ASUS_LOG_LEVEL": "WARNING"}):
            args = parse_args([])
            assert args.log_level == "WARNING"

    def test_parse_args_cli_overrides_env(self):
        with patch.dict(os.environ, {"ASUS_ROUTER_HOST": "192.168.1.1"}):
            args = parse_args(["--router-host", "10.0.0.1"])
            assert args.router_host == "10.0.0.1"

    def test_parse_args_multiple_options(self):
        args = parse_args([
            "--router-host", "10.0.0.1",
            "--router-auth", "token",
            "--metrics-port", "9100",
            "--log-level", "DEBUG",
        ])
        assert args.router_host == "10.0.0.1"
        assert args.router_auth == "token"
        assert args.metrics_port == 9100
        assert args.log_level == "DEBUG"


class TestValidateArgs:
    """Tests for validate_args function."""

    def test_validate_args_with_config_path(self):
        args = argparse.Namespace(
            config_path="config.yaml",
            router_host=None,
            router_auth=None,
        )
        assert validate_args(args) is True

    def test_validate_args_with_host_and_auth(self):
        args = argparse.Namespace(
            config_path=None,
            router_host="192.168.1.1",
            router_auth="token",
        )
        assert validate_args(args) is True

    def test_validate_args_missing_host(self, capsys):
        args = argparse.Namespace(
            config_path=None,
            router_host=None,
            router_auth="token",
        )
        result = validate_args(args)

        assert result is False
        captured = capsys.readouterr()
        assert "router-host is required" in captured.err

    def test_validate_args_missing_auth(self, capsys):
        args = argparse.Namespace(
            config_path=None,
            router_host="192.168.1.1",
            router_auth=None,
        )
        result = validate_args(args)

        assert result is False
        captured = capsys.readouterr()
        assert "router-auth is required" in captured.err

    def test_validate_args_missing_both(self, capsys):
        args = argparse.Namespace(
            config_path=None,
            router_host=None,
            router_auth=None,
        )
        result = validate_args(args)

        assert result is False
        # Should fail on first check (router-host)
        captured = capsys.readouterr()
        assert "router-host is required" in captured.err


class TestMain:
    """Tests for main function."""

    @patch('asus_router_exporter.cli.create_exporter')
    @patch('asus_router_exporter.cli.setup_logging')
    def test_main_success(self, mock_setup_logging, mock_create_exporter):
        mock_exporter = MagicMock()
        mock_create_exporter.return_value = mock_exporter

        result = main([
            "--router-host", "192.168.1.1",
            "--router-auth", "token",
        ])

        assert result == 0
        mock_create_exporter.assert_called_once()
        mock_exporter.run.assert_called_once()

    @patch('asus_router_exporter.cli.create_exporter')
    @patch('asus_router_exporter.cli.setup_logging')
    def test_main_with_config(self, mock_setup_logging, mock_create_exporter):
        mock_exporter = MagicMock()
        mock_create_exporter.return_value = mock_exporter

        result = main(["--config", "config.yaml"])

        assert result == 0
        mock_create_exporter.assert_called_once_with(
            config_path="config.yaml",
            router_host=None,
            router_auth=None,
            metrics_port=8000,
        )

    @patch('asus_router_exporter.cli.create_exporter')
    @patch('asus_router_exporter.cli.setup_logging')
    def test_main_with_all_options(self, mock_setup_logging, mock_create_exporter):
        mock_exporter = MagicMock()
        mock_create_exporter.return_value = mock_exporter

        result = main([
            "--router-host", "10.0.0.1",
            "--router-auth", "mytoken",
            "--metrics-port", "9100",
            "--log-level", "DEBUG",
        ])

        assert result == 0
        mock_create_exporter.assert_called_once_with(
            config_path=None,
            router_host="10.0.0.1",
            router_auth="mytoken",
            metrics_port=9100,
        )
        mock_setup_logging.assert_called_once_with(
            level="DEBUG",
            mask_sensitive=True,
        )

    def test_main_missing_required_args(self):
        # Clear env vars that might provide defaults
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASUS_ROUTER_HOST", None)
            os.environ.pop("ASUS_ROUTER_AUTH", None)

            result = main([])

            assert result == 1

    @patch('asus_router_exporter.cli.create_exporter')
    @patch('asus_router_exporter.cli.setup_logging')
    def test_main_keyboard_interrupt(self, mock_setup_logging, mock_create_exporter):
        mock_exporter = MagicMock()
        mock_exporter.run.side_effect = KeyboardInterrupt()
        mock_create_exporter.return_value = mock_exporter

        result = main([
            "--router-host", "192.168.1.1",
            "--router-auth", "token",
        ])

        assert result == 0

    @patch('asus_router_exporter.cli.create_exporter')
    @patch('asus_router_exporter.cli.setup_logging')
    def test_main_exception(self, mock_setup_logging, mock_create_exporter):
        mock_create_exporter.side_effect = RuntimeError("Connection failed")

        result = main([
            "--router-host", "192.168.1.1",
            "--router-auth", "token",
        ])

        assert result == 1

    @patch('asus_router_exporter.cli.create_exporter')
    @patch('asus_router_exporter.cli.setup_logging')
    def test_main_no_mask_sensitive(self, mock_setup_logging, mock_create_exporter):
        mock_exporter = MagicMock()
        mock_create_exporter.return_value = mock_exporter

        result = main([
            "--router-host", "192.168.1.1",
            "--router-auth", "token",
            "--no-mask-sensitive",
        ])

        assert result == 0
        mock_setup_logging.assert_called_once_with(
            level="INFO",
            mask_sensitive=False,
        )


class TestCLIIntegration:
    """Integration tests for CLI."""

    def test_parse_and_validate_with_config(self):
        """Test parsing and validating with config file."""
        args = parse_args(["--config", "config.yaml"])
        assert validate_args(args) is True

    def test_parse_and_validate_with_host_auth(self):
        """Test parsing and validating with host and auth."""
        args = parse_args([
            "--router-host", "192.168.1.1",
            "--router-auth", "token",
        ])
        assert validate_args(args) is True

    def test_parse_and_validate_missing_required(self):
        """Test parsing and validating with missing required args."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASUS_ROUTER_HOST", None)
            os.environ.pop("ASUS_ROUTER_AUTH", None)

            args = parse_args([])
            assert validate_args(args) is False
