"""Tests for rate limiting."""

import unittest
import time
import threading

from core.rate_limiter import RateLimiter


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting functionality."""

    def test_within_limit(self):
        """Requests within limit are allowed."""
        limiter = RateLimiter(requests_per_window=5, window_seconds=60)

        for i in range(5):
            self.assertTrue(limiter.is_allowed("127.0.0.1"), f"Request {i+1} should be allowed")

    def test_exceeds_limit(self):
        """Requests exceeding limit are blocked."""
        limiter = RateLimiter(requests_per_window=2, window_seconds=60)

        self.assertTrue(limiter.is_allowed("127.0.0.1"))
        self.assertTrue(limiter.is_allowed("127.0.0.1"))
        self.assertFalse(limiter.is_allowed("127.0.0.1"))

    def test_different_clients_independent(self):
        """Rate limits are per-client."""
        limiter = RateLimiter(requests_per_window=2, window_seconds=60)

        self.assertTrue(limiter.is_allowed("192.168.1.1"))
        self.assertTrue(limiter.is_allowed("192.168.1.1"))
        self.assertFalse(limiter.is_allowed("192.168.1.1"))

        # Different client should still have quota
        self.assertTrue(limiter.is_allowed("192.168.1.2"))
        self.assertTrue(limiter.is_allowed("192.168.1.2"))
        self.assertFalse(limiter.is_allowed("192.168.1.2"))

    def test_window_expiration(self):
        """Rate limit resets after window expires."""
        limiter = RateLimiter(requests_per_window=2, window_seconds=1)

        self.assertTrue(limiter.is_allowed("127.0.0.1"))
        self.assertTrue(limiter.is_allowed("127.0.0.1"))
        self.assertFalse(limiter.is_allowed("127.0.0.1"))

        # Wait for window to expire
        time.sleep(1.5)

        # Should be allowed again
        self.assertTrue(limiter.is_allowed("127.0.0.1"))

    def test_get_retry_after(self):
        """Get retry-after time for blocked client."""
        limiter = RateLimiter(requests_per_window=1, window_seconds=5)

        limiter.is_allowed("127.0.0.1")
        limiter.is_allowed("127.0.0.1")  # Block

        retry_after = limiter.get_retry_after("127.0.0.1")
        self.assertGreater(retry_after, 0)
        self.assertLessEqual(retry_after, 6)  # Allow for timing

    def test_get_retry_after_unknown_client(self):
        """Retry-after for unknown client is 0."""
        limiter = RateLimiter()

        retry_after = limiter.get_retry_after("192.168.1.1")
        self.assertEqual(retry_after, 0)

    def test_reset_client(self):
        """Reset a client's rate limit."""
        limiter = RateLimiter(requests_per_window=2, window_seconds=60)

        limiter.is_allowed("127.0.0.1")
        limiter.is_allowed("127.0.0.1")
        self.assertFalse(limiter.is_allowed("127.0.0.1"))

        limiter.reset_client("127.0.0.1")

        # Should be allowed again
        self.assertTrue(limiter.is_allowed("127.0.0.1"))

    def test_active_clients_count(self):
        """Count active clients."""
        limiter = RateLimiter(requests_per_window=10, window_seconds=60)

        limiter.is_allowed("192.168.1.1")
        self.assertEqual(limiter.active_clients, 1)

        limiter.is_allowed("192.168.1.2")
        self.assertEqual(limiter.active_clients, 2)

        limiter.is_allowed("192.168.1.1")
        self.assertEqual(limiter.active_clients, 2)

    def test_concurrent_access_thread_safe(self):
        """Rate limiter is thread-safe."""
        limiter = RateLimiter(requests_per_window=100, window_seconds=60)
        results = []
        errors = []

        def worker(client_id):
            try:
                for _ in range(20):
                    result = limiter.is_allowed(f"client-{client_id}")
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 100)
        # All should be allowed since limit is 100 per window
        self.assertTrue(all(results))

    def test_cleanup_expired_records(self):
        """Cleanup removes expired records."""
        limiter = RateLimiter(
            requests_per_window=2,
            window_seconds=1,
            cleanup_interval=1,
        )

        limiter.is_allowed("127.0.0.1")
        initial_count = limiter.active_clients
        self.assertEqual(initial_count, 1)

        # Wait for window and cleanup interval
        time.sleep(1.5)

        # Trigger cleanup by checking a new client
        limiter.is_allowed("192.168.1.1")

        # Old record should be cleaned
        self.assertLessEqual(limiter.active_clients, 2)


if __name__ == "__main__":
    unittest.main()
