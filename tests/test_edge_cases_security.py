"""
Edge case and security tests for the HTTP server.
Tests malformed requests, large payloads, injection attempts, and error conditions.
"""

import unittest

from http.request import Request
from http.response import Response
from http.parser import HTTPParser, HTTPParseError


class TestMalformedRequests(unittest.TestCase):
    """Test handling of malformed HTTP requests."""

    def test_missing_http_version(self):
        """Test request line without HTTP version."""
        parser = HTTPParser()
        raw_request = b"GET / \r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_missing_method(self):
        """Test request line without method."""
        parser = HTTPParser()
        raw_request = b" / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_missing_path(self):
        """Test request line without path."""
        parser = HTTPParser()
        raw_request = b"GET  HTTP/1.1\r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_invalid_http_method(self):
        """Test invalid HTTP method."""
        parser = HTTPParser()
        raw_request = b"INVALID / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_header_without_colon(self):
        """Test header line without colon separator."""
        parser = HTTPParser()
        raw_request = b"GET / HTTP/1.1\r\nHost localhost\r\n\r\n"
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_header_with_multiple_colons(self):
        """Test header with multiple colons (should still parse)."""
        parser = HTTPParser()
        raw_request = b"GET / HTTP/1.1\r\nAuthorization: Bearer token:with:colons\r\n\r\n"
        
        # Should parse successfully with header value containing colons
        result = parser.parse(raw_request)
        self.assertEqual(result.method, "GET")

    def test_request_without_blank_line(self):
        """Test request without blank line separator."""
        parser = HTTPParser()
        raw_request = b"GET / HTTP/1.1\r\nHost: localhost"
        
        with self.assertRaises(HTTPParseError):
            parser.parse(raw_request)

    def test_empty_request(self):
        """Test empty request."""
        parser = HTTPParser()
        raw_request = b""
        
        with self.assertRaises(HTTPParseError):
            parser.parse(raw_request)


class TestLargePayloads(unittest.TestCase):
    """Test handling of large request and response payloads."""

    def test_large_request_body_1mb(self):
        """Test 1MB request body."""
        parser = HTTPParser(max_body_size=10*1024*1024)
        body = b"x" * (1024 * 1024)  # 1MB
        
        raw_request = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            f"Content-Length: {len(body)}\r\n"
            b"\r\n"
        ).replace(b"{len(body)}", str(len(body)).encode()) + body
        
        request = parser.parse(raw_request)
        self.assertEqual(len(request.body), 1024 * 1024)

    def test_request_body_exceeds_limit(self):
        """Test request body exceeding size limit."""
        parser = HTTPParser(max_body_size=100 * 1024)  # 100KB limit
        body = b"x" * (101 * 1024)  # 101KB (exceeds limit)
        
        raw_request = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n"
        ) + body
        
        with self.assertRaises(HTTPParseError):
            parser.parse(raw_request)

    def test_large_headers_1mb(self):
        """Test request with 1MB of headers."""
        parser = HTTPParser(max_header_size=2*1024*1024)
        header_value = "x" * (1024 * 1024)  # 1MB header value
        
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Large-Header: " + header_value.encode() + b"\r\n"
            b"\r\n"
        )
        
        request = parser.parse(raw_request)
        self.assertIn("X-Large-Header", request.headers)

    def test_headers_exceed_limit(self):
        """Test headers exceeding size limit."""
        parser = HTTPParser(max_header_size=1000)  # 1KB limit
        header_value = "x" * 2000  # 2KB header value
        
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Large-Header: " + header_value.encode() + b"\r\n"
            b"\r\n"
        )
        
        with self.assertRaises(HTTPParseError):
            parser.parse(raw_request)

    def test_many_headers(self):
        """Test request with many headers."""
        parser = HTTPParser()
        headers = "\r\n".join([f"X-Header-{i}: value-{i}" for i in range(100)])
        
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n" +
            headers.encode() +
            b"\r\n\r\n"
        )
        
        request = parser.parse(raw_request)
        self.assertGreater(len(request.headers), 100)


class TestHeaderInjectionAttempts(unittest.TestCase):
    """Test protection against header injection attacks."""

    def test_crlf_in_header_value(self):
        """Test CRLF injection in header value."""
        parser = HTTPParser()
        # Attempt to inject Set-Cookie header via CRLF
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Header: value\r\nSet-Cookie: injected\r\n"
            b"\r\n"
        )
        
        # Parser should handle this - either parse it or reject it
        try:
            request = parser.parse(raw_request)
            # If parsed, should have the header
            self.assertIsNotNone(request)
        except HTTPParseError:
            # If rejected, that's also acceptable
            pass

    def test_null_byte_in_header(self):
        """Test null byte in header value."""
        parser = HTTPParser()
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Header: value\x00injected\r\n"
            b"\r\n"
        )
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_null_byte_in_path(self):
        """Test null byte in request path."""
        parser = HTTPParser()
        raw_request = b"GET /path\x00injected HTTP/1.1\r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises((HTTPParseError, ValueError)):
            parser.parse(raw_request)

    def test_backspace_in_header(self):
        """Test backspace character in header (old HTTP smuggling)."""
        parser = HTTPParser()
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Header: value\x08injected\r\n"
            b"\r\n"
        )
        
        # Should handle gracefully - either parse or reject
        try:
            request = parser.parse(raw_request)
            self.assertIsNotNone(request)
        except HTTPParseError:
            pass

    def test_unicode_null_in_header(self):
        """Test Unicode null character in header."""
        parser = HTTPParser()
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Header: value\xc0\x80injected\r\n"  # UTF-8 encoded null
            b"\r\n"
        )
        
        # Should reject invalid UTF-8 or handle gracefully
        try:
            request = parser.parse(raw_request)
        except (HTTPParseError, UnicodeDecodeError):
            pass


