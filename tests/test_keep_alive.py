"""Phase 7 — HTTP Keep-Alive tests.

Every test that opens a socket talks to a real server thread so the full
keep-alive loop (buffered reader, connection-policy logic, idle timeout)
is exercised end-to-end.

Test categories
---------------
1. Basic persistent connections
2. Connection header behaviour (HTTP/1.0, HTTP/1.1, case, tokens)
3. TCP buffering (chunked delivery, pipelined writes, partial requests)
4. Timeout and disconnect handling
5. Integration (routes + static files over one connection)
"""

import socket
import threading
import time
import unittest

from server import HTTPServer


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("Server did not start in time")


def _read_response(conn: socket.socket) -> bytes:
    """Read bytes until the server closes the connection."""
    parts = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        parts.append(chunk)
    return b"".join(parts)


def _read_one_response(conn: socket.socket) -> bytes:
    """Read exactly one HTTP response from an open connection.

    Parses Content-Length so the caller knows where the response ends and
    the next one begins — which is the whole point of keep-alive framing.
    """
    raw = bytearray()

    # Read headers.
    while b"\r\n\r\n" not in raw:
        chunk = conn.recv(4096)
        if not chunk:
            break
        raw.extend(chunk)

    header_end = raw.index(b"\r\n\r\n")
    header_bytes = bytes(raw[:header_end])
    body_start = header_end + 4
    leftover = bytes(raw[body_start:])

    # Find Content-Length.
    content_length = 0
    for line in header_bytes.decode("iso-8859-1").split("\r\n")[1:]:
        if ":" in line:
            name, _, value = line.partition(":")
            if name.strip().lower() == "content-length":
                content_length = int(value.strip())

    # Read remaining body bytes.
    body = bytearray(leftover)
    while len(body) < content_length:
        chunk = conn.recv(min(4096, content_length - len(body)))
        if not chunk:
            break
        body.extend(chunk)

    return header_bytes + b"\r\n\r\n" + bytes(body)


def _http11(path: str = "/", extra_headers: str = "") -> bytes:
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"{extra_headers}"
        f"\r\n"
    ).encode()


def _http10(path: str = "/", extra_headers: str = "") -> bytes:
    return (
        f"GET {path} HTTP/1.0\r\n"
        f"Host: localhost\r\n"
        f"{extra_headers}"
        f"\r\n"
    ).encode()


# ---------------------------------------------------------------------------
# Base test case — starts one server per test class
# ---------------------------------------------------------------------------

class _ServerTestCase(unittest.TestCase):
    """Spin up a server once per test method."""

    # Subclasses may override these.
    SOCKET_TIMEOUT = 2.0
    KEEP_ALIVE_TIMEOUT = 2.0
    MAX_REQUESTS = 100

    def setUp(self):
        self.port = _free_port()
        self.server = HTTPServer(
            host="127.0.0.1",
            port=self.port,
            max_clients=50,
            socket_timeout=self.SOCKET_TIMEOUT,
            keep_alive_timeout=self.KEEP_ALIVE_TIMEOUT,
            max_requests_per_connection=self.MAX_REQUESTS,
        )
        self._thread = threading.Thread(
            target=self.server.start, daemon=True
        )
        self._thread.start()
        _wait_for_server(self.port)

    def tearDown(self):
        self.server.shutdown()
        self._thread.join(timeout=5)

    def connect(self, timeout: float = 4.0) -> socket.socket:
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=timeout)
        return conn


# ===========================================================================
# 1. Basic persistent connections
# ===========================================================================

