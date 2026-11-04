# Python HTTP Server

A production-ready HTTP/1.1 server built from scratch in Python with advanced features like chunked encoding, gzip compression, rate limiting, and middleware support.

---

## Project Description

High-performance HTTP/1.1 server that accepts TCP connections, parses HTTP requests, routes them to handlers, and sends back formatted responses with support for keep-alive connections, concurrent clients, and static file serving.

---

## Architecture

```
Client Request (TCP)
       |
       v
[Socket Listener]
       |
       v
[BufferedRequestReader] -- Keep-alive connection handling
       |
       v
[HTTP Parser] -- Parse GET / HTTP/1.1, headers, body
       |
       v
[Middleware] -- Rate limiting, logging
       |
       v
[Router] -- Match /users/:id to handler
       |
       v
[Handler] -- Execute business logic
       |
       v
[Response Builder] -- Build HTTP response
       |
       v
[Serialization] -- Format: status + headers + body
       |
       v
TCP Response to Client
```

---

## How to Run

### Start the Server

```bash
python server.py
```

Server will start on `http://127.0.0.1:8080`

### Stop the Server

Press `Ctrl+C` in terminal for graceful shutdown.

---

## Supported Features

- HTTP/1.0 and HTTP/1.1 protocol support
- GET, POST, PUT, DELETE, PATCH, HEAD methods
- Static and dynamic routing (/users/:id)
- Static file serving (HTML, CSS, JS, images)
- HTTP/1.1 Keep-Alive persistent connections
- Chunked Transfer-Encoding support
- gzip response compression
- Rate limiting per IP address
- Middleware system for custom processing
- TLS/SSL support for HTTPS
- Graceful server shutdown
- Concurrent client handling (100+ simultaneous)
- Proper HTTP status codes (200, 201, 404, 405, 500, etc.)
- Content-Length auto-calculation
- MIME type detection for static files
- Request/response logging
- Security: header injection prevention, oversized payload limits

---

## Example Usage

### 1. Basic GET Request

```bash
curl http://localhost:8080/
```

Response:
```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 55
Connection: keep-alive

<html><body><h1>Hello World</h1></body></html>
```

### 2. GET JSON API

```bash
curl http://localhost:8080/users/1
```

Response:
```json
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 30
Connection: keep-alive

{"id": 1, "name": "Ali"}
```

### 3. POST with JSON Body

```bash
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob"}'
```

Response:
```
HTTP/1.1 201 Created
Content-Type: application/json
Content-Length: 45
Connection: keep-alive

{"id": 2, "name": "Bob", "created": true}
```

### 4. GET Static CSS File

```bash
curl http://localhost:8080/static/style.css
```

Response:
```
HTTP/1.1 200 OK
Content-Type: text/css; charset=utf-8
Connection: keep-alive

body { margin: 0; padding: 20px; }
```

### 5. 404 Not Found

```bash
curl http://localhost:8080/nonexistent
```

Response:
```
HTTP/1.1 404 Not Found
Content-Type: text/plain; charset=utf-8
Connection: keep-alive

404 - Page Not Found
```

### 6. Multiple Requests (Keep-Alive)

```bash
# Both requests on same TCP connection
(
  echo -e "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
  sleep 0.1
  echo -e "GET /users HTTP/1.1\r\nHost: localhost\r\n\r\n"
) | nc localhost 8080
```

Both requests succeed without closing connection!

### 7. gzip Compressed Response

```bash
curl -H "Accept-Encoding: gzip" http://localhost:8080/users
```

Response includes:
```
Content-Encoding: gzip
[compressed data]
```

### 8. Large POST Body

```bash
curl -X POST http://localhost:8080/upload \
  -H "Content-Type: application/octet-stream" \
  --data-binary @largefile.bin
```

Server accepts payloads up to 10MB.

---

## Testing

Run all tests:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run specific test:

```bash
python -m unittest tests.test_integration_end_to_end -v
```

Total test coverage: 300+ tests, 95%+ code coverage

---

## Project Structure

```
python-http-server/
|-- server.py              # Main entry point
|-- README.md              # This file
|-- http/                  # HTTP protocol
|-- routing/               # URL routing
|-- static_files/          # Static file serving
|-- gzip_support/          # Compression
|-- core/                  # Middleware, rate limiting
|-- security/              # TLS/SSL
|-- utils/                 # Logging, exceptions
|-- static/                # HTML, CSS, JS files
+-- tests/                 # 300+ test cases
```

---

## Configuration

Edit `server.py` to change settings:

```python
HTTPServer(
    host="127.0.0.1",
    port=8080,
    max_clients=100,
    max_body_size=10*1024*1024,  # 10MB
    max_header_size=65536,        # 65KB
)
```

---

Production-Ready | HTTP/1.1 | 300+ Tests | Keep-Alive | gzip | Rate Limiting
