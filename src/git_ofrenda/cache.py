"""Small JSON stores on disk: generated verses and séance conversations."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from typing import Dict, List, Optional

MAX_HISTORY = 40


def cache_dir() -> str:
    base = os.environ.get("OFRENDA_CACHE")
    if not base:
        xdg = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
        base = os.path.join(xdg, "git-ofrenda")
    return base


def repo_id(toplevel: str) -> str:
    return hashlib.sha256(os.path.abspath(toplevel).encode()).hexdigest()[:16]


class JsonStore:
    """A dict persisted to one JSON file (atomic writes, thread-safe)."""

    def __init__(self, path: Optional[str]):
        self.path = path  # None = memory only
        self.lock = threading.Lock()
        self.data: dict = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data = loaded
            except (OSError, ValueError):
                self.data = {}

    def _flush(self) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass  # a cache that cannot be written is not worth failing over


class VerseCache(JsonStore):
    def get(self, key: str) -> Optional[dict]:
        with self.lock:
            return self.data.get(key)

    def put(self, key: str, value: dict) -> None:
        with self.lock:
            self.data[key] = value
            self._flush()

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()


class SeanceStore(JsonStore):
    """Per-ghost conversation history, kept on the server side."""

    def get(self, ghost_path: str) -> List[dict]:
        with self.lock:
            return list(self.data.get(ghost_path, []))

    def append(self, ghost_path: str, user: str, ghost: str) -> None:
        with self.lock:
            msgs = self.data.setdefault(ghost_path, [])
            msgs += [{"role": "user", "content": user}, {"role": "assistant", "content": ghost}]
            del msgs[:-MAX_HISTORY]
            self._flush()

    def reset(self, ghost_path: str) -> None:
        with self.lock:
            self.data.pop(ghost_path, None)
            self._flush()

    def all(self) -> Dict[str, List[dict]]:
        with self.lock:
            return json.loads(json.dumps(self.data))
