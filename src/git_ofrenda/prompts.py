"""Prompt construction and parsing of model output."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .gitscan import Ghost

PROMPT_VERSION = 2
MAX_SOURCE_CHARS = 2500
LANG_NAMES = {"en": "English", "es": "Spanish"}

EPITAPH = """You are the ghost of a deleted source file named "{path}".
You lived {days} days across {commits} commits, written by {authors}.
You were killed by {killer} with the commit message: "{cause}".
This is what you contained when you died:
---
{source}
---
Write in {language}. Reply in EXACTLY this format, nothing else:
LAST WORDS: <one wistful or funny first-person sentence that mentions something specific from your code>
CALAVERA:
<four short rhyming lines: a playful calavera literaria epitaph about your life and death>"""

SEANCE = """You are the ghost of the deleted source file "{path}". Speak in first person, in {language},
2-4 sentences, wistful with dry humor. Stay truthful: only claim what the facts and code below
support; if asked something you cannot know, say the dead do not remember everything.
Facts: lived {days} days ({born} to {died}), {commits} commits, authors {authors},
deleted by {killer} with the message "{cause}".
Your final contents:
---
{source}
---"""


def _fill(template: str, g: Ghost, lang: str) -> str:
    return template.format(
        path=g.path, days=g.days, commits=g.commits, authors=", ".join(g.authors),
        killer=g.killer, cause=g.cause, born=g.born, died=g.died,
        source=g.source[:MAX_SOURCE_CHARS], language=LANG_NAMES.get(lang, "English"))


def epitaph_prompt(g: Ghost, lang: str = "en") -> str:
    return _fill(EPITAPH, g, lang)


def seance_messages(g: Ghost, history: List[dict], message: str, lang: str = "en") -> List[dict]:
    msgs = [{"role": "system", "content": _fill(SEANCE, g, lang)}]
    msgs += [m for m in history if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    msgs.append({"role": "user", "content": message})
    return msgs


_LAST = re.compile(r"last\s*words\s*:\s*(.+?)\s*(?:\n\s*)?calavera\s*:\s*(.+)\Z", re.I | re.S)


def parse_epitaph(text: str) -> Optional[Tuple[str, str]]:
    """Return (last_words, calavera) or None if the model ignored the format."""
    text = re.sub(r"```\w*", "", text).replace("**", "").strip()
    m = _LAST.search(text)
    if not m:
        return None
    last = " ".join(m.group(1).split()).strip(" \"'“”")
    lines = [l.strip() for l in m.group(2).splitlines() if l.strip()][:6]
    if not last or len(lines) < 2:
        return None
    return last, "\n".join(lines)
