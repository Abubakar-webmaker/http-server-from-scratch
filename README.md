# Python HTTP Server

A basic HTTP server built using Python's standard socket library.

## Project Phases

- Phase 1: TCP Server
- Phase 2: HTTP Request Parsing
- Phase 3: HTTP Response Generation

## Phase 3 Features

- HTTP status line generation
- HTTP response headers
- HTML, JSON and plain text responses
- UTF-8 response body encoding
- Byte-accurate Content-Length
- Connection: close
- Complete response serialization
- Socket integration using sendall()
- Basic HTTP error handling

## Supported Status Codes

| Code | Reason |
|------|--------|
| 200 | OK |
| 201 | Created |
| 400 | Bad Request |
| 404 | Not Found |
| 500 | Internal Server Error |

## Supported Content Types

- text/html; charset=utf-8
- application/json; charset=utf-8
- text/plain; charset=utf-8

## Run the Server

```bash
python server.py