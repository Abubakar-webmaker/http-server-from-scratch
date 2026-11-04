"""HTTP and server-specific exceptions."""


class HTTPException(Exception):
    """Base class for HTTP protocol errors."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class BadRequestError(HTTPException):
    """400 Bad Request — malformed HTTP message."""

    def __init__(self, message: str = "Bad Request") -> None:
        super().__init__(400, message)


class RequestTooLargeError(HTTPException):
    """413 Payload Too Large."""

    def __init__(self, message: str = "Request body too large") -> None:
        super().__init__(413, message)


class RequestTimeoutError(HTTPException):
    """408 Request Timeout."""

    def __init__(self, message: str = "Request timeout") -> None:
        super().__init__(408, message)


class RateLimitExceededError(HTTPException):
    """429 Too Many Requests."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(429, "Too Many Requests")


class UnsupportedMediaTypeError(HTTPException):
    """415 Unsupported Media Type."""

    def __init__(self, message: str = "Unsupported Media Type") -> None:
        super().__init__(415, message)


class NotImplementedError(HTTPException):
    """501 Not Implemented."""

    def __init__(self, message: str = "Not Implemented") -> None:
        super().__init__(501, message)


class SSLConfigurationError(Exception):
    """TLS/SSL configuration error."""

    pass


class MiddlewareError(Exception):
    """Middleware execution error."""

    pass
