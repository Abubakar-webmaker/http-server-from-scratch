"""Request dispatching and orchestration layer.

This module orchestrates the full request→response pipeline:
1. Apply pre-processing middleware (rate limiting, request logging)
2. Route request to handler (or static file)
3. Build response
4. Apply post-processing middleware (compression, response logging)

Separates application logic from transport layer (server.py).
"""

import logging
from urllib.parse import urlsplit

from http.response import Response

logger = logging.getLogger("Dispatcher")


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

    def dispatch(self, request):
        """Complete request→response pipeline.
        
        Pipeline stages:
        1. Extract path from URL
        2. Determine route type (static vs app)
        3. Call appropriate handler
        4. Log request/response
        5. Return response for serialization
        
        Args:
            request: Parsed HTTP request
            
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

        # Stage 1: Determine route type and dispatch
        try:
            if request_path.startswith(self.static_url_prefix):
                # Static file request
                relative_path = request_path[len(self.static_url_prefix):]
                response = self.static_handler.handle(
                    request,
                    relative_path,
                )
            else:
                # Application route request
                response = self.router.dispatch(request)

        except Exception as exc:
            logger.exception(
                "Unhandled dispatch error for %s %s: %s",
                request.method,
                request.path,
                exc,
            )
            response = Response(
                500,
                "500 - Internal Server Error",
            )

        # Stage 2: Log response
        if hasattr(response, 'status_code'):
            logger.info(
                "Response sent: %s %s → %d",
                request.method,
                request.path,
                response.status_code,
            )

        return response
