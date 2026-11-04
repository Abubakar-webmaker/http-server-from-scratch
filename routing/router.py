"""HTTP request routing module.

This module provides URL pattern matching and request dispatching.
It supports both static routes (e.g., /users) and dynamic routes with
parameters (e.g., /users/:id).
"""

import re
from dataclasses import dataclass

from http.request import Request
from http.response import Response


@dataclass
class Route:
    """Compiled route specification."""
    method: str
    pattern: str
    regex: re.Pattern
    parameter_names: list[str]
    handler: object


class Router:
    """HTTP router supporting static and dynamic URL paths.
    
    Features:
    - Static routes: GET /users
    - Dynamic routes: GET /users/:user_id
    - Nested routes: GET /users/:user_id/posts/:post_id
    - Automatic parameter extraction
    - 404/405 error responses
    """

    def __init__(self):
        """Initialize empty route table."""
        self.routes: dict[tuple[str, str], object] = {}
        self._route_specs: list[Route] = []

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize URL path for consistent matching.
        
        Args:
            path: Raw request path (may include query string)
        
        Returns:
            Normalized path starting with / without trailing slash
            
        Raises:
            ValueError: If path is invalid
        """
        # Remove query string (keep only path part)
        path = path.split("?", 1)[0]

        # Path must start with /
        if not path.startswith("/"):
            raise ValueError("Route path must start with /")

        # Reject double slashes (e.g., /users//profile)
        if "//" in path:
            raise ValueError("Invalid route path")

        # Remove trailing slash (except for root /)
        if len(path) > 1:
            path = path.rstrip("/")

        return path

    @staticmethod
    def _patterns_equivalent(a: str, b: str) -> bool:
        """Check if two route patterns are structurally equivalent.
        
        Two patterns are equivalent when they have the same structure
        but different parameter names. For example:
        - /users/:id and /users/:user_id are equivalent
        - /users/:id and /users/:id/:post_id are NOT equivalent
        
        This prevents ambiguous route registration.
        
        Args:
            a: First route pattern
            b: Second route pattern
            
        Returns:
            True if patterns are equivalent, False otherwise
        """
        a_parts = a.split("/")
        b_parts = b.split("/")

        if len(a_parts) != len(b_parts):
            return False

        for first, second in zip(a_parts, b_parts):
            first_dynamic = first.startswith(":")
            second_dynamic = second.startswith(":")

            # Both must be dynamic or both must be static
            if first_dynamic != second_dynamic:
                return False

            # Static parts must be identical
            if not first_dynamic and first != second:
                return False

        return True

    def add_route(self, method: str, path: str, handler):
        """Register a new route with handler.
        
        Validates method, path, and handler, then converts the path
        pattern into a compiled regex for efficient matching.
        
        Route patterns:
        - Static: /users
        - Dynamic: /users/:id
        - Nested: /users/:user_id/posts/:post_id
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: URL path pattern
            handler: Callable that takes Request and route parameters
            
        Raises:
            TypeError: If handler is not callable
            ValueError: If method, path, or parameters are invalid
        """
        if not callable(handler):
            raise TypeError("Handler must be callable")

        method = method.upper()
        path = self.normalize_path(path)

        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("Unsupported HTTP method")

        key = (method, path)

        if key in self.routes:
            raise ValueError(f"Duplicate route: {method} {path}")

        # Extract parameter names from route pattern (e.g., :id, :user_id)
        names = re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", path)

        if len(names) != len(set(names)):
            raise ValueError("Duplicate route parameter")

        # Build regex pattern by replacing parameters with capture groups
        # Example: /users/:id -> /users/(?P<id>[^/]+)
        parts = path.split("/")
        regex_parts = []

        for part in parts:
            if part.startswith(":"):
                name = part[1:]

                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name):
                    raise ValueError("Invalid route parameter")

                # Capture group for parameter: matches anything except /
                regex_parts.append(f"(?P<{name}>[^/]+)")
            else:
                # Escape special regex characters in static path parts
                regex_parts.append(re.escape(part))

        regex = re.compile("^" + "/".join(regex_parts) + "$")

        # Check for ambiguous routes (same structure, different param names)
        for existing in self._route_specs:
            if existing.method == method and self._patterns_equivalent(
                existing.pattern,
                path,
            ):
                raise ValueError("Ambiguous route")

        self.routes[key] = handler
        self._route_specs.append(
            Route(
                method=method,
                pattern=path,
                regex=regex,
                parameter_names=names,
                handler=handler,
            )
        )

    def get(self, path, handler):
        self.add_route("GET", path, handler)

    def post(self, path, handler):
        self.add_route("POST", path, handler)

    def put(self, path, handler):
        self.add_route("PUT", path, handler)

    def delete(self, path, handler):
        self.add_route("DELETE", path, handler)

    def dispatch(self, request: Request) -> Response:
        """Route a parsed request to the appropriate handler.
        
        Matching priority:
        1. Exact method and path match
        2. Static routes take precedence over dynamic routes
        3. If path matches but method doesn't: return 405 (Method Not Allowed)
        4. If no match at all: return 404 (Not Found)
        
        Args:
            request: Parsed HTTP request object
            
        Returns:
            HTTP Response from handler or error response (404/405/500)
        """
        try:
            path = self.normalize_path(request.path)
        except ValueError:
            return Response(400, "400 - Bad Request")

        method = request.method.upper()

        # Find all routes that match the path with the given method
        matches = []

        for route in self._route_specs:
            if route.method == method:
                match = route.regex.fullmatch(path)

                if match:
                    matches.append((route, match))

        if matches:
            # Prefer static routes over dynamic routes by parameter count
            # Example: /users (0 params) > /users/:id (1 param)
            route, match = min(
                matches,
                key=lambda item: len(item[0].parameter_names),
            )

            try:
                # Call handler with request and extracted parameters
                result = route.handler(
                    request,
                    **match.groupdict(),
                )

                if not isinstance(result, Response):
                    raise TypeError("Handler must return Response")

                return result

            except Exception:
                return Response(
                    500,
                    "500 - Internal Server Error",
                )

        # Check if path matches any route with different method (405)
        allowed_methods = []

        for route in self._route_specs:
            if route.regex.fullmatch(path):
                if route.method not in allowed_methods:
                    allowed_methods.append(route.method)

        if allowed_methods:
            return Response(
                405,
                "405 - Method Not Allowed",
                {"Allow": ", ".join(sorted(allowed_methods))},
            )

        # No route found (404)
        return Response(404, "404 - Route Not Found")
