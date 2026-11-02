
import socket


HOST = "127.0.0.1"
PORT = 8080
BUFFER_SIZE = 1024


def start_server():
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen()

        print(f"Server listening on {HOST}:{PORT}")
        print("Waiting for incoming connections...\n")

        while True:
            conn, client_address = server_socket.accept()

            try:
                client_ip, client_port = client_address

                print("=" * 60)
                print(f"Client connected: {client_ip}:{client_port}")

                raw_data = conn.recv(BUFFER_SIZE)

                print("\nRaw HTTP Request (bytes):")
                print(raw_data)

                decoded_data = raw_data.decode(
                    "utf-8",
                    errors="replace"
                )

                print("\nDecoded HTTP Request:")
                print(decoded_data)

                print("=" * 60)
                print()

            except ConnectionResetError:
                print("Client connection was reset.")

            except OSError as error:
                print(f"Client connection error: {error}")

            finally:
                conn.close()
                print("Client connection closed.\n")

    except KeyboardInterrupt:
        print("\nServer shutdown requested.")

    except OSError as error:
        print(f"Server error: {error}")

    finally:
        server_socket.close()
        print("Server socket closed.")


if __name__ == "__main__":
    start_server()