class TestBasicPersistentConnections(_ServerTestCase):

    def test_single_request_http11(self):
        """One HTTP/1.1 request receives a valid 200 response."""
        with self.connect() as conn:
            conn.sendall(_http11("/"))
            conn.sendall(b"")          # keep conn open
            resp = _read_one_response(conn)
        self.assertIn(b"200 OK", resp)
        self.assertIn(b"Hello World", resp)

    def test_two_requests_same_connection(self):
        """Two sequential requests over one TCP connection both succeed."""
        with self.connect() as conn:
            conn.sendall(_http11("/"))
            r1 = _read_one_response(conn)

            conn.sendall(_http11("/users"))
            r2 = _read_one_response(conn)

        self.assertIn(b"200 OK", r1)
        self.assertIn(b"200 OK", r2)
        self.assertIn(b"Ali", r2)

    def test_five_requests_same_connection(self):
        """Five sequential requests all return correct responses."""
        paths = ["/", "/users", "/products", "/users/1", "/"]
        with self.connect() as conn:
            responses = []
            for path in paths:
                conn.sendall(_http11(path))
                responses.append(_read_one_response(conn))

        self.assertEqual(len(responses), 5)
        for resp in responses:
            self.assertIn(b"200 OK", resp)

    def test_connection_stays_open_http11(self):
        """After one HTTP/1.1 request the server has NOT closed the socket."""
        with self.connect() as conn:
            conn.sendall(_http11("/"))
            _read_one_response(conn)
            # If the server closed the socket recv would return b"".
            # Send a second request to prove it is still open.
            conn.sendall(_http11("/users"))
            r2 = _read_one_response(conn)
        self.assertIn(b"200 OK", r2)

    def test_request_counter_counts_all_requests(self):
        """Stats counter reflects every request on a persistent connection."""
        before = self.server.get_stats()["total_requests"]
        with self.connect() as conn:
            for _ in range(5):
                conn.sendall(_http11("/"))
                _read_one_response(conn)
        after = self.server.get_stats()["total_requests"]
        self.assertEqual(after - before, 5)

    def test_response_connection_header_keep_alive(self):
        """HTTP/1.1 persistent response carries Connection: keep-alive."""
        with self.connect() as conn:
            conn.sendall(_http11("/"))
            resp = _read_one_response(conn)
        self.assertIn(b"Connection: keep-alive", resp)

    def test_response_connection_header_close(self):
        """Connection: close request receives Connection: close response."""
        with self.connect() as conn:
            conn.sendall(_http11("/", "Connection: close\r\n"))
            resp = _read_response(conn)
        self.assertIn(b"Connection: close", resp)


# ===========================================================================
# 2. Connection header behaviour
# ===========================================================================

class TestConnectionHeaderBehaviour(_ServerTestCase):

    def test_http11_no_connection_header_is_persistent(self):
        """HTTP/1.1 without Connection header keeps the connection open."""
        with self.connect() as conn:
            conn.sendall(_http11("/"))
            r1 = _read_one_response(conn)
            conn.sendall(_http11("/users"))
            r2 = _read_one_response(conn)
        self.assertIn(b"200 OK", r1)
        self.assertIn(b"200 OK", r2)

    def test_http11_connection_keep_alive_explicit(self):
        """HTTP/1.1 with explicit Connection: keep-alive stays open."""
        with self.connect() as conn:
            conn.sendall(_http11("/", "Connection: keep-alive\r\n"))
            r1 = _read_one_response(conn)
            conn.sendall(_http11("/users"))
            r2 = _read_one_response(conn)
        self.assertIn(b"200 OK", r1)
        self.assertIn(b"200 OK", r2)

    def test_http11_connection_close_closes_after_response(self):
        """HTTP/1.1 with Connection: close closes after one response."""
        with self.connect() as conn:
            conn.sendall(_http11("/", "Connection: close\r\n"))
            resp = _read_response(conn)
        self.assertIn(b"200 OK", resp)
        self.assertIn(b"Connection: close", resp)

    def test_http10_default_closes(self):
        """HTTP/1.0 without keep-alive header closes after response."""
        with self.connect() as conn:
            conn.sendall(_http10("/"))
            resp = _read_response(conn)
        self.assertIn(b"200 OK", resp)
        self.assertIn(b"Connection: close", resp)

    def test_http10_explicit_keepalive(self):
        """HTTP/1.0 with Connection: keep-alive stays open."""
        with self.connect() as conn:
            conn.sendall(_http10("/", "Connection: keep-alive\r\n"))
            r1 = _read_one_response(conn)
            conn.sendall(_http10("/users", "Connection: keep-alive\r\n"))
            r2 = _read_one_response(conn)
        self.assertIn(b"200 OK", r1)
        self.assertIn(b"200 OK", r2)

    def test_connection_header_case_insensitive_close(self):
        """Connection: Close (mixed case) is respected."""
        with self.connect() as conn:
            conn.sendall(_http11("/", "Connection: Close\r\n"))
            resp = _read_response(conn)
        self.assertIn(b"200 OK", resp)
        self.assertIn(b"Connection: close", resp)

    def test_connection_header_case_insensitive_keepalive(self):
        """Connection: Keep-Alive (mixed case) is respected."""
        with self.connect() as conn:
            conn.sendall(_http11("/", "Connection: Keep-Alive\r\n"))
            r1 = _read_one_response(conn)
            conn.sendall(_http11("/"))
            r2 = _read_one_response(conn)
        self.assertIn(b"200 OK", r1)
        self.assertIn(b"200 OK", r2)

    def test_connection_close_wins_over_keepalive(self):
        """When both close and keep-alive appear, close wins."""
        with self.connect() as conn:
            conn.sendall(
                _http11("/", "Connection: keep-alive, close\r\n")
            )
            resp = _read_response(conn)
        self.assertIn(b"Connection: close", resp)


# ===========================================================================
# 3. TCP buffering
# ===========================================================================

