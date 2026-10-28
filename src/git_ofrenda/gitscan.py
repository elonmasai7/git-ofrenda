"""Read a repository's history and find the files that died."""
from __future__ import annotations

import datetime as dt
import fnmatch
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

SEP = "\x1f"
MAX_SOURCE_BYTES = 2_000_000
PRERANK_THRESHOLD = 60  # above this many deleted files, pre-rank cheaply


class GitError(RuntimeError):
    """Raised for problems talking to git."""


def run_git(repo: str, *args: str) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["git", "-c", "core.quotepath=false", "-C", repo, *args],
            capture_output=True, text=True, errors="replace",
        )
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH") from None
    return r.returncode, r.stdout, r.stderr


def git_out(repo: str, *args: str) -> str:
    rc, out, err = run_git(repo, *args)
    if rc != 0:
        raise GitError(err.strip() or f"git {' '.join(args)} failed")
    return out


def toplevel(repo: str) -> str:
    rc, out, _ = run_git(repo, "rev-parse", "--show-toplevel")
    if rc != 0 or not out.strip():
        raise GitError(f"{repo!r} is not a git repository")
    return out.strip()


@dataclass
class Ghost:
    path: str
    born: str
    died: str
    days: int
    commits: int
    authors: List[str]
    killer: str
    cause: str
    commit: str
    source: str = ""
    last_words: str = ""
    calavera: str = ""
    voice: str = "template"  # "template" or "model:<name>"

    @property
    def score(self) -> float:
        return self.commits * 10 + self.days / 30

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def to_dict(self, with_source: bool = False) -> dict:
        d = {
            "path": self.path, "born": self.born, "died": self.died,
            "days_lived": self.days, "commits": self.commits,
            "authors": self.authors, "killed_by": self.killer,
            "cause_of_death": self.cause, "deleted_in": self.commit,
            "last_words": self.last_words, "calavera": self.calavera,
            "voice": self.voice,
        }
        if with_source:
            d["final_contents"] = self.source
        return d


def deleted_files(repo: str, since: Optional[str] = None) -> Dict[str, dict]:
    """Map path -> info about the (most recent) commit that deleted it."""
    args = ["log", "--diff-filter=D", "-M", "--name-only", "--date=short",
            f"--format=@@%H{SEP}%an{SEP}%ad{SEP}%s"]
    if since:
        args.append(f"--since={since}")
    found: Dict[str, dict] = {}
    cur = None
    for line in git_out(repo, *args).splitlines():
        if line.startswith("@@"):
            h, a, d, s = line[2:].split(SEP, 3)
            cur = dict(commit=h, killer=a, died=d, cause=s)
        elif line.strip() and cur:
            found.setdefault(line.strip(), cur)  # newest deletion wins
    return found


def touch_counts(repo: str) -> Dict[str, int]:
    """One cheap pass over history: how many commits touched each path."""
    counts: Dict[str, int] = {}
    for line in git_out(repo, "log", "--name-only", "--pretty=format:@@", "-M").splitlines():
        if line and line != "@@":
            counts[line] = counts.get(line, 0) + 1
    return counts


def profile(repo: str, path: str, info: dict) -> Optional[Ghost]:
    """Full biography of one dead file, or None if it has nothing to read."""
    rc, src, _ = run_git(repo, "show", f"{info['commit']}^:{path}")
    if rc != 0 or "\x00" in src or not src.strip() or len(src) > MAX_SOURCE_BYTES:
        return None
    dates = git_out(repo, "log", "--follow", "--format=%ad", "--date=short", "--", path).split()
    authors = sorted({l for l in git_out(repo, "log", "--follow", "--format=%an", "--", path).splitlines() if l})
    born = min(dates) if dates else info["died"]
    try:
        days = max(0, (dt.date.fromisoformat(info["died"]) - dt.date.fromisoformat(born)).days)
    except ValueError:
        days = 0
    return Ghost(path=path, born=born, died=info["died"], days=days,
                 commits=len(dates), authors=authors or [info["killer"]],
                 killer=info["killer"], cause=info["cause"], commit=info["commit"], source=src)


def read_blob(repo: str, commit: str, path: str) -> bytes:
    """Exact bytes of a file as it was just before `commit` deleted it."""
    r = subprocess.run(["git", "-C", repo, "show", f"{commit}^:{path}"], capture_output=True)
    if r.returncode != 0:
        raise GitError(f"cannot read {path} at {commit[:8]}^")
    return r.stdout


def scan(repo: str, include: Sequence[str] = (), exclude: Sequence[str] = (),
         since: Optional[str] = None, limit: Optional[int] = None) -> List[Ghost]:
    """Find dead files, ranked by how loved they were (most loved first)."""
    top = toplevel(repo)
    alive = set(git_out(top, "ls-files").splitlines())
    candidates = {}
    for path, info in deleted_files(top, since).items():
        if path in alive:
            continue
        if include and not any(fnmatch.fnmatch(path, g) for g in include):
            continue
        if any(fnmatch.fnmatch(path, g) for g in exclude):
            continue
        candidates[path] = info
    if limit and len(candidates) > PRERANK_THRESHOLD:
        counts = touch_counts(top)
        keep = sorted(candidates, key=lambda p: counts.get(p, 0), reverse=True)[: limit * 5]
        candidates = {p: candidates[p] for p in keep}
    ghosts = [g for g in (profile(top, p, i) for p, i in candidates.items()) if g]
    ghosts.sort(key=lambda g: g.score, reverse=True)
    return ghosts[:limit] if limit else ghosts


def repo_name(repo: str) -> str:
    return os.path.basename(toplevel(repo)) or "this repo"
