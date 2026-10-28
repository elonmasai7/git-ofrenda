"""The séance: a localhost-only web server where you can talk to each ghost.

Safety notes:
  * binds to 127.0.0.1 only
  * rejects requests whose Host header is not localhost (DNS-rebinding defence)
  * POST endpoints require a custom X-Ofrenda header, which browsers will not
    send cross-site without a CORS preflight that we never approve (CSRF defence)
  * request bodies and messages are size-capped
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List

from . import poet, prompts, render
from .cache import SeanceStore
from .gitscan import Ghost
from .llm import Backend, LLMError

MAX_BODY = 20_000
MAX_MESSAGE = 500
HISTORY_WINDOW = 12


class OfrendaServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, ghosts: List[Ghost], repo_name: str, backend: Backend,
                 store: SeanceStore, lang: str = "en"):
        super().__init__(addr, Handler)
        self.ghosts = {g.path: g for g in ghosts}
        self.ordered = ghosts
        self.repo_name, self.backend, self.store, self.lang = repo_name, backend, store, lang
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    def page(self) -> bytes:
        return render.html_page(self.repo_name, self.ordered, self.lang, interactive=True,
                                history=self.store.all()).encode()


class Handler(BaseHTTPRequestHandler):
    server: OfrendaServer
    server_version = "git-ofrenda"

    def log_message(self, *args):  # keep the terminal quiet
        pass

    # -- helpers
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in self.server.allowed_hosts

    # -- routes
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "bad host"})
        if self.path in ("/", "/index.html"):
            return self._send(200, self.server.page(), "text/html; charset=utf-8")
        if self.path == "/healthz":
            return self._json(200, {"ok": True, "ghosts": len(self.server.ghosts)})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "bad host"})
        if self.headers.get("X-Ofrenda") != "1":
            return self._json(403, {"error": "missing X-Ofrenda header"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > MAX_BODY:
                return self._json(413, {"error": "bad body size"})
            body = json.loads(self.rfile.read(n))
            ghost = self.server.ghosts[body["path"]]
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"error": "bad request"})
        if self.path == "/api/chat":
            msg = body.get("message")
            if not isinstance(msg, str) or not msg.strip() or len(msg) > MAX_MESSAGE:
                return self._json(400, {"error": "message must be 1-500 characters"})
            return self._chat(ghost, msg.strip())
        if self.path == "/api/reset":
            self.server.store.reset(ghost.path)
            return self._json(200, {"ok": True})
        self._json(404, {"error": "not found"})

    def _emit(self, obj: dict) -> None:
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode() + b"\n")
        self.wfile.flush()

    def _chat(self, g: Ghost, message: str) -> None:
        srv = self.server
        history = srv.store.get(g.path)[-HISTORY_WINDOW:]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()  # HTTP/1.0: the stream ends when we close the connection
        parts: List[str] = []
        voice = "model"
        try:
            try:
                if srv.backend.name == "none":
                    raise LLMError("no model")
                for tok in srv.backend.chat_stream(prompts.seance_messages(g, history, message, srv.lang)):
                    parts.append(tok)
                    self._emit({"token": tok})
            except LLMError:
                if not parts:  # nothing streamed yet: answer from git facts instead
                    text = poet.seance_fallback(g, message, srv.lang)
                    parts.append(text)
                    voice = "template"
                    self._emit({"token": text})
            reply = "".join(parts).strip()
            if reply:
                srv.store.append(g.path, message, reply)
            self._emit({"done": True, "voice": voice})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser went away mid-answer


def make_server(ghosts: List[Ghost], repo_name: str, backend: Backend, store: SeanceStore,
                lang: str = "en", port: int = 8666) -> OfrendaServer:
    return OfrendaServer(("127.0.0.1", port), ghosts, repo_name, backend, store, lang)
