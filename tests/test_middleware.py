"""Tests for middleware system."""

import unittest
from http.request import Request
from http.response import Response
from core.middleware import MiddlewarePipeline
from utils.exceptions import MiddlewareError


class TestMiddlewarePipeline(unittest.TestCase):
    """Test middleware pipeline functionality."""

    def setUp(self):
        """Create a fresh pipeline for each test."""
        self.pipeline = MiddlewarePipeline()

    def test_empty_pipeline(self):
        """Pipeline with no middleware just calls the handler."""
        def handler(request):
            return Response(200, "OK")

        request = Request("GET", "/", "HTTP/1.1")
        response = self.pipeline.execute(request, handler)

        self.assertEqual(response.status_code, 200)

    def test_single_middleware(self):
        """Single middleware can execute."""
        def middleware(request, next_handler):
            return next_handler(request)

        def handler(request):
            return Response(200, "OK")

        self.pipeline.register(middleware)
        request = Request("GET", "/", "HTTP/1.1")
        response = self.pipeline.execute(request, handler)

        self.assertEqual(response.status_code, 200)

    def test_multiple_middleware(self):
        """Multiple middleware execute in registration order."""
        call_order = []

        def mw1(request, next_handler):
            call_order.append(1)
            return next_handler(request)

        def mw2(request, next_handler):
            call_order.append(2)
            return next_handler(request)

        def handler(request):
            call_order.append(3)
            return Response(200, "OK")

        self.pipeline.register(mw1)
        self.pipeline.register(mw2)
        request = Request("GET", "/", "HTTP/1.1")
        self.pipeline.execute(request, handler)

        self.assertEqual(call_order, [1, 2, 3])

    def test_middleware_can_modify_request(self):
        """Middleware can inspect and modify requests."""
        def modify_middleware(request, next_handler):
            request.headers["X-Modified"] = "true"
            return next_handler(request)

        def handler(request):
            modified = request.headers.get("X-Modified") == "true"
            return Response(200, "Modified" if modified else "Not Modified")

        self.pipeline.register(modify_middleware)
        request = Request("GET", "/", "HTTP/1.1")
        response = self.pipeline.execute(request, handler)

        self.assertIn(b"Modified", response.body)

    def test_middleware_can_short_circuit(self):
        """Middleware can skip remaining handlers."""
        def short_circuit_middleware(request, next_handler):
            return Response(403, "Forbidden")

        def handler(request):
            return Response(200, "OK")

        self.pipeline.register(short_circuit_middleware)
        request = Request("GET", "/", "HTTP/1.1")
        response = self.pipeline.execute(request, handler)

        self.assertEqual(response.status_code, 403)

    def test_middleware_can_modify_response(self):
        """Middleware can inspect and modify responses."""
        def response_middleware(request, next_handler):
            response = next_handler(request)
            response.headers["X-Added"] = "by-middleware"
            return response

        def handler(request):
            return Response(200, "OK")

        self.pipeline.register(response_middleware)
        request = Request("GET", "/", "HTTP/1.1")
        response = self.pipeline.execute(request, handler)

        self.assertEqual(response.headers.get("X-Added"), "by-middleware")

    def test_middleware_exception_propagates(self):
        """Exceptions in middleware propagate."""
        def failing_middleware(request, next_handler):
            raise ValueError("Middleware error")

        self.pipeline.register(failing_middleware)
        request = Request("GET", "/", "HTTP/1.1")

        with self.assertRaises(ValueError):
            self.pipeline.execute(request, lambda r: Response(200, "OK"))

    def test_invalid_middleware_rejected(self):
        """Non-callable middleware is rejected."""
        with self.assertRaises(TypeError):
            self.pipeline.register("not-a-function")

    def test_middleware_count(self):
        """Count of registered middleware is accurate."""
        def mw(request, next_handler):
            return next_handler(request)

        self.assertEqual(self.pipeline.middleware_count, 0)
        self.pipeline.register(mw)
        self.assertEqual(self.pipeline.middleware_count, 1)
        self.pipeline.register(mw)
        self.assertEqual(self.pipeline.middleware_count, 2)

    def test_build_handler_creates_wrapped_handler(self):
        """build_handler returns a callable."""
        def handler(request):
            return Response(200, "OK")

        wrapped = self.pipeline.build_handler(handler)
        self.assertTrue(callable(wrapped))


if __name__ == "__main__":
    unittest.main()
