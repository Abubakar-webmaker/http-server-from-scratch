import os
import tempfile
import threading
import unittest

from types import SimpleNamespace

from static_files.handler import StaticFileHandler


class StaticFileHandlerTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name

        self.handler = StaticFileHandler(self.root)

        self.html_content = b"<h1>Hello Static Files</h1>"

        self.create_file("index.html", self.html_content)
        self.create_file("style.css", b"body { color: red; }")
        self.create_file("script.js", b"console.log('hello');")
        self.create_file("image.png", b"\x89PNG\r\n\x1a\n")
        self.create_file("document.pdf", b"%PDF-1.4 test")
        self.create_file("unknown.xyz123", b"\x00\x01\x02")

        self.request_headers = {}

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_file(self, name, content):
        path = os.path.join(self.root, name)

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as file:
            file.write(content)

        return path

    def make_request(self, method="GET", headers=None):
        return SimpleNamespace(
            method=method,
            headers=headers or {},
            path="/static/index.html",
        )

    def get_response(self, path, method="GET", headers=None):
        request = self.make_request(method, headers)

        return self.handler.handle(request, path)

    def test_serve_html_file(self):
        response = self.get_response("index.html")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, self.html_content)
        self.assertEqual(
            response.headers["Content-Type"],
            "text/html",
        )

    def test_serve_css_file(self):
        response = self.get_response("style.css")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "text/css",
        )

    def test_serve_javascript_file(self):
        response = self.get_response("script.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "javascript",
            response.headers["Content-Type"],
        )

    def test_serve_png_file_as_binary(self):
        response = self.get_response("image.png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.body,
            b"\x89PNG\r\n\x1a\n",
        )
        self.assertEqual(
            response.headers["Content-Type"],
            "image/png",
        )

    def test_serve_pdf_file(self):
        response = self.get_response("document.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "application/pdf",
        )

    def test_unknown_extension_uses_binary_mime_type(self):
        response = self.get_response("unknown.xyz123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "application/octet-stream",
        )

    def test_content_length_is_correct(self):
        response = self.get_response("index.html")

        self.assertEqual(
            int(response.headers["Content-Length"]),
            len(self.html_content),
        )

    def test_missing_file_returns_404(self):
        response = self.get_response("missing.html")

        self.assertEqual(response.status_code, 404)

    def test_directory_access_returns_404(self):
        os.makedirs(os.path.join(self.root, "folder"))

        response = self.get_response("folder")

        self.assertEqual(response.status_code, 404)

    def test_parent_directory_traversal_is_blocked(self):
        outside_file = os.path.join(
            os.path.dirname(self.root),
            "outside_secret.txt",
        )

        with open(outside_file, "wb") as file:
            file.write(b"secret")

        try:
            response = self.get_response("../outside_secret.txt")
            self.assertEqual(response.status_code, 403)
        finally:
            os.remove(outside_file)

    def test_encoded_traversal_is_blocked(self):
        response = self.get_response("%2e%2e/secret.txt")

        self.assertEqual(response.status_code, 403)

    def test_double_encoded_traversal_does_not_escape_root(self):
        response = self.get_response("%252e%252e/secret.txt")

        self.assertNotEqual(response.status_code, 200)

    def test_absolute_path_is_blocked(self):
        response = self.get_response(
            os.path.abspath(__file__)
        )

        self.assertEqual(response.status_code, 403)

    def test_null_byte_is_rejected(self):
        response = self.get_response("index.html\x00.txt")

        self.assertEqual(response.status_code, 403)

    def test_backslash_path_is_rejected(self):
        response = self.get_response("..\\secret.txt")

        self.assertEqual(response.status_code, 403)

    def test_symlink_outside_root_is_blocked(self):
        outside_dir = tempfile.TemporaryDirectory()

        try:
            outside_file = os.path.join(
                outside_dir.name,
                "secret.txt",
            )

            with open(outside_file, "wb") as file:
                file.write(b"secret")

            link_path = os.path.join(self.root, "external")

            try:
                os.symlink(outside_file, link_path)
            except (OSError, NotImplementedError):
                self.skipTest(
                    "Symbolic link creation is unavailable"
                )

            response = self.get_response("external")

            self.assertEqual(response.status_code, 403)

        finally:
            outside_dir.cleanup()

    def test_etag_is_generated(self):
        response = self.get_response("index.html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("ETag", response.headers)
        self.assertTrue(
            response.headers["ETag"].startswith('"')
        )

    def test_matching_etag_returns_304(self):
        first = self.get_response("index.html")
        etag = first.headers["ETag"]

        second = self.get_response(
            "index.html",
            headers={"If-None-Match": etag},
        )

        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.body, b"")

    def test_weak_etag_returns_304(self):
        first = self.get_response("index.html")
        etag = first.headers["ETag"]

        response = self.get_response(
            "index.html",
            headers={"If-None-Match": "W/" + etag},
        )

        self.assertEqual(response.status_code, 304)

    def test_wildcard_etag_returns_304(self):
        response = self.get_response(
            "index.html",
            headers={"If-None-Match": "*"},
        )

        self.assertEqual(response.status_code, 304)

    def test_changed_file_returns_new_etag(self):
        first = self.get_response("index.html")
        old_etag = first.headers["ETag"]

        self.create_file(
            "index.html",
            b"<h1>Updated content</h1>",
        )

        second = self.get_response("index.html")

        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            second.headers["ETag"],
            old_etag,
        )

    def test_last_modified_header_is_generated(self):
        response = self.get_response("index.html")

        self.assertIn("Last-Modified", response.headers)

    def test_matching_if_modified_since_returns_304(self):
        first = self.get_response("index.html")
        last_modified = first.headers["Last-Modified"]

        response = self.get_response(
            "index.html",
            headers={
                "If-Modified-Since": last_modified,
            },
        )

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.body, b"")

    def test_if_none_match_takes_precedence(self):
        first = self.get_response("index.html")
        etag = first.headers["ETag"]

        # An invalid date must not override a matching ETag.
        response = self.get_response(
            "index.html",
            headers={
                "If-None-Match": etag,
                "If-Modified-Since": "invalid-date",
            },
        )

        self.assertEqual(response.status_code, 304)

    def test_non_matching_etag_returns_200(self):
        response = self.get_response(
            "index.html",
            headers={"If-None-Match": '"different-etag"'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, self.html_content)

    def test_head_returns_no_body(self):
        response = self.get_response(
            "index.html",
            method="HEAD",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"")

        # HEAD must preserve the GET representation length.
        self.assertEqual(
            int(response.headers["Content-Length"]),
            len(self.html_content),
        )

    def test_unsupported_method_returns_405(self):
        response = self.get_response(
            "index.html",
            method="POST",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            response.headers["Allow"],
            "GET, HEAD",
        )

    def test_concurrent_file_requests(self):
        results = []
        errors = []

        def worker():
            try:
                response = self.get_response("index.html")

                results.append(response.status_code)

            except Exception as error:
                errors.append(error)

        threads = [
            threading.Thread(target=worker)
            for _ in range(20)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=5)

        self.assertTrue(
            all(not thread.is_alive() for thread in threads)
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 20)
        self.assertTrue(all(code == 200 for code in results))


if __name__ == "__main__":
    unittest.main()