class TestTCPBuffering(_ServerTestCase):

    def test_request_arrives_in_two_chunks(self):
        """Split a request mid-headers; server must reassemble it."""
        req = _http11("/")
        mid = len(req) // 2
        with self.connect() as conn:
            conn.sendall(req[:mid])
            time.sleep(0.05)
            conn.sendall(req[mid:])
            resp = _read_one_response(conn)
        self.assertIn(b"200 OK", resp)

    def test_request_arrives_byte_by_byte(self):
        """One byte at a time — extreme fragmentation."""
        req = _http11("/")
        with self.connect() as conn:
            for byte in req:
                conn.send(bytes([byte]))
                time.sleep(0.001)
            resp = _read_one_response(conn)
        self.assertIn(b"200 OK", resp)

    def test_two_requests_in_one_write(self):
        """Both requests pipelined in a single sendall."""
        req1 = _http11("/")
        req2 = _http11("/users")
        with self.connect() as conn:
            conn.sendall(req1 + req2)
            r1 = _read_one_response(conn)
            r2 = _read_one_response(conn)
        self.assertIn(b"200 OK", r1)
        self.assertIn(b"Ali", r2)

    def test_headers_and_body_in_separate_chunks(self):
        """POST where headers and body arrive separately."""
        body = b'{"name":"Bilal"}'
        headers = (
            b"POST /users HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n"
        )
        with self.connect() as conn:
            conn.sendall(headers)
            time.sleep(0.05)
            conn.sendall(body)
            resp = _read_one_response(conn)
        self.assertIn(b"201 Created", resp)
        self.assertIn(b"Bilal", resp)

    def test_body_of_first_request_not_mixed_into_second(self):
        """Bodies and next request do not bleed into each other."""
        body1 = b'{"name":"Zara"}'
        req1 = (
            b"POST /users HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body1)).encode() + b"\r\n"
            b"\r\n" + body1
        )
        req2 = _http11("/users")
        with self.connect() as conn:
            conn.sendall(req1 + req2)
            r1 = _read_one_response(conn)
            r2 = _read_one_response(conn)
        self.assertIn(b"201 Created", r1)
        self.assertIn(b"200 OK", r2)

    def test_three_pipelined_requests(self):
        """Three requests pipelined — all responses correct and in order."""
        pipeline = _http11("/") + _http11("/users") + _http11("/products")
        with self.connect() as conn:
            conn.sendall(pipeline)
            r1 = _read_one_response(conn)
            r2 = _read_one_response(conn)
            r3 = _read_one_response(conn)
        self.assertIn(b"200 OK", r1)
        self.assertIn(b"Ali", r2)
        self.assertIn(b"Laptop", r3)

    def test_malformed_request_returns_400(self):
        """A bad request on a persistent connection gets a 400 response."""
        with self.connect() as conn:
            conn.sendall(b"NOT_HTTP\r\n\r\n")
            resp = _read_response(conn)
        self.assertIn(b"400", resp)

    def test_content_length_too_large_returns_400(self):
        """Claimed Content-Length over the limit is rejected."""
        huge = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 99999999\r\n\r\n"
        with self.connect() as conn:
            conn.sendall(huge)
            resp = _read_response(conn)
        self.assertIn(b"400", resp)


# ===========================================================================
# 4. Timeout and disconnect handling
# ===========================================================================

class TestTimeoutAndDisconnect(_ServerTestCase):
    SOCKET_TIMEOUT = 1.0
    KEEP_ALIVE_TIMEOUT = 1.0

    def test_idle_connection_closed_after_timeout(self):
        """Server closes an idle keep-alive connection after the timeout."""
        with self.connect(timeout=5.0) as conn:
            conn.sendall(_http11("/"))
            _read_one_response(conn)
            # Now idle — wait for the server to close.
            conn.settimeout(self.KEEP_ALIVE_TIMEOUT + 1.5)
            data = conn.recv(1)
        # recv returns b"" when the peer closes the connection.
        self.assertEqual(data, b"")

    def test_client_disconnect_mid_headers_does_not_crash_server(self):
        """Client disconnects after sending partial headers."""
        with self.connect() as conn:
            conn.sendall(b"GET / HTTP/1.1\r\n")
            # Close without finishing headers.
        # Server must still respond to other clients.
        with self.connect() as conn2:
            conn2.sendall(_http11("/"))
            resp = _read_response(conn2)
        self.assertIn(b"200 OK", resp)

    def test_client_disconnect_cleanly_between_requests(self):
        """Client closes the connection cleanly after first request."""
        with self.connect() as conn:
            conn.sendall(_http11("/"))
            _read_one_response(conn)
            # Graceful close.
            conn.shutdown(socket.SHUT_WR)
            remaining = _read_response(conn)
        # Server may or may not send anything after SHUT_WR; just ensure
        # no crash and the server is still healthy.
        with self.connect() as conn2:
            conn2.sendall(_http11("/"))
            resp = _read_response(conn2)
        self.assertIn(b"200 OK", resp)

    def test_incomplete_request_times_out(self):
        """A connection stuck mid-request is eventually closed."""
        start = time.monotonic()
        with self.connect(timeout=self.SOCKET_TIMEOUT + 2.0) as conn:
            conn.sendall(b"GET / HTTP/1.1\r\n")  # no \r\n\r\n
            conn.settimeout(self.SOCKET_TIMEOUT + 2.0)
            data = conn.recv(4096)
        elapsed = time.monotonic() - start
        # Server should have closed within timeout + some margin.
        self.assertLess(elapsed, self.SOCKET_TIMEOUT + 2.5)

    def test_resources_released_after_client_disconnect(self):
        """Active thread count returns to baseline after disconnect."""
        baseline = self.server.get_stats()["active_threads"]
        with self.connect() as conn:
            conn.sendall(_http11("/", "Connection: close\r\n"))
            _read_response(conn)
        # Give the thread time to clean up.
        time.sleep(0.3)
        after = self.server.get_stats()["active_threads"]
        self.assertLessEqual(after, baseline)


