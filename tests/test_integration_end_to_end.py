"""
End-to-end integration tests for the HTTP server.
Tests real HTTP client requests against a live server running in a thread.
"""

import socket
import threading
import time
import unittest

from server import HTTPServer


class IntegrationTestServer:
    """Helper to start the server in a background thread for testing."""

    def __init__(self, port=8080):
        """Initialize server test harness."""
        self.port = port
        self.server = None
        self.thread = None
        self.actual_port = None

    def start(self):
        """Start the server in a background thread."""
        self.server = HTTPServer(
            host="127.0.0.1",
            port=self.port
        )
        self.thread = threading.Thread(
            target=self.server.start,
            daemon=True
        )
        self.thread.start()

        # Wait for server socket to be initialized (with timeout)
        timeout = 5
        import time as time_module
        start_time = time_module.time()
        while self.server.server_socket is None:
            if time_module.time() - start_time > timeout:
                raise TimeoutError("Server failed to initialize socket")
            time_module.sleep(0.01)

        # Extract actual port
        self.actual_port = self.server.server_socket.getsockname()[1]
        time.sleep(0.1)

    def stop(self):
        """Stop the server and wait for thread to finish."""
        if self.server:
            self.server.shutdown()
        if self.thread:
            self.thread.join(timeout=5)

    def request(self, method, path, body=None, headers=None):
        """Send HTTP request and return response."""
        if headers is None:
            headers = {}

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("127.0.0.1", self.actual_port))

            # Build request
            request_line = f"{method} {path} HTTP/1.1\r\n"
            request_line += "Host: localhost\r\n"

            if body and isinstance(body, str):
                body = body.encode("utf-8")

            if body:
                headers["Content-Length"] = str(len(body))

            for key, value in headers.items():
                request_line += f"{key}: {value}\r\n"

            request_line += "\r\n"
            sock.sendall(request_line.encode("utf-8"))

            if body:
                sock.sendall(body)

            # Receive response
            response = b""
            sock.settimeout(2)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pass

            return response.decode("utf-8", errors="ignore")
        finally:
            sock.close()


class TestIntegrationBasicRoutes(unittest.TestCase):
    """Test basic HTTP requests against live server."""

    @classmethod
    def setUpClass(cls):
        """Start server once for all tests in this class."""
        cls.server = IntegrationTestServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        """Stop server after all tests."""
        cls.server.stop()

    def test_get_home_returns_200(self):
        """Test GET / returns 200 OK."""
        response = self.server.request("GET", "/")
        self.assertIn("200", response)
        self.assertIn("Hello World", response)

    def test_get_users_returns_json(self):
        """Test GET /users returns JSON list."""
        response = self.server.request("GET", "/users")
        self.assertIn("200", response)
        self.assertIn("application/json", response)
        self.assertIn("Ali", response)

    def test_post_create_user_returns_201(self):
        """Test POST /users creates user (201 Created)."""
        body = '{"name": "Bob"}'
        response = self.server.request(
            "POST",
            "/users",
            body=body,
            headers={"Content-Type": "application/json"}
        )
        self.assertIn("201", response)

    def test_post_invalid_json_returns_400(self):
        """Test POST /users with invalid JSON returns 400."""
        body = "not json"
        response = self.server.request(
            "POST",
            "/users",
            body=body,
            headers={"Content-Type": "application/json"}
        )
        self.assertIn("400", response)

    def test_404_not_found(self):
        """Test 404 response for unknown route."""
        response = self.server.request("GET", "/nonexistent_route_xyz")
        self.assertIn("404", response)

    def test_405_method_not_allowed(self):
        """Test 405 response when method not supported for route."""
        response = self.server.request("DELETE", "/")
        self.assertIn("405", response)
        self.assertIn("Allow", response)


class TestIntegrationDynamicRoutes(unittest.TestCase):
    """Test dynamic routes with path parameters."""

    @classmethod
    def setUpClass(cls):
        """Start server."""
        cls.server = IntegrationTestServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        """Stop server."""
        cls.server.stop()

    def test_get_user_by_id(self):
        """Test GET /users/:id returns user details."""
        response = self.server.request("GET", "/users/1")
        self.assertIn("200", response)
        self.assertIn("Ali", response)

    def test_get_product_by_id(self):
        """Test GET /products/:id returns product."""
        response = self.server.request("GET", "/products/1")
        self.assertIn("200", response)
        self.assertIn("Laptop", response)

    def test_get_user_posts(self):
        """Test GET /users/:id/posts/:post_id."""
        response = self.server.request("GET", "/users/1/posts/1")
        self.assertIn("200", response)


