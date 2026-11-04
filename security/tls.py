"""TLS/HTTPS support using Python's built-in ssl module."""

import ssl
import socket
from pathlib import Path
from typing import Optional, Tuple

from utils.logger import get_logger
from utils.exceptions import SSLConfigurationError

logger = get_logger(__name__)


class SSLContextFactory:
    """Factory for creating SSL/TLS contexts."""

    @staticmethod
    def create_context(
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        protocol: int = ssl.PROTOCOL_TLS_SERVER,
    ) -> ssl.SSLContext:
        """Create an SSL context for HTTPS.

        Args:
            cert_file: Path to the certificate file (PEM format).
            key_file: Path to the private key file (PEM format).
            protocol: SSL protocol version (default: TLS_SERVER).

        Returns:
            Configured SSLContext.

        Raises:
            SSLConfigurationError: If cert/key files are missing or invalid.
        """
        if not cert_file or not key_file:
            raise SSLConfigurationError(
                "Both cert_file and key_file must be specified"
            )

        cert_path = Path(cert_file)
        key_path = Path(key_file)

        if not cert_path.exists():
            raise SSLConfigurationError(f"Certificate file not found: {cert_file}")

        if not key_path.exists():
            raise SSLConfigurationError(f"Key file not found: {key_file}")

        try:
            context = ssl.SSLContext(protocol)

            # Load certificate and key
            context.load_cert_chain(str(cert_path), str(key_path))

            # Recommended security settings
            context.options |= ssl.OP_NO_COMPRESSION
            context.set_ciphers("DEFAULT:!aNULL:!eNULL:!MD5:!3DES:!DES:!RC4:!IDEA:!SEED:!aDSS:!SRP:!PSK")

            return context

        except ssl.SSLError as exc:
            raise SSLConfigurationError(
                f"Failed to load SSL certificate/key: {exc}"
            ) from exc

    @staticmethod
    def create_self_signed_context(
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
    ) -> ssl.SSLContext:
        """Create an SSL context using provided self-signed certificate.

        For development/testing only. Same as create_context().

        Args:
            cert_file: Path to the self-signed certificate (PEM format).
            key_file: Path to the private key (PEM format).

        Returns:
            Configured SSLContext.
        """
        return SSLContextFactory.create_context(cert_file, key_file)


def wrap_socket_tls(
    sock: socket.socket,
    ssl_context: ssl.SSLContext,
    server_side: bool = True,
) -> Tuple[ssl.SSLSocket, bool]:
    """Wrap a socket with TLS.

    Args:
        sock: The TCP socket to wrap.
        ssl_context: The SSLContext to use.
        server_side: True for server, False for client.

    Returns:
        (ssl_socket, success) tuple where success indicates if wrapping succeeded.
        On failure, returns the original socket and False. SSL errors are logged.
    """
    try:
        ssl_sock = ssl_context.wrap_socket(
            sock,
            server_side=server_side,
            do_handshake_on_connect=True,
        )
        return ssl_sock, True

    except ssl.SSLError as exc:
        logger.debug("SSL handshake error: %s", exc)
        return sock, False

    except Exception as exc:
        logger.debug("Unexpected TLS wrapping error: %s", exc)
        return sock, False
