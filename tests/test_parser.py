import unittest

from http.parser import parse_request, HTTPParseError


class FakeSocket:
    """A simple socket replacement for unit testing."""

    def __init__(self, data, chunk_size=1024):
        self.data = data
        self.chunk_size = chunk_size

    def recv(self, size):
        if not self.data:
            return b""

        amount = min(size, self.chunk_size, len(self.data))
        chunk = self.data[:amount]
        self.data = self.data[amount:]

        return chunk


class TestHTTPParser(unittest.TestCase):

    def test_get_request(self):
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"User-Agent: test-client\r\n"
            b"\r\n"
        )

        request = parse_request(FakeSocket(raw))

        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/")
        self.assertEqual(request.version, "HTTP/1.1")
        self.assertEqual(request.headers["host"], "localhost")
        self.assertEqual(request.body, b"")

    def test_header_names_are_lowercase(self):
        raw = (
            b"GET /test HTTP/1.1\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
        )

        request = parse_request(FakeSocket(raw))

        self.assertIn("content-type", request.headers)
        self.assertNotIn("Content-Type", request.headers)

    def test_post_request_with_body(self):
        body = b"Hello World"

        raw = (
            b"POST /submit HTTP/1.1\r\n"
            b"Content-Length: 11\r\n"
            b"\r\n"
            + body
        )

        request = parse_request(FakeSocket(raw))

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/submit")
        self.assertEqual(request.body, body)

    def test_body_larger_than_1024_bytes(self):
        body = b"A" * 5000

        raw = (
            b"POST /upload HTTP/1.1\r\n"
            b"Content-Length: 5000\r\n"
            b"\r\n"
            + body
        )

        request = parse_request(
            FakeSocket(raw, chunk_size=1024)
        )

        self.assertEqual(len(request.body), 5000)
        self.assertEqual(request.body, body)

    def test_request_with_invalid_content_length(self):
        raw = (
            b"POST /submit HTTP/1.1\r\n"
            b"Content-Length: invalid\r\n"
            b"\r\n"
        )

        with self.assertRaises(HTTPParseError):
            parse_request(FakeSocket(raw))

    def test_chunked_encoding_is_rejected(self):
        raw = (
            b"POST /submit HTTP/1.1\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
        )

        with self.assertRaises(HTTPParseError):
            parse_request(FakeSocket(raw))

    def test_invalid_request_line(self):
        raw = b"INVALID_REQUEST\r\n\r\n"

        with self.assertRaises(HTTPParseError):
            parse_request(FakeSocket(raw))

    def test_incomplete_body_is_rejected(self):
        raw = (
            b"POST /submit HTTP/1.1\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"Hello"
        )

        with self.assertRaises(HTTPParseError):
            parse_request(FakeSocket(raw))


if __name__ == "__main__":
    unittest.main()