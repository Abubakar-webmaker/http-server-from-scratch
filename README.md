# Phase 6: Static File Serving

The HTTP server supports serving static files from a configured directory.

## Supported features

- HTML, CSS and JavaScript
- PNG, JPEG and SVG images
- PDF and binary files
- Automatic MIME type detection
- Binary file reading
- ETag generation using SHA-256
- Last-Modified headers
- If-None-Match
- If-Modified-Since
- GET and HEAD methods
- Directory traversal protection
- Symbolic-link containment checks
- Concurrent file requests

## Static directory

All public files must be placed inside:

    static/

The static URL prefix is:

    /static/

Example:

    static/index.html
    static/style.css
    static/script.js
    static/images/logo.svg

## Run the server

    python server.py

## Test static files

    curl -i http://127.0.0.1:8080/static/index.html

    curl -i http://127.0.0.1:8080/static/style.css

    curl -i http://127.0.0.1:8080/static/script.js

    curl -I http://127.0.0.1:8080/static/index.html

## Test ETag caching

First request:

    curl -i http://127.0.0.1:8080/static/index.html

Copy the ETag value.

Second request:

    curl -i -H "If-None-Match: YOUR_ETAG" http://127.0.0.1:8080/static/index.html

Expected result:

    HTTP/1.1 304 Not Modified

## Test Last-Modified caching

Copy the Last-Modified value from the first response.

    curl -i -H "If-Modified-Since: YOUR_DATE" http://127.0.0.1:8080/static/index.html

Expected result:

    HTTP/1.1 304 Not Modified

## Run tests

Run all project tests:

    python -m unittest discover -s tests -v

Run only Phase 6 tests:

    python -m unittest tests.test_static_files -v