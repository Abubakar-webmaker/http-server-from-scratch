"""Middleware pipeline system."""

from typing import Callable, List

from http.request import Request
from http.response import Response
from utils.logger import get_logger

logger = get_logger(__name__)


# Middleware function signature
# def middleware(request: Request, next_handler: Callable) -> Response: ...
MiddlewareFunc = Callable[[Request, Callable], Response]


class MiddlewarePipeline:
    """Manages a chain of middleware functions.

    Middleware executes in the order it was registered. Each middleware
    receives the request and a next_handler callable that represents the
    remainder of the pipeline (or the final route handler).
    """

    def __init__(self) -> None:
        self._middleware_stack: List[MiddlewareFunc] = []
        self.client_address = None  # Can be set before execute()

    def register(self, middleware: MiddlewareFunc) -> None:
        """Register a middleware function.

        Args:
            middleware: A callable(request, next_handler) -> Response.
        """
        if not callable(middleware):
            raise TypeError("Middleware must be callable")
        self._middleware_stack.append(middleware)

    def build_handler(
        self,
        final_handler: Callable[[Request], Response],
    ) -> Callable[[Request], Response]:
        """Build a wrapped handler with all middleware applied.

        Args:
            final_handler: The final route/response handler.

        Returns:
            A wrapped handler that executes all middleware.
        """
        # Build the chain from right to left (final handler first)
        handler = final_handler

        # Wrap with middleware in reverse order so they execute in
        # registration order
        for middleware in reversed(self._middleware_stack):
            # Capture the current handler in a closure
            current_handler = handler

            def wrapped(
                request: Request,
                mw=middleware,
                next_h=current_handler,
            ) -> Response:
                try:
                    return mw(request, next_h)
                except Exception as exc:
                    logger.exception(
                        "Middleware error for %s %s: %s",
                        request.method,
                        request.path,
                        exc,
                    )
                    raise

            handler = wrapped

        return handler

    def execute(
        self,
        request: Request,
        final_handler: Callable[[Request], Response],
    ) -> Response:
        """Execute the middleware pipeline.

        Args:
            request: The HTTP request.
            final_handler: The final route/response handler.

        Returns:
            HTTP response.
        """
        wrapped_handler = self.build_handler(final_handler)
        return wrapped_handler(request)

    @property
    def middleware_count(self) -> int:
        """Get the number of registered middleware."""
        return len(self._middleware_stack)
