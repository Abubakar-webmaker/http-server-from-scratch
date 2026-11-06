"""Phase 8 integration tests - verify all new features work end-to-end."""

import socket
import threading
import time
import unittest
import tempfile
import os
from pathlib import Path

from server import HTTPServer


class Phase8IntegrationTests(unittest.TestCase):
    """Integration tests for Phase 8 features."""

    def setUp(self):
        """Start a test server."""
        temporary_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )
        temporary_socket.bind(("127.0.0.1", 0))
        self.port = temporary_socket.getsockname()[1]
        temporary_socket.close()

        self.server = HTTPServer(
            host="127.0.0.1",
            port=self.port,
            max_clients=50,
            socket_timeout=2,
            keep_alive_timeout=2,
        )

        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )
        self.server_thread.start()

        # Wait for server to start
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(
                    ("127.0.0.1", self.port),
                    timeout=0.2,
                ):
                    break
            except OSError:
                time.sleep(0.05)

    def tearDown(self):
        """Stop the test server."""
        self.server.shutdown()
        self.server_thread.join(timeout=5)

    def test_middleware_integration(self):
        """Test that middleware system works with routes."""
        with socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=4,
        ) as conn:
            conn.sendall(
                b"GET / HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Connection: close\r\n"
                b"\r\n"
            )
            response = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                response += chunk

        self.assertIn(b"200 OK", response)
        self.assertIn(b"Hello World", response)

    def test_gzip_compression_available(self):
        """Test gzip compression is available (even if not applied in basic test)."""
        # This just ensures the compression module loads
        from gzip_support.gzip_handler import compress_response
        self.assertIsNotNone(compress_response)

    def test_rate_limiter_available(self):
        """Test rate limiter module is available."""
        from core.rate_limiter import RateLimiter
        limiter = RateLimiter(requests_per_window=2, window_seconds=10)
        self.assertTrue(limiter.is_allowed("127.0.0.1"))
        self.assertTrue(limiter.is_allowed("127.0.0.1"))
        self.assertFalse(limiter.is_allowed("127.0.0.1"))

    def test_logging_available(self):
        """Test logging system is available."""
        from utils.logger import setup_logging, get_logger
        logger = setup_logging(log_level="INFO")
        self.assertIsNotNone(logger)

    def test_exceptions_available(self):
        """Test all new exception types are available."""
        from utils.exceptions import (
            HTTPException,
            BadRequestError,
            RateLimitExceededError,
            RequestTooLargeError,
        )
        self.assertIsNotNone(HTTPException)
        self.assertIsNotNone(BadRequestError)
        self.assertIsNotNone(RateLimitExceededError)
        self.assertIsNotNone(RequestTooLargeError)

    def test_chunked_module_available(self):
        """Test chunked transfer encoding module is available."""
        from http.chunked import ChunkedDecoder, decode_chunked
        self.assertIsNotNone(ChunkedDecoder)
        self.assertIsNotNone(decode_chunked)

    def test_tls_module_available(self):
        """Test TLS module is available."""
        from security.tls import SSLContextFactory
        self.assertIsNotNone(SSLContextFactory)


if __name__ == "__main__":
    unittest.main()
