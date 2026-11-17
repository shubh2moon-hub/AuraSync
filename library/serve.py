"""Local gallery server: serves the library and saves the phone framing you pick.

  python serve.py        then open http://127.0.0.1:8765
"""
import http.server, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from phone import make_phone
import render


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # framing changes rewrite the same file names
        super().end_headers()

    def do_POST(self):
        if self.path != "/api/phone":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            pid = body["id"]
            if not re.fullmatch(r"[a-z0-9_]+", pid) or not os.path.isdir(os.path.join(HERE, "packs", pid)):
                return self.send_error(400, "unknown pack")
            mode = body.get("mode") if body.get("mode") in ("crop", "whole") else None
            meta = make_phone(os.path.join(HERE, "packs", pid), mode, body.get("center"), body.get("offset"))
            render.write_index()
            data = json.dumps(meta).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"AuraSync library: http://127.0.0.1:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
