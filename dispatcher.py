"""Request dispatching and orchestration layer.

This module orchestrates the full request→response pipeline:
1. Apply pre-processing middleware (rate limiting, request logging)
2. Route request to handler (or static file)
3. Build response
4. Apply post-processing middleware (compression, response logging)

Separates application logic from transport layer (server.py).
"""

import logging
import threading
from urllib.parse import urlsplit

from http.response import Response
from core.middleware import MiddlewarePipeline

logger = logging.getLogger("Dispatcher")

# Thread-local storage for client address (avoids race conditions)
_thread_local = threading.local()


class RequestDispatcher:
    """Orchestrates the complete request→response pipeline.
    
    Responsibilities:
    - Determine if request is static file or application route
    - Apply middleware pre-processing
    - Dispatch to appropriate handler
    - Apply middleware post-processing
    - Log request/response
    """

    def __init__(
        self,
        router,
        static_handler,
        static_url_prefix="/static/",
    ):
        """Initialize dispatcher with routing components.
        
        Args:
            router: Router instance for application routing
            static_handler: StaticFileHandler for static files
            static_url_prefix: URL prefix for static files
        """
        self.router = router
        self.static_handler = static_handler
        self.static_url_prefix = static_url_prefix
        
        # Initialize middleware pipeline
        self.middleware_pipeline = MiddlewarePipeline()

    def dispatch(self, request, client_address=None):
        """Complete request→response pipeline.
        
        Pipeline stages:
        1. Extract path from URL
        2. Apply middleware pipeline (including rate limiting)
        3. Determine route type (static vs app)
        4. Call appropriate handler
        5. Log request/response
        6. Return response for serialization
        
        Args:
            request: Parsed HTTP request
            client_address: Tuple (ip, port) of client connection (for rate limiting)
            
        Returns:
            Response object ready for serialization
        """
        # Extract clean path (without query string)
        try:
            request_path = urlsplit(request.path).path
        except (ValueError, AttributeError):
            return Response(400, "400 - Bad Request")

        # Log incoming request
        logger.info(
            "Incoming request: %s %s",
            request.method,
            request.path,
        )

        # Stage 1: Apply middleware pipeline
        # Middleware gets request and final handler, executes in chain order
        def route_handler(req):
            """Final handler after middleware processing."""
            try:
                if request_path.startswith(self.static_url_prefix):
                    # Static file request
                    relative_path = request_path[len(self.static_url_prefix):]
                    return self.static_handler.handle(
                        req,
                        relative_path,
                    )
                else:
                    # Application route request
                    return self.router.dispatch(req)
            except Exception as exc:
                logger.exception(
                    "Unhandled dispatch error for %s %s: %s",
                    req.method,
                    req.path,
                    exc,
                )
                return Response(500, "500 - Internal Server Error")

        # Execute middleware pipeline with route handler as final target
        try:
            # Store client address in thread-local storage (thread-safe)
            # This avoids race conditions in concurrent requests
            _thread_local.client_address = client_address
            response = self.middleware_pipeline.execute(
                request,
                route_handler,
            )
        except Exception as exc:
            logger.exception(
                "Middleware pipeline error: %s",
                exc,
            )
            response = Response(500, "500 - Internal Server Error")
        finally:
            # Clear client address from thread-local storage
            _thread_local.client_address = None

        # Stage 2: Log response
        if hasattr(response, 'status_code'):
            logger.info(
                "Response sent: %s %s → %d",
                request.method,
                request.path,
                response.status_code,
            )

        return response

    def register_middleware(self, middleware):
        """Register a middleware function to the pipeline.
        
        Args:
            middleware: A callable(request, next_handler) -> Response
        """
        self.middleware_pipeline.register(middleware)


def get_client_address():
    """Get client address from thread-local storage (thread-safe).
    
    Returns:
        Tuple (ip, port) or None if not set.
    """
    return getattr(_thread_local, 'client_address', None)
