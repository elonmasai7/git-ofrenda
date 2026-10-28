"""Command-line interface."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import webbrowser
from typing import List, Optional

from . import __version__, poet, render
from .cache import SeanceStore, VerseCache, cache_dir, repo_id
from .gitscan import GitError, Ghost, read_blob, repo_name, run_git, scan, toplevel
from .llm import DEFAULT_MODEL, Backend, NoBackend, make_backend

COMMANDS = ("scan", "build", "seance", "exhume", "doctor")


def eprint(*a) -> None:
    print(*a, file=sys.stderr)


def die(msg: str, code: int = 1):
    eprint(f"error: {msg}")
    raise SystemExit(code)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="git-ofrenda",
        description="An ofrenda for the files your repo has lost. Verses are written by a model "
                    "running on your own machine; nothing is sent anywhere.",
        epilog="Environment: OFRENDA_BACKEND, OFRENDA_MODEL, OFRENDA_HOST, OFRENDA_API_KEY, OFRENDA_CACHE.")
    p.add_argument("--version", action="version", version=f"git-ofrenda {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    def selection(sp, default_limit):
        sp.add_argument("repo", nargs="?", default=".", help="path to a git repository (default: .)")
        sp.add_argument("-n", "--limit", type=int, default=default_limit,
                        help="how many ghosts (0 = all; default %(default)s)")
        sp.add_argument("--include", action="append", default=[], metavar="GLOB", help="only paths matching GLOB (repeatable)")
        sp.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="skip paths matching GLOB (repeatable)")
        sp.add_argument("--since", metavar="WHEN", help="only files deleted since WHEN (e.g. 2023-01-01, '1 year ago')")

    def model(sp):
        sp.add_argument("--backend", choices=["ollama", "openai", "none"], help="model server type (default: ollama)")
        sp.add_argument("--model", help=f"model name (default: {DEFAULT_MODEL})")
        sp.add_argument("--host", help="model server URL")
        sp.add_argument("--lang", choices=["en", "es"], default="en", help="language of verses and séance")

    s = sub.add_parser("scan", help="list dead files (no model needed)")
    selection(s, 0)
    s.add_argument("--json", action="store_true", help="machine-readable output")

    b = sub.add_parser("build", help="write the ofrenda as HTML, Markdown or JSON")
    selection(b, 6); model(b)
    b.add_argument("-o", "--out", default="ofrenda.html", help="output file, or - for stdout (default: ofrenda.html)")
    b.add_argument("--format", choices=["html", "md", "json"], help="default: from the file extension")
    b.add_argument("--with-source", action="store_true", help="include final file contents in JSON output")
    b.add_argument("--no-cache", action="store_true", help="do not read or write the verse cache")
    b.add_argument("--refresh", action="store_true", help="rewrite verses even if cached")

    c = sub.add_parser("seance", help="serve a local page where you can talk to each ghost")
    selection(c, 6); model(c)
    c.add_argument("--port", type=int, default=8666)
    c.add_argument("--no-open", action="store_true", help="do not open a browser")
    c.add_argument("--no-cache", action="store_true", help="do not read or write the verse cache")
    c.add_argument("--refresh", action="store_true", help="rewrite verses even if cached")

    x = sub.add_parser("exhume", help="restore dead files' final contents into a folder")
    x.add_argument("repo", help="path to a git repository")
    x.add_argument("dest", help="folder to write the files into")
    x.add_argument("-n", "--limit", type=int, default=0, help="how many (0 = all)")
    x.add_argument("--include", action="append", default=[], metavar="GLOB")
    x.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    x.add_argument("--since", metavar="WHEN")

    d = sub.add_parser("doctor", help="check git and your model server")
    d.add_argument("--backend", choices=["ollama", "openai", "none"])
    d.add_argument("--model")
    d.add_argument("--host")
    return p


def load_ghosts(a) -> List[Ghost]:
    try:
        ghosts = scan(a.repo, a.include, a.exclude, a.since, a.limit or None)
    except GitError as e:
        die(str(e))
    if not ghosts:
        die("no deleted text files found: this repo has no ghosts (yet).", 2)
    return ghosts


def resolve_backend(a) -> Backend:
    try:
        b = make_backend(a.backend, a.host, a.model)
    except ValueError as e:
        die(str(e))
    if b.name == "none":
        return b
    ok, msg = b.check()
    if not ok:
        eprint(f"warning: {msg}\n  using built-in template verses instead. Run `git-ofrenda doctor` for help.")
        return NoBackend()
    eprint(f"using {b.name} model {b.model!r}")
    return b


def write_verses(ghosts: List[Ghost], backend: Backend, a) -> None:
    cache = None if (a.no_cache or backend.name == "none") else VerseCache(os.path.join(cache_dir(), "verses.json"))
    for i, g in enumerate(ghosts, 1):
        eprint(f"[{i}/{len(ghosts)}] summoning {g.path}")
        poet.compose(g, backend, a.lang, cache, a.refresh, log=eprint)


def cmd_scan(a) -> int:
    ghosts = load_ghosts(a)
    if a.json:
        print(json.dumps([g.to_dict() for g in ghosts], indent=2, ensure_ascii=False))
        return 0
    w = max(len(g.path) for g in ghosts)
    print(f"{'PATH'.ljust(w)}  {'BORN':10}  {'DIED':10}  {'DAYS':>5}  {'COMMITS':>7}  KILLER / CAUSE")
    for g in ghosts:
        print(f"{g.path.ljust(w)}  {g.born:10}  {g.died:10}  {g.days:>5}  {g.commits:>7}  {g.killer}: {g.cause}")
    return 0


def cmd_build(a) -> int:
    ghosts = load_ghosts(a)
    backend = resolve_backend(a)
    write_verses(ghosts, backend, a)
    name = repo_name(a.repo)
    fmt = a.format or ("md" if a.out.endswith(".md") else "json" if a.out.endswith(".json") else "html")
    text = (render.markdown(name, ghosts) if fmt == "md" else
            render.json_dump(name, ghosts, a.with_source) if fmt == "json" else
            render.html_page(name, ghosts, a.lang))
    if a.out == "-":
        sys.stdout.write(text)
    else:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        eprint(f"ofrenda lit: {a.out} ({len(ghosts)} ghosts)")
    return 0


def cmd_seance(a) -> int:
    from .server import make_server
    ghosts = load_ghosts(a)
    backend = resolve_backend(a)
    write_verses(ghosts, backend, a)
    top = toplevel(a.repo)
    store = SeanceStore(os.path.join(cache_dir(), "seances", repo_id(top) + ".json"))
    try:
        srv = make_server(ghosts, repo_name(a.repo), backend, store, a.lang, a.port)
    except OSError as e:
        die(f"cannot listen on 127.0.0.1:{a.port} ({e}); try --port")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    eprint(f"séance open at {url}  (Ctrl+C to end it)")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        eprint("\nthe candles go out.")
    finally:
        srv.server_close()
    return 0


def cmd_exhume(a) -> int:
    ghosts = load_ghosts(a)
    top = toplevel(a.repo)
    root = os.path.abspath(a.dest)
    for g in ghosts:
        target = os.path.abspath(os.path.join(root, g.path))
        if not target.startswith(root + os.sep):
            eprint(f"skipping suspicious path {g.path!r}")
            continue
        data = read_blob(top, g.commit, g.path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        print(f"exhumed {g.path}  ({g.born} .. {g.died})")
    print(f"{len(ghosts)} file(s) restored into {root}")
    return 0


def cmd_doctor(a) -> int:
    ok = True
    print(f"git-ofrenda {__version__}  |  python {platform.python_version()}  |  {platform.system()}")
    try:
        rc, out, _ = run_git(".", "--version")
        print(f"[ok]   {out.strip()}")
    except GitError:
        print("[FAIL] git was not found on PATH")
        ok = False
    try:
        b = make_backend(a.backend, a.host, a.model)
    except ValueError as e:
        print(f"[FAIL] {e}")
        return 1
    good, msg = b.check()
    print(f"[{'ok' if good else 'FAIL'}]   {msg}")
    ok = ok and good
    print(f"[info] cache folder: {cache_dir()}")
    if not good:
        print("\nWithout a model, git-ofrenda still works using built-in template verses (--backend none).")
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "--version")):
        argv.insert(0, "build")  # `git-ofrenda [repo]` means `git-ofrenda build [repo]`
    a = build_parser().parse_args(argv)
    handler = {"scan": cmd_scan, "build": cmd_build, "seance": cmd_seance,
               "exhume": cmd_exhume, "doctor": cmd_doctor}[a.cmd]
    try:
        code = handler(a)
    except GitError as e:
        die(str(e))
    sys.exit(code)
