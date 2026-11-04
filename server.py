import json
import logging
import socket
import threading

from http.parser import HTTPParseError
from http.response import Response, serialize_response
from http.keepalive import BufferedRequestReader, should_keep_alive
from routing.router import Router
from pathlib import Path
from static_files.handler import StaticFileHandler
from urllib.parse import urlsplit


BASE_DIR = Path(__file__).resolve().parent
STATIC_URL_PREFIX = "/static/"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
)

logger = logging.getLogger("HTTPServer")


class HTTPServer:
    """Threaded HTTP server using Python's built-in socket module."""

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
    ):
        self.host = host
        self.port = port
        self.socket_timeout = socket_timeout
        self.keep_alive_timeout = keep_alive_timeout
        self.max_requests_per_connection = max_requests_per_connection
        self.max_header_size = max_header_size
        self.max_body_size = max_body_size

        self.router = Router()

        self.static_handler = StaticFileHandler(
            root_directory=str(BASE_DIR / "static"),
        )

        self.server_socket = None
        self.running = threading.Event()
        self.shutdown_event = threading.Event()

        self.client_slots = threading.BoundedSemaphore(max_clients)

        self.active_threads = set()
        self.threads_lock = threading.Lock()

        self.stats_lock = threading.Lock()
        self.request_count = 0

        self._register_routes()

    def _register_routes(self):
        """Register demonstration routes."""

        users = [
            {"id": 1, "name": "Ali"},
        ]

        products = [
            {"id": 1, "name": "Laptop"},
            {"id": 2, "name": "Keyboard"},
        ]

        def home(request):
            return Response(
                200,
                "<html><body><h1>Hello World</h1></body></html>",
                {"Content-Type": "text/html; charset=utf-8"},
            )

        def get_users(request):
            return Response(
                200,
                json.dumps(users),
                {"Content-Type": "application/json"},
            )

        def create_user(request):
            try:
                data = json.loads(request.body.decode("utf-8"))

                if not isinstance(data, dict) or not data.get("name"):
                    return Response(400, "Invalid user data")

                user = {
                    "id": len(users) + 1,
                    "name": data["name"],
                }

                users.append(user)

                return Response(
                    201,
                    json.dumps(user),
                    {"Content-Type": "application/json"},
                )

            except (ValueError, UnicodeDecodeError):
                return Response(400, "Invalid JSON")

        def get_products(request):
            return Response(
                200,
                json.dumps(products),
                {"Content-Type": "application/json"},
            )

        def get_user(request, id):
            user = next(
                (item for item in users if str(item["id"]) == id),
                None,
            )

            if user is None:
                return Response(404, "User not found")

            return Response(
                200,
                json.dumps(user),
                {"Content-Type": "application/json"},
            )

        def get_user_post(request, id, post_id):
            return Response(
                200,
                json.dumps({
                    "user_id": id,
                    "post_id": post_id,
                }),
                {"Content-Type": "application/json"},
            )

        self.router.get("/", home)
        self.router.get("/users", get_users)
        self.router.post("/users", create_user)
        self.router.get("/products", get_products)
        self.router.get("/users/:id", get_user)
        self.router.get(
            "/users/:id/posts/:post_id",
            get_user_post,
        )

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
        response: Response,
        keep_alive: bool = False,
    ) -> None:
        """Serialize and send a response, honouring the keep-alive flag."""
        response_bytes = serialize_response(response, keep_alive=keep_alive)
        client_socket.sendall(response_bytes)

    def _dispatch_request(self, request):
        """Route a parsed request to the right handler and return a Response."""
        request_path = urlsplit(request.path).path

        if request_path.startswith(STATIC_URL_PREFIX):
            relative_path = request_path[len(STATIC_URL_PREFIX):]
            return self.static_handler.handle(request, relative_path)

        return self.router.dispatch(request)

    def _handle_client(self, client_socket, client_address):
        """Process all HTTP requests on a single persistent connection.

        Implements HTTP/1.1 keep-alive: a single TCP connection can serve
        multiple HTTP requests/responses.

        Connection lifecycle:
        1. Accept client connection
        2. Read HTTP request (including chunked body if present)
        3. Route to handler, get response
        4. Decide keep-alive based on:
           - HTTP version (1.1 keep-alive by default, 1.0 doesn't)
           - Connection header (Connection: close forces close)
           - Request limit reached
           - Handler/parsing errors
        5. Send response with Connection header
        6. If keep-alive: loop back to step 2
        7. If close: break and cleanup

        For chunked requests:
        - BufferedRequestReader handles Transfer-Encoding: chunked
        - Collects all chunks into request.body
        - Validates chunk format (size in hex + CRLF + data + CRLF)
        - Rejects oversized decoded bodies

        Args:
            client_socket: Connected TCP socket to client
            client_address: (host, port) tuple
        """
        requests_served = 0

        reader = BufferedRequestReader(
            client_socket,
            max_header_size=self.max_header_size,
            max_body_size=self.max_body_size,
        )

        try:
            # First request uses normal timeout; subsequent requests
            # use keep-alive timeout (shorter to reclaim idle connections)
            client_socket.settimeout(self.socket_timeout)

            while True:
                # --- Read one complete request ---
                try:
                    request = reader.read_request()
                except socket.timeout:
                    logger.debug(
                        "Keep-alive timeout on idle connection: %s",
                        client_address,
                    )
                    break

                if request is None:
                    # Clean EOF - client closed connection gracefully
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

                # --- Decide connection policy BEFORE error handling ---
                # We decide now so errors don't keep connection open
                client_wants_keep_alive = should_keep_alive(request)
                limit_reached = (
                    requests_served >= self.max_requests_per_connection
                )
                keep_connection = client_wants_keep_alive and not limit_reached

                # --- Dispatch to router and handler ---
                try:
                    response = self._dispatch_request(request)
                except Exception:
                    logger.exception(
                        "Unhandled dispatch error for %s",
                        client_address,
                    )
                    response = Response(500, "500 - Internal Server Error")
                    keep_connection = False

                # --- Send HTTP response ---
                try:
                    self._send_response(
                        client_socket,
                        response,
                        keep_alive=keep_connection,
                    )
                except OSError as exc:
                    logger.debug(
                        "Send error to %s: %s",
                        client_address,
                        exc,
                    )
                    break

                # --- Loop control ---
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
                self._send_response(
                    client_socket,
                    Response(400, "400 - Bad Request"),
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
                self._send_response(
                    client_socket,
                    Response(500, "500 - Internal Server Error"),
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
        """Start accepting incoming client connections."""

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
            "Server listening on %s:%s",
            self.host,
            self.port,
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