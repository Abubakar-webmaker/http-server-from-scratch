import json
import logging
import socket
import threading

from http.parser import parse_request, HTTPParseError
from http.response import Response, serialize_response
from routing.router import Router


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
    ):
        self.host = host
        self.port = port
        self.socket_timeout = socket_timeout

        self.router = Router()

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

    def _send_response(self, client_socket, response):
        response_bytes = serialize_response(response)
        client_socket.sendall(response_bytes)

    def _read_request(self, client_socket):
        """Read one HTTP request using Content-Length."""

        buffer = bytearray()
        header_end = b"\r\n\r\n"

        while header_end not in buffer:
            chunk = client_socket.recv(4096)

            if not chunk:
                raise HTTPParseError("Client disconnected before headers")

            buffer.extend(chunk)

            if len(buffer) > 65536:
                raise HTTPParseError("HTTP headers too large")

        header_bytes, _, remaining = bytes(buffer).partition(header_end)

        try:
            header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
            content_length = 0

            for line in header_lines[1:]:
                if ":" not in line:
                    raise HTTPParseError("Invalid HTTP header")

                name, value = line.split(":", 1)

                if name.strip().lower() == "content-length":
                    content_length = int(value.strip())

                    if content_length < 0:
                        raise HTTPParseError("Invalid Content-Length")

                if name.strip().lower() == "transfer-encoding":
                    raise HTTPParseError(
                        "Transfer-Encoding is not supported"
                    )

        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPParseError("Invalid HTTP headers") from exc

        if content_length > 10 * 1024 * 1024:
            raise HTTPParseError("Request body too large")

        body = bytearray(remaining)

        if len(body) > content_length:
            raise HTTPParseError("Unexpected extra request data")

        while len(body) < content_length:
            chunk = client_socket.recv(
                min(4096, content_length - len(body))
            )

            if not chunk:
                raise HTTPParseError("Incomplete request body")

            body.extend(chunk)

        return parse_request(
            header_bytes + header_end + bytes(body)
        )

    def _handle_client(self, client_socket, client_address):
        """Process a single client's HTTP request."""

        try:
            client_socket.settimeout(self.socket_timeout)

            request = self._read_request(client_socket)

            self._increment_request_count()

            logger.info(
                "Request: %s %s from %s",
                request.method,
                request.path,
                client_address,
            )

            response = self.router.dispatch(request)

            self._send_response(client_socket, response)

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
                )
            except OSError:
                pass

        except socket.timeout:
            logger.warning("Client timed out: %s", client_address)

        except (ConnectionError, OSError) as exc:
            logger.warning(
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
                self.active_threads.discard(
                    threading.current_thread()
                )

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