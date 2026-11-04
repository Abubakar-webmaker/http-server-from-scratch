from .request import Request
from .chunked import ChunkedDecoder
from utils.exceptions import BadRequestError


class HTTPParseError(Exception):
    """Raised when an HTTP request is malformed."""


def _read_from_socket(socket_obj) -> bytes:
    """Read a complete HTTP/1.x request from a socket-like object.

    The object must expose a ``recv(size)`` method returning bytes. The
    request is read incrementally so that bodies larger than a single
    recv() chunk are assembled correctly.
    """

    buffer = bytearray()
    header_end = b"\r\n\r\n"

    while header_end not in buffer:
        chunk = socket_obj.recv(4096)

        if not chunk:
            raise HTTPParseError("Client disconnected before headers")

        buffer.extend(chunk)

        if len(buffer) > 65536:
            raise HTTPParseError("HTTP headers too large")

    header_bytes, _, remaining = bytes(buffer).partition(header_end)

    try:
        header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
        content_length = 0

        for line in header_lines[1:]:
            if ":" not in line:
                raise HTTPParseError("Invalid HTTP header")

            name, value = line.split(":", 1)

            if name.strip().lower() == "content-length":
                content_length = int(value.strip())

                if content_length < 0:
                    raise HTTPParseError("Invalid Content-Length")

            if name.strip().lower() == "transfer-encoding":
                raise HTTPParseError(
                    "Transfer-Encoding is not supported"
                )

    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPParseError("Invalid HTTP headers") from exc

    if content_length > 10 * 1024 * 1024:
        raise HTTPParseError("Request body too large")

    body = bytearray(remaining)

    if len(body) > content_length:
        raise HTTPParseError("Unexpected extra request data")

    while len(body) < content_length:
        chunk = socket_obj.recv(
            min(4096, content_length - len(body))
        )

        if not chunk:
            raise HTTPParseError("Incomplete request body")

        body.extend(chunk)

    return header_bytes + header_end + bytes(body)


def parse_request(raw_request) -> Request:
    """Parse a complete HTTP/1.x request from bytes or a socket-like object."""

    if hasattr(raw_request, "recv"):
        raw_request = _read_from_socket(raw_request)

    if not raw_request:
        raise HTTPParseError("Empty request")

    try:
        header_data, separator, body = raw_request.partition(b"\r\n\r\n")

        if not separator:
            raise HTTPParseError("Incomplete HTTP headers")

        lines = header_data.decode("iso-8859-1").split("\r\n")

        request_line = lines[0].split()

        if len(request_line) != 3:
            raise HTTPParseError("Invalid request line")

        method, path, version = request_line

        if not version.startswith("HTTP/1."):
            raise HTTPParseError("Unsupported HTTP version")

        headers = {}

        for line in lines[1:]:
            if not line or ":" not in line:
                raise HTTPParseError("Invalid header")

            name, value = line.split(":", 1)
            name = name.strip().lower()
            value = value.strip()

            if not name:
                raise HTTPParseError("Empty header name")

            if name in headers:
                raise HTTPParseError("Duplicate header")

            headers[name] = value

        content_length = headers.get("content-length", "0")

        try:
            content_length = int(content_length)
        except ValueError as exc:
            raise HTTPParseError("Invalid Content-Length") from exc

        if content_length < 0:
            raise HTTPParseError("Negative Content-Length")

        if len(body) < content_length:
            raise HTTPParseError("Incomplete request body")

        if len(body) > content_length:
            raise HTTPParseError("Unexpected extra request data")

        if "transfer-encoding" in headers:
            raise HTTPParseError("Transfer-Encoding is not supported")

        return Request(
            method=method.upper(),
            path=path,
            version=version,
            headers=headers,
            body=body,
        )

    except UnicodeDecodeError as exc:
        raise HTTPParseError("Invalid request encoding") from exc