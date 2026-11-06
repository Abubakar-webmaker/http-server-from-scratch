import unittest

from http.parser import parse_request, HTTPParseError
from http.response import Response, serialize_response


class HTTPParserTests(unittest.TestCase):

    def test_parse_get_request(self):
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"\r\n"
        )

        request = parse_request(raw)

        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/")
        self.assertEqual(request.headers["host"], "localhost")

    def test_parse_post_body(self):
        body = b'{"name":"Ali"}'

        raw = (
            b"POST /users HTTP/1.1\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"\r\n" + body
        )

        request = parse_request(raw)

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.body, body)

    def test_invalid_request_line(self):
        with self.assertRaises(HTTPParseError):
            parse_request(b"INVALID\r\n\r\n")

    def test_incomplete_headers(self):
        with self.assertRaises(HTTPParseError):
            parse_request(b"GET / HTTP/1.1\r\nHost: localhost")

    def test_incomplete_body(self):
        raw = (
            b"POST /users HTTP/1.1\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"abc"
        )

        with self.assertRaises(HTTPParseError):
            parse_request(raw)


class HTTPResponseTests(unittest.TestCase):

    def test_response_status(self):
        response = Response(200, "Hello")

        result = serialize_response(response)

        self.assertIn(b"HTTP/1.1 200 OK", result)

    def test_response_body(self):
        response = Response(201, '{"id":1}')

        result = serialize_response(response)

        self.assertTrue(result.endswith(b'{"id":1}'))

    def test_content_length(self):
        response = Response(200, "Hello")

        result = serialize_response(response)

        self.assertIn(b"Content-Length: 5", result)

    def test_connection_close(self):
        response = Response(200, "Hello")

        result = serialize_response(response)

        self.assertIn(b"Connection: close", result)

    def test_utf8_response(self):
        response = Response(200, "Hello World")

        result = serialize_response(response)

        self.assertTrue(result.endswith("Hello World".encode("utf-8")))


if __name__ == "__main__":
    unittest.main()