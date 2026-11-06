import socket
import threading
import time
import unittest

from server import HTTPServer


class ServerTestCase(unittest.TestCase):

    def setUp(self):
        temporary_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        temporary_socket.bind(("127.0.0.1", 0))
        self.port = temporary_socket.getsockname()[1]
        temporary_socket.close()

        self.server = HTTPServer(
            host="127.0.0.1",
            port=self.port,
            max_clients=20,
            socket_timeout=2,
        )

        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )

        self.server_thread.start()

        self.wait_for_server()

    def wait_for_server(self):
        deadline = time.monotonic() + 3

        while time.monotonic() < deadline:
            try:
                connection = socket.create_connection(
                    ("127.0.0.1", self.port),
                    timeout=0.2,
                )
                connection.close()
                return
            except OSError:
                time.sleep(0.05)

        self.fail("Server did not start")

    def tearDown(self):
        self.server.shutdown()
        self.server_thread.join(timeout=4)

    def send_request(self, request):
        with socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=3,
        ) as client:
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)

            response = bytearray()

            while True:
                chunk = client.recv(4096)

                if not chunk:
                    break

                response.extend(chunk)

            return bytes(response)

    def test_home_route(self):
        response = self.send_request(
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"200 OK", response)
        self.assertIn(b"Hello World", response)

    def test_users_route(self):
        response = self.send_request(
            b"GET /users HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"200 OK", response)
        self.assertIn(b"Ali", response)

    def test_products_route(self):
        response = self.send_request(
            b"GET /products HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"200 OK", response)
        self.assertIn(b"Laptop", response)

    def test_dynamic_route(self):
        response = self.send_request(
            b"GET /users/1 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"200 OK", response)
        self.assertIn(b"Ali", response)

    def test_unknown_route(self):
        response = self.send_request(
            b"GET /unknown HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"404 Not Found", response)

    def test_unsupported_method(self):
        response = self.send_request(
            b"DELETE /users HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"405 Method Not Allowed", response)
        self.assertIn(b"Allow:", response)

    def test_malformed_request(self):
        response = self.send_request(b"INVALID REQUEST\r\n\r\n")

        self.assertIn(b"400 Bad Request", response)

    def test_request_counter(self):
        self.send_request(
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertGreaterEqual(
            self.server.get_stats()["total_requests"],
            1,
        )

    def test_handler_exception_returns_500(self):
        def broken_handler(request):
            raise RuntimeError("Test handler failure")

        self.server.router.get("/test-error", broken_handler)

        response = self.send_request(
            b"GET /test-error HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"500 Internal Server Error", response)

    def test_invalid_handler_return_returns_500(self):
        self.server.router.get(
            "/invalid-return",
            lambda request: "not a Response",
        )

        response = self.send_request(
            b"GET /invalid-return HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )

        self.assertIn(b"500 Internal Server Error", response)


if __name__ == "__main__":
    unittest.main()