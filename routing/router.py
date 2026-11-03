
"""
HTTP routing engine.

Responsibilities:
- Register GET and POST routes.
- Match static and dynamic URL paths.
- Extract named URL parameters.
- Execute route handlers.
- Return 404, 405, and 500 responses safely.
"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit

from http.response import Response


Handler = Callable[..., Response]


@dataclass
class Route:
    method: str
    path: str
    handler: Handler
    pattern: re.Pattern
    parameter_names: list[str]
    is_dynamic: bool


class Router:
    """
    Register routes and dispatch HTTP requests to handlers.
    """

    def __init__(self):
        self.routes: Dict[tuple[str, str], Handler] = {}
        self._compiled_routes: list[Route] = []

    @staticmethod
    def _normalize_path(path: str) -> str:
        """
        Normalize trailing slashes.

        Examples:
            /users/  -> /users
            /        -> /
        """

        if not isinstance(path, str):
            raise ValueError("Route path must be a string.")

        if not path.startswith("/"):
            raise ValueError("Route path must start with '/'.")

        if "?" in path or "#" in path:
            raise ValueError("Route patterns cannot contain query strings or fragments.")

        if "//" in path:
            raise ValueError("Repeated slashes are not allowed.")

        if path != "/":
            path = path.rstrip("/")

        return path or "/"

    @staticmethod
    def _compile_pattern(path: str):
        """
        Convert a route pattern into a regular expression.

        Example:
            /users/:id
            becomes:
            ^/users/(?P<id>[^/]+)$
        """

        parameter_names = []
        regex_parts = []

        segments = path.strip("/").split("/") if path != "/" else []

        for segment in segments:
            if segment.startswith(":"):
                parameter_name = segment[1:]

                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parameter_name):
                    raise ValueError(
                        f"Invalid route parameter: {segment}"
                    )

                if parameter_name in parameter_names:
                    raise ValueError(
                        f"Duplicate parameter name: {parameter_name}"
                    )

                parameter_names.append(parameter_name)
                regex_parts.append(
                    f"(?P<{parameter_name}>[^/]+)"
                )

            else:
                if ":" in segment:
                    raise ValueError(
                        f"Invalid dynamic route segment: {segment}"
                    )

                regex_parts.append(re.escape(segment))

        if not regex_parts:
            regex = r"^/$"
        else:
            regex = r"^/" + "/".join(regex_parts) + r"$"

        return re.compile(regex), parameter_names

    def add_route(
        self,
        method: str,
        path: str,
        handler: Handler
    ) -> None:
        """
        Register a route.

        Duplicate routes using the same method and path are rejected.
        """

        if not isinstance(method, str) or not method.strip():
            raise ValueError("HTTP method must be a non-empty string.")

        method = method.strip().upper()
        path = self._normalize_path(path)

        if not callable(handler):
            raise TypeError("Route handler must be callable.")

        route_key = (method, path)

        if route_key in self.routes:
            raise ValueError(
                f"Route already registered: {method} {path}"
            )

        pattern, parameter_names = self._compile_pattern(path)

        is_dynamic = bool(parameter_names)

        # Prevent ambiguous dynamic patterns for the same method.
        if is_dynamic:
            new_shape = self._get_route_shape(path)

            for route in self._compiled_routes:
                if route.method != method or not route.is_dynamic:
                    continue

                if self._get_route_shape(route.path) == new_shape:
                    raise ValueError(
                        f"Ambiguous dynamic route: {method} {path}"
                    )

        self.routes[route_key] = handler

        self._compiled_routes.append(
            Route(
                method=method,
                path=path,
                handler=handler,
                pattern=pattern,
                parameter_names=parameter_names,
                is_dynamic=is_dynamic,
            )
        )

    @staticmethod
    def _get_route_shape(path: str) -> tuple:
        """
        Return a normalized route shape.

        /users/:id and /users/:name have the same shape.
        """

        segments = path.strip("/").split("/") if path != "/" else []

        return tuple(
            ":parameter" if segment.startswith(":") else segment
            for segment in segments
        )

    def get(self, path: str, handler: Handler) -> None:
        self.add_route("GET", path, handler)

    def post(self, path: str, handler: Handler) -> None:
        self.add_route("POST", path, handler)

    def _find_route(self, method: str, path: str):
        """
        Find the best matching route.

        Static routes have priority over dynamic routes.
        """

        matches = []

        for route in self._compiled_routes:
            match = route.pattern.fullmatch(path)

            if match:
                matches.append((route, match))

        # Prefer exact static routes.
        for route, match in matches:
            if route.method == method and not route.is_dynamic:
                return route, match

        # Then check dynamic routes.
        for route, match in matches:
            if route.method == method:
                return route, match

        return None, None

    def _path_exists(self, path: str) -> bool:
        """
        Check whether a path matches any registered route,
        regardless of HTTP method.
        """

        return any(
            route.pattern.fullmatch(path)
            for route in self._compiled_routes
        )

    def _allowed_methods(self, path: str) -> list[str]:
        """
        Return the HTTP methods registered for a matching path.
        """

        methods = set()

        for route in self._compiled_routes:
            if route.pattern.fullmatch(path):
                methods.add(route.method)

        return sorted(methods)

    @staticmethod
    def _error_response(
        status_code: int,
        message: str
    ) -> Response:
        return Response(
            status_code=status_code,
            headers={
                "Content-Type": "text/plain; charset=utf-8"
            },
            body=message.encode("utf-8"),
        )

    def dispatch(self, request) -> Response:
        """
        Match an HTTP request and execute its handler.

        Handler interface:

            def handler(request):
                ...

            def handler(request, id):
                ...
        """

        try:
            method = request.method.strip().upper()

            if not method:
                return self._error_response(
                    400,
                    "400 - Invalid HTTP Method"
                )

            # Remove query string and fragment from the request target.
            path = urlsplit(request.path).path

            path = self._normalize_path(path)

        except (AttributeError, TypeError, ValueError):
            return self._error_response(
                400,
                "400 - Bad Request"
            )

        route, match = self._find_route(method, path)

        if route is None:

            if self._path_exists(path):
                allowed = self._allowed_methods(path)

                response = self._error_response(
                    405,
                    "405 - Method Not Allowed"
                )

                response.headers["Allow"] = ", ".join(allowed)

                return response

            return self._error_response(
                404,
                "404 - Route Not Found"
            )

        parameters = match.groupdict()

        try:
            response = route.handler(
                request,
                **parameters
            )

            if not isinstance(response, Response):
                raise TypeError(
                    "Handler must return an http.response.Response object."
                )

            return response

        except Exception:
            # Never expose internal exception details to the client.
            return self._error_response(
                500,
                "500 - Internal Server Error"
            )
