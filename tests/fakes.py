"""Tiny fake model servers so the real HTTP/streaming code runs in tests."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GOOD_REPLY = ("LAST WORDS: I was upload_report() and I never missed a night.\n"
              "CALAVERA:\nHere lies a file of ftp,\nit shipped the reports faithfully.\n"
              "Marta came with a delete key,\nnow it dances, ghostly and free.")
TOKENS = ["The ", "dead ", "remember ", "S3."]


class FakeServer:
    """kind = 'ollama' or 'openai'. reply overrides the /generate answer."""

    def __init__(self, kind="ollama", reply=GOOD_REPLY, models=("gemma3:latest",)):
        self.kind, self.reply, self.models, self.requests = kind, reply, models, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _body(self):
                n = int(self.headers.get("Content-Length", 0))
                return json.loads(self.rfile.read(n)) if n else {}

            def _json(self, obj):
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/tags":
                    return self._json({"models": [{"name": m} for m in outer.models]})
                if self.path == "/v1/models":
                    return self._json({"data": [{"id": "m"}]})
                self.send_response(404); self.end_headers()

            def do_POST(self):
                body = self._body()
                outer.requests.append((self.path, body))
                if self.path == "/api/generate":
                    return self._json({"response": outer.reply, "done": True})
                if self.path == "/api/chat":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    for t in TOKENS:
                        self.wfile.write(json.dumps({"message": {"role": "assistant", "content": t}, "done": False}).encode() + b"\n")
                    self.wfile.write(json.dumps({"done": True}).encode() + b"\n")
                    return
                if self.path == "/v1/chat/completions":
                    if not body.get("stream"):
                        return self._json({"choices": [{"message": {"content": outer.reply}}]})
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for t in TOKENS:
                        self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n\n")
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                self.send_response(404); self.end_headers()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
