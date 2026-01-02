"""
Command-line interface for the ASUS Router Exporter.

Usage:
    asus-router-exporter --router-host 192.168.1.1 --router-auth TOKEN
    asus-router-exporter --config config.yaml
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .server.exporter import create_exporter


def setup_logging(level: str = "INFO", mask_sensitive: bool = True) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        mask_sensitive: Whether to mask sensitive data in logs
    """
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Use SensitiveFormatter for masking sensitive data in logs
    formatter: logging.Formatter
    if mask_sensitive:
        from .utils.logging import SensitiveFormatter

        formatter = SensitiveFormatter(fmt)
    else:
        formatter = logging.Formatter(fmt)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers = [handler]


def parse_args(args: list | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        args: Command-line arguments (uses sys.argv if None)

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="ASUS Router Prometheus Exporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using command-line arguments
  %(prog)s --router-host 192.168.1.1 --router-auth BASE64_TOKEN

  # Using config file
  %(prog)s --config config.yaml

  # Using environment variables
  ASUS_ROUTER_HOST=192.168.1.1 ASUS_ROUTER_AUTH=TOKEN %(prog)s

Environment variables:
  ASUS_ROUTER_HOST      Router hostname or IP address
  ASUS_ROUTER_AUTH      Router authentication token (base64)
  ASUS_METRICS_PORT     Metrics HTTP port (default: 8000)
  ASUS_SCRAPE_INTERVAL  Scrape interval in seconds (default: 30)
  ASUS_LOG_LEVEL        Log level (default: INFO)
        """,
    )

    parser.add_argument(
        "--router-host",
        dest="router_host",
        default=os.getenv("ASUS_ROUTER_HOST"),
        help="Router hostname or IP address",
    )

    parser.add_argument(
        "--router-auth",
        dest="router_auth",
        default=os.getenv("ASUS_ROUTER_AUTH"),
        help="Router authentication token (base64 encoded)",
    )

    parser.add_argument(
        "--metrics-port",
        dest="metrics_port",
        type=int,
        default=int(os.getenv("ASUS_METRICS_PORT", "8000")),
        help="Port for Prometheus metrics HTTP server (default: 8000)",
    )

    parser.add_argument(
        "--config",
        dest="config_path",
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--log-level",
        dest="log_level",
        default=os.getenv("ASUS_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    parser.add_argument(
        "--no-mask-sensitive",
        dest="mask_sensitive",
        action="store_false",
        default=True,
        help="Disable sensitive data masking in logs",
    )

    return parser.parse_args(args)


def validate_args(args: argparse.Namespace) -> bool:
    """
    Validate command-line arguments.

    Args:
        args: Parsed arguments

    Returns:
        True if valid, False otherwise
    """
    # If config file is provided, other args are optional
    if args.config_path:
        return True

    # Otherwise, router-host and router-auth are required
    if not args.router_host:
        print("Error: --router-host is required (or set ASUS_ROUTER_HOST env var)", file=sys.stderr)
        return False

    if not args.router_auth:
        print("Error: --router-auth is required (or set ASUS_ROUTER_AUTH env var)", file=sys.stderr)
        return False

    return True


def main(args: list | None = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        args: Command-line arguments (uses sys.argv if None)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parsed_args = parse_args(args)

    if not validate_args(parsed_args):
        return 1

    # Setup logging
    setup_logging(
        level=parsed_args.log_level,
        mask_sensitive=parsed_args.mask_sensitive,
    )

    logger = logging.getLogger(__name__)

    try:
        # Create and run exporter
        exporter = create_exporter(
            config_path=parsed_args.config_path,
            router_host=parsed_args.router_host,
            router_auth=parsed_args.router_auth,
            metrics_port=parsed_args.metrics_port,
        )
        exporter.run()
        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0

    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
