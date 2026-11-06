"""HTTP/1.1 chunked transfer encoding support."""

from __future__ import annotations

import re
from typing import Optional

from utils.exceptions import BadRequestError


# Chunk size line max: "7fffffff\r\n" = 10 bytes
CHUNK_SIZE_LINE_MAX = 100
# Single chunk data max: 100 MB
CHUNK_DATA_MAX = 100 * 1024 * 1024
# Total decoded body max: 100 MB (same as Content-Length limit elsewhere)
DECODED_BODY_MAX = 100 * 1024 * 1024
# Trailer section max: 64 KB
TRAILER_MAX = 64 * 1024


class ChunkedDecoder:
    """Decode HTTP/1.1 chunked request bodies.

    Manages a per-connection buffer so that chunks split across socket reads
    or multiple chunks in a single read are handled correctly.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._state = "SIZE"  # "SIZE", "DATA", "TRAILER", "DONE"
        self._chunk_size = 0
        self._chunk_remaining = 0
        self._decoded_body = bytearray()
        self._trailer_headers = {}

    def feed(self, data: bytes) -> None:
        """Add received data to the decoder.
        
        Raises:
            RuntimeError: If attempting to feed data after decoding is complete.
        """
        if self._state == "DONE":
            raise RuntimeError("Decoder cannot be reused after completion")
        self._buffer.extend(data)

    @property
    def complete(self) -> bool:
        """True when the final chunk and trailers have been received."""
        return self._state == "DONE"

    @property
    def decoded_body(self) -> bytes:
        """Get the complete decoded body."""
        if not self.complete:
            raise RuntimeError("Decoding not complete")
        return bytes(self._decoded_body)

    @property
    def trailer_headers(self) -> dict[str, str]:
        """Get trailer headers (if any)."""
        return self._trailer_headers

    def decode_step(self) -> bool:
        """Process one step of decoding.

        Returns:
            True if more data is available and decoding continues.
            False if the decoder needs more network data.

        Raises:
            BadRequestError: On malformed chunked encoding.
        """
        if self._state == "SIZE":
            return self._decode_size()
        elif self._state == "DATA":
            return self._decode_data()
        elif self._state == "TRAILER":
            return self._decode_trailer()
        elif self._state == "DONE":
            return False

        raise RuntimeError(f"Invalid decoder state: {self._state}")

    def _decode_size(self) -> bool:
        """Decode the chunk size line."""
        # Look for "\r\n" to end the size line.
        crlf_pos = self._buffer.find(b"\r\n")
        if crlf_pos == -1:
            # Not enough data yet.
            if len(self._buffer) > CHUNK_SIZE_LINE_MAX:
                raise BadRequestError("Chunk size line too large")
            return False

        size_line = bytes(self._buffer[:crlf_pos])

        try:
            # Chunk size is a hexadecimal number, optionally followed by
            # chunk extensions (e.g., "1a;name=value"). We ignore extensions.
            size_str = size_line.decode("iso-8859-1").split(";", 1)[0].strip()

            if not size_str:
                raise BadRequestError("Empty chunk size")

            self._chunk_size = int(size_str, 16)

        except (ValueError, UnicodeDecodeError) as exc:
            raise BadRequestError("Invalid chunk size") from exc

        if self._chunk_size < 0:
            raise BadRequestError("Negative chunk size")

        # Remove the size line from the buffer.
        del self._buffer[: crlf_pos + 2]

        if self._chunk_size == 0:
            # Final chunk — next we parse trailers.
            self._state = "TRAILER"
        else:
            # Regular chunk — read data.
            if self._chunk_size > CHUNK_DATA_MAX:
                raise BadRequestError("Chunk size too large")

            self._chunk_remaining = self._chunk_size
            self._state = "DATA"

        return True

    def _decode_data(self) -> bool:
        """Decode chunk data."""
        if len(self._decoded_body) + self._chunk_size > DECODED_BODY_MAX:
            raise BadRequestError("Total decoded body too large")

        # Read up to chunk_remaining bytes from the buffer.
        to_read = min(self._chunk_remaining, len(self._buffer))

        if to_read > 0:
            chunk_data = bytes(self._buffer[:to_read])
            self._decoded_body.extend(chunk_data)
            del self._buffer[:to_read]
            self._chunk_remaining -= to_read

        # If we've read the entire chunk, look for the trailing CRLF.
        if self._chunk_remaining == 0:
            if len(self._buffer) < 2:
                # Not enough data for the trailing CRLF yet.
                return False

            trailing_crlf = bytes(self._buffer[:2])
            if trailing_crlf != b"\r\n":
                raise BadRequestError("Missing CRLF after chunk data")

            del self._buffer[:2]

            # Next chunk size.
            self._state = "SIZE"

        return len(self._buffer) > 0

    def _decode_trailer(self) -> bool:
        """Decode trailer headers (if any) until CRLF."""
        # Trailer section ends with an empty line (CRLF).
        crlf_pos = self._buffer.find(b"\r\n")

        if crlf_pos == -1:
            # Not enough data yet.
            if len(self._buffer) > TRAILER_MAX:
                raise BadRequestError("Trailer section too large")
            return False

        # If the first thing we see is CRLF, there are no trailers.
        if crlf_pos == 0:
            del self._buffer[:2]
            self._state = "DONE"
            return False

        # Parse trailer headers (each ending with CRLF).
        trailer_data = bytes(self._buffer[:crlf_pos])

        try:
            trailer_text = trailer_data.decode("iso-8859-1")
        except UnicodeDecodeError as exc:
            raise BadRequestError("Invalid trailer encoding") from exc

        for line in trailer_text.split("\r\n"):
            if not line:
                continue

            if ":" not in line:
                raise BadRequestError("Invalid trailer header")

            name, value = line.split(":", 1)
            name = name.strip().lower()
            value = value.strip()

            if not name:
                raise BadRequestError("Empty trailer header name")

            self._trailer_headers[name] = value

        # Remove trailers and final CRLF from buffer.
        del self._buffer[: crlf_pos + 2]

        self._state = "DONE"
        return False


def decode_chunked(data: bytes, decoder: Optional[ChunkedDecoder] = None) -> tuple[Optional[bytes], ChunkedDecoder]:
    """Convenience function to decode chunked data from a complete byte string.

    Used in tests; the server uses ChunkedDecoder incrementally.

    Returns:
        (decoded_body, decoder) or (None, decoder) if incomplete.
    """
    if decoder is None:
        decoder = ChunkedDecoder()

    decoder.feed(data)

    while not decoder.complete:
        if not decoder.decode_step():
            break

    if decoder.complete:
        return decoder.decoded_body, decoder

    return None, decoder
