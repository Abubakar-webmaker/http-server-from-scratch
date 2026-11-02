from .request import Request


class HTTPParseError(Exception):
    """Raised when an HTTP request is malformed or unsupported."""


def parse_request(conn) -> Request:
    """
    Read and parse one HTTP request from a connected TCP socket.

    The function reads until the complete headers and the exact
    Content-Length body have been received.
    """

    buffer = bytearray()
    header_end = b"\r\n\r\n"

    # Step 1: Read until the complete header section is available.
    while header_end not in buffer:
        chunk = conn.recv(1024)

        if not chunk:
            raise HTTPParseError("Connection closed before headers completed.")

        buffer.extend(chunk)

        if len(buffer) > 65536:
            raise HTTPParseError("HTTP headers are too large.")

    header_bytes, body_buffer = bytes(buffer).split(header_end, 1)

    # Step 2: Decode headers.
    try:
        header_text = header_bytes.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise HTTPParseError("Invalid header encoding.") from exc

    lines = header_text.split("\r\n")

    if not lines or not lines[0]:
        raise HTTPParseError("Missing HTTP request line.")

    # Step 3: Parse request line.
    request_line = lines[0].split()

    if len(request_line) != 3:
        raise HTTPParseError("Invalid HTTP request line.")

    method, path, version = request_line

    if not method.isascii() or not method.isalpha():
        raise HTTPParseError("Invalid HTTP method.")

    if not path:
        raise HTTPParseError("Missing request path.")

    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise HTTPParseError("Unsupported HTTP version.")

    # Step 4: Parse headers.
    headers = {}

    for line in lines[1:]:
        if not line:
            continue

        if line.startswith((" ", "\t")):
            raise HTTPParseError("Folded headers are not supported.")

        if ":" not in line:
            raise HTTPParseError(f"Invalid HTTP header: {line}")

        name, value = line.split(":", 1)
        name = name.strip().lower()
        value = value.strip()

        if not name or any(
            not (char.isalnum() or char in "!#$%&'*+-.^_`|~")
            for char in name
        ):
            raise HTTPParseError("Invalid HTTP header name.")

        if name in headers:
            if name == "content-length":
                raise HTTPParseError("Duplicate Content-Length header.")

            headers[name] += ", " + value
        else:
            headers[name] = value

    # Step 5: Reject unsupported chunked transfer encoding.
    transfer_encoding = headers.get("transfer-encoding", "")

    if "chunked" in [
        item.strip().lower()
        for item in transfer_encoding.split(",")
    ]:
        raise HTTPParseError("Transfer-Encoding: chunked is not supported.")

    if transfer_encoding:
        raise HTTPParseError("Transfer-Encoding is not supported.")

    # Step 6: Validate Content-Length.
    content_length = 0

    if "content-length" in headers:
        value = headers["content-length"]

        if not value.isascii() or not value.isdigit():
            raise HTTPParseError("Invalid Content-Length value.")

        content_length = int(value)

    # Step 7: Read the exact request body.
    body = bytearray(body_buffer)

    if len(body) > content_length:
        body = body[:content_length]

    while len(body) < content_length:
        chunk = conn.recv(min(1024, content_length - len(body)))

        if not chunk:
            raise HTTPParseError("Connection closed before body completed.")

        body.extend(chunk)

    # Step 8: Return structured Request object.
    return Request(
        method=method,
        path=path,
        version=version,
        headers=headers,
        body=bytes(body),
    )