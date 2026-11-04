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
    status_code: int = 200
    body: bytes | str = b""
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.body, str):
            self.body = self.body.encode("utf-8")

        if not isinstance(self.body, bytes):
            raise TypeError("Response body must be bytes or str")


def serialize_response(response: Response, keep_alive: bool = False) -> bytes:
    """Serialize a Response object into HTTP response bytes.

    The caller owns the connection policy and conveys it through
    ``keep_alive``. The serialized response carries a single
    ``Connection`` header reflecting that decision (``keep-alive`` or
    ``close``). Any ``Connection`` header a handler may have set is
    overridden, because the connection lifecycle is the server's
    responsibility, not the handler's.
    """

    if response.status_code not in STATUS_CODES:
        raise ValueError(
            f"Unsupported status code: {response.status_code}"
        )

    status = STATUS_CODES[response.status_code]

    has_content_type = any(
        name.lower() == "content-type"
        for name in response.headers
    )

    connection_value = "keep-alive" if keep_alive else "close"

    # Default Content-Length is derived from the body. A handler may
    # override it (e.g. a HEAD request keeps the GET representation
    # length while sending no body).
    headers = {
        "Content-Length": str(len(response.body)),
    }

    if not has_content_type:
        headers["Content-Type"] = "text/plain; charset=utf-8"

    headers.update(response.headers)

    # The connection lifecycle is owned by the server. Remove any
    # Connection header a handler may have supplied (case-insensitively)
    # and replace it with a single authoritative value.
    for name in list(headers):
        if name.lower() == "connection":
            del headers[name]

    headers["Connection"] = connection_value

    for name, value in headers.items():
        if (
            "\r" in name
            or "\n" in name
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError("Invalid response header")

    lines = [
        f"HTTP/1.1 {response.status_code} {status}"
    ]

    lines.extend(
        f"{name}: {value}"
        for name, value in headers.items()
    )

    header_bytes = "\r\n".join(lines).encode("iso-8859-1")

    return header_bytes + b"\r\n\r\n" + response.body