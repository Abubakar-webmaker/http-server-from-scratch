"""Tests for gzip compression."""

import unittest
import gzip
import io

from http.response import Response
from gzip_support.gzip_handler import (
    compress_response,
    client_accepts_gzip,
    parse_accept_encoding,
    should_compress,
)


class TestGzipCompression(unittest.TestCase):
    """Test gzip compression functionality."""

    def test_client_accepts_gzip_simple(self):
        """Client accepts gzip with simple header."""
        self.assertTrue(client_accepts_gzip("gzip"))

    def test_client_accepts_gzip_with_deflate(self):
        """Client accepts multiple encodings."""
        self.assertTrue(client_accepts_gzip("gzip, deflate"))

    def test_client_does_not_accept_gzip(self):
        """Client does not accept gzip."""
        self.assertFalse(client_accepts_gzip("deflate"))

    def test_client_rejects_gzip_with_q0(self):
        """Client rejects gzip explicitly with q=0."""
        self.assertFalse(client_accepts_gzip("gzip;q=0"))

    def test_parse_accept_encoding_single(self):
        """Parse single encoding."""
        result = parse_accept_encoding("gzip")
        self.assertEqual(result["gzip"], 1.0)

    def test_parse_accept_encoding_multiple(self):
        """Parse multiple encodings with quality values."""
        result = parse_accept_encoding("gzip;q=0.8, deflate;q=0.9")
        self.assertEqual(result["gzip"], 0.8)
        self.assertEqual(result["deflate"], 0.9)

    def test_parse_accept_encoding_whitespace(self):
        """Parse with extra whitespace."""
        result = parse_accept_encoding("gzip ; q = 0.5")
        self.assertEqual(result["gzip"], 0.5)

    def test_parse_accept_encoding_empty(self):
        """Parse empty Accept-Encoding."""
        result = parse_accept_encoding("")
        self.assertEqual(result, {})

    def test_should_compress_text(self):
        """Text content should be compressed."""
        response = Response(200, "Hello World" * 200)
        response.headers["Content-Type"] = "text/plain"
        self.assertTrue(should_compress(response))

    def test_should_compress_json(self):
        """JSON content should be compressed."""
        response = Response(200, '{"data": "' + "x" * 1000 + '"}')
        response.headers["Content-Type"] = "application/json"
        self.assertTrue(should_compress(response))

    def test_should_not_compress_small_body(self):
        """Small bodies should not be compressed."""
        response = Response(200, "Hi")
        response.headers["Content-Type"] = "text/plain"
        self.assertFalse(should_compress(response))

    def test_should_not_compress_already_compressed(self):
        """Already-compressed content should not be re-compressed."""
        response = Response(200, b"\x1f\x8b\x08")  # gzip magic number
        response.headers["Content-Type"] = "application/gzip"
        self.assertFalse(should_compress(response))

    def test_should_not_compress_image(self):
        """Image content should not be compressed."""
        response = Response(200, b"\x89PNG\r\n")
        response.headers["Content-Type"] = "image/png"
        self.assertFalse(should_compress(response))

    def test_should_not_compress_empty_body(self):
        """Empty body should not be compressed."""
        response = Response(200, "")
        response.headers["Content-Type"] = "text/plain"
        self.assertFalse(should_compress(response))

    def test_should_not_compress_304(self):
        """304 Not Modified should not be compressed."""
        response = Response(304, "")
        self.assertFalse(should_compress(response))

    def test_compress_response_with_gzip_support(self):
        """Compress response when client supports gzip."""
        response = Response(200, "Hello World" * 500)
        response.headers["Content-Type"] = "text/plain"

        compressed, was_compressed = compress_response(response, "gzip")

        self.assertTrue(was_compressed)
        self.assertIn("Content-Encoding", compressed.headers)
        self.assertEqual(compressed.headers["Content-Encoding"], "gzip")

    def test_compress_response_without_gzip_support(self):
        """Do not compress if client doesn't support gzip."""
        response = Response(200, "Hello World" * 500)
        response.headers["Content-Type"] = "text/plain"

        compressed, was_compressed = compress_response(response, "deflate")

        self.assertFalse(was_compressed)
        self.assertEqual(compressed, response)

    def test_compressed_body_decompresses_correctly(self):
        """Compressed body can be decompressed."""
        original_text = "Hello World" * 500
        response = Response(200, original_text)
        response.headers["Content-Type"] = "text/plain"

        compressed, _ = compress_response(response, "gzip")

        # Decompress and verify
        decompressed = gzip.decompress(compressed.body)
        self.assertEqual(decompressed.decode("utf-8"), original_text)

    def test_compression_adds_vary_header(self):
        """Compression adds Vary: Accept-Encoding."""
        response = Response(200, "Hello World" * 500)
        response.headers["Content-Type"] = "text/plain"

        compressed, was_compressed = compress_response(response, "gzip")

        if was_compressed:
            self.assertIn("Vary", compressed.headers)
            self.assertEqual(compressed.headers["Vary"], "Accept-Encoding")

    def test_no_compression_if_no_savings(self):
        """Don't use compression if it doesn't reduce size."""
        response = Response(200, b"\xff\xff\xff\xff\xff")  # Random-looking bytes
        response.headers["Content-Type"] = "application/octet-stream"

        compressed, was_compressed = compress_response(response, "gzip")

        # For small random data, compression often expands
        self.assertFalse(was_compressed)


if __name__ == "__main__":
    unittest.main()
