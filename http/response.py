from dataclasses import dataclass, field
import re


STATUS_CODES = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}

DEFAULT_CONTENT_TYPE = "text/plain; charset=utf-8"

HEADER_NAME_PATTERN = re.compile(
    r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$"
)


@dataclass
class Response:
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | str = b""

    def __post_init__(self):
        if isinstance(self.body, str):
            self.body = self.body.encode("utf-8")
        elif not isinstance(self.body, bytes):
            raise TypeError("Response body must be str or bytes.")


def serialize_response(response: Response) -> bytes:
    """
    Convert a Response object into a complete HTTP response.

    Returns:
        bytes: Serialized HTTP response.
    """

    # 1. Validate status code.
    if (
        isinstance(response.status_code, bool)
        or response.status_code not in STATUS_CODES
    ):
        raise ValueError(
            f"Unsupported HTTP status code: {response.status_code}"
        )

    # 2. Validate response body.
    if not isinstance(response.body, bytes):
        raise TypeError("Response body must be bytes.")

    # 3. Validate and normalize headers.
    normalized_headers = {}

    for name, value in response.headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("Header names and values must be strings.")

        if not HEADER_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"Invalid HTTP header name: {name}")

        if any(ord(char) < 32 and char != "\t" for char in value):
            raise ValueError("HTTP header contains invalid control characters.")

        if "\r" in value or "\n" in value:
            raise ValueError("HTTP header values cannot contain CRLF.")

        normalized_name = name.lower()

        if normalized_name in normalized_headers:
            raise ValueError(f"Duplicate HTTP header: {name}")

        if normalized_name in ("content-length", "connection"):
            raise ValueError(
                f"{name} is generated automatically and cannot be overridden."
            )

        normalized_headers[normalized_name] = (name, value)

    # 4. Add default Content-Type when missing.
    if "content-type" not in normalized_headers:
        normalized_headers["content-type"] = (
            "Content-Type",
            DEFAULT_CONTENT_TYPE,
        )

    # 5. Generate status line.
    reason_phrase = STATUS_CODES[response.status_code]

    status_line = (
        f"HTTP/1.1 {response.status_code} {reason_phrase}\r\n"
    )

    # 6. Generate response headers.
    header_lines = []

    for original_name, value in normalized_headers.values():
        header_lines.append(f"{original_name}: {value}\r\n")

    # 7. Generate automatic headers.
    header_lines.append(f"Content-Length: {len(response.body)}\r\n")
    header_lines.append("Connection: close\r\n")

    # 8. Serialize headers and body.
    header_section = status_line + "".join(header_lines) + "\r\n"

    try:
        header_bytes = header_section.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError("HTTP headers must use Latin-1-compatible values.") from exc

    return header_bytes + response.body