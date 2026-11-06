
import unittest

from http.request import Request
from http.response import Response
from routing.router import Router


def make_request(method, path):
    return Request(
        method=method,
        path=path,
        version="HTTP/1.1",
        headers={},
        body=b"",
    )


def make_response(body="OK", status=200):
    return Response(
        status_code=status,
        headers={
            "Content-Type": "text/plain; charset=utf-8"
        },
        body=body.encode("utf-8"),
    )


def response_body(response):
    body = response.body

    if isinstance(body, bytes):
        return body.decode("utf-8")

    return body


class TestRouteRegistration(unittest.TestCase):

    def setUp(self):
        self.router = Router()

    def test_get_route_registration(self):
        def handler(request):
            return make_response()

        self.router.get("/users", handler)

        self.assertIn(
            ("GET", "/users"),
            self.router.routes
        )

    def test_post_route_registration(self):
        def handler(request):
            return make_response()

        self.router.post("/users", handler)

        self.assertIn(
            ("POST", "/users"),
            self.router.routes
        )

    def test_get_and_post_same_path(self):
        def get_handler(request):
            return make_response("GET")

        def post_handler(request):
            return make_response("POST")

        self.router.get("/users", get_handler)
        self.router.post("/users", post_handler)

        self.assertIs(
            self.router.routes[("GET", "/users")],
            get_handler
        )

        self.assertIs(
            self.router.routes[("POST", "/users")],
            post_handler
        )

    def test_duplicate_route_rejected(self):
        def handler(request):
            return make_response()

        self.router.get("/users", handler)

        with self.assertRaises(ValueError):
            self.router.get("/users", handler)

    def test_invalid_handler_rejected(self):
        with self.assertRaises(TypeError):
            self.router.get("/users", "not-a-function")

    def test_invalid_route_pattern_rejected(self):
        def handler(request):
            return make_response()

        with self.assertRaises(ValueError):
            self.router.get("users", handler)

        with self.assertRaises(ValueError):
            self.router.get("/users/:", handler)

        with self.assertRaises(ValueError):
            self.router.get("/users/:id/:id", handler)


class TestStaticRouting(unittest.TestCase):

    def setUp(self):
        self.router = Router()

    def test_root_route(self):
        self.router.get(
            "/",
            lambda request: make_response("HOME")
        )

        response = self.router.dispatch(
            make_request("GET", "/")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_body(response), "HOME")

    def test_users_route(self):
        self.router.get(
            "/users",
            lambda request: make_response("USERS")
        )

        response = self.router.dispatch(
            make_request("GET", "/users")
        )

        self.assertEqual(response_body(response), "USERS")

    def test_path_is_case_sensitive(self):
        self.router.get(
            "/users",
            lambda request: make_response("USERS")
        )

        response = self.router.dispatch(
            make_request("GET", "/Users")
        )

        self.assertEqual(response.status_code, 404)

    def test_trailing_slash_policy(self):
        self.router.get(
            "/users",
            lambda request: make_response("USERS")
        )

        response = self.router.dispatch(
            make_request("GET", "/users/")
        )

        self.assertEqual(response.status_code, 200)


class TestDynamicRouting(unittest.TestCase):

    def setUp(self):
        self.router = Router()

    def test_single_parameter(self):
        def handler(request, id):
            return make_response(f"User ID: {id}")

        self.router.get("/users/:id", handler)

        response = self.router.dispatch(
            make_request("GET", "/users/25")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response_body(response),
            "User ID: 25"
        )

    def test_multiple_parameters(self):
        def handler(request, id, post_id):
            return make_response(
                f"User: {id}, Post: {post_id}"
            )

        self.router.get(
            "/users/:id/posts/:post_id",
            handler
        )

        response = self.router.dispatch(
            make_request(
                "GET",
                "/users/25/posts/10"
            )
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response_body(response),
            "User: 25, Post: 10"
        )

    def test_parameter_matches_one_segment_only(self):
        self.router.get(
            "/users/:id",
            lambda request, id: make_response(id)
        )

        response = self.router.dispatch(
            make_request("GET", "/users/25/profile")
        )

        self.assertEqual(response.status_code, 404)

    def test_empty_parameter_does_not_match(self):
        self.router.get(
            "/users/:id",
            lambda request, id: make_response(id)
        )

        response = self.router.dispatch(
            make_request("GET", "/users/")
        )

        # Trailing slash is normalized to /users.
        # It must not match /users/:id.
        self.assertEqual(response.status_code, 404)

    def test_unrelated_dynamic_route_does_not_match(self):
        self.router.get(
            "/products/:id",
            lambda request, id: make_response(id)
        )

        response = self.router.dispatch(
            make_request("GET", "/users/25")
        )

        self.assertEqual(response.status_code, 404)

    def test_static_route_has_priority(self):
        self.router.get(
            "/users/:id",
            lambda request, id: make_response("DYNAMIC")
        )

        self.router.get(
            "/users/profile",
            lambda request: make_response("STATIC")
        )

        response = self.router.dispatch(
            make_request("GET", "/users/profile")
        )

        self.assertEqual(response_body(response), "STATIC")

    def test_ambiguous_dynamic_route_rejected(self):
        self.router.get(
            "/users/:id",
            lambda request, id: make_response()
        )

        with self.assertRaises(ValueError):
            self.router.get(
                "/users/:name",
                lambda request, name: make_response()
            )


class TestHTTPMethods(unittest.TestCase):

    def setUp(self):
        self.router = Router()

    def test_get_method(self):
        self.router.get(
            "/users",
            lambda request: make_response("GET")
        )

        response = self.router.dispatch(
            make_request("GET", "/users")
        )

        self.assertEqual(response_body(response), "GET")

    def test_post_method(self):
        self.router.post(
            "/users",
            lambda request: make_response("POST")
        )

        response = self.router.dispatch(
            make_request("POST", "/users")
        )

        self.assertEqual(response_body(response), "POST")

    def test_unsupported_method_returns_405(self):
        self.router.get(
            "/users",
            lambda request: make_response()
        )

        response = self.router.dispatch(
            make_request("DELETE", "/users")
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "GET")

    def test_unknown_route_returns_404(self):
        response = self.router.dispatch(
            make_request("GET", "/unknown")
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response_body(response),
            "404 - Route Not Found"
        )


class TestHandlerErrors(unittest.TestCase):

    def setUp(self):
        self.router = Router()

    def test_handler_exception_returns_500(self):
        def handler(request):
            raise RuntimeError("Sensitive internal information")

        self.router.get("/error", handler)

        response = self.router.dispatch(
            make_request("GET", "/error")
        )

        self.assertEqual(response.status_code, 500)

        self.assertNotIn(
            "Sensitive internal information",
            response_body(response)
        )

    def test_invalid_handler_response_returns_500(self):
        def handler(request):
            return {"message": "Not a Response"}

        self.router.get("/invalid", handler)

        response = self.router.dispatch(
            make_request("GET", "/invalid")
        )

        self.assertEqual(response.status_code, 500)

    def test_query_string_is_not_part_of_route(self):
        self.router.get(
            "/users",
            lambda request: make_response("USERS")
        )

        response = self.router.dispatch(
            make_request("GET", "/users?page=1")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_body(response), "USERS")


if __name__ == "__main__":
    unittest.main()
