"""Gzip compression support for HTTP responses."""

import gzip
import io
import re
from typing import Optional

from http.response import Response


# Content types that are eligible for compression
COMPRESSIBLE_TYPES = {
    "text/",
    "application/json",
    "application/javascript",
    "application/xml",
    "image/svg+xml",
}

# Content types that should NOT be compressed (already compressed)
NON_COMPRESSIBLE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/gzip",
    "application/zip",
    "application/x-bzip2",
}

# Minimum response body size to compress (bytes)
MIN_COMPRESSION_SIZE = 1024  # 1 KB


def should_compress(response: Response, min_size: int = MIN_COMPRESSION_SIZE) -> bool:
    """Determine if a response body should be compressed.

    Args:
        response: The HTTP response.
        min_size: Minimum body size to compress.

    Returns:
        True if the response should be gzipped.
    """
    # Do not compress responses with no body
    if not response.body:
        return False
    
    # Get body size (body is always bytes after Response.__post_init__)
    body_size = len(response.body)
    if body_size < min_size:
        return False

    # Do not compress 204, 304, or HEAD responses
    if response.status_code in (204, 304):
        return False

    content_type = ""
    for name, value in response.headers.items():
        if name.lower() == "content-type":
            content_type = value.lower()
            break

    if not content_type:
        return False

    # Check non-compressible types first
    for typ in NON_COMPRESSIBLE_TYPES:
        if typ in content_type:
            return False

    # Check compressible types
    for typ in COMPRESSIBLE_TYPES:
        if typ in content_type:
            return True

    return False


def parse_accept_encoding(accept_encoding: str) -> dict[str, float]:
    """Parse Accept-Encoding header.

    Returns:
        Dict mapping encoding name to quality (q) value.
        Default q=1.0 if not specified.
    """
    encodings = {}

    if not accept_encoding:
        return encodings

    for part in accept_encoding.split(","):
        part = part.strip()

        if not part:
            continue

        # Parse "gzip;q=0.8" or "gzip ; q = 0.8" (with spaces)
        # Remove all spaces around = and ;
        part = part.replace(" ", "")
        match = re.match(r"([a-z\-]+)(?:;q=([0-9.]+))?", part)

        if match:
            encoding = match.group(1).lower()
            q_str = match.group(2)
            q = float(q_str) if q_str else 1.0

            # Clamp q to [0.0, 1.0]
            q = max(0.0, min(1.0, q))
            encodings[encoding] = q

    return encodings


def client_accepts_gzip(accept_encoding: str) -> bool:
    """Check if the client accepts gzip encoding.

    Args:
        accept_encoding: Value of the Accept-Encoding header.

    Returns:
        True if gzip is accepted with q > 0.
    """
    encodings = parse_accept_encoding(accept_encoding)
    return encodings.get("gzip", 0.0) > 0.0


def compress_response(
    response: Response,
    accept_encoding: str = "",
) -> tuple[Response, bool]:
    """Compress a response body with gzip if appropriate.

    Args:
        response: The original HTTP response.
        accept_encoding: Value of the Accept-Encoding header.

    Returns:
        (modified_response, was_compressed) where modified_response has
        Content-Encoding and Vary headers set if compressed.
    """
    # Check if client accepts gzip
    if not client_accepts_gzip(accept_encoding):
        return response, False

    # Check if response should be compressed
    if not should_compress(response):
        return response, False

    # Compress the body
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        if isinstance(response.body, str):
            gz.write(response.body.encode("utf-8"))
        else:
            gz.write(response.body)

    compressed_body = buf.getvalue()

    # Only use compression if it actually reduces size
    if len(compressed_body) >= len(response.body):
        return response, False

    # Create new response with compressed body
    new_headers = dict(response.headers)
    new_headers["Content-Encoding"] = "gzip"
    new_headers["Vary"] = "Accept-Encoding"

    compressed_response = Response(
        status_code=response.status_code,
        body=compressed_body,
        headers=new_headers,
    )

    return compressed_response, True
