"""Comprehensive tests for HTTP response building."""

import unittest
from http.response import Response, serialize_response
from http.request import Request


class TestResponseBuilder(unittest.TestCase):
    """Test Response object creation."""

    def test_simple_response(self):
        """Create a simple response."""
        response = Response(200, "Hello World")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"Hello World")

    def test_response_with_headers(self):
        """Response with custom headers."""
        response = Response(
            200,
            "OK",
            {"Content-Type": "text/plain", "X-Custom": "value"}
        )

        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.headers["X-Custom"], "value")

    def test_response_string_to_bytes(self):
        """String body is converted to bytes."""
        response = Response(200, "Hello")

        self.assertIsInstance(response.body, bytes)
        self.assertEqual(response.body, b"Hello")

    def test_response_bytes_preserved(self):
        """Bytes body is preserved."""
        body = b"\x00\x01\x02\xff"
        response = Response(200, body)

        self.assertEqual(response.body, body)

    def test_status_codes(self):
        """Various status codes."""
        codes = [200, 201, 204, 301, 304, 400, 401, 403, 404, 405, 500, 503]
        for code in codes:
            response = Response(code, "")
            self.assertEqual(response.status_code, code)


class TestResponseSerialization(unittest.TestCase):
    """Test response serialization."""

    def test_serialize_simple_response(self):
        """Serialize a simple response."""
        response = Response(200, "Hello")
        serialized = serialize_response(response)

        self.assertIn(b"HTTP/1.1 200 OK", serialized)
        self.assertIn(b"Hello", serialized)
        self.assertTrue(serialized.endswith(b"Hello"))

    def test_serialize_has_content_length(self):
        """Serialized response includes Content-Length."""
        response = Response(200, "Hello")
        serialized = serialize_response(response)

        self.assertIn(b"Content-Length: 5", serialized)

    def test_serialize_has_connection_close(self):
        """Serialized response includes Connection header."""
        response = Response(200, "Test")
        serialized = serialize_response(response)

        self.assertIn(b"Connection:", serialized)

    def test_serialize_keep_alive(self):
        """Response can be serialized with keep-alive."""
        response = Response(200, "Test")
        serialized = serialize_response(response, keep_alive=True)

        self.assertIn(b"Connection: keep-alive", serialized)

    def test_serialize_close(self):
        """Response can be serialized with connection close."""
        response = Response(200, "Test")
        serialized = serialize_response(response, keep_alive=False)

        self.assertIn(b"Connection: close", serialized)

    def test_serialize_has_headers_separator(self):
        """Serialized response has \r\n\r\n separator."""
        response = Response(200, "Body")
        serialized = serialize_response(response)

        self.assertIn(b"\r\n\r\n", serialized)

    def test_serialize_custom_headers(self):
        """Custom headers are in serialized response."""
        response = Response(200, "OK", {"X-Custom": "value"})
        serialized = serialize_response(response)

        self.assertIn(b"X-Custom: value", serialized)

    def test_serialize_multiple_headers(self):
        """Multiple headers are all included."""
        response = Response(
            200,
            "OK",
            {
                "Content-Type": "application/json",
                "X-Request-ID": "123",
                "Cache-Control": "no-cache"
            }
        )
        serialized = serialize_response(response)

        self.assertIn(b"Content-Type: application/json", serialized)
        self.assertIn(b"X-Request-ID: 123", serialized)
        self.assertIn(b"Cache-Control: no-cache", serialized)

    def test_serialize_utf8_body(self):
        """UTF-8 body is correctly encoded."""
        response = Response(200, "Hello — World")
        serialized = serialize_response(response)

        self.assertIn("Hello — World".encode("utf-8"), serialized)

    def test_serialize_binary_body(self):
        """Binary body is preserved."""
        body = b"\x89PNG\r\n\x1a\n"
        response = Response(200, body)
        serialized = serialize_response(response)

        self.assertIn(body, serialized)

    def test_serialize_empty_body(self):
        """Empty body is handled."""
        response = Response(204, "")
        serialized = serialize_response(response)

        self.assertIn(b"Content-Length: 0", serialized)

    def test_serialize_status_line(self):
        """Status line format is correct."""
        tests = [
            (200, b"HTTP/1.1 200 OK"),
            (201, b"HTTP/1.1 201 Created"),
            (404, b"HTTP/1.1 404 Not Found"),
            (500, b"HTTP/1.1 500 Internal Server Error"),
        ]

        for code, expected_line in tests:
            response = Response(code, "")
            serialized = serialize_response(response)
            self.assertIn(expected_line, serialized)

    def test_serialize_header_value_with_spaces(self):
        """Header values with spaces are preserved."""
        response = Response(200, "OK", {"X-Description": "This is a description"})
        serialized = serialize_response(response)

        self.assertIn(b"X-Description: This is a description", serialized)

    def test_serialize_no_unsafe_headers(self):
        """Headers with CRLF are rejected."""
        response = Response(200, "OK", {"X-Test": "value\r\nX-Injected: true"})

        with self.assertRaises(ValueError):
            serialize_response(response)


