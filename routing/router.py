import re
from dataclasses import dataclass

from http.request import Request
from http.response import Response


@dataclass
class Route:
    method: str
    pattern: str
    regex: re.Pattern
    parameter_names: list[str]
    handler: object


class Router:
    """Simple HTTP router supporting static and dynamic paths."""

    def __init__(self):
        self.routes: dict[tuple[str, str], object] = {}
        self._route_specs: list[Route] = []

    @staticmethod
    def normalize_path(path: str) -> str:
        path = path.split("?", 1)[0]

        if not path.startswith("/"):
            raise ValueError("Route path must start with /")

        if "//" in path:
            raise ValueError("Invalid route path")

        if len(path) > 1:
            path = path.rstrip("/")

        return path

    @staticmethod
    def _patterns_equivalent(a: str, b: str) -> bool:
        """Two patterns are equivalent when they share the same structure,
        ignoring parameter names (e.g. ``/users/:id`` and ``/users/:name``)."""

        a_parts = a.split("/")
        b_parts = b.split("/")

        if len(a_parts) != len(b_parts):
            return False

        for first, second in zip(a_parts, b_parts):
            first_dynamic = first.startswith(":")
            second_dynamic = second.startswith(":")

            if first_dynamic != second_dynamic:
                return False

            if not first_dynamic and first != second:
                return False

        return True

    def add_route(self, method: str, path: str, handler):
        if not callable(handler):
            raise TypeError("Handler must be callable")

        method = method.upper()
        path = self.normalize_path(path)

        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("Unsupported HTTP method")

        key = (method, path)

        if key in self.routes:
            raise ValueError(f"Duplicate route: {method} {path}")

        names = re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", path)

        if len(names) != len(set(names)):
            raise ValueError("Duplicate route parameter")

        parts = path.split("/")
        regex_parts = []

        for part in parts:
            if part.startswith(":"):
                name = part[1:]

                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name):
                    raise ValueError("Invalid route parameter")

                regex_parts.append(f"(?P<{name}>[^/]+)")
            else:
                regex_parts.append(re.escape(part))

        regex = re.compile("^" + "/".join(regex_parts) + "$")

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
        try:
            path = self.normalize_path(request.path)
        except ValueError:
            return Response(400, "400 - Bad Request")

        method = request.method.upper()

        matches = []

        for route in self._route_specs:
            if route.method == method:
                match = route.regex.fullmatch(path)

                if match:
                    matches.append((route, match))

        if matches:
            # Static routes (fewer parameters) take priority over dynamic
            # ones when both match the same path.
            route, match = min(
                matches,
                key=lambda item: len(item[0].parameter_names),
            )

            try:
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

        return Response(404, "404 - Route Not Found")
