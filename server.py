
"""
Custom Python HTTP Server - Phase 4.

TCP handling, HTTP parsing, routing, and response
serialization remain separate responsibilities.
"""

import json
import socket

from http.parser import parse_request, HTTPParseError
from http.response import Response, serialize_response
from routing import Router


class HTTPServer:
    def __init__(
        self,
        host="127.0.0.1",
        port=8080
    ):
        self.host = host
        self.port = port
        self.router = Router()

    def get(self, path, handler):
        self.router.get(path, handler)

    def post(self, path, handler):
        self.router.post(path, handler)

    @staticmethod
    def _internal_error():
        return Response(
            status_code=500,
            headers={
                "Content-Type": "text/plain; charset=utf-8"
            },
            body=b"500 - Internal Server Error",
        )

    def handle_request(self, request):
        return self.router.dispatch(request)

    def handle_client(self, client_socket):
        try:
            request = parse_request(client_socket)

            response = self.handle_request(request)

        except HTTPParseError:
            response = Response(
                status_code=400,
                headers={
                    "Content-Type": "text/plain; charset=utf-8"
                },
                body=b"400 - Bad Request",
            )

        except Exception:
            response = self._internal_error()

        try:
            response_bytes = serialize_response(response)
            client_socket.sendall(response_bytes)

        except Exception:
            # Attempt a generic 500 response if serialization fails.
            try:
                error_bytes = serialize_response(
                    self._internal_error()
                )
                client_socket.sendall(error_bytes)
            except Exception:
                pass

        finally:
            client_socket.close()

    def serve_forever(self):
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        ) as server_socket:

            server_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1
            )

            server_socket.bind(
                (self.host, self.port)
            )

            server_socket.listen()

            print(
                f"Server listening on {self.host}:{self.port}"
            )
            print("Waiting for incoming connections...")

            while True:
                client_socket, client_address = (
                    server_socket.accept()
                )

                print(
                    f"Connection received from {client_address}"
                )

                self.handle_client(client_socket)


# --------------------------------------------------
# Application route handlers
# --------------------------------------------------

users = [
    {
        "id": 1,
        "name": "Ali"
    }
]

products = [
    {
        "id": 1,
        "name": "Laptop"
    },
    {
        "id": 2,
        "name": "Keyboard"
    }
]


def home(request):
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Python HTTP Server</title>
    </head>
    <body>
        <h1>Hello World</h1>
        <p>Welcome to my Python HTTP Server.</p>
        <p>Phase 4: HTTP Routing System is working.</p>
    </body>
    </html>
    """

    return Response(
        status_code=200,
        headers={
            "Content-Type": "text/html; charset=utf-8"
        },
        body=html.encode("utf-8"),
    )


def get_users(request):
    return Response(
        status_code=200,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        body=json.dumps(users).encode("utf-8"),
    )


def create_user(request):
    try:
        data = json.loads(request.body.decode("utf-8"))

        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")

        name = data.get("name")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("A valid name is required.")

    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return Response(
            status_code=400,
            headers={
                "Content-Type": "text/plain; charset=utf-8"
            },
            body=b"400 - Invalid JSON request body",
        )

    user = {
        "id": max(
            (item["id"] for item in users),
            default=0
        ) + 1,
        "name": name.strip(),
    }

    users.append(user)

    return Response(
        status_code=201,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        body=json.dumps(user).encode("utf-8"),
    )


def get_products(request):
    return Response(
        status_code=200,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        body=json.dumps(products).encode("utf-8"),
    )


def get_user(request, id):
    user = next(
        (
            item for item in users
            if item["id"] == int(id)
        ),
        None
    )

    if user is None:
        return Response(
            status_code=404,
            headers={
                "Content-Type": "text/plain; charset=utf-8"
            },
            body=b"404 - User Not Found",
        )

    return Response(
        status_code=200,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        body=json.dumps(user).encode("utf-8"),
    )


def get_user_post(request, id, post_id):
    return Response(
        status_code=200,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        },
        body=json.dumps({
            "user_id": id,
            "post_id": post_id,
        }).encode("utf-8"),
    )


# --------------------------------------------------
# Register application routes
# --------------------------------------------------

server = HTTPServer()

server.get("/", home)
server.get("/users", get_users)
server.post("/users", create_user)
server.get("/products", get_products)

server.get("/users/:id", get_user)
server.get(
    "/users/:id/posts/:post_id",
    get_user_post
)


if __name__ == "__main__":
    server.serve_forever()
