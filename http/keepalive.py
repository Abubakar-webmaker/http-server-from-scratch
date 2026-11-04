"""HTTP keep-alive (persistent connection) support.

This module provides the pieces that turn a single-request-per-connection
server into one that handles many requests over the same TCP connection:

- :class:`BufferedRequestReader` frames HTTP requests out of a raw TCP byte
  stream while preserving leftover bytes for the next request.
- :func:`should_keep_alive` decides, per request, whether the connection may
  stay open after the response.

Connection management is kept separate from routing and response
generation: these helpers know nothing about routes or ``Response``
objects.
"""

from __future__ import annotations

from .parser import parse_request, HTTPParseError
from .request import Request
from .chunked import ChunkedDecoder
from utils.exceptions import BadRequestError


# The four-byte sequence that terminates HTTP/1.x request headers.
HEADER_END = b"\r\n\r\n"


class BufferedRequestReader:
    """Read complete HTTP/1.x requests from a socket, frame by frame.

    TCP is a byte stream, not a message protocol: one request may arrive
    spread across several ``recv()`` calls and several requests may arrive
    inside a single ``recv()`` call. This reader keeps a per-connection
    buffer so bytes belonging to a following request are never discarded and
    the body of one request is never mixed with the next.

    Framing rules enforced here:

    * Headers end at the first ``\\r\\n\\r\\n``.
    * For chunked encoding: Content-Length and Transfer-Encoding: chunked
      are mutually exclusive. Chunked bodies are decoded incrementally.
    * For non-chunked: The body length is taken *only* from ``Content-Length``.
    * Invalid or ambiguous framing is rejected to prevent request smuggling.
    """

    def __init__(
        self,
        conn,
        max_header_size: int = 65536,
        max_body_size: int = 10 * 1024 * 1024,
    ) -> None:
        self._conn = conn
        self._buffer = bytearray()
        self._max_header_size = max_header_size
        self._max_body_size = max_body_size

    @property
    def pending(self) -> int:
        """Number of buffered bytes not yet consumed by a parsed request."""

        return len(self._buffer)

    def read_request(self) -> Request | None:
        """Read exactly one complete HTTP request.

        Returns:
            A parsed :class:`Request` on success.

            ``None`` when the client closed the connection cleanly with no
            pending bytes (the normal end of a persistent connection).

        Raises:
            HTTPParseError: for malformed, oversized, or incomplete requests
                (including a disconnect mid-request).
            socket.timeout: when the socket read/idle timeout expires.
        """
        # 1. Read until the complete headers are available.
        while HEADER_END not in self._buffer:
            chunk = self._recv(4096)

            if not chunk:
                if not self._buffer:
                    # Clean disconnect with nothing pending: done.
                    return None
                # Partial headers already received, then disconnect.
                raise HTTPParseError(
                    "Client disconnected before headers complete"
                )

            self._buffer.extend(chunk)

            if len(self._buffer) > self._max_header_size:
                raise HTTPParseError("HTTP headers too large")

        end_index = self._buffer.index(HEADER_END)
        header_bytes = bytes(self._buffer[:end_index])
        body_start = end_index + len(HEADER_END)

        # 2. Inspect the headers for framing information.
        content_length, has_transfer_encoding_chunked, has_transfer_encoding_other = _parse_framing(
            header_bytes
        )

        # 3a. Check for invalid framing combinations
        if content_length > 0 and has_transfer_encoding_chunked:
            raise BadRequestError(
                "Content-Length and Transfer-Encoding: chunked are mutually exclusive"
            )

        if has_transfer_encoding_other:
            raise BadRequestError("Unsupported Transfer-Encoding")

        # 3b. Decode chunked body if present
        if has_transfer_encoding_chunked:
            body = self._read_chunked_body(body_start)
        else:
            # 3c. Read regular Content-Length body
            if content_length < 0:
                raise HTTPParseError("Invalid Content-Length")

            if content_length > self._max_body_size:
                raise HTTPParseError("Request body too large")

            body = self._read_fixed_length_body(body_start, content_length)

        # 4. Keep any leftover bytes for the next request.
        del self._buffer[:body_start + len(body)]

        # 5. Parse and validate the full request.
        return parse_request(header_bytes + HEADER_END + body)

    def _read_fixed_length_body(self, body_start: int, content_length: int) -> bytes:
        """Read a fixed-length body based on Content-Length."""
        # Read the complete body. Bytes already buffered after the
        # headers count toward the body.
        while len(self._buffer) - body_start < content_length:
            chunk = self._recv(4096)

            if not chunk:
                raise HTTPParseError("Incomplete request body")

            self._buffer.extend(chunk)

        return bytes(self._buffer[body_start : body_start + content_length])

    def _read_chunked_body(self, body_start: int) -> bytes:
        """Read and decode a chunked transfer-encoded body."""
        decoder = ChunkedDecoder()

        # Feed any buffered data after headers to the decoder
        decoder.feed(bytes(self._buffer[body_start:]))

        # Decode chunks until complete
        while not decoder.complete:
            if not decoder.decode_step():
                # Need more data from socket
                try:
                    chunk = self._recv(4096)
                except Exception as exc:
                    raise BadRequestError("Error reading chunked body") from exc

                if not chunk:
                    raise BadRequestError("Incomplete chunked body")

                decoder.feed(chunk)

        # Update buffer to remove consumed bytes
        # Calculate how many bytes from body_start were consumed
        remaining = decoder._buffer  # ChunkedDecoder's leftover
        bytes_consumed = len(self._buffer) - body_start - len(remaining)
        del self._buffer[body_start : body_start + bytes_consumed]

        return decoder.decoded_body

    def _recv(self, size: int) -> bytes:
        return self._conn.recv(size)


