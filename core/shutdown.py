"""Graceful shutdown handling using signal module."""

import signal
import threading
from typing import Optional, Callable

from utils.logger import get_logger

logger = get_logger(__name__)


class GracefulShutdownHandler:
    """Handles graceful server shutdown on SIGINT/SIGTERM.

    Signal handlers should only request shutdown, not perform cleanup.
    Actual cleanup happens in the main server lifecycle.
    """

    def __init__(self) -> None:
        self._shutdown_requested = threading.Event()
        self._original_sigint_handler: Optional[signal.Handlers] = None
        self._original_sigterm_handler: Optional[signal.Handlers] = None

    def request_shutdown(self, signum: int, frame) -> None:
        """Signal handler to request shutdown.

        Args:
            signum: Signal number (SIGINT=2, SIGTERM=15).
            frame: Stack frame.
        """
        logger.info("Shutdown requested (signal %d)", signum)
        self._shutdown_requested.set()

    def register_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        try:
            self._original_sigint_handler = signal.signal(
                signal.SIGINT, self.request_shutdown
            )
            logger.debug("Registered SIGINT handler")
        except Exception as exc:
            logger.warning("Could not register SIGINT handler: %s", exc)

        try:
            self._original_sigterm_handler = signal.signal(
                signal.SIGTERM, self.request_shutdown
            )
            logger.debug("Registered SIGTERM handler")
        except Exception as exc:
            logger.warning("Could not register SIGTERM handler: %s", exc)

    def unregister_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._original_sigint_handler)
            except Exception as exc:
                logger.warning("Could not restore SIGINT handler: %s", exc)

        if self._original_sigterm_handler is not None:
            try:
                signal.signal(signal.SIGTERM, self._original_sigterm_handler)
            except Exception as exc:
                logger.warning("Could not restore SIGTERM handler: %s", exc)

    @property
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested.is_set()

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """Wait for shutdown request.

        Args:
            timeout: Max time to wait (seconds). None = wait forever.

        Returns:
            True if shutdown was requested, False if timeout expired.
        """
        return self._shutdown_requested.wait(timeout)
