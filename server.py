"""HTTP/1.1 Server - Transport Layer.

This module handles ONLY network transport:
- Socket creation and binding
- Accepting client connections
- Managing connection lifecycle (threading)
- Keep-alive connection handling
- Reading/writing data on sockets

Application logic is delegated to:
- dispatcher.py (request orchestration)
- handlers.py (business logic)
- routing/router.py (URL routing)
"""

import logging
import socket
import threading

from http.parser import HTTPParseError
from http.response import Response, serialize_response
from http.keepalive import BufferedRequestReader, should_keep_alive
from gzip_support.gzip_handler import compress_response
from routing.router import Router
from static_files.handler import StaticFileHandler
from dispatcher import RequestDispatcher, get_client_address
from core.rate_limiter import RateLimiter
from security.tls import SSLContextFactory

from pathlib import Path
import handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
)

logger = logging.getLogger("HTTPServer")

BASE_DIR = Path(__file__).resolve().parent


class HTTPServer:
    """HTTP/1.1 server - manages socket connections and request processing.
    
    Responsibilities:
    - Socket management (bind, listen, accept)
    - Thread pool for concurrent clients
    - Connection lifecycle (keep-alive loop)
    - Delegation to RequestDispatcher for app logic
    
    Does NOT handle:
    - Routing (handled by Router)
    - Request handlers (handlers.py)
    - Request orchestration (Dispatcher)
    - Static files (StaticFileHandler)
    """

    def __init__(
        self,
        host="127.0.0.1",
        port=8080,
        max_clients=100,
        socket_timeout=5.0,
        keep_alive_timeout=15.0,
        max_requests_per_connection=100,
        max_header_size=65536,
        max_body_size=10 * 1024 * 1024,
        use_tls=False,
        cert_file=None,
        key_file=None,
        rate_limit_requests=100,
        rate_limit_window=60,
    ):
        """Initialize HTTP server with configuration.
        
        Args:
            host: Bind address (default: localhost)
            port: Bind port (default: 8080)
            max_clients: Max concurrent connections (default: 100)
            socket_timeout: Timeout for initial request (seconds)
            keep_alive_timeout: Timeout for keep-alive requests (seconds)
            max_requests_per_connection: Max requests per connection
            max_header_size: Max header size in bytes
            max_body_size: Max request body size in bytes
            use_tls: Enable TLS/HTTPS (default: False)
            cert_file: Path to SSL certificate (PEM format)
            key_file: Path to SSL private key (PEM format)
            rate_limit_requests: Max requests per client per window (default: 100)
            rate_limit_window: Rate limit window in seconds (default: 60)
        """
        self.host = host
        self.port = port
        self.socket_timeout = socket_timeout
        self.keep_alive_timeout = keep_alive_timeout
        self.max_requests_per_connection = max_requests_per_connection
        self.max_header_size = max_header_size
        self.max_body_size = max_body_size
        self.use_tls = use_tls
        self.cert_file = cert_file
        self.key_file = key_file
        self.ssl_context = None

        # Initialize TLS if enabled
        if use_tls and cert_file and key_file:
            try:
                self.ssl_context = SSLContextFactory.create_context(
                    cert_file=cert_file,
                    key_file=key_file,
                )
                logger.info("TLS enabled with cert: %s", cert_file)
            except Exception as exc:
                logger.warning("TLS initialization failed: %s", exc)
                self.ssl_context = None

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_window=rate_limit_requests,
            window_seconds=rate_limit_window,
        )

        # Initialize routing
        self.router = Router()
        self._register_routes()

        # Initialize static file handler
        self.static_handler = StaticFileHandler(
            root_directory=str(BASE_DIR / "static"),
        )

        # Initialize request dispatcher (app orchestration)
        self.dispatcher = RequestDispatcher(
            router=self.router,
            static_handler=self.static_handler,
            static_url_prefix="/static/",
        )

        # Register rate limiter middleware
        self._register_middleware()

        # Socket and lifecycle management
        self.server_socket = None
        self.running = threading.Event()
        self.shutdown_event = threading.Event()

        # Connection pooling
        self.client_slots = threading.BoundedSemaphore(max_clients)
        self.active_threads = set()
        self.threads_lock = threading.Lock()

        # Statistics
        self.stats_lock = threading.Lock()
        self.request_count = 0

    def _register_routes(self):
        """Register all application routes with their handlers.
        
        Handlers are imported from handlers.py module.
        This keeps route registration in server.py but handlers in handlers.py.
        """
        self.router.get("/", handlers.home)
        self.router.get("/users", handlers.get_users)
        self.router.post("/users", handlers.create_user)
        self.router.get("/products", handlers.get_products)
        self.router.get("/products/:id", handlers.get_product)
        self.router.get("/users/:id", handlers.get_user)
        self.router.get(
            "/users/:id/posts/:post_id",
            handlers.get_user_post,
        )

    def _register_middleware(self):
        """Register middleware functions with the dispatcher.
        
        Middleware executes in registration order (left to right):
        1. Rate limiting - enforce per-client request limits
        """
        
        def rate_limit_middleware(request, next_handler):
            """Rate limit middleware - enforce per-client request limits.
            
            Extracts client IP from thread-local storage (thread-safe).
            Returns 429 (Too Many Requests) if limit exceeded.
            """
            # Get client IP from thread-local storage (thread-safe, no race conditions)
            client_ip = "0.0.0.0"
            client_address = get_client_address()
            
            if client_address:
                client_ip = client_address[0]
            
            # Fall back to X-Forwarded-For header if available
            if client_ip == "0.0.0.0" and hasattr(request, 'headers'):
                for name, value in request.headers.items():
                    if name.lower() == "x-forwarded-for":
                        # X-Forwarded-For can have multiple IPs; use first
                        client_ip = value.split(",")[0].strip()
                        break
            
            logger.debug("Rate limiter: checking client %s", client_ip)
            
            # Check if client is rate limited
            if not self.rate_limiter.is_allowed(client_ip):
                retry_after = self.rate_limiter.get_retry_after(client_ip)
                response = Response(429, "429 - Too Many Requests")
                response.headers["Retry-After"] = str(retry_after)
                logger.warning(
                    "Rate limit exceeded for client %s (active clients: %d)",
                    client_ip,
                    self.rate_limiter.active_clients,
                )
                return response
            
            # Client is allowed, proceed to next middleware/handler
            return next_handler(request)
        
        self.dispatcher.register_middleware(rate_limit_middleware)

    def get_stats(self):
        """Return a consistent snapshot of shared server statistics."""

        with self.stats_lock:
            request_count = self.request_count

        with self.threads_lock:
            active_threads = len(self.active_threads)

        return {
            "total_requests": request_count,
            "active_threads": active_threads,
        }

    def _increment_request_count(self):
        """Safely increment the shared request counter."""

        with self.stats_lock:
            self.request_count += 1

    def _send_response(
        self,
        client_socket,
        response,
        request=None,
        keep_alive: bool = False,
    ) -> None:
        """Serialize and send a response over socket.
        
        Applies gzip compression if client accepts it.
        
        Args:
            client_socket: Connected socket to client
            response: Response object
            request: Request object (to check Accept-Encoding header)
            keep_alive: Whether connection should stay open
        """
        # Apply gzip compression if client accepts it
        if request and hasattr(request, 'headers'):
            accept_encoding = ""
            for name, value in request.headers.items():
                if name.lower() == "accept-encoding":
                    accept_encoding = value
                    break
            
            response, was_compressed = compress_response(
                response,
                accept_encoding=accept_encoding,
            )
            
            if was_compressed:
                logger.debug("Response compressed with gzip")
        
        response_bytes = serialize_response(
            response,
            keep_alive=keep_alive,
        )
        client_socket.sendall(response_bytes)

    def _handle_client(self, client_socket, client_address):
        """Process all HTTP requests on a single persistent connection.

        Socket management only - delegates to dispatcher for app logic.
        Wraps socket with TLS if HTTPS enabled.
        
        Keeps connection open for multiple requests (keep-alive):
        1. Wrap socket with TLS if enabled
        2. Read HTTP request (including chunked body if present)
        3. Dispatch to application via self.dispatcher
        4. Send response with Connection header
        5. If keep-alive: loop back to step 2
        6. If close: break and cleanup

        Args:
            client_socket: Connected TCP socket to client
            client_address: (host, port) tuple
        """
        # Stage 0: Wrap socket with TLS if enabled
        if self.ssl_context:
            try:
                from security.tls import wrap_socket_tls
                client_socket, tls_ok = wrap_socket_tls(
                    client_socket,
                    self.ssl_context,
                    server_side=True,
                )
                if not tls_ok:
                    logger.warning("TLS handshake failed for %s", client_address)
                    try:
                        client_socket.close()
                    except OSError:
                        pass
                    self.client_slots.release()
                    with self.threads_lock:
                        self.active_threads.discard(threading.current_thread())
                    return
                logger.debug("TLS connection established with %s", client_address)
            except Exception as exc:
                logger.exception("TLS wrapping error for %s: %s", client_address, exc)
                try:
                    client_socket.close()
                except OSError:
                    pass
                self.client_slots.release()
                with self.threads_lock:
                    self.active_threads.discard(threading.current_thread())
                return
        
        requests_served = 0

        reader = BufferedRequestReader(
            client_socket,
            max_header_size=self.max_header_size,
            max_body_size=self.max_body_size,
        )

        try:
            # First request uses normal timeout
            client_socket.settimeout(self.socket_timeout)

            while True:
                # --- Stage 1: Read request ---
                try:
                    request = reader.read_request()
                except socket.timeout:
                    logger.debug(
                        "Keep-alive timeout on idle connection: %s",
                        client_address,
                    )
                    break

                if request is None:
                    logger.debug(
                        "Client closed connection: %s",
                        client_address,
                    )
                    break

                requests_served += 1
                self._increment_request_count()

                logger.info(
                    "Request %d: %s %s from %s",
                    requests_served,
                    request.method,
                    request.path,
                    client_address,
                )

                # --- Stage 2: Decide connection policy ---
                client_wants_keep_alive = should_keep_alive(request)
                limit_reached = (
                    requests_served >= self.max_requests_per_connection
                )
                keep_connection = client_wants_keep_alive and not limit_reached

                # --- Stage 3: Dispatch to application layer ---
                try:
                    response = self.dispatcher.dispatch(
                        request,
                        client_address=client_address,
                    )
                except Exception:
                    logger.exception(
                        "Unhandled dispatch error for %s",
                        client_address,
                    )
                    response = Response(500, "500 - Internal Server Error")
                    keep_connection = False

                # --- Stage 4: Send response (with gzip compression) ---
                try:
                    self._send_response(
                        client_socket,
                        response,
                        request=request,
                        keep_alive=keep_connection,
                    )
                except OSError as exc:
                    logger.debug(
                        "Send error to %s: %s",
                        client_address,
                        exc,
                    )
                    break

                # --- Stage 5: Loop control ---
                if not keep_connection:
                    break

                # Switch to keep-alive timeout for next request
                client_socket.settimeout(self.keep_alive_timeout)

        except HTTPParseError as exc:
            logger.warning(
                "Malformed request from %s: %s",
                client_address,
                exc,
            )
            try:
                response = Response(400, "400 - Bad Request")
                self._send_response(
                    client_socket,
                    response,
                    keep_alive=False,
                )
            except OSError:
                pass

        except socket.timeout:
            logger.debug("Initial request timeout: %s", client_address)

        except (ConnectionError, OSError) as exc:
            logger.debug(
                "Connection error from %s: %s",
                client_address,
                exc,
            )

        except Exception:
            logger.exception(
                "Unexpected client handler error: %s",
                client_address,
            )
            try:
                response = Response(500, "500 - Internal Server Error")
                self._send_response(
                    client_socket,
                    response,
                    keep_alive=False,
                )
            except OSError:
                pass

        finally:
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            try:
                client_socket.close()
            except OSError:
                pass

            with self.threads_lock:
                self.active_threads.discard(threading.current_thread())

            self.client_slots.release()

    def start(self):
        """Start accepting incoming client connections.
        
        If TLS is enabled, wrap the server socket with SSL/TLS.
        """

        if self.running.is_set():
            raise RuntimeError("Server is already running")

        self.shutdown_event.clear()

        self.server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        self.server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(128)
        self.server_socket.settimeout(1.0)

        self.running.set()

        logger.info(
            "Server listening on %s:%s%s",
            self.host,
            self.port,
            " (TLS enabled)" if self.use_tls and self.ssl_context else "",
        )

        try:
            while self.running.is_set():
                try:
                    client_socket, client_address = (
                        self.server_socket.accept()
                    )

                except socket.timeout:
                    continue

                except OSError:
                    if not self.running.is_set():
                        break
                    raise

                if not self.client_slots.acquire(blocking=False):
                    logger.warning(
                        "Maximum clients reached: %s",
                        client_address,
                    )

                    try:
                        client_socket.settimeout(1.0)
                        self._send_response(
                            client_socket,
                            Response(
                                503,
                                "503 - Server Busy",
                            ),
                        )
                    except OSError:
                        pass
                    finally:
                        client_socket.close()

                    continue

                worker = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=False,
                )

                with self.threads_lock:
                    self.active_threads.add(worker)

                try:
                    worker.start()

                except Exception:
                    with self.threads_lock:
                        self.active_threads.discard(worker)

                    self.client_slots.release()
                    client_socket.close()
                    logger.exception("Could not start client thread")

        finally:
            self.shutdown()

    def shutdown(self):
        """Stop accepting connections and wait for active workers."""

        if self.shutdown_event.is_set():
            return

        self.shutdown_event.set()
        self.running.clear()

        logger.info("Server shutdown initiated")

        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except OSError:
                pass

        current_thread = threading.current_thread()

        with self.threads_lock:
            workers = list(self.active_threads)

        for worker in workers:
            if worker is not current_thread and worker.is_alive():
                worker.join(timeout=self.socket_timeout + 2)

        with self.threads_lock:
            remaining = len(self.active_threads)

        if remaining:
            logger.warning(
                "%s client thread(s) are still active",
                remaining,
            )

        logger.info("Server shutdown finished")


if __name__ == "__main__":
    server = HTTPServer(
        host="127.0.0.1",
        port=8080,
        max_clients=100,
        socket_timeout=5,
    )

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        server.shutdown()