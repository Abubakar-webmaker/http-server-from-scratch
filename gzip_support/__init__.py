"""Compression support package."""

from .gzip_handler import (
    compress_response,
    client_accepts_gzip,
    parse_accept_encoding,
    should_compress,
)

__all__ = [
    "compress_response",
    "client_accepts_gzip",
    "parse_accept_encoding",
    "should_compress",
]
