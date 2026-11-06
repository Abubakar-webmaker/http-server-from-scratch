"""Tests for HTTP/1.1 chunked transfer encoding."""

import unittest
from http.chunked import ChunkedDecoder, decode_chunked
from utils.exceptions import BadRequestError


class TestChunkedDecoding(unittest.TestCase):
    """Test chunked transfer encoding decoding."""

    def test_single_chunk(self):
        """Decode a single chunk."""
        data = b"5\r\nHello\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"Hello")

    def test_multiple_chunks(self):
        """Decode multiple chunks."""
        data = b"5\r\nHello\r\n1\r\n \r\n5\r\nWorld\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"Hello World")

    def test_empty_body(self):
        """Decode an empty chunked body."""
        data = b"0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"")

    def test_chunk_size_hex(self):
        """Chunk size is hexadecimal."""
        # 0x0a = 10
        data = b"a\r\n0123456789\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"0123456789")

    def test_chunk_size_uppercase_hex(self):
        """Chunk size hex letters can be uppercase."""
        # 0x0F = 15
        data = b"F\r\n012345678901234\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"012345678901234")

    def test_partial_chunks_received(self):
        """Handle chunks arriving in multiple reads."""
        decoder = ChunkedDecoder()

        # Send chunk size line
        decoder.feed(b"5\r\n")
        while not decoder.complete and decoder.decode_step():
            pass

        # Send chunk data
        decoder.feed(b"Hello")
        while not decoder.complete and decoder.decode_step():
            pass

        # Send chunk trailing CRLF
        decoder.feed(b"\r\n")
        while not decoder.complete and decoder.decode_step():
            pass

        # Send final chunk
        decoder.feed(b"0\r\n\r\n")
        while not decoder.complete and decoder.decode_step():
            pass

        self.assertTrue(decoder.complete)
        self.assertEqual(decoder.decoded_body, b"Hello")

    def test_chunk_with_extensions(self):
        """Chunk size can have extensions (which are ignored)."""
        # "5;name=value" -> size is 5
        data = b"5;name=value\r\nHello\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"Hello")

    def test_invalid_chunk_size(self):
        """Reject non-hexadecimal chunk size."""
        data = b"ZZZ\r\nHello\r\n0\r\n\r\n"
        with self.assertRaises(BadRequestError):
            decode_chunked(data)

    def test_missing_crlf_after_chunk(self):
        """Reject missing CRLF after chunk data."""
        data = b"5\r\nHelloX0\r\n\r\n"
        decoder = ChunkedDecoder()
        decoder.feed(data)
        with self.assertRaises(BadRequestError):
            while not decoder.complete and decoder.decode_step():
                pass

    def test_empty_chunk_size(self):
        """Reject empty chunk size."""
        data = b"\r\nHello\r\n0\r\n\r\n"
        decoder = ChunkedDecoder()
        decoder.feed(data)
        with self.assertRaises(BadRequestError):
            decoder.decode_step()

    def test_negative_chunk_size(self):
        """Reject negative chunk size (parsed as -1)."""
        data = b"-1\r\nHello\r\n0\r\n\r\n"
        with self.assertRaises(BadRequestError):
            decode_chunked(data)

    def test_chunk_size_too_large(self):
        """Reject chunk size exceeding limit."""
        # ChunkedDecoder has CHUNK_DATA_MAX = 100 MB
        # Create a chunk size that exceeds it
        huge_size = (100 * 1024 * 1024) + 1
        data = f"{huge_size:x}\r\n".encode()
        decoder = ChunkedDecoder()
        decoder.feed(data)
        with self.assertRaises(BadRequestError):
            while not decoder.complete and decoder.decode_step():
                pass

    def test_decoded_body_too_large(self):
        """Reject total decoded body exceeding limit."""
        # Two chunks that sum to > DECODED_BODY_MAX
        huge_size = (100 * 1024 * 1024) // 2
        data = (
            f"{huge_size:x}\r\n".encode()
            + (b"X" * huge_size)
            + b"\r\n"
            + f"{huge_size:x}\r\n".encode()
            + (b"X" * huge_size)
            + b"\r\n"
        )
        decoder = ChunkedDecoder()
        decoder.feed(data)
        with self.assertRaises(BadRequestError):
            while not decoder.complete:
                if not decoder.decode_step():
                    decoder.feed(b"")

    def test_trailer_headers_ignored(self):
        """Trailer headers are decoded but can be ignored."""
        # Chunk with a trailer header
        data = b"5\r\nHello\r\n0\r\nX-Trailer: value\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"Hello")
        self.assertIn("x-trailer", decoder.trailer_headers)

    def test_multiple_trailer_headers(self):
        """Handle multiple trailer headers."""
        data = b"5\r\nWorld\r\n0\r\nX-A: 1\r\nX-B: 2\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"World")
        self.assertEqual(decoder.trailer_headers.get("x-a"), "1")
        self.assertEqual(decoder.trailer_headers.get("x-b"), "2")

    def test_no_trailers(self):
        """Final chunk can omit trailers."""
        data = b"5\r\nHello\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"Hello")
        self.assertEqual(len(decoder.trailer_headers), 0)

    def test_pipelined_chunks_in_one_read(self):
        """Multiple chunks can arrive in a single read."""
        data = b"2\r\nHi\r\n2\r\nBy\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)
        self.assertEqual(body, b"HiBy")


class TestChunkedDecoder(unittest.TestCase):
    """Test ChunkedDecoder state machine."""

    def test_decoder_incremental(self):
        """Test incremental decoding."""
        decoder = ChunkedDecoder()
        self.assertFalse(decoder.complete)

        # Feed data byte-by-byte
        data = b"5\r\nHello\r\n0\r\n\r\n"
        for byte in data:
            decoder.feed(bytes([byte]))
            while decoder.decode_step():
                pass

        self.assertTrue(decoder.complete)
        self.assertEqual(decoder.decoded_body, b"Hello")

    def test_decoder_reuse_not_allowed(self):
        """Decoder cannot be reused after completion."""
        data = b"5\r\nHello\r\n0\r\n\r\n"
        body, decoder = decode_chunked(data)

        # Decoder is complete
        self.assertTrue(decoder.complete)
        
        # Accessing decoded_body should work (it's completed)
        self.assertEqual(decoder.decoded_body, b"Hello")
        
        # But trying to feed more data should raise RuntimeError
        self.assertRaises(RuntimeError, lambda: decoder.feed(b"more"))


if __name__ == "__main__":
    unittest.main()
