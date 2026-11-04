"""HTTP request handling module.

This module provides the Request data class representing a parsed HTTP request.
"""

from dataclasses import dataclass, field


@dataclass
class Request:
    """Parsed HTTP request representation.
    
    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD)
        path: Request path with query string (e.g., /users?id=1)
        version: HTTP version (HTTP/1.0, HTTP/1.1)
        headers: Request headers as dict (case-insensitive keys)
        body: Request body as bytes (empty for GET/HEAD)
    """
    method: str
    path: str
    version: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""