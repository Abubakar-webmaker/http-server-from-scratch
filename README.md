# Python HTTP Server

A basic HTTP server built from scratch using Python's built-in socket
and threading modules.

## Features

- TCP socket server
- HTTP request parsing
- HTTP response serialization
- Static and dynamic routing
- GET and POST routes
- 404 Not Found handling
- 405 Method Not Allowed handling
- 500 Internal Server Error handling
- Concurrent client handling using threading.Thread
- Maximum active client limit
- Socket timeouts
- Thread-safe request counter
- Graceful server shutdown

## Requirements

- Python 3.10 or later
- No third-party dependencies

## Run the server

From the project root:

    python server.py

Server address:

    http://127.0.0.1:8080

## Run automated tests

Run all tests:

    python -m unittest discover -s tests -v

Run HTTP tests:

    python -m unittest tests.test_http -v

Run server tests:

    python -m unittest tests.test_server -v

Run concurrency tests:

    python -m unittest tests.test_concurrency -v

## Test endpoints

GET /

GET /users

POST /users

GET /products

GET /users/1

GET /users/25/posts/10

## cURL examples

Home:

    curl -i http://127.0.0.1:8080/

Users:

    curl -i http://127.0.0.1:8080/users

Products:

    curl -i http://127.0.0.1:8080/products

Create user:

    curl -i -X POST http://127.0.0.1:8080/users ^
      -H "Content-Type: application/json" ^
      -d "{\"name\":\"Abdullah\"}"

Dynamic route:

    curl -i http://127.0.0.1:8080/users/1

Unknown route:

    curl -i http://127.0.0.1:8080/unknown

Unsupported method:

    curl -i -X DELETE http://127.0.0.1:8080/users

## Load testing

ApacheBench:

    ab -n 1000 -c 100 http://127.0.0.1:8080/

wrk:

    wrk -t4 -c100 -d30s http://127.0.0.1:8080/

Record:

- Total requests
- Requests per second
- Average response time
- Failed requests
- Timeout errors

Do not report performance results without actually executing
the load test.

## Concurrency design

The main server thread accepts incoming connections.

Each accepted client connection is passed to a dedicated
thread created using threading.Thread.

A BoundedSemaphore limits the number of active client connections.

A threading.Lock protects the shared request counter.

Client sockets are closed in a finally block.

The server stops accepting connections during shutdown and
waits for active client threads for a bounded period.

## Current limitations

- One HTTP request per connection.
- Connection: close is used.
- HTTP keep-alive is not implemented.
- Chunked transfer encoding is not supported.
- Request bodies are limited to 10 MB.
- This is a learning HTTP server, not a production-hardened
  replacement for established web servers.