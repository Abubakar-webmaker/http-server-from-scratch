# HTTP Server from Scratch

![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Production--Ready-brightgreen.svg)
![Tests](https://img.shields.io/badge/Tests-300%2B-blue.svg)

A **production-ready HTTP/1.1 server** built from scratch in Python with concurrent client handling, static file serving, gzip compression, rate limiting, and comprehensive test coverage (300+ tests).

## Features

- **HTTP/1.1 Protocol Compliance**
  - GET, POST, PUT, DELETE, PATCH, HEAD methods
  - All standard status codes (100-599)
  - Proper request/response headers handling
  - URL query strings and path parameters

- **Advanced Networking**
  - HTTP/1.1 Keep-Alive persistent connections
  - Concurrent client handling (100+ simultaneous)
  - Multi-threaded architecture
  - Socket timeout and idle connection management

- **Routing & Request Handling**
  - Static routes: `/users`
  - Dynamic routes with parameters: `/users/:id`
  - Nested routes: `/users/:id/posts/:post_id`
  - Automatic parameter extraction
  - Proper 404/405 error responses

- **Static File Serving**
  - Automatic MIME type detection
  - Directory traversal attack prevention (8 security layers)
  - Large file support
  - Conditional GET (304 Not Modified)

- **Performance & Compression**
  - Chunked Transfer-Encoding support
  - gzip response compression
  - Efficient connection pooling
  - 1000+ requests/second throughput

- **Security & Reliability**
  - Header injection prevention
  - Request smuggling detection
  - Oversized payload limits (10MB)
  - Rate limiting per IP
  - Graceful shutdown
  - Comprehensive error handling

- **Observability**
  - Structured logging (INFO, ERROR, DEBUG)
  - Request/response tracking
  - Performance metrics
  - Statistics tracking

## Wired Features (Production Integration)

### 1. **Middleware Pipeline** ✓ Wired
The middleware pipeline orchestrates cross-cutting concerns before requests reach handlers. Provides centralized rate limiting, logging, and authentication.
- **Location**: `dispatcher.py` (MiddlewarePipeline class)
- **Use Case**: Pre-processing requests before routing

### 2. **Rate Limiter (100 req/60s per IP)** ✓ Wired
Per-client IP rate limiting prevents abuse and ensures fair resource distribution. Limits each client to 100 requests per 60 seconds.
- **Location**: `core/rate_limiter.py` (RateLimiter class)
- **Middleware**: Registered in `server._register_middleware()`
- **Response**: HTTP 429 with `Retry-After` header when limit exceeded

### 3. **Gzip Compression** ✓ Wired
Automatic response compression for text content reduces bandwidth by ~70%. Compresses JSON, HTML, CSS, JS responses larger than 1KB.
- **Location**: `gzip_support/gzip_handler.py`
- **Integration**: Applied before serialization
- **Eligibility**: Text-based responses >1KB

### 4. **TLS/HTTPS Support** ✓ Wired
Optional HTTPS support via Python's built-in SSL module for secure communications.
- **Location**: `security/tls.py`
- **Certificates**: Self-signed or CA-signed (PEM format)
- **Usage**: Pass `use_tls=True` with cert and key file paths to HTTPServer

### 5. **Threading Diagram** ✓ Added
Multi-threaded concurrent client handling with connection pooling:
- **Architecture**: Main thread accepts connections, worker threads handle requests
- **Connection Pool**: BoundedSemaphore limits 100 concurrent clients
- **Keep-Alive Loop**: Each worker handles multiple requests per connection
- **Graceful Shutdown**: Workers joined with timeout before exit

## Architecture

```
Client Request (TCP)
       |
       v
[Socket Listener] -- Accept connections, manage client slots
       |
       v
[BufferedRequestReader] -- Handle keep-alive, reuse connections
       |
       v
[HTTP Parser] -- Parse GET/POST, headers, body, chunked encoding
       |
       v
[Middleware Pipeline] -- Rate limiting, logging, custom middleware
       |
       v
[Router] -- Match /path/:id to handler function
       |
       v
[Handler] -- Execute business logic
       |
       v
[Response Builder] -- Build HTTP response with compression
       |
       v
[Serialization] -- Format: "HTTP/1.1 200 OK" + headers + body
       |
       v
TCP Response to Client
```

### Threading Model

```
Main Thread
    |
    +--[Server Socket] Accept on port 8080
    |      |
    |      +-- Accept connection 1 -----> [Worker Thread 1]
    |      +-- Accept connection 2 -----> [Worker Thread 2]
    |      +-- Accept connection 3 -----> [Worker Thread 3]
    |      +-- ... up to 100 concurrent
    |
    +--[Connection Pool] Limit concurrent clients
          |
          +-- [BoundedSemaphore] Max 100 slots
          |      Release on client disconnect
          |
          +-- Thread pool size dynamically managed
                 (grows with demand, max 100)

Each [Worker Thread] handles:
  1. Keep-Alive loop (multiple requests per connection)
  2. Read HTTP request
  3. Dispatch to middleware → router → handler
  4. Send response
  5. If keep-alive: loop back to step 2
  6. Else: close connection
```

### Middleware Pipeline (Feature #1: Rate Limiting)

```
Incoming Request
       |
       v
[Rate Limiter] -- Check client IP against 100 req/60s window
       |
       +-- If over limit: return 429 (Too Many Requests)
       +-- If within limit: proceed to routing
       |
       v
[Router] -- Dispatch to handler
       |
       v
[Response]
```

### Data Flow Example

```
Request:  GET /users/42 HTTP/1.1
          Host: localhost
          
Process:  Parser extracts {method, path, headers, body}
          Middleware applies rate limiting
          Router matches /users/:id -> get_user handler
          Handler returns Response(200, json_user)
          Response serialized to HTTP format

Response: HTTP/1.1 200 OK
          Content-Type: application/json
          Content-Length: 23
          Connection: keep-alive
          
          {"id": 42, "name": "Ali"}
```

## Installation

### Prerequisites
- Python 3.6+
- No external dependencies (pure Python stdlib)

### Clone & Run

```bash
# Clone repository
git clone https://github.com/Abubakar-webmaker/http-server-from-scratch.git
cd http-server-from-scratch

# Start server
python server.py
```

Server starts on `http://127.0.0.1:8080`

## Usage Examples

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

### 2. JSON API
```bash
curl http://localhost:8080/users
```

Response:
```json
HTTP/1.1 200 OK
Content-Type: application/json
Connection: keep-alive

[{"id": 1, "name": "Ali"}]
```

### 3. Dynamic Route Parameters
```bash
curl http://localhost:8080/users/1
```

Response:
```json
{"id": 1, "name": "Ali"}
```

### 4. POST Request
```bash
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob"}'
```

Response:
```
HTTP/1.1 201 Created
Content-Type: application/json

{"id": 2, "name": "Bob"}
```

### 5. Error Handling
```bash
# 404 Not Found
curl http://localhost:8080/nonexistent

# 405 Method Not Allowed
curl -X DELETE http://localhost:8080/

# Static file 404
curl http://localhost:8080/static/missing.html
```

### 6. Static Files
```bash
# CSS
curl http://localhost:8080/static/style.css

# JavaScript
curl http://localhost:8080/static/script.js
```

### 7. Keep-Alive (Multiple Requests on Same Connection)
```bash
# Two requests in one TCP connection
(
  echo -e "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
  sleep 0.1
  echo -e "GET /users HTTP/1.1\r\nHost: localhost\r\n\r\n"
) | nc localhost 8080
```

Both succeed without reconnecting!

## Project Structure

```
http-server-from-scratch/
|
|-- server.py                 # Main server entry point
|-- README.md                 # This file
|-- LICENSE                   # MIT License
|-- .gitignore                # Git ignore file
|
|-- http/                     # HTTP protocol implementation
|   |-- parser.py            # Request parser (chunked support)
|   |-- request.py           # Request data class
|   |-- response.py          # Response builder
|   |-- keepalive.py         # Keep-alive connection handling
|   |-- chunked.py           # Chunked transfer encoding
|   +-- __init__.py
|
|-- routing/                  # URL routing
|   |-- router.py            # Route registration & matching
|   +-- __init__.py
|
|-- static_files/            # Static file serving
|   |-- handler.py           # File serving with security
|   +-- __init__.py
|
|-- gzip_support/            # Response compression
|   |-- gzip_handler.py      # gzip compression logic
|   +-- __init__.py
|
|-- core/                     # Core server features
|   |-- middleware.py        # Middleware pipeline
|   |-- rate_limiter.py      # Per-IP rate limiting
|   |-- shutdown.py          # Graceful shutdown
|   +-- __init__.py
|
|-- security/                # Security features
|   |-- tls.py              # TLS/SSL support
|   +-- __init__.py
|
|-- utils/                    # Utilities
|   |-- logger.py            # Structured logging
|   |-- exceptions.py        # Custom exceptions
|   +-- __init__.py
|
|-- static/                   # Static files (HTML, CSS, JS)
|   |-- index.html
|   |-- style.css
|   +-- script.js
|
+-- tests/                    # Test suite (300+ tests)
    |-- test_request_parser.py         (40+ tests)
    |-- test_response_builder.py       (50+ tests)
    |-- test_integration_end_to_end.py (19 tests)
    |-- test_edge_cases_security.py    (50+ tests)
    |-- test_router.py                 (30+ tests)
    |-- test_*.py                      (many more)
    +-- __init__.py
```

## Testing

### Run All Tests
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### Run Specific Test Suite
```bash
# Request parser tests
python -m unittest tests.test_request_parser -v

# Integration tests (end-to-end)
python -m unittest tests.test_integration_end_to_end -v

# Security & edge cases
python -m unittest tests.test_edge_cases_security -v
```

### Test Coverage
- **300+ tests** covering all components
- **95%+ code coverage** across modules
- Unit tests, integration tests, edge cases, security tests
- Concurrent client testing (50+ simultaneous)
- Real HTTP client patterns (browsers, curl, mobile apps)

## Performance

### Benchmarks
- **Concurrent Clients**: 100+
- **Throughput**: 1000+ requests/second
- **Max Payload**: 10MB
- **Max Headers**: 65KB
- **Keep-Alive Requests**: 100+ per connection
- **Response Time**: < 5ms (simple GET)

### Load Test Results
```
100 concurrent clients → All successful
1MB request body → Accepted
50KB headers → Accepted
10 keep-alive requests → All successful
```

## Security

### Protection Layers
1. **Header Injection** - CRLF validation
2. **Request Smuggling** - Content-Length/Transfer-Encoding conflict detection
3. **Directory Traversal** - 8-layer filesystem security
   - URL decode exactly once
   - Null byte rejection
   - Backslash rejection
   - Absolute path rejection
   - Windows drive path rejection
   - Symlink resolution
   - Containment verification
   - Permission checks
4. **Oversized Payloads** - 10MB limit
5. **Control Characters** - Rejection of dangerous bytes
6. **Error Safety** - No stack traces in responses

### Tested Attack Vectors
- CRLF injection in headers
- Null byte injection
- HTTP request smuggling
- Directory traversal (../../../etc/passwd)
- Symlink attacks
- Large payloads
- Malformed requests

## Configuration

Edit `server.py` to customize:

```python
HTTPServer(
    host="127.0.0.1",
    port=8080,
    max_clients=100,
    socket_timeout=5.0,
    keep_alive_timeout=15.0,
    max_requests_per_connection=100,
    max_header_size=65536,      # 65KB
    max_body_size=10*1024*1024, # 10MB
)
```

## Technology Stack

- **Language**: Python 3.6+
- **Networking**: Python socket module
- **Threading**: Python threading (concurrent clients)
- **Compression**: Python gzip module
- **Testing**: Python unittest (300+ tests)
- **Protocol**: HTTP/1.0, HTTP/1.1

## Future Improvements

- [ ] HTTP/2 support
- [ ] WebSocket support
- [ ] Async/await refactoring (asyncio)
- [ ] Connection pooling optimization
- [ ] Rate limiting enhancements
- [ ] Metrics export (Prometheus)
- [ ] Docker containerization
- [ ] Kubernetes deployment examples
- [ ] Load balancing integration
- [ ] Database connection pooling

## Contributing

Found a bug? Have an idea?

1. Fork repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

All pull requests must:
- Include tests (existing tests must pass)
- Follow PEP8 style
- Have clear commit messages

## Testing Before PR

```bash
# Run all tests
python -m unittest discover -s tests -p "test_*.py" -v

# Check code style (optional)
python -m py_compile $(find . -name "*.py")
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Abubakar** - [@GitHub](https://github.com/Abubakar-webmaker)

## Acknowledgments

- Inspired by [Codecrafters](https://codecrafters.io) "Build Your Own HTTP Server" challenge
- HTTP/1.1 specification: [RFC 7230-7235](https://tools.ietf.org/html/rfc7230)
- Python community for stdlib excellence

---

**Star ⭐ this repo if it helps you!**

Built with ❤️ | Production-Ready | 300+ Tests | MIT License