class TestResponseSerializationWithKeepAlive(unittest.TestCase):
    """Test response serialization with keep-alive flag."""

    def test_keep_alive_true(self):
        """keep_alive=True produces keep-alive header."""
        response = Response(200, "OK")
        serialized = serialize_response(response, keep_alive=True)

        self.assertIn(b"Connection: keep-alive", serialized)
        self.assertNotIn(b"Connection: close", serialized)

    def test_keep_alive_false(self):
        """keep_alive=False produces close header."""
        response = Response(200, "OK")
        serialized = serialize_response(response, keep_alive=False)

        self.assertIn(b"Connection: close", serialized)

    def test_handler_connection_header_overridden(self):
        """Handler's Connection header is overridden by keep_alive flag."""
        response = Response(
            200,
            "OK",
            {"Connection": "keep-alive"}  # Handler says keep-alive
        )

        # But server says close
        serialized = serialize_response(response, keep_alive=False)

        # Server's decision wins
        self.assertIn(b"Connection: close", serialized)

    def test_multiple_requests_keep_alive(self):
        """Multiple responses with keep-alive can be serialized."""
        responses = [
            Response(200, "Response 1"),
            Response(200, "Response 2"),
            Response(200, "Response 3"),
        ]

        for response in responses:
            serialized = serialize_response(response, keep_alive=True)
            self.assertIn(b"Connection: keep-alive", serialized)


class TestResponseStatusCodes(unittest.TestCase):
    """Test various HTTP status codes."""

    def test_all_supported_status_codes(self):
        """All documented status codes serialize correctly."""
        codes_and_messages = [
            (200, b"200 OK"),
            (201, b"201 Created"),
            (204, b"204 No Content"),
            (304, b"304 Not Modified"),
            (400, b"400 Bad Request"),
            (401, b"401 Unauthorized"),
            (403, b"403 Forbidden"),
            (404, b"404 Not Found"),
            (405, b"405 Method Not Allowed"),
            (413, b"413 Payload Too Large"),
            (500, b"500 Internal Server Error"),
            (503, b"503 Service Unavailable"),
        ]

        for code, expected_msg in codes_and_messages:
            response = Response(code, "")
            serialized = serialize_response(response)
            self.assertIn(expected_msg, serialized)

    def test_unsupported_status_code_rejected(self):
        """Unsupported status code raises error."""
        response = Response(999, "")

        with self.assertRaises(ValueError):
            serialize_response(response)

    def test_redirect_status_codes(self):
        """Redirect status codes work (3xx)."""
        response = Response(301, "", {"Location": "/new-path"})
        serialized = serialize_response(response)

        self.assertIn(b"301", serialized)
        self.assertIn(b"Location: /new-path", serialized)


class TestResponseContentLength(unittest.TestCase):
    """Test Content-Length handling."""

    def test_content_length_calculation(self):
        """Content-Length is calculated correctly."""
        body = "Hello World"
        response = Response(200, body)
        serialized = serialize_response(response)

        expected_length = len(body.encode("utf-8"))
        self.assertIn(f"Content-Length: {expected_length}".encode(), serialized)

    def test_content_length_binary(self):
        """Content-Length for binary data."""
        body = b"\x00\x01\x02\x03\x04"
        response = Response(200, body)
        serialized = serialize_response(response)

        self.assertIn(b"Content-Length: 5", serialized)

    def test_content_length_utf8_multibyte(self):
        """Content-Length for multi-byte UTF-8."""
        body = "日本語"  # 9 bytes in UTF-8
        response = Response(200, body)
        serialized = serialize_response(response)

        self.assertIn(b"Content-Length: 9", serialized)

    def test_content_length_empty_body(self):
        """Content-Length for empty body."""
        response = Response(200, "")
        serialized = serialize_response(response)

        self.assertIn(b"Content-Length: 0", serialized)


class TestResponseHeadersHandling(unittest.TestCase):
    """Test header handling in responses."""

    def test_default_content_type_added(self):
        """Default Content-Type is added if missing."""
        response = Response(200, "Text")
        serialized = serialize_response(response)

        self.assertIn(b"Content-Type: text/plain", serialized)

    def test_custom_content_type_preserved(self):
        """Custom Content-Type is not replaced."""
        response = Response(
            200,
            '{"key": "value"}',
            {"Content-Type": "application/json"}
        )
        serialized = serialize_response(response)

        self.assertIn(b"Content-Type: application/json", serialized)
        self.assertNotIn(b"Content-Type: text/plain", serialized)

    def test_case_insensitive_header_detection(self):
        """Header detection is case-insensitive."""
        response = Response(
            200,
            "Data",
            {"content-TYPE": "text/custom"}  # Mixed case
        )
        serialized = serialize_response(response)

        # Should not add default since custom is present
        self.assertIn(b"content-TYPE: text/custom", serialized)


if __name__ == "__main__":
    unittest.main()