# ===========================================================================
# 5. Max requests per connection limit
# ===========================================================================

class TestMaxRequestsLimit(_ServerTestCase):
    MAX_REQUESTS = 3

    def test_connection_closed_at_limit(self):
        """Server closes the connection after max_requests_per_connection."""
        with self.connect() as conn:
            # First two requests stay open.
            for _ in range(self.MAX_REQUESTS - 1):
                conn.sendall(_http11("/"))
                resp = _read_one_response(conn)
                self.assertIn(b"Connection: keep-alive", resp)

            # The final (3rd) request should get Connection: close.
            conn.sendall(_http11("/"))
            resp = _read_response(conn)
        self.assertIn(b"Connection: close", resp)


# ===========================================================================
# 6. Integration — routes and static files over one connection
# ===========================================================================

class TestIntegration(_ServerTestCase):

    def test_different_routes_over_one_connection(self):
        """/, /users, /products, /users/1 all succeed on same connection."""
        with self.connect() as conn:
            results = {}
            for path in ["/", "/users", "/products", "/users/1"]:
                conn.sendall(_http11(path))
                results[path] = _read_one_response(conn)

        self.assertIn(b"Hello World", results["/"])
        self.assertIn(b"Ali", results["/users"])
        self.assertIn(b"Laptop", results["/products"])
        self.assertIn(b"Ali", results["/users/1"])

    def test_static_html_and_css_over_one_connection(self):
        """Static HTML then CSS fetched on the same persistent connection."""
        with self.connect() as conn:
            conn.sendall(_http11("/static/index.html"))
            r1 = _read_one_response(conn)
            conn.sendall(_http11("/static/style.css"))
            r2 = _read_one_response(conn)

        self.assertIn(b"200 OK", r1)
        self.assertIn(b"text/html", r1)
        self.assertIn(b"200 OK", r2)
        self.assertIn(b"text/css", r2)

    def test_binary_static_file_over_persistent_connection(self):
        """SVG (binary-ish) file served correctly over keep-alive."""
        with self.connect() as conn:
            conn.sendall(_http11("/static/images/logo.svg"))
            resp = _read_one_response(conn)

        self.assertIn(b"200 OK", resp)
        self.assertIn(b"svg", resp.lower())

    def test_mixed_api_and_static_requests(self):
        """API and static requests interleaved on one connection."""
        with self.connect() as conn:
            conn.sendall(_http11("/users"))
            r1 = _read_one_response(conn)
            conn.sendall(_http11("/static/style.css"))
            r2 = _read_one_response(conn)
            conn.sendall(_http11("/products"))
            r3 = _read_one_response(conn)

        self.assertIn(b"200 OK", r1)
        self.assertIn(b"200 OK", r2)
        self.assertIn(b"200 OK", r3)

    def test_404_then_200_on_same_connection(self):
        """A 404 does not close a persistent connection."""
        with self.connect() as conn:
            conn.sendall(_http11("/nonexistent"))
            r1 = _read_one_response(conn)
            conn.sendall(_http11("/"))
            r2 = _read_one_response(conn)

        self.assertIn(b"404", r1)
        self.assertIn(b"200 OK", r2)

    def test_concurrent_persistent_clients(self):
        """Multiple clients each using persistent connections concurrently."""
        errors = []
        results = []

        def client_task():
            try:
                with self.connect() as conn:
                    for path in ["/", "/users", "/products"]:
                        conn.sendall(_http11(path))
                        resp = _read_one_response(conn)
                        results.append(b"200 OK" in resp)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=client_task) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=8)

        self.assertEqual(errors, [], msg=f"Client errors: {errors}")
        self.assertEqual(len(results), 30)
        self.assertTrue(all(results))


if __name__ == "__main__":
    unittest.main()
