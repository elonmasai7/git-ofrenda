"""Pull a few concrete facts out of a source file (no model involved)."""
from __future__ import annotations

import re
from typing import List, Optional

_DEF = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|fn|fun)\s+([A-Za-z_$][\w$]*)", re.M)
_IMPORTS = [
    re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)", re.M),
    re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import", re.M),
    re.compile(r"require\(\s*['\"]([^'\"./][^'\"]*)['\"]\s*\)"),
    re.compile(r"from\s+['\"]([^'\"./][^'\"]*)['\"]"),
]
_STOP = {"os", "sys", "re", "json", "time", "typing", "random", "math", "__future__", "datetime"}
_DOC = re.compile(r'("""|\'\'\')(.+?)\1', re.S)
_COMMENT = re.compile(r"^\s*(?:#(?!!)|//|--)\s*(\S.*)$", re.M)


def functions(src: str, limit: int = 5) -> List[str]:
    seen: List[str] = []
    for m in _DEF.finditer(src):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen[:limit]


def dependencies(src: str, limit: int = 3) -> List[str]:
    seen: List[str] = []
    for rx in _IMPORTS:
        for m in rx.finditer(src):
            name = m.group(1).split(".")[0]
            if name not in _STOP and name not in seen:
                seen.append(name)
    return seen[:limit]


def intent(src: str) -> Optional[str]:
    """What the file said it was for: first docstring or comment line."""
    m = _DOC.search(src)
    if m and m.group(2).strip():
        return m.group(2).strip().splitlines()[0].strip()[:90]
    m = _COMMENT.search(src)
    return m.group(1).strip()[:90] if m else None
