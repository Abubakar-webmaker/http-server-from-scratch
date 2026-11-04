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


def serialize_response(response: Response) -> bytes:
    """Serialize a Response object into HTTP response bytes."""

    if response.status_code not in STATUS_CODES:
        raise ValueError(
            f"Unsupported status code: {response.status_code}"
        )

    status = STATUS_CODES[response.status_code]

    has_content_type = any(
        name.lower() == "content-type"
        for name in response.headers
    )

    headers = {
        "Content-Length": str(len(response.body)),
        "Connection": "close",
    }

    if not has_content_type:
        headers["Content-Type"] = "text/plain; charset=utf-8"

    headers.update(response.headers)

    for name, value in headers.items():
        if (
            "\r" in name
            or "\n" in name
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError("Invalid response header")

    # Honor an explicit Content-Length from the response (e.g. a HEAD
    # request keeps the GET representation length while sending no body).
    # When none is provided, the default computed from len(body) stands.

    if any(name.lower() == "connection" for name in response.headers):
        headers["Connection"] = "close"

    lines = [
        f"HTTP/1.1 {response.status_code} {status}"
    ]

    lines.extend(
        f"{name}: {value}"
        for name, value in headers.items()
    )

    header_bytes = "\r\n".join(lines).encode("iso-8859-1")

    return header_bytes + b"\r\n\r\n" + response.body