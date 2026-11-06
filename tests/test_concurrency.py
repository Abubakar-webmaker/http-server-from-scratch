import socket
import threading
import time
import unittest

from http.response import Response
from server import HTTPServer


class ConcurrencyTests(unittest.TestCase):

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
            max_clients=50,
            socket_timeout=4,
        )

        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )

        self.server_thread.start()

        deadline = time.monotonic() + 3

        while time.monotonic() < deadline:
            try:
                connection = socket.create_connection(
                    ("127.0.0.1", self.port),
                    timeout=0.2,
                )
                connection.close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("Server did not start")

    def tearDown(self):
        self.server.shutdown()
        self.server_thread.join(timeout=5)

    def request(self, path="/"):
        with socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=4,
        ) as client:
            client.sendall(
                f"GET {path} HTTP/1.1\r\n"
                "Host: localhost\r\n"
                "Connection: close\r\n"
                "\r\n".encode()
            )

            response = bytearray()

            while True:
                data = client.recv(4096)

                if not data:
                    break

                response.extend(data)

            return bytes(response)

    def test_multiple_clients(self):
        results = []
        errors = []

        def client_task():
            try:
                results.append(self.request("/"))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=client_task)
            for _ in range(20)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=6)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 20)

        for response in results:
            self.assertIn(b"200 OK", response)

    def test_slow_client_does_not_block_fast_client(self):
        slow_connection = socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=3,
        )

        try:
            # Send incomplete headers and keep the connection open.
            slow_connection.sendall(b"GET / HTTP/1.1\r\n")

            start = time.monotonic()
            response = self.request("/")
            elapsed = time.monotonic() - start

            self.assertIn(b"200 OK", response)
            self.assertLess(elapsed, 2)

        finally:
            slow_connection.close()

    def test_concurrent_request_counter(self):
        number_of_clients = 30
        threads = []

        def client_task():
            self.request("/")

        for _ in range(number_of_clients):
            thread = threading.Thread(target=client_task)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=6)

        stats = self.server.get_stats()

        self.assertEqual(
            stats["total_requests"],
            number_of_clients,
        )

    def test_slow_route_runs_independently(self):
        def slow_handler(request):
            time.sleep(1)
            return Response(200, "Slow response")

        self.server.router.get("/slow", slow_handler)

        slow_result = {}

        def slow_request():
            slow_result["response"] = self.request("/slow")

        thread = threading.Thread(target=slow_request)
        thread.start()

        time.sleep(0.1)

        start = time.monotonic()
        fast_response = self.request("/")
        elapsed = time.monotonic() - start

        thread.join(timeout=3)

        self.assertIn(b"200 OK", fast_response)
        self.assertLess(elapsed, 0.8)
        self.assertIn(b"200 OK", slow_result["response"])

    def test_client_disconnect_does_not_crash_server(self):
        connection = socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=3,
        )

        connection.sendall(b"GET / HTTP/1.1\r\n")
        connection.close()

        response = self.request("/")

        self.assertIn(b"200 OK", response)

    def test_shutdown_stops_server(self):
        self.server.shutdown()

        self.server_thread.join(timeout=5)

        self.assertFalse(self.server_thread.is_alive())


if __name__ == "__main__":
    unittest.main()