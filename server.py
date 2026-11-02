import json
import logging
import socket

from http.parser import parse_request, HTTPParseError
from http.response import Response, serialize_response


HOST = "127.0.0.1"
PORT = 8080

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


def create_error_response(status_code: int, message: str) -> Response:
    return Response(
        status_code=status_code,
        headers={
            "Content-Type": "text/plain; charset=utf-8"
        },
        body=message
    )


def handle_request(request, users: list) -> Response:
    """
    Select a response based on the parsed HTTP request.
    """

    # GET /
    if request.method == "GET" and request.path == "/":
        html_body = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Python HTTP Server</title>
</head>
<body>
    <h1>Hello World</h1>
    <p>Welcome to my Python HTTP Server.</p>
    <p>Phase 3: HTTP Response Generation is working.</p>
</body>
</html>
"""

        return Response(
            status_code=200,
            headers={
                "Content-Type": "text/html; charset=utf-8"
            },
            body=html_body
        )

    # POST /users
    if request.method == "POST" and request.path == "/users":

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return create_error_response(
                400,
                "Invalid JSON request body."
            )

        if not isinstance(payload, dict):
            return create_error_response(
                400,
                "Request body must be a JSON object."
            )

        name = payload.get("name")

        if not isinstance(name, str) or not name.strip():
            return create_error_response(
                400,
                "A valid name is required."
            )

        # Create an actual in-memory test resource.
        user = {
            "id": len(users) + 1,
            "name": name.strip()
        }

        users.append(user)

        return Response(
            status_code=201,
            headers={
                "Content-Type": "application/json; charset=utf-8"
            },
            body=json.dumps(user, ensure_ascii=False)
        )

    # Unknown path or unsupported route.
    return create_error_response(
        404,
        "The requested resource was not found."
    )


def handle_client(client_socket, client_address, users):
    """
    Parse one request, generate its response and send it.
    """

    with client_socket:
        logging.info(
            "Client connected: %s:%s",
            client_address[0],
            client_address[1]
        )

        try:
            # Phase 2: Parse the incoming request.
            request = parse_request(client_socket)

            logging.info(
                "Request received: %s %s %s",
                request.method,
                request.path,
                request.version
            )

            # Phase 3: Generate the appropriate response.
            response = handle_request(request, users)

        except HTTPParseError as error:
            logging.warning("Malformed HTTP request: %s", error)

            response = create_error_response(
                400,
                "Bad Request"
            )

        except Exception:
            logging.exception("Unexpected server-side error.")

            response = create_error_response(
                500,
                "Internal Server Error"
            )

        try:
            # Serialize the complete HTTP response.
            response_bytes = serialize_response(response)

            # Send all response bytes to the client.
            client_socket.sendall(response_bytes)

            logging.info(
                "Response sent: HTTP %s (%s bytes)",
                response.status_code,
                len(response_bytes)
            )

        except (OSError, ValueError, TypeError):
            logging.exception("Failed to generate or send HTTP response.")

        logging.info(
            "Client connection closed: %s:%s",
            client_address[0],
            client_address[1]
        )


def start_server():
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    users = []

    try:
        server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        server_socket.bind((HOST, PORT))
        server_socket.listen()

        print(f"Server listening on {HOST}:{PORT}")

        while True:
            print("Waiting for incoming connections...")

            client_socket, client_address = server_socket.accept()

            handle_client(
                client_socket,
                client_address,
                users
            )

    except KeyboardInterrupt:
        print("\nServer shutting down...")

    finally:
        server_socket.close()
        print("Server stopped.")


if __name__ == "__main__":
    start_server()