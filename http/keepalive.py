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
    * The body length is taken *only* from ``Content-Length``.
    * ``Transfer-Encoding`` is rejected outright (unsupported). This is
      deliberate: silently treating an unsupported chunked body as a plain
      one would desynchronize the persistent connection (request
      smuggling).
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

        # 2. Inspect the headers for framing information. Strict validation
        #    (duplicate headers, invalid request line, etc.) is left to
        #    parse_request, which runs on the assembled bytes below.
        content_length, has_transfer_encoding = _parse_framing(header_bytes)

        if has_transfer_encoding:
            raise HTTPParseError("Transfer-Encoding is not supported")

        if content_length < 0:
            raise HTTPParseError("Invalid Content-Length")

        if content_length > self._max_body_size:
            raise HTTPParseError("Request body too large")

        # 3. Read the complete body. Bytes already buffered after the
        #    headers count toward the body.
        while len(self._buffer) - body_start < content_length:
            chunk = self._recv(4096)

            if not chunk:
                raise HTTPParseError("Incomplete request body")

            self._buffer.extend(chunk)

        body = bytes(self._buffer[body_start : body_start + content_length])

        # 4. Keep any leftover bytes for the next request on this
        #    connection. This is what makes pipelined and back-to-back
        #    requests safe: we never discard bytes that belong to a
        #    following request, and we never let one body bleed into the
        #    next request's headers.
        del self._buffer[: body_start + content_length]

        # 5. Parse and validate the full request through the existing
        #    parser so all of its rules (lowercased headers, duplicate
        #    detection, request-line shape, body/length checks) still apply.
        return parse_request(header_bytes + HEADER_END + body)

    def _recv(self, size: int) -> bytes:
        return self._conn.recv(size)


def _parse_framing(header_bytes: bytes) -> tuple[int, bool]:
    """Extract ``Content-Length`` and detect ``Transfer-Encoding``.

    Returns ``(content_length, has_transfer_encoding)``.

    The scan is tolerant of header ordering because it only needs enough
    framing information to read the right number of body bytes. The strict
    checks (duplicate headers, an invalid Content-Length value, etc.) are
    performed by :func:`parse_request` on the assembled request; if they
    fail the caller closes the connection, so a slightly-off body length
    here cannot desynchronize anything.
    """

    content_length = 0
    has_transfer_encoding = False

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
            has_transfer_encoding = True

    return content_length, has_transfer_encoding


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
