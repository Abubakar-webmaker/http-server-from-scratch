# Python HTTP Server

A custom HTTP server built using Python's standard library.

The project implements TCP communication, HTTP request parsing,
HTTP response generation, and a modular routing system.

No Flask, Django, FastAPI, Werkzeug, or third-party routing
framework is used.

## Project Phases

- Phase 1: TCP Server
- Phase 2: HTTP Request Parsing
- Phase 3: HTTP Response Generation
- Phase 4: HTTP Routing System

## Project Structure

```text
python-http-server/
├── server.py
├── http/
│   ├── __init__.py
│   ├── request.py
│   ├── parser.py
│   └── response.py
├── routing/
│   ├── __init__.py
│   └── router.py
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_response.py
│   └── test_router.py
└── README.md