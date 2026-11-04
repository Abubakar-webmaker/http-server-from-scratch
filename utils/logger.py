"""Professional logging system for the HTTP server."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive data from logs."""

    SENSITIVE_KEYS = {
        "authorization",
        "password",
        "secret",
        "token",
        "api-key",
        "x-api-key",
        "cookie",
        "set-cookie",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive headers and fields."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            for key in self.SENSITIVE_KEYS:
                # Redact header values
                import re

                pattern = rf"({re.escape(key)}):\s*([^\r\n]+)"
                record.msg = re.sub(
                    pattern, r"\1: ***", record.msg, flags=re.IGNORECASE
                )
        return True


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """Configure logging for the server.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file. If None, only console logging.
        max_bytes: Max size of a log file before rotation.
        backup_count: Number of backup log files to keep.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("HTTPServer")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove any existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add sensitive data filter
    sensitive_filter = SensitiveDataFilter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance."""
    logger = logging.getLogger(name)
    return logger
