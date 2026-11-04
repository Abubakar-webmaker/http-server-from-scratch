"""
Secure static file handler.

Features:
- Binary file reading
- MIME type detection
- Directory traversal protection
- Symbolic-link containment checks
- ETag support
- Last-Modified support
- Conditional GET requests
- GET and HEAD support
"""

import hashlib
import mimetypes
import os
import re

from datetime import timezone
from email.utils import formatdate, parsedate_to_datetime
from urllib.parse import unquote_to_bytes, urlsplit

from http.response import Response


class StaticFileHandler:
    """Serve files safely from a configured static directory."""

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

    def __init__(self, root_directory: str):
        self.root_directory = os.path.realpath(
            os.path.abspath(root_directory)
        )

        if not os.path.isdir(self.root_directory):
            raise ValueError("Static directory does not exist")

    def handle(self, request, relative_path: str = "") -> Response:
        """
        Handle a static file request.

        request must expose:
            request.method
            request.headers

        relative_path is the URL path relative to the static URL prefix.
        """

        method = request.method.upper()

        if method not in ("GET", "HEAD"):
            return self._response(
                405,
                b"405 - Method Not Allowed",
                {
                    "Content-Type": "text/plain; charset=utf-8",
                    "Allow": "GET, HEAD",
                },
            )

        try:
            file_path = self._resolve_path(relative_path)

            if not os.path.isfile(file_path):
                return self._not_found()

            stat_result = os.stat(file_path)

            if stat_result.st_size > self.MAX_FILE_SIZE:
                return self._response(
                    413,
                    b"413 - File Too Large",
                    {"Content-Type": "text/plain; charset=utf-8"},
                )

            # Read the file in binary mode.
            with open(file_path, "rb") as file:
                file_stat = os.fstat(file.fileno())

                # Check that the opened file is still inside the root.
                opened_path = os.path.realpath(file_path)

                if not self._is_inside_root(opened_path):
                    return self._forbidden()

                if not os.path.isfile(opened_path):
                    return self._not_found()

                content = file.read()

            # Detect MIME type automatically.
            content_type, encoding = mimetypes.guess_type(file_path)

            if content_type is None:
                content_type = "application/octet-stream"

            # SHA-256 content-based ETag.
            etag = '"' + hashlib.sha256(content).hexdigest() + '"'

            # HTTP dates have one-second precision.
            last_modified = formatdate(
                file_stat.st_mtime,
                usegmt=True,
            )

            headers = {
                "Content-Type": content_type,
                "Content-Length": str(len(content)),
                "ETag": etag,
                "Last-Modified": last_modified,
                "Cache-Control": "public, max-age=0, must-revalidate",
            }

            # If-None-Match has precedence over If-Modified-Since.
            if_none_match = self._get_header(
                request.headers,
                "If-None-Match",
            )

            if if_none_match is not None:
                if self._etag_matches(if_none_match, etag):
                    return self._not_modified(etag, last_modified)

            else:
                if_modified_since = self._get_header(
                    request.headers,
                    "If-Modified-Since",
                )

                if if_modified_since:
                    if self._not_modified_since(
                        if_modified_since,
                        file_stat.st_mtime,
                    ):
                        return self._not_modified(
                            etag,
                            last_modified,
                        )

            # HEAD returns GET headers without the body.
            body = b"" if method == "HEAD" else content

            return self._response(
                200,
                body,
                headers,
            )

        except PermissionError:
            return self._forbidden()

        except FileNotFoundError:
            return self._not_found()

        except (ValueError, UnicodeError, OSError):
            return self._forbidden()

        except Exception:
            # Do not expose filesystem paths or stack traces.
            return self._response(
                500,
                b"500 - Internal Server Error",
                {"Content-Type": "text/plain; charset=utf-8"},
            )

    def _resolve_path(self, requested_path: str) -> str:
        """Resolve a URL path and prevent filesystem traversal."""

        if not isinstance(requested_path, str):
            raise ValueError("Invalid path")

        # Strip query string and fragment.
        requested_path = urlsplit(requested_path).path

        # Decode exactly once.
        decoded_bytes = unquote_to_bytes(requested_path)
        decoded_path = decoded_bytes.decode("utf-8", errors="strict")

        # Reject dangerous characters and platform separators.
        if "\x00" in decoded_path:
            raise ValueError("Invalid path")

        if "\\" in decoded_path:
            raise ValueError("Invalid path")

        if decoded_path.startswith(("/", "\\")):
            raise ValueError("Absolute paths are not allowed")

        # Reject Windows drive paths.
        if re.match(r"^[a-zA-Z]:", decoded_path):
            raise ValueError("Drive paths are not allowed")

        normalized_path = os.path.normpath(decoded_path)

        if normalized_path in ("", "."):
            raise FileNotFoundError

        if normalized_path == ".." or normalized_path.startswith(
            ".." + os.sep
        ):
            raise PermissionError

        candidate = os.path.abspath(
            os.path.join(self.root_directory, normalized_path)
        )

        resolved = os.path.realpath(candidate)

        if not self._is_inside_root(resolved):
            raise PermissionError

        return resolved

    def _is_inside_root(self, path: str) -> bool:
        """Check canonical path containment using commonpath."""

        try:
            common = os.path.commonpath(
                [self.root_directory, os.path.realpath(path)]
            )

            return os.path.normcase(common) == os.path.normcase(
                self.root_directory
            )

        except (ValueError, OSError):
            return False

    @staticmethod
    def _get_header(headers, name: str):
        """Read a header case-insensitively."""

        if not headers:
            return None

        for key, value in headers.items():
            if key.lower() == name.lower():
                return value

        return None

    @staticmethod
    def _etag_matches(header_value: str, current_etag: str) -> bool:
        """
        If-None-Match uses weak comparison for GET and HEAD.
        Also supports wildcard '*'.
        """

        if not header_value:
            return False

        current_opaque = current_etag.strip('"')

        for candidate in header_value.split(","):
            candidate = candidate.strip()

            if candidate == "*":
                return True

            # Weak and strong validators are equivalent for
            # If-None-Match GET/HEAD comparisons.
            if candidate.startswith("W/"):
                candidate = candidate[2:].strip()

            if candidate == current_etag:
                return True

            if candidate.strip('"') == current_opaque:
                return True

        return False

    @staticmethod
    def _not_modified_since(
        header_value: str,
        file_mtime: float,
    ) -> bool:
        """Check If-Modified-Since using HTTP date precision."""

        try:
            parsed_date = parsedate_to_datetime(header_value)

            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(
                    tzinfo=timezone.utc
                )

            request_timestamp = int(parsed_date.timestamp())
            file_timestamp = int(file_mtime)

            return file_timestamp <= request_timestamp

        except (TypeError, ValueError, OverflowError):
            # Invalid conditional date is ignored.
            return False

    def _not_modified(
        self,
        etag: str,
        last_modified: str,
    ) -> Response:
        """Return an empty 304 response."""

        return self._response(
            304,
            b"",
            {
                "ETag": etag,
                "Last-Modified": last_modified,
                "Cache-Control": "public, max-age=0, must-revalidate",
            },
        )

    @staticmethod
    def _response(status_code, body, headers):
        """
        Create a response using the existing Response class.

        Expected constructor:
            Response(status_code=..., body=..., headers=...)
        """

        return Response(
            status_code=status_code,
            body=body,
            headers=headers,
        )

    def _not_found(self):
        return self._response(
            404,
            b"404 - Not Found",
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    def _forbidden(self):
        return self._response(
            403,
            b"403 - Forbidden",
            {"Content-Type": "text/plain; charset=utf-8"},
        )