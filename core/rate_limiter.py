"""Thread-safe request rate limiting."""

import time
import threading
from typing import Dict, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Fixed-window rate limiter per client IP.

    Tracks request count per client in a configurable time window.
    Thread-safe using threading.Lock.
    """

    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        cleanup_interval: int = 300,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            requests_per_window: Max requests per client per window.
            window_seconds: Duration of each time window in seconds.
            cleanup_interval: Interval (seconds) to clean expired records.
        """
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval

        # client_ip -> (request_count, window_start_time)
        self._client_records: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def is_allowed(self, client_ip: str) -> bool:
        """Check if a client is allowed to make a request.

        Args:
            client_ip: The client's IP address.

        Returns:
            True if the client is within limits; False otherwise.
        """
        current_time = time.monotonic()

        with self._lock:
            # Periodically clean up expired records
            if current_time - self._last_cleanup > self.cleanup_interval:
                self._cleanup_expired()
                self._last_cleanup = current_time

            if client_ip not in self._client_records:
                # New client
                self._client_records[client_ip] = (1, current_time)
                return True

            count, window_start = self._client_records[client_ip]

            # Check if window has expired
            if current_time - window_start >= self.window_seconds:
                # New window
                self._client_records[client_ip] = (1, current_time)
                return True

            # Still in same window
            if count < self.requests_per_window:
                self._client_records[client_ip] = (count + 1, window_start)
                return True

            # Limit exceeded
            return False

    def get_retry_after(self, client_ip: str) -> int:
        """Get seconds until the client's window expires.

        Args:
            client_ip: The client's IP address.

        Returns:
            Seconds to wait, or 0 if no active record.
        """
        current_time = time.monotonic()

        with self._lock:
            if client_ip not in self._client_records:
                return 0

            count, window_start = self._client_records[client_ip]
            elapsed = current_time - window_start
            remaining = max(0, self.window_seconds - elapsed)

            return int(remaining) + 1

    def _cleanup_expired(self) -> None:
        """Remove expired client records (must be called with lock held)."""
        current_time = time.monotonic()
        expired = [
            ip
            for ip, (count, window_start) in self._client_records.items()
            if current_time - window_start >= self.window_seconds
        ]

        for ip in expired:
            del self._client_records[ip]

        if expired:
            logger.debug(
                "Rate limiter: cleaned up %d expired records", len(expired)
            )

    def reset_client(self, client_ip: str) -> None:
        """Reset a client's rate limit record (for testing/admin)."""
        with self._lock:
            if client_ip in self._client_records:
                del self._client_records[client_ip]

    @property
    def active_clients(self) -> int:
        """Get the number of active client records."""
        with self._lock:
            return len(self._client_records)
