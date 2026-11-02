
# Python Raw TCP Server

A basic TCP server implemented using Python's built-in socket module.

## Requirements

- Python 3
- No third-party dependencies

## Project Structure

python-http-server/
├── server.py
└── README.md

## Start the Server

Open a terminal inside the project directory:

```bash
python3 server.py
```

Expected output:

Server listening on 127.0.0.1:8080

## Test Using cURL

Open another terminal:

```bash
curl -v http://127.0.0.1:8080/
```

The server will display the raw HTTP request bytes and decoded request.

## Test Using Browser

Open:

http://127.0.0.1:8080/

The server should accept the browser connection and display its HTTP request.

Note: This phase does not generate HTTP responses. The browser may report that the connection was closed without a response.

## Stop the Server

Press:

Ctrl + C

The server will close its socket gracefully.

# Python HTTP Server - Phase 2

A basic HTTP request parser built using Python's standard library
and TCP sockets.

## Features

- HTTP request line parsing
- HTTP method, path and version extraction
- Case-insensitive HTTP headers
- Content-Length validation
- Exact request body reading
- Support for request bodies larger than 1024 bytes
- Rejection of unsupported chunked transfer encoding
- Structured Request dataclass
- Unit tests using unittest

## Requirements

- Python 3.10 or newer
- No third-party dependencies

## Run the server

```bash
python server.py