"""Model backends. Everything here talks to a server YOU run.

ollama  - Ollama's native API (default http://localhost:11434)
openai  - any OpenAI-compatible server: llama.cpp `llama-server`, LM Studio,
          vLLM, LocalAI... (default http://localhost:8080)
none    - no model; built-in templates only
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterator, List, Optional, Tuple

DEFAULT_MODEL = "gemma3"
DEFAULT_HOSTS = {"ollama": "http://localhost:11434", "openai": "http://localhost:8080"}


class LLMError(RuntimeError):
    """The model server was unreachable or answered badly."""


def _open(url: str, payload: Optional[dict], timeout: float, headers: Optional[dict] = None):
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise LLMError(f"{url} returned HTTP {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LLMError(f"cannot reach {url}: {getattr(e, 'reason', e)}") from e


class Backend:
    name = "none"
    model = ""

    @property
    def ident(self) -> str:
        return f"{self.name}:{self.model}"

    def generate(self, prompt: str) -> str:
        raise LLMError("no model configured")

    def chat_stream(self, messages: List[dict]) -> Iterator[str]:
        raise LLMError("no model configured")

    def check(self) -> Tuple[bool, str]:
        return True, "no model (templates only)"


class NoBackend(Backend):
    pass


class OllamaBackend(Backend):
    name = "ollama"

    def __init__(self, host: str, model: str, timeout: float = 180.0):
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout

    def generate(self, prompt: str) -> str:
        with _open(f"{self.host}/api/generate",
                   {"model": self.model, "prompt": prompt, "stream": False,
                    "options": {"temperature": 0.9}}, self.timeout) as r:
            try:
                return json.load(r)["response"].strip()
            except (KeyError, ValueError) as e:
                raise LLMError("unexpected reply from Ollama") from e

    def chat_stream(self, messages: List[dict]) -> Iterator[str]:
        with _open(f"{self.host}/api/chat",
                   {"model": self.model, "messages": messages, "stream": True}, self.timeout) as r:
            for raw in r:
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError as e:
                    raise LLMError("garbled stream from Ollama") from e
                if "error" in ev:
                    raise LLMError(str(ev["error"]))
                tok = (ev.get("message") or {}).get("content", "")
                if tok:
                    yield tok
                if ev.get("done"):
                    return

    def check(self) -> Tuple[bool, str]:
        try:
            with _open(f"{self.host}/api/tags", None, 3.0) as r:
                names = [m.get("name", "") for m in json.load(r).get("models", [])]
        except (LLMError, ValueError) as e:
            return False, f"Ollama is not reachable at {self.host} ({e})"
        if any(n == self.model or n == f"{self.model}:latest" or n.split(":")[0] == self.model for n in names):
            return True, f"Ollama at {self.host} has model {self.model!r}"
        return False, f"Ollama is running but model {self.model!r} is not installed (try: ollama pull {self.model})"


class OpenAICompatBackend(Backend):
    name = "openai"

    def __init__(self, host: str, model: str, timeout: float = 180.0, api_key: Optional[str] = None):
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def generate(self, prompt: str) -> str:
        payload = {"model": self.model, "temperature": 0.9, "stream": False,
                   "messages": [{"role": "user", "content": prompt}]}
        with _open(f"{self.host}/v1/chat/completions", payload, self.timeout, self.headers) as r:
            try:
                return json.load(r)["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, ValueError) as e:
                raise LLMError("unexpected reply from server") from e

    def chat_stream(self, messages: List[dict]) -> Iterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True}
        with _open(f"{self.host}/v1/chat/completions", payload, self.timeout, self.headers) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    tok = json.loads(body)["choices"][0].get("delta", {}).get("content") or ""
                except (ValueError, KeyError, IndexError) as e:
                    raise LLMError("garbled stream from server") from e
                if tok:
                    yield tok

    def check(self) -> Tuple[bool, str]:
        try:
            with _open(f"{self.host}/v1/models", None, 3.0, self.headers):
                return True, f"OpenAI-compatible server reachable at {self.host}"
        except LLMError as e:
            return False, f"server is not reachable at {self.host} ({e})"


def make_backend(kind: Optional[str] = None, host: Optional[str] = None,
                 model: Optional[str] = None) -> Backend:
    kind = (kind or os.environ.get("OFRENDA_BACKEND") or "ollama").lower()
    model = model or os.environ.get("OFRENDA_MODEL") or DEFAULT_MODEL
    if kind == "none":
        return NoBackend()
    if kind not in DEFAULT_HOSTS:
        raise ValueError(f"unknown backend {kind!r} (choose ollama, openai or none)")
    host = host or os.environ.get("OFRENDA_HOST") or DEFAULT_HOSTS[kind]
    if kind == "ollama":
        return OllamaBackend(host, model)
    return OpenAICompatBackend(host, model, api_key=os.environ.get("OFRENDA_API_KEY"))
