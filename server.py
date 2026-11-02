import socket

from http.parser import parse_request, HTTPParseError


HOST = "127.0.0.1"
PORT = 8080


def start_server():
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

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

            with client_socket:
                print("\n" + "=" * 60)
                print(f"Client connected: {client_address[0]}:{client_address[1]}")

                try:
                    request = parse_request(client_socket)

                    print("\nParsed HTTP Request:")
                    print(f"Method:  {request.method}")
                    print(f"Path:    {request.path}")
                    print(f"Version: {request.version}")

                    print("\nHeaders:")
                    for name, value in request.headers.items():
                        print(f"{name}: {value}")

                    print(f"\nBody length: {len(request.body)} bytes")
                    print(f"Body: {request.body!r}")

                except HTTPParseError as error:
                    print(f"\nHTTP Request Parsing Error: {error}")

                except OSError as error:
                    print(f"\nSocket Error: {error}")

                print("\nClient connection closed.")
                print("=" * 60)

    except KeyboardInterrupt:
        print("\nServer shutting down...")

    finally:
        server_socket.close()
        print("Server stopped.")


if __name__ == "__main__":
    start_server()