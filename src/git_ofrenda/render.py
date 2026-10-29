"""Turn ghosts into an HTML page, a Markdown file, or JSON."""
from __future__ import annotations

import html
import json
from importlib import resources
from typing import Dict, List, Optional

from . import __version__, poet
from .gitscan import Ghost

STRINGS = {
    "en": dict(intro="The files this repository lost, remembered by the commits that outlived them.",
               cause="Cause of death", killer="Taken by", loved="Loved by", lived="lived", days="days",
               commits="commits", seance="Hold a séance", ask="Ask", ph="Ask the ghost...", forget="forget this conversation",
               title="Ofrenda for", kicker="Día de los Muertos"),
    "es": dict(intro="Los archivos que este repositorio perdió, recordados por los commits que los sobrevivieron.",
               cause="Causa de muerte", killer="Se lo llevó", loved="Lo quisieron", lived="vivió", days="días",
               commits="commits", seance="Hacer una sesión espiritista", ask="Preguntar", ph="Pregúntale al fantasma...",
               forget="olvidar esta conversación", title="Ofrenda para", kicker="Día de los Muertos"),
}


def _asset(name: str) -> str:
    return resources.files("git_ofrenda").joinpath("static").joinpath(name).read_text(encoding="utf-8")


def snippet(src: str, n: int = 6) -> str:
    lines = [l.rstrip()[:90] for l in src.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def html_page(repo_name: str, ghosts: List[Ghost], lang: str = "en", interactive: bool = False,
              history: Optional[Dict[str, List[dict]]] = None) -> str:
    e, s = html.escape, STRINGS.get(lang, STRINGS["en"])
    cards = []
    for g in ghosts:
        chat = (f'<button class="summon" type="button">{e(s["seance"])}</button>'
                f'<div class="chat" hidden><div class="log"></div><div class="row">'
                f'<input placeholder="{e(s["ph"])}" maxlength="500" aria-label="{e(s["ph"])}">'
                f'<button class="send" type="button">{e(s["ask"])}</button></div>'
                f'<button class="forget" type="button">{e(s["forget"])}</button></div>') if interactive else ""
        voice = "template" if g.voice == "template" else g.voice.split(":", 1)[1]
        cards.append(f"""<article class="card" data-path="{e(g.path)}"><div class="candle"><div class="flame"></div></div>
<h2 class="name">{e(g.path)}</h2>
<div class="dates">{e(g.born)} &rarr; {e(g.died)} &middot; {s["lived"]} {g.days} {s["days"]} &middot; {g.commits} {s["commits"]}</div>
<div class="last">&ldquo;{e(g.last_words)}&rdquo;</div>
<div class="cal">{e(g.calavera)}</div>
<span class="voice" title="who wrote the verse">verse: {e(voice)}</span>
<div class="meta"><b>{s["cause"]}:</b> {e(g.cause)}<br><b>{s["killer"]}:</b> {e(g.killer)}<br>
<b>{s["loved"]}:</b> {e(", ".join(g.authors))}</div>
<pre>{e(snippet(g.source))}</pre>{chat}</article>""")
    script = ""
    if interactive:
        data = json.dumps(history or {}).replace("</", "<\\/")
        script = f'<script type="application/json" id="seance-data">{data}</script><script>{_asset("seance.js")}</script>'
    return f"""<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(s["title"])} {e(repo_name)}</title>
<style>{_asset("ofrenda.css")}</style></head><body><header>
<p class="kicker">{e(s["kicker"])}</p><h1>{e(s["title"])} {e(repo_name)}</h1>
<p>{e(s["intro"])} {e(poet.summary(ghosts, lang))}</p></header>
<main class="grid">{"".join(cards)}</main>
<footer>git-ofrenda {__version__}</footer>{script}</body></html>"""


def markdown(repo_name: str, ghosts: List[Ghost]) -> str:
    out = [f"# Ofrenda for {repo_name}", "", f"*{poet.summary(ghosts)}*", ""]
    for g in ghosts:
        out += [f"## `{g.path}`",
                f"*{g.born} → {g.died} · lived {g.days} days · {g.commits} commits*", "",
                f"> “{g.last_words}”", ""]
        out += [f"> {line}  " for line in g.calavera.splitlines()]
        out += ["", f"- **Cause of death:** {g.cause}", f"- **Taken by:** {g.killer}",
                f"- **Loved by:** {', '.join(g.authors)}", f"- **Verse by:** {g.voice}", ""]
    return "\n".join(out)


def json_dump(repo_name: str, ghosts: List[Ghost], with_source: bool = False) -> str:
    return json.dumps({"repository": repo_name, "generator": f"git-ofrenda {__version__}",
                       "ghosts": [g.to_dict(with_source) for g in ghosts]}, indent=2, ensure_ascii=False)
