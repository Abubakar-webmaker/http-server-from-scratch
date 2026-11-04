"""HTTP response handling module.

This module provides Response data class and serialization function
for converting Response objects into proper HTTP/1.1 formatted byte strings.
"""

from dataclasses import dataclass, field


STATUS_CODES = {
    200: "OK",
    201: "Created",
    304: "Not Modified",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


@dataclass
class Response:
    """HTTP response representation.
    
    Attributes:
        status_code: HTTP status code (200, 404, 500, etc.)
        body: Response body (bytes or str, auto-converted to bytes)
        headers: Response headers as dict (case-insensitive)
    """
    status_code: int = 200
    body: bytes | str = b""
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Convert string body to bytes and validate types."""
        if isinstance(self.body, str):
            self.body = self.body.encode("utf-8")

        if not isinstance(self.body, bytes):
            raise TypeError("Response body must be bytes or str")


def serialize_response(response: Response, keep_alive: bool = False) -> bytes:
    """Serialize a Response object into HTTP/1.1 formatted bytes.

    The server controls the connection lifecycle and passes keep_alive
    to indicate whether the connection should remain open. Any Connection
    header set by the handler is overridden with the server's decision.

    Format:
        HTTP/1.1 <status_code> <status_text>
        <header_name>: <header_value>
        ... (more headers) ...
        
        <body>

    Args:
        response: Response object to serialize
        keep_alive: Whether to keep connection open (sets Connection header)

    Returns:
        Complete HTTP response as bytes

    Raises:
        ValueError: If status code is unsupported or headers invalid
    """
    # Validate status code
    if response.status_code not in STATUS_CODES:
        raise ValueError(
            f"Unsupported status code: {response.status_code}"
        )

    status = STATUS_CODES[response.status_code]

    # Check if Content-Type header already set (case-insensitive)
    has_content_type = any(
        name.lower() == "content-type"
        for name in response.headers
    )

    connection_value = "keep-alive" if keep_alive else "close"

    # Start with default headers (can be overridden by handler)
    headers = {
        "Content-Length": str(len(response.body)),
    }

    if not has_content_type:
        headers["Content-Type"] = "text/plain; charset=utf-8"

    # Merge handler-supplied headers
    headers.update(response.headers)

    # Remove any Connection header handler may have set (case-insensitive)
    # The server's connection policy takes precedence
    for name in list(headers):
        if name.lower() == "connection":
            del headers[name]

    headers["Connection"] = connection_value

    # Validate headers don't contain CRLF (header injection prevention)
    for name, value in headers.items():
        if (
            "\r" in name
            or "\n" in name
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError("Invalid response header")

    # Build status line and headers
    lines = [
        f"HTTP/1.1 {response.status_code} {status}"
    ]

    lines.extend(
        f"{name}: {value}"
        for name, value in headers.items()
    )

    # Encode headers as bytes (ISO-8859-1 per HTTP spec)
    header_bytes = "\r\n".join(lines).encode("iso-8859-1")

    # Complete response: headers + blank line + body
    return header_bytes + b"\r\n\r\n" + response.body