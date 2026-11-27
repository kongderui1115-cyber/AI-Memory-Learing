"""UrllibHttpTransport must not follow redirects onto another URL."""

import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.transports import UrllibHttpTransport  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/go"):
            self.send_response(302)
            self.send_header("Location", "/land")
            self.end_headers()
            return
        body = b"followed"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


class RedirectTests(unittest.TestCase):
    def test_authenticated_http_does_not_follow_redirects(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        transport = UrllibHttpTransport()
        try:
            redirected = transport.request("GET", f"http://127.0.0.1:{port}/go")
            direct = transport.request("GET", f"http://127.0.0.1:{port}/land")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(redirected.status_code, 302)
        self.assertNotIn("followed", redirected.body)
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(direct.body, "followed")


if __name__ == "__main__":
    unittest.main()
