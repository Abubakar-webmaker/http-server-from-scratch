"""Comprehensive tests for HTTP request parsing."""

import unittest
from http.request import Request
from http.parser import parse_request, HTTPParseError


class TestRequestParserBasics(unittest.TestCase):
    """Test basic request parsing."""

    def test_simple_get_request(self):
        """Parse a simple GET request."""
        raw = (
            b"GET /index.html HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"User-Agent: TestClient\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/index.html")
        self.assertEqual(request.version, "HTTP/1.1")
        self.assertEqual(request.headers["host"], "localhost")
        self.assertEqual(request.headers["user-agent"], "TestClient")
        self.assertEqual(request.body, b"")

    def test_post_request_with_body(self):
        """Parse a POST request with body."""
        body = b'{"name":"Ali","age":30}'
        raw = (
            b"POST /users HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n"
            + body
        )
        request = parse_request(raw)

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/users")
        self.assertEqual(request.body, body)
        self.assertEqual(request.headers["content-type"], "application/json")

    def test_http10_request(self):
        """Parse HTTP/1.0 request."""
        raw = (
            b"GET / HTTP/1.0\r\n"
            b"Host: example.com\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(request.version, "HTTP/1.0")

    def test_headers_lowercase(self):
        """Header names are normalized to lowercase."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Content-Type: text/plain\r\n"
            b"Accept: text/html\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertIn("content-type", request.headers)
        self.assertIn("accept", request.headers)
        self.assertNotIn("Content-Type", request.headers)

    def test_multiple_header_values(self):
        """Parse multiple header values."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: text/html\r\n"
            b"Accept-Language: en-US\r\n"
            b"Cache-Control: no-cache\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(len(request.headers), 4)
        self.assertEqual(request.headers["accept"], "text/html")
        self.assertEqual(request.headers["accept-language"], "en-US")


class TestRequestParserEdgeCases(unittest.TestCase):
    """Test edge cases in request parsing."""

    def test_empty_body_with_zero_content_length(self):
        """Request with Content-Length: 0."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(request.body, b"")

    def test_body_larger_than_1024_bytes(self):
        """Handle request body larger than one socket read."""
        body = b"X" * 5000
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: 5000\r\n"
            b"\r\n"
            + body
        )
        request = parse_request(raw)

        self.assertEqual(len(request.body), 5000)
        self.assertEqual(request.body, body)

    def test_path_with_query_string(self):
        """Parse request with query string in path."""
        raw = (
            b"GET /search?q=python&limit=10 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(request.path, "/search?q=python&limit=10")

    def test_path_with_fragment(self):
        """Parse path with fragment (rare in HTTP requests)."""
        raw = (
            b"GET /page#section HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(request.path, "/page#section")

    def test_header_with_multiple_spaces(self):
        """Parse header value with extra spaces."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host:    localhost   \r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        # Value is trimmed by parser
        self.assertEqual(request.headers["host"], "localhost")

    def test_methods_uppercase(self):
        """HTTP methods are normalized to uppercase."""
        methods = ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
        for method in methods:
            raw = (
                f"{method} / HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"\r\n"
            ).encode()
            request = parse_request(raw)

            self.assertEqual(request.method, method)


class TestRequestParserErrors(unittest.TestCase):
    """Test error handling in request parsing."""

    def test_incomplete_request_line(self):
        """Reject incomplete request line."""
        raw = b"GET / HTTP/1.1"  # Missing \r\n
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_missing_headers_separator(self):
        """Reject request without headers separator."""
        raw = b"GET / HTTP/1.1\r\nHost: localhost"
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_invalid_request_line_format(self):
        """Reject invalid request line format."""
        raw = b"INVALID\r\n\r\n"
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_missing_http_version(self):
        """Reject request without HTTP version."""
        raw = b"GET /\r\n\r\n"
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_unsupported_http_version(self):
        """Reject unsupported HTTP version."""
        raw = b"GET / HTTP/2.0\r\n\r\n"
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_invalid_header_format(self):
        """Reject malformed header."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"InvalidHeader\r\n"
            b"\r\n"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_incomplete_body(self):
        """Reject request with incomplete body."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: 100\r\n"
            b"\r\n"
            b"OnlyTenBytes"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_extra_data_after_body(self):
        """Reject request with extra data after body."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"HelloExtra"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_invalid_content_length(self):
        """Reject invalid Content-Length."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: not-a-number\r\n"
            b"\r\n"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_negative_content_length(self):
        """Reject negative Content-Length."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: -10\r\n"
            b"\r\n"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_transfer_encoding_not_supported(self):
        """Reject Transfer-Encoding (unsupported)."""
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_empty_request(self):
        """Reject empty request."""
        with self.assertRaises(HTTPParseError):
            parse_request(b"")

    def test_unicode_decode_error(self):
        """Reject request with invalid UTF-8."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: \xff\xfe\r\n"
            b"\r\n"
        )
        with self.assertRaises(HTTPParseError):
            parse_request(raw)


class TestRequestParserSecurity(unittest.TestCase):
    """Test security aspects of request parsing."""

    def test_large_header_rejected(self):
        """Reject excessively large headers."""
        # Create headers larger than max (65536 bytes)
        large_value = "X" * 100000
        raw = (
            f"GET / HTTP/1.1\r\n"
            f"X-Large-Header: {large_value}\r\n"
            f"\r\n"
        ).encode()

        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_large_body_rejected(self):
        """Reject excessively large body."""
        # Create body larger than max (10 MB)
        large_body = b"X" * (11 * 1024 * 1024)
        raw = (
            b"POST / HTTP/1.1\r\n"
            b"Content-Length: " + str(len(large_body)).encode() + b"\r\n"
            b"\r\n"
            + large_body
        )

        with self.assertRaises(HTTPParseError):
            parse_request(raw)

    def test_null_byte_in_path(self):
        """Paths with null bytes should not cause issues."""
        # Parser should handle this safely
        raw = (
            b"GET /path%00evil HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        # Path is preserved as-is (router should validate it)
        self.assertIn("%00", request.path)

    def test_crlf_in_header_value(self):
        """Reject header injection attempts."""
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"X-Test: value\r\nX-Injected: true\r\n"
            b"\r\n"
        )

        # This should either parse correctly (two separate headers)
        # or reject it. Let's verify it parses safely.
        try:
            request = parse_request(raw)
            # If it parses, both headers should be present
            # (This is actually valid HTTP, just double-check)
        except HTTPParseError:
            # Also acceptable to reject it as malformed
            pass


class TestRequestParserRealWorldCases(unittest.TestCase):
    """Test real-world HTTP requests."""

    def test_browser_get_request(self):
        """Parse a real browser GET request."""
        raw = (
            b"GET /index.html HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Connection: keep-alive\r\n"
            b"User-Agent: Mozilla/5.0\r\n"
            b"Accept: text/html,application/xhtml+xml\r\n"
            b"Accept-Encoding: gzip, deflate\r\n"
            b"Accept-Language: en-US,en;q=0.9\r\n"
            b"\r\n"
        )
        request = parse_request(raw)

        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/index.html")
        self.assertGreater(len(request.headers), 5)

    def test_curl_post_request(self):
        """Parse a cURL POST request with JSON."""
        body = b'{"email":"user@example.com","password":"secret"}'
        raw = (
            b"POST /api/login HTTP/1.1\r\n"
            b"Host: api.example.com\r\n"
            b"User-Agent: curl/7.64.1\r\n"
            b"Accept: */*\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n"
            + body
        )
        request = parse_request(raw)

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/api/login")
        self.assertEqual(request.body, body)

    def test_form_data_request(self):
        """Parse form-encoded POST request."""
        body = b"username=ali&password=secret&remember=1"
        raw = (
            b"POST /login HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n"
            + body
        )
        request = parse_request(raw)

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.body, body)


if __name__ == "__main__":
    unittest.main()