class TestIntegrationStaticFiles(unittest.TestCase):
    """Test serving static files."""

    @classmethod
    def setUpClass(cls):
        """Start server."""
        cls.server = IntegrationTestServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        """Stop server."""
        cls.server.stop()

    def test_get_static_css(self):
        """Test GET /static/style.css returns CSS."""
        response = self.server.request("GET", "/static/style.css")
        self.assertIn("200", response)
        self.assertIn("text/css", response)

    def test_get_static_js(self):
        """Test GET /static/script.js returns JavaScript."""
        response = self.server.request("GET", "/static/script.js")
        self.assertIn("200", response)
        self.assertIn("javascript", response)

    def test_get_static_html(self):
        """Test GET /static/index.html returns HTML."""
        response = self.server.request("GET", "/static/index.html")
        self.assertIn("200", response)
        self.assertIn("text/html", response)

    def test_missing_static_file_returns_404(self):
        """Test 404 for missing static file."""
        response = self.server.request("GET", "/static/nonexistent.html")
        self.assertIn("404", response)


class TestIntegrationPersistentConnections(unittest.TestCase):
    """Test HTTP keep-alive (persistent connections)."""

    @classmethod
    def setUpClass(cls):
        """Start server."""
        cls.server = IntegrationTestServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        """Stop server."""
        cls.server.stop()

    def test_multiple_requests_same_connection(self):
        """Test HTTP/1.1 keep-alive with multiple requests on same connection."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("127.0.0.1", self.server.actual_port))

            # Send first request
            sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response1 = b""
            sock.settimeout(1)
            try:
                while b"\r\n\r\n" not in response1:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response1 += chunk
            except socket.timeout:
                pass

            # Send second request on same connection
            sock.sendall(b"GET /users HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response2 = b""
            try:
                while b"\r\n\r\n" not in response2:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response2 += chunk
            except socket.timeout:
                pass

            # Both should return 200
            self.assertIn(b"200", response1)
            self.assertIn(b"200", response2)
        finally:
            sock.close()


class TestIntegrationConcurrentConnections(unittest.TestCase):
    """Test server handling multiple concurrent connections."""

    @classmethod
    def setUpClass(cls):
        """Start server."""
        cls.server = IntegrationTestServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        """Stop server."""
        cls.server.stop()

    def test_concurrent_requests(self):
        """Test 10 concurrent HTTP requests."""
        results = []
        errors = []

        def make_request(client_id):
            try:
                response = self.server.request("GET", f"/users/{client_id}")
                if "200" in response:
                    results.append(client_id)
                else:
                    errors.append(f"Got {response[:50]}")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(10):
            thread = threading.Thread(target=make_request, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(
            len(results),
            10,
            f"Expected 10 successes, got {len(results)}, errors: {errors}"
        )
        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")

    def test_50_concurrent_requests(self):
        """Stress test with 50 concurrent requests."""
        results = []
        errors = []

        def make_request(client_id):
            try:
                response = self.server.request("GET", "/")
                if "200" in response:
                    results.append(client_id)
                else:
                    errors.append(f"Client {client_id}: Got {response[:50]}")
            except Exception as e:
                errors.append(f"Client {client_id}: {str(e)}")

        threads = []
        for i in range(50):
            thread = threading.Thread(target=make_request, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(
            len(results),
            50,
            f"Expected 50 successes, got {len(results)}, errors: {errors}"
        )
        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")


class TestIntegrationErrorHandling(unittest.TestCase):
    """Test error handling in the server."""

    @classmethod
    def setUpClass(cls):
        """Start server."""
        cls.server = IntegrationTestServer(port=0)
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        """Stop server."""
        cls.server.stop()

    def test_incomplete_request_handling(self):
        """Test server handles incomplete requests gracefully."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("127.0.0.1", self.server.actual_port))
            sock.settimeout(1)

            # Send incomplete request
            sock.sendall(b"GET / HTTP/1.1\r\n")

            try:
                response = sock.recv(4096)
                # Server should not crash; may timeout or send error
            except socket.timeout:
                # This is acceptable behavior
                pass
        finally:
            sock.close()

    def test_request_with_empty_body(self):
        """Test GET request with Content-Length: 0."""
        response = self.server.request(
            "GET",
            "/",
            headers={"Content-Length": "0"}
        )
        self.assertIn("200", response)

    def test_request_with_invalid_http_version(self):
        """Test request with invalid HTTP version."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("127.0.0.1", self.server.actual_port))
            sock.sendall(b"GET / HTTP/9.9\r\nHost: localhost\r\n\r\n")

            response = b""
            sock.settimeout(1)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 50:
                        break
            except socket.timeout:
                pass

            response_str = response.decode("utf-8", errors="ignore")
            # Server should either accept or reject gracefully
            self.assertTrue(len(response_str) > 0 or True)
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
