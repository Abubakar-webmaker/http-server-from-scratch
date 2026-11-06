import unittest

from http.response import Response, serialize_response


class TestHTTPResponse(unittest.TestCase):

    def test_200_ok(self):
        response = Response(
            status_code=200,
            body="Hello World"
        )

        result = serialize_response(response)

        self.assertTrue(
            result.startswith(b"HTTP/1.1 200 OK\r\n")
        )

    def test_201_created(self):
        response = Response(
            status_code=201,
            body='{"message":"User created"}',
            headers={
                "Content-Type": "application/json; charset=utf-8"
            }
        )

        result = serialize_response(response)

        self.assertTrue(
            result.startswith(b"HTTP/1.1 201 Created\r\n")
        )

    def test_400_bad_request(self):
        response = Response(400, body="Bad Request")

        result = serialize_response(response)

        self.assertTrue(
            result.startswith(b"HTTP/1.1 400 Bad Request\r\n")
        )

    def test_404_not_found(self):
        response = Response(404, body="Not Found")

        result = serialize_response(response)

        self.assertTrue(
            result.startswith(b"HTTP/1.1 404 Not Found\r\n")
        )

    def test_500_internal_server_error(self):
        response = Response(500, body="Internal Server Error")

        result = serialize_response(response)

        self.assertTrue(
            result.startswith(
                b"HTTP/1.1 500 Internal Server Error\r\n"
            )
        )

    def test_html_content_type(self):
        response = Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            body="<h1>Hello</h1>"
        )

        result = serialize_response(response)

        self.assertIn(
            b"Content-Type: text/html; charset=utf-8\r\n",
            result
        )

    def test_json_content_type(self):
        response = Response(
            200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body='{"status":"success"}'
        )

        result = serialize_response(response)

        self.assertIn(
            b"Content-Type: application/json; charset=utf-8\r\n",
            result
        )

    def test_plain_text_content_type(self):
        response = Response(200, body="Welcome")

        result = serialize_response(response)

        self.assertIn(
            b"Content-Type: text/plain; charset=utf-8\r\n",
            result
        )

    def test_content_length_uses_bytes(self):
        body = "Hello World"

        response = Response(200, body=body)
        result = serialize_response(response)

        expected_length = len(body.encode("utf-8"))

        self.assertIn(
            f"Content-Length: {expected_length}\r\n".encode("ascii"),
            result
        )

    def test_utf8_content_length(self):
        body = "Hello World — پاکستان"

        response = Response(200, body=body)
        result = serialize_response(response)

        expected_body = body.encode("utf-8")

        self.assertIn(
            f"Content-Length: {len(expected_body)}\r\n".encode("ascii"),
            result
        )

        self.assertTrue(result.endswith(expected_body))

    def test_bytes_body_is_preserved(self):
        body = b"\x00\x01\x02\xff"

        response = Response(200, body=body)
        result = serialize_response(response)

        self.assertTrue(result.endswith(body))

    def test_connection_close_header(self):
        response = Response(200, body="Hello")

        result = serialize_response(response)

        self.assertIn(b"Connection: close\r\n", result)

    def test_header_body_separator(self):
        response = Response(200, body="Hello")

        result = serialize_response(response)

        self.assertIn(b"\r\n\r\n", result)

    def test_serialized_response_is_bytes(self):
        response = Response(200, body="Hello")

        result = serialize_response(response)

        self.assertIsInstance(result, bytes)

    def test_unsupported_status_code(self):
        response = Response(302, body="Redirect")

        with self.assertRaises(ValueError):
            serialize_response(response)

    def test_unsafe_header_value(self):
        response = Response(
            200,
            headers={"X-Test": "safe\r\nInjected: bad"},
            body="Hello"
        )

        with self.assertRaises(ValueError):
            serialize_response(response)


if __name__ == "__main__":
    unittest.main()