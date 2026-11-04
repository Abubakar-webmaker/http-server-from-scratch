"""Security and TLS support."""

from .tls import SSLContextFactory, wrap_socket_tls

__all__ = [
    "SSLContextFactory",
    "wrap_socket_tls",
]