def _parse_framing(header_bytes: bytes) -> tuple[int, bool, bool]:
    """Extract Content-Length and detect Transfer-Encoding types.

    Returns ``(content_length, is_chunked, has_other_encoding)``.
    """

    content_length = 0
    is_chunked = False
    has_other_encoding = False

    try:
        text = header_bytes.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise HTTPParseError("Invalid HTTP header encoding") from exc

    lines = text.split("\r\n")

    # The first line is the request line; the rest are headers.
    for line in lines[1:]:
        if ":" not in line:
            continue

        name, value = line.split(":", 1)
        name = name.strip().lower()
        value = value.strip()

        if name == "content-length":
            try:
                content_length = int(value)
            except ValueError:
                # A genuinely invalid Content-Length is rejected by
                # parse_request. Read zero body bytes here so parse_request
                # surfaces the error and the connection is closed.
                content_length = 0
        elif name == "transfer-encoding":
            # Normalize the Transfer-Encoding value
            encodings = {e.strip().lower() for e in value.split(",")}
            if "chunked" in encodings:
                is_chunked = True
            # Any other encoding is unsupported
            if encodings - {"chunked"}:
                has_other_encoding = True

    return content_length, is_chunked, has_other_encoding


def should_keep_alive(request: Request) -> bool:
    """Decide whether the connection stays open after this request.

    HTTP/1.1 defaults to persistent connections; HTTP/1.0 defaults to close.
    The ``Connection`` header overrides the default. Its value is parsed
    case-insensitively as a comma-separated list of tokens.

    When both ``keep-alive`` and ``close`` appear together, ``close`` wins:
    a client asking to close should never be kept open against its wishes.
    """

    connection_header = request.headers.get("connection", "") or ""

    tokens = {
        token.strip().lower()
        for token in connection_header.split(",")
        if token.strip()
    }

    if "close" in tokens:
        return False

    if "keep-alive" in tokens:
        return True

    if request.version == "HTTP/1.0":
        return False

    # HTTP/1.1 (and any future 1.x version) defaults to persistent.
    return True