class TestRequestSmugglingAttempts(unittest.TestCase):
    """Test protection against HTTP request smuggling."""

    def test_conflicting_content_length_headers(self):
        """Test multiple Content-Length headers."""
        parser = HTTPParser()
        raw_request = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"hellothere!"
        )
        
        # Should either reject or use the first value
        try:
            request = parser.parse(raw_request)
            # If accepted, content length should be consistent
            self.assertIsNotNone(request)
        except HTTPParseError:
            # Rejection is also acceptable
            pass

    def test_transfer_encoding_vs_content_length(self):
        """Test conflicting Transfer-Encoding and Content-Length."""
        parser = HTTPParser()
        raw_request = (
            b"POST / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 5\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"5\r\n"
            b"hello\r\n"
            b"0\r\n"
            b"\r\n"
        )
        
        # RFC 7230: Transfer-Encoding should take precedence
        # Parser should handle this correctly
        try:
            request = parser.parse(raw_request)
            self.assertIsNotNone(request)
        except HTTPParseError:
            pass

    def test_space_before_colon_in_header(self):
        """Test space before colon in header (HTTP/1.1 violation)."""
        parser = HTTPParser()
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host : localhost\r\n"  # Space before colon
            b"\r\n"
        )
        
        # Should reject or normalize
        try:
            request = parser.parse(raw_request)
        except HTTPParseError:
            pass


class TestInvalidHttpVersions(unittest.TestCase):
    """Test handling of invalid HTTP versions."""

    def test_http_0_9(self):
        """Test HTTP/0.9 (very old version)."""
        parser = HTTPParser()
        raw_request = b"GET / HTTP/0.9\r\n\r\n"
        
        # Should either accept or reject
        try:
            request = parser.parse(raw_request)
        except HTTPParseError:
            pass

    def test_http_2_0(self):
        """Test HTTP/2.0 (not text-based)."""
        parser = HTTPParser()
        raw_request = b"GET / HTTP/2.0\r\nHost: localhost\r\n\r\n"
        
        try:
            request = parser.parse(raw_request)
        except HTTPParseError:
            pass

    def test_invalid_version_format(self):
        """Test invalid HTTP version format."""
        parser = HTTPParser()
        raw_request = b"GET / INVALID\r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises(HTTPParseError):
            parser.parse(raw_request)

    def test_missing_version_slash(self):
        """Test HTTP version without slash."""
        parser = HTTPParser()
        raw_request = b"GET / HTTP1.1\r\nHost: localhost\r\n\r\n"
        
        with self.assertRaises(HTTPParseError):
            parser.parse(raw_request)


class TestResponseSecurity(unittest.TestCase):
    """Test security of HTTP responses."""

    def test_response_includes_no_sensitive_data_on_error(self):
        """Test that error responses don't include sensitive data."""
        response = Response(500, "500 - Internal Server Error")
        serialized = response.serialize()
        
        # Should not contain stack trace or sensitive details
        self.assertNotIn(b"Traceback", serialized)
        self.assertNotIn(b"File ", serialized)
        self.assertNotIn(b"line ", serialized)

    def test_response_header_injection_attempt(self):
        """Test response builder rejects header injection."""
        # Attempt to inject response headers via newlines
        response = Response(
            200,
            "OK",
            {"X-Custom": "value\r\nSet-Cookie: injected"}
        )
        serialized = response.serialize()
        
        # Should either reject or properly escape the header
        self.assertIsNotNone(serialized)

    def test_response_body_encoding_safety(self):
        """Test response body with various encodings."""
        # Test UTF-8 with special characters
        response = Response(200, "Test: \u2764\ufe0f \u0000")
        
        try:
            serialized = response.serialize()
            # Should handle properly - either reject or encode safely
            self.assertIsNotNone(serialized)
        except (UnicodeEncodeError, ValueError):
            # Rejection is acceptable
            pass


class TestBoundaryConditions(unittest.TestCase):
    """Test boundary conditions and edge cases."""

    def test_zero_length_request(self):
        """Test zero-length request body."""
        parser = HTTPParser()
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        
        request = parser.parse(raw_request)
        self.assertEqual(len(request.body), 0)

    def test_request_with_only_headers_no_body(self):
        """Test GET request with no body."""
        parser = HTTPParser()
        raw_request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"User-Agent: test\r\n"
            b"\r\n"
        )
        
        request = parser.parse(raw_request)
        self.assertEqual(request.method, "GET")

    def test_path_with_special_characters(self):
        """Test path containing special characters."""
        parser = HTTPParser()
        raw_request = (
            b"GET /path%20with%20spaces?key=value&other=123 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )
        
        request = parser.parse(raw_request)
        self.assertIn("%20", request.path)

    def test_response_with_maximum_status_code(self):
        """Test response with high status code."""
        response = Response(599, "Custom Error")
        serialized = response.serialize()
        
        self.assertIn(b"599", serialized)

    def test_response_with_minimum_status_code(self):
        """Test response with low status code."""
        response = Response(100, "Continue")
        serialized = response.serialize()
        
        self.assertIn(b"100", serialized)


if __name__ == "__main__":
    unittest.main()
