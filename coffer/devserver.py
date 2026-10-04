"""Development server: exposes the same core over HTTP on 127.0.0.1 so the
interface can be worked on in a normal browser with hot reload.

Never used by the desktop app. It binds to the loopback address only, accepts
requests only from the Vite dev server origin, and keeps its vault in
``.dev-data`` unless ``COFFER_DATA_DIR`` says otherwise.

    python -m coffer.devserver
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import Coffer

HOST = "127.0.0.1"
PORT = int(os.environ.get("COFFER_DEV_PORT", "1430"))
ALLOWED_ORIGINS = {"http://localhost:1420", "http://127.0.0.1:1420"}
MAX_BODY = 16 * 1024 * 1024


def make_handler(app: Coffer):
    class Handler(BaseHTTPRequestHandler):
        def _origin_allowed(self) -> bool:
            """Checked before anything else: a page from another origin must
            not be able to run commands, not even ones whose answer it cannot
            read."""
            origin = self.headers.get("Origin")
            if origin and origin not in ALLOWED_ORIGINS:
                self.send_error(403, "Origin not allowed")
                return False
            return True

        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def do_OPTIONS(self):  # noqa: N802 - http.server naming
            if not self._origin_allowed():
                return
            self.send_response(204)
            self._cors_headers()
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):  # noqa: N802
            if not self._origin_allowed():
                return
            if self.path != "/rpc":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self.send_error(413)
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                result = app.call(body.get("command", ""), body.get("args") or {})
            except (ValueError, AttributeError):
                result = {"error": {"code": "invalid", "message": "Malformed request"}}
            payload = json.dumps(result).encode()
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            logging.getLogger("coffer.dev").info(fmt, *args)

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    folder = Path(os.environ.get("COFFER_DATA_DIR", Path(__file__).resolve().parent.parent / ".dev-data"))
    app = Coffer(folder)
    server = ThreadingHTTPServer((HOST, PORT), make_handler(app))
    logging.getLogger("coffer.dev").info("Coffer dev server on http://%s:%d (vault in %s)", HOST, PORT, folder)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
