"""Gives each ghost a voice: model-written when possible, templated otherwise."""
from __future__ import annotations

import hashlib
import re
from typing import Callable, List, Optional

from . import facts, prompts
from .cache import VerseCache
from .gitscan import Ghost
from .llm import Backend, LLMError

ATTEMPTS = 2


# ------------------------------------------------------------ template mode

def span(days: int, lang: str = "en") -> str:
    es = lang == "es"
    if days >= 365:
        n = days // 365
        return f"{n} {'año' if n == 1 else 'años'}" if es else f"{n} year{'s' if n != 1 else ''}"
    if days >= 60:
        return f"{days // 30} {'meses' if es else 'months'}"
    return f"{days} {'días' if es else 'days'}"


def _seed(g: Ghost) -> int:
    return int(hashlib.sha1(f"{g.path}{g.commit}".encode()).hexdigest(), 16)


def _short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


_EN_BASE = ("Here lies {name}, humble and true,\n{span} it ran and {n} commits it knew.\n"
            "{killer} came with a final rm,\nno tests, no tears, no alarm.")
_EN_FN = [
    "O {name}, you carried {fn} with pride,\nthrough {n} commits you never lied.\n"
    "{killer} laid you down, the diff turned red,\nand now you're marigolds instead.",
    "They say {name} is dead and gone,\nbut its history still carries on.\n"
    "{n} commits whisper in the git log's night,\nand {fn} still glows in candlelight.",
]
_EN_DEP = ("{name} leaned on {dep}, loyal and small,\n{span} it stood, then took the fall.\n"
           "{killer} swung the delete key's blade,\nand in the log its legend stayed.")

_ES_BASE = ("Aquí yace {name}, fiel compañero,\n{span} vivió, {n} commits fue su sendero.\n"
            "{killer} llegó con su delete certero,\ny hoy baila en el log como un lucero.")
_ES_FN = ("La Catrina visitó a {name} un día,\n{killer} escribió: \"{cause}\" con alegría.\n"
          "{fn} ya no corre, pero no se olvida,\nvive en el historial, de cempasúchil vestida.")


def template_verse(g: Ghost, lang: str = "en"):
    """(last_words, calavera) built only from facts found in the file and its history."""
    seed = _seed(g)
    fns, deps, why = facts.functions(g.source), facts.dependencies(g.source), facts.intent(g.source)
    vals = dict(name=g.name, span=span(g.days, lang), n=g.commits, killer=g.killer,
                fn=f"{fns[0]}()" if fns else "", dep=deps[0] if deps else "", cause=_short(g.cause))
    if lang == "es":
        verses = [_ES_BASE] + ([_ES_FN] if fns else [])
        opts = [f"Viví {vals['span']} y fui lo que pude. No me olviden."]
        if fns:
            opts.append(f"Fui {vals['fn']} durante {vals['span']}. No me olviden.")
        if deps:
            opts.append(f"Me apoyé en {vals['dep']} durante {vals['span']}. Que no me olviden.")
        if why:
            opts.append(f"Quería ser esto: \"{why}\". Y lo fui.")
    else:
        verses = [_EN_BASE] + (_EN_FN if fns else []) + ([_EN_DEP] if deps else [])
        opts = [f"I lived {vals['span']}. Then: \"{vals['cause']}\". Fair enough."]
        if fns:
            opts.append(f"I carried {vals['fn']} for {vals['span']}. Tell the next file to write tests.")
        if why:
            opts.append(f"All I ever wanted was this: \"{why}\"")
        if deps:
            opts.append(f"I leaned on {vals['dep']} for {vals['span']}. Do not let them forget me.")
    return opts[(seed >> 8) % len(opts)], verses[seed % len(verses)].format(**vals)


# ------------------------------------------------------------ model mode

def compose(g: Ghost, backend: Backend, lang: str = "en", cache: Optional[VerseCache] = None,
            refresh: bool = False, log: Callable[[str], None] = lambda m: None) -> Ghost:
    """Fill in g.last_words / g.calavera / g.voice. Never raises."""
    key = VerseCache.key(str(prompts.PROMPT_VERSION), backend.ident, lang, g.commit, g.path)
    if backend.name != "none":
        if cache and not refresh:
            hit = cache.get(key)
            if hit:
                g.last_words, g.calavera, g.voice = hit["last"], hit["cal"], hit["voice"]
                return g
        for attempt in range(ATTEMPTS):
            try:
                parsed = prompts.parse_epitaph(backend.generate(prompts.epitaph_prompt(g, lang)))
            except LLMError as e:
                log(f"  model error: {e}")
                break
            if parsed:
                g.last_words, g.calavera = parsed
                g.voice = f"model:{backend.model}"
                if cache:
                    cache.put(key, {"last": g.last_words, "cal": g.calavera, "voice": g.voice})
                return g
            log("  model ignored the verse format" + (", retrying" if attempt + 1 < ATTEMPTS else ""))
    g.last_words, g.calavera = template_verse(g, lang)
    g.voice = "template"
    return g


# ------------------------------------------------------------ séance fallback

def seance_fallback(g: Ghost, message: str, lang: str = "en") -> str:
    """Rule-based answer built from git facts, used when no model is available."""
    m = message.lower()
    fns = facts.functions(g.source)
    es = lang == "es"
    if re.search(r"\b(why|die|died|kill|killed|death|delete|deleted|remove|removed|cause|por qu[eé]|muri[oó]|mataron)\b", m):
        return (f'{g.killer} me despidió el {g.died} con estas palabras: "{g.cause}". Sin rencores. Casi.' if es else
                f'{g.killer} ended me on {g.died} with these words: "{g.cause}". I hold no grudge. Mostly.')
    if re.search(r"\b(who|author|authors|wrote|written|made|love|loved|qui[eé]n|escribi[oó])\b", m):
        who = ", ".join(g.authors)
        return f"Me escribieron {who}. Fueron amables conmigo." if es else f"I was written by {who}. They were kind to me."
    if re.search(r"\b(old|long|live|lived|born|age|when|cu[aá]ndo|naci[oó]|vivi[oó])\b", m):
        return (f"Nací el {g.born} y viví {span(g.days, lang)} en {g.commits} commits." if es else
                f"I was born {g.born} and lived {span(g.days, lang)} across {g.commits} commits.")
    if fns and re.search(r"\b(code|function|functions|contain|purpose|job|hac[ií]as|c[oó]digo)\b|what (did|do) you", m):
        listing = ", ".join(f"{f}()" for f in fns)
        return (f"En vida guardé {listing}. Cosas pequeñas, hechas con honra." if es else
                f"In life I held {listing}. Small things, honestly done.")
    return ("Los muertos no lo recuerdan todo. Pregúntame cómo morí, o quién me quiso." if es else
            "The dead do not remember everything. Ask me how I died, or who loved me.")


def summary(ghosts: List[Ghost], lang: str = "en") -> str:
    n = len(ghosts)
    by_model = [g for g in ghosts if g.voice.startswith("model:")]
    es = lang == "es"
    if not by_model:
        return ("Versos de plantillas incluidas (no se usó ningún modelo)." if es
                else "Verses from built-in templates (no model was used).")
    name = by_model[0].voice.split(":", 1)[1]
    if len(by_model) == n:
        return (f"Versos escritos por {name}, un modelo que corre en esta máquina." if es
                else f"Verses written by {name}, a model running on this machine.")
    return (f"{len(by_model)} de {n} versos escritos por {name} en esta máquina; el resto, de plantillas incluidas." if es
            else f"{len(by_model)} of {n} verses written by {name} on this machine; the rest from built-in templates.")